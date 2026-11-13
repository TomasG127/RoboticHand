"""
Hand-level abstraction: a table of servos on one bus, with soft limits enforced in software.

Open-loop. There is no position feedback loop and no collision checking; `present` positions are
read back for display and safety checks only.

Lenient by design (see config.py): servos may come from config.SERVOS, calibration.json, an explicit
id list, or a bus scan. A servo with no calibrated limits gets a PROVISIONAL window around its
startup position. Hard safety rules still apply:
  * torque is OFF until you ask for it;
  * enabling torque first sets the goal to the servo's CURRENT position, so it cannot jump;
  * enabling torque is refused if the servo is outside its soft limits;
  * motion is refused when torque is off, the servo is offline, or the id is invalid.
"""

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from calibration import load_calibration
from config import (
    CALIBRATION_FILE,
    JOINTS,
    PROVISIONAL_WINDOW_FRACTION,
    SERVOS,
    ConfigError,
    ServoConfig,
    ServoModel,
    resolve_acceleration,
    resolve_speed,
    validate_all,
)
from servo_bus import BaseBus


class HandError(Exception):
    """A command was refused or failed. The message says why; nothing was left half-done."""


@dataclass
class ServoState:
    online: bool = False
    present: Optional[int] = None   # last position read from the servo (counts)
    target: Optional[int] = None    # last position we commanded (counts)
    torque: bool = False
    note: str = ""                  # why a servo is offline/refused, for the operator


def servo_from_id(servo_id: int, model: ServoModel = ServoModel.STS3215) -> ServoConfig:
    return ServoConfig(name=f"servo_{servo_id}", servo_id=servo_id, model=model)


def build_servo_table(
    calibration_path=CALIBRATION_FILE,
    extra_ids: Iterable[int] = (),
    default_model: ServoModel = ServoModel.STS3215,
    only: Optional[Iterable[str]] = None,
) -> Tuple[Dict[str, ServoConfig], List[str]]:
    """Merge config.SERVOS + calibration.json + explicit ids. Returns (table, warnings).

    Precedence for limits: calibration.json (newest measurement) > config.py > none.
    A calibration entry whose id/model disagrees with config is skipped: applying limits measured
    on a different servo is worse than having no limits.
    """
    warnings: List[str] = []
    table: Dict[str, ServoConfig] = dict(SERVOS)
    entries, cal_warnings = load_calibration(calibration_path)
    warnings.extend(cal_warnings)

    for name, entry in entries.items():
        model = ServoModel(entry["model"])
        if name in table:
            cfg = table[name]
            if cfg.servo_id != entry["servo_id"] or cfg.model != model:
                warnings.append(f"calibration for '{name}' is for id {entry['servo_id']}/{model.value} but config "
                                f"says id {cfg.servo_id}/{cfg.model.value}; calibration ignored")
                continue
        else:
            cfg = ServoConfig(name, entry["servo_id"], model)
        table[name] = cfg.with_limits(entry["min_count"], entry["max_count"], "calibration")

    used_ids = {c.servo_id for c in table.values()}
    for servo_id in extra_ids:
        if servo_id not in used_ids:
            cfg = servo_from_id(servo_id, default_model)
            table[cfg.name] = cfg
            used_ids.add(servo_id)

    if only is not None:
        wanted = list(only)
        unknown = [n for n in wanted if n not in table]
        if unknown:
            raise ConfigError(f"unknown servo name(s) {unknown}; available: {sorted(table)}")
        table = {n: table[n] for n in wanted}

    warnings.extend(validate_all(table))  # raises on hard errors (bad ids, bad limits, duplicates)
    return table, warnings


class Hand:
    def __init__(self, bus: BaseBus, servos: Dict[str, ServoConfig], joints: Optional[Dict[str, dict]] = None,
                 speed: Optional[int] = None, acceleration: Optional[int] = None):
        self.bus = bus
        self.servos: Dict[str, ServoConfig] = dict(servos)
        self.joints = JOINTS if joints is None else joints
        self.state: Dict[str, ServoState] = {n: ServoState() for n in self.servos}
        self._speed = speed
        self._acc = acceleration

    # --- helpers -----------------------------------------------------------------
    def names(self) -> List[str]:
        return list(self.servos)

    def active_names(self) -> List[str]:
        """Servos that answered at connect() time; these are the ones worth selecting."""
        return [n for n, s in self.state.items() if s.online]

    def _cfg(self, name: str) -> ServoConfig:
        try:
            return self.servos[name]
        except KeyError:
            raise HandError(f"unknown servo '{name}'; known: {self.names()}") from None

    def speed_for(self, cfg: ServoConfig) -> int:
        return self._speed if self._speed is not None else resolve_speed(cfg.model)

    def acceleration_for(self, cfg: ServoConfig) -> int:
        return self._acc if self._acc is not None else resolve_acceleration(cfg.model)

    # --- start-up ------------------------------------------------------------------
    def connect(self, strict: bool = False) -> List[str]:
        """Ping every servo, read positions, assign provisional limits. Returns operator messages.

        strict=True restores the original "refuse without limits" behavior: servos with no
        configured/calibrated limits are left offline.
        """
        messages: List[str] = []
        for name, cfg in list(self.servos.items()):
            st = self.state[name]
            if cfg.errors():
                st.note = "; ".join(cfg.errors())
                messages.append(f"{name}: REFUSED ({st.note})")
                continue
            if self.bus.ping(cfg.servo_id, cfg.model) is None:
                st.note = "no response on the bus"
                messages.append(f"{name} (id {cfg.servo_id}): no response; check id, power, baud, wiring")
                continue
            present = self.bus.read_position(cfg.servo_id, cfg.model)
            if present is None:
                st.note = "answers ping but position unreadable"
                messages.append(f"{name} (id {cfg.servo_id}): {st.note}")
                continue
            st.online, st.present = True, present

            if not cfg.has_limits:
                if strict:
                    st.online, st.note = False, "no limits (strict mode)"
                    messages.append(f"{name}: left offline, no limits and --strict is set; run calibration.py")
                    continue
                lo_r, hi_r = cfg.count_range
                window = max(1, int((hi_r - lo_r) * PROVISIONAL_WINDOW_FRACTION))
                cfg = cfg.with_limits(max(lo_r, present - window), min(hi_r, present + window), "provisional")
                self.servos[name] = cfg
                messages.append(f"{name}: PROVISIONAL limits {cfg.min_count}..{cfg.max_count} "
                                f"(start {present} +/- {window}); run calibration.py for real limits")
            if not (cfg.min_count <= present <= cfg.max_count):
                messages.append(f"{name}: at {present}, OUTSIDE limits {cfg.min_count}..{cfg.max_count}; "
                                "torque will be refused until it is inside (move by hand or recalibrate)")
            for warning in cfg.warnings():
                if "PROVISIONAL" not in warning and "provisional window" not in warning:
                    messages.append(f"{name}: note: {warning}")
        return messages

    # --- reading ---------------------------------------------------------------------
    def refresh(self, name: str) -> Optional[int]:
        cfg, st = self._cfg(name), self.state[name]
        if not st.online:
            return None
        value = self.bus.read_position(cfg.servo_id, cfg.model)
        if value is not None:
            st.present = value
        return value

    def refresh_all(self) -> None:
        for name in self.servos:
            self.refresh(name)

    # --- torque --------------------------------------------------------------------------
    def enable_torque(self, name: str) -> None:
        cfg, st = self._cfg(name), self.state[name]
        if not st.online:
            raise HandError(f"{name} is offline ({st.note or 'not connected'})")
        present = self.refresh(name)
        if present is None:
            raise HandError(f"{name}: cannot read position, refusing to enable torque blind")
        if not cfg.has_limits:
            raise HandError(f"{name}: no limits, refusing to enable torque")
        if not (cfg.min_count <= present <= cfg.max_count):
            raise HandError(f"{name}: position {present} is outside limits {cfg.min_count}..{cfg.max_count}; "
                            "enabling torque would make it jump. Move it inside by hand, or recalibrate.")
        # Hold-in-place first: goal = where it is NOW, so torque-on cannot cause a lunge.
        if not self.bus.move(cfg.servo_id, cfg.model, present, self.speed_for(cfg), self.acceleration_for(cfg)):
            raise HandError(f"{name}: could not set the hold position; torque NOT enabled")
        if not self.bus.set_torque(cfg.servo_id, cfg.model, True):
            raise HandError(f"{name}: torque-enable command failed")
        st.torque, st.target = True, present

    def disable_torque(self, name: str) -> bool:
        cfg, st = self._cfg(name), self.state[name]
        ok = self.bus.set_torque(cfg.servo_id, cfg.model, False) or self.bus.set_torque(cfg.servo_id, cfg.model, False)
        if ok:
            st.torque = False
        return ok

    # --- motion ------------------------------------------------------------------------------
    def move_to(self, name: str, count: int) -> Tuple[int, bool]:
        """Command an absolute position. Returns (commanded_count, was_clamped)."""
        cfg, st = self._cfg(name), self.state[name]
        if not st.online:
            raise HandError(f"{name} is offline ({st.note or 'not connected'})")
        if not st.torque:
            raise HandError(f"{name}: torque is off; enable it first")
        target = cfg.clamp(count)
        if not self.bus.move(cfg.servo_id, cfg.model, target, self.speed_for(cfg), self.acceleration_for(cfg)):
            raise HandError(f"{name}: move command failed (bus error)")
        st.target = target
        return target, target != int(count)

    def step(self, name: str, delta: int) -> Tuple[int, bool]:
        """Move relative to the last commanded target (or the present position if none yet)."""
        self._cfg(name)  # raises a clear HandError for unknown names
        st = self.state[name]
        base = st.target if st.target is not None else st.present
        if base is None:
            raise HandError(f"{name}: no known position to step from")
        return self.move_to(name, base + delta)

    def move_joint(self, joint: str, fraction: float) -> Tuple[int, bool]:
        """Move a joint to 0.0..1.0 of its servo's soft-limit band (1.0 = max_count unless inverted).

        Only direct servo<->joint mapping is supported; antagonistic pairs and the wrist
        differential are not modeled until the actuator/joint map is documented.
        """
        entry = self.joints.get(joint)
        servo_name, invert = (entry["servo"], bool(entry.get("invert", False))) if entry else (joint, False)
        cfg = self._cfg(servo_name)
        if not cfg.has_limits:
            raise HandError(f"{servo_name}: no limits; cannot interpret a 0..1 fraction")
        fraction = min(1.0, max(0.0, float(fraction)))
        if invert:
            fraction = 1.0 - fraction
        return self.move_to(servo_name, round(cfg.min_count + fraction * (cfg.max_count - cfg.min_count)))

    # --- shutdown ------------------------------------------------------------------------------
    def panic_stop(self) -> List[str]:
        """Release torque on EVERY known servo, even ones marked offline. Never raises.

        Returns names that could not be confirmed released so the operator can cut power.
        """
        failed = []
        for name, cfg in self.servos.items():
            released = False
            for _ in range(2):
                try:
                    if self.bus.set_torque(cfg.servo_id, cfg.model, False):
                        released = True
                        break
                except Exception:  # panic must keep going no matter what
                    pass
            if released:
                self.state[name].torque = False
            elif self.state[name].online or self.state[name].torque:
                failed.append(name)
        return failed

    def status_line(self, name: str) -> str:
        cfg, st = self._cfg(name), self.state[name]
        if not st.online:
            return f"{name} (id {cfg.servo_id}) OFFLINE: {st.note}"
        limits = f"{cfg.min_count}-{cfg.max_count} [{cfg.limits_source}]" if cfg.has_limits else "none"
        return (f"{name} (id {cfg.servo_id}, {cfg.model.value}) pos {st.present} target {st.target} "
                f"limits {limits} torque {'ON' if st.torque else 'off'}")