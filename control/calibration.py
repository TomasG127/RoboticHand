"""
Soft-limit calibration for the dexterous hand.

Procedure (matches the README: set limits against a SLACK tendon):
  1. Tendons slack or disconnected. This tool switches torque OFF for the servo being calibrated.
  2. You turn the horn/joint BY HAND to one mechanical stop; press Enter -> the count is recorded.
  3. Repeat at the other stop.
  4. The tool backs off a margin from both stops and saves the result to calibration.json.

hand.py overlays calibration.json on config.SERVOS, so you never have to hand-edit limits.

Examples:
  python calibration.py --port COM3 --scan             # find servos, calibrate the ones you pick
  python calibration.py --port /dev/ttyUSB0 --ids 1,2  # calibrate specific ids (assumed STS3215)
  python calibration.py --sim --ids 1                  # dry run with no hardware
  python calibration.py --show                         # print saved calibration
"""

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from config import (
    BAUD_RATE,
    CALIBRATION_FILE,
    CALIBRATION_MARGIN_FRACTION,
    CALIBRATION_MIN_MARGIN,
    CALIBRATION_MIN_SPAN,
    MODEL_COUNT_RANGE,
    MODEL_RANGE_VERIFIED,
    SERVOS,
    ConfigError,
    ServoConfig,
    ServoModel,
    parse_ids,
)
from servo_bus import BaseBus, BusError, FeetechBus, SimulatedBus

SCHEMA_VERSION = 1
REQUIRED_KEYS = ("servo_id", "model", "min_count", "max_count")


# --- file format -------------------------------------------------------------
def load_calibration(path: Path = CALIBRATION_FILE) -> Tuple[Dict[str, dict], List[str]]:
    """Return ({name: entry}, warnings). Missing or empty file = no calibration, not an error.

    A file that is not valid JSON IS an error: silently ignoring it could later overwrite
    someone's measurements.
    """
    path = Path(path)
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return {}, []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON ({exc}); fix or delete it") from None

    warnings: List[str] = []
    entries: Dict[str, dict] = {}
    for name, entry in (data.get("servos") or {}).items():
        try:
            if any(key not in entry for key in REQUIRED_KEYS):
                raise ValueError(f"missing keys (need {REQUIRED_KEYS})")
            ServoModel(entry["model"])
            entry = dict(entry, servo_id=int(entry["servo_id"]),
                         min_count=int(entry["min_count"]), max_count=int(entry["max_count"]))
            entries[name] = entry
        except (ValueError, TypeError) as exc:
            warnings.append(f"calibration entry '{name}' ignored: {exc}")
    return entries, warnings


def save_calibration(entries: Dict[str, dict], path: Path = CALIBRATION_FILE) -> None:
    """Atomic write: a crash mid-save must not leave a half-written calibration file."""
    path = Path(path)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "_note": "Written by calibration.py. Counts are raw servo counts measured by hand against slack tendons.",
        "servos": entries,
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


# --- the math (pure, easy to test) --------------------------------------------
def compute_limits(stop_a: int, stop_b: int, model: ServoModel) -> Tuple[int, int, int, List[str]]:
    """Turn two hand-found stops into soft limits. Returns (min, max, margin, warnings)."""
    lo, hi = sorted((stop_a, stop_b))
    span = hi - lo
    notes: List[str] = []
    range_lo, range_hi = MODEL_COUNT_RANGE[model]
    if span < CALIBRATION_MIN_SPAN:
        raise ConfigError(f"stops are only {span} counts apart; did the joint actually move?")
    if span > 0.9 * (range_hi - range_lo):
        notes.append("span covers >90% of the servo range: the joint may not have a hard stop, or the "
                     "reading wrapped past 0/max. Double-check before trusting these limits.")
    margin = max(CALIBRATION_MIN_MARGIN, round(span * CALIBRATION_MARGIN_FRACTION))
    if 2 * margin >= span:  # tiny joint: shrink the margin so a usable band remains
        margin = span // 4
    return max(range_lo, lo + margin), min(range_hi, hi - margin), margin, notes


def read_stable(bus: BaseBus, servo_id: int, model: ServoModel, samples: int = 5, spread_max: int = 8) -> Optional[int]:
    """Median of a few quick reads; None if reads fail or the horn is still moving."""
    values = []
    for _ in range(samples):
        value = bus.read_position(servo_id, model)
        if value is None:
            return None
        values.append(value)
        time.sleep(0.02)
    if max(values) - min(values) > spread_max:
        return None
    return int(statistics.median(values))


# --- interactive flow ------------------------------------------------------------
def capture_stop(bus: BaseBus, cfg: ServoConfig, label: str, input_fn: Callable[[str], str]) -> int:
    while True:
        input_fn(f"  Move '{cfg.name}' BY HAND to the {label} stop, hold it there, press Enter... ")
        if isinstance(bus, SimulatedBus):
            bus.set_position(cfg.servo_id, int(input_fn("  [sim] enter the count you are 'holding': ")))
        value = read_stable(bus, cfg.servo_id, cfg.model)
        if value is not None:
            print(f"  recorded {label} stop: {value}")
            return value
        print("  could not get a steady reading (bus error or still moving). Try again.")


def calibrate_servo(bus: BaseBus, cfg: ServoConfig, input_fn: Callable[[str], str] = input) -> Optional[dict]:
    """Calibrate one servo. Returns a calibration entry, or None if skipped."""
    print(f"\n== {cfg.name} (id {cfg.servo_id}, {cfg.model.value}) ==")
    if bus.ping(cfg.servo_id, cfg.model) is None:
        print("  no response from this id; skipping.")
        return None
    if not bus.set_torque(cfg.servo_id, cfg.model, False):
        print("  could not switch torque off; skipping (do not hand-turn a servo that may be holding).")
        return None
    stop_a = capture_stop(bus, cfg, "FIRST", input_fn)
    stop_b = capture_stop(bus, cfg, "SECOND (opposite)", input_fn)
    lo, hi, margin, notes = compute_limits(stop_a, stop_b, cfg.model)
    for note in notes:
        print(f"  WARNING: {note}")
    print(f"  stops {stop_a} and {stop_b} -> soft limits {lo}..{hi} (backed off {margin} counts)")
    if input_fn("  Save these limits? [Y/n] ").strip().lower() in ("n", "no"):
        return None
    return {
        "servo_id": cfg.servo_id,
        "model": cfg.model.value,
        "min_count": lo,
        "max_count": hi,
        "raw_stop_a": stop_a,
        "raw_stop_b": stop_b,
        "margin_counts": margin,
        "calibrated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


SAFETY_BANNER = """\
Before you continue:
  * Tendons must be SLACK or disconnected from the servo horn.
  * Torque is switched OFF on each servo you calibrate; support the finger/joint so it cannot fall.
  * Only turn the horn by hand, gently, until the mechanism's own stop.
"""


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", help="serial port, e.g. /dev/ttyUSB0 or COM3 (not needed with --sim/--show)")
    parser.add_argument("--baud", type=int, default=BAUD_RATE)
    parser.add_argument("--sim", action="store_true", help="use the simulated bus (no hardware)")
    parser.add_argument("--ids", help="servo ids to calibrate, e.g. 1,2,5-7 (named servo_<id>)")
    parser.add_argument("--model", choices=[m.value for m in ServoModel], default=ServoModel.STS3215.value,
                        help="model assumed for --ids/--scan servos (default STS3215)")
    parser.add_argument("--servo", action="append", help="calibrate a servo named in config.SERVOS (repeatable)")
    parser.add_argument("--scan", action="store_true", help="scan ids 1-32 first and offer what answers")
    parser.add_argument("--scan-range", default="1-32", help="ids to scan (default 1-32)")
    parser.add_argument("--file", type=Path, default=CALIBRATION_FILE, help="calibration file to read/write")
    parser.add_argument("--show", action="store_true", help="print the saved calibration and exit")
    args = parser.parse_args(argv)

    try:
        entries, warnings = load_calibration(args.file)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)

    if args.show:
        print(json.dumps(entries, indent=2, sort_keys=True) if entries else "(no calibration saved)")
        return 0
    if not args.sim and not args.port:
        parser.error("--port is required unless --sim or --show is used")

    model = ServoModel(args.model)
    if not MODEL_RANGE_VERIFIED[model]:
        print(f"warning: the count range for {model.value} is an unverified assumption "
              f"{MODEL_COUNT_RANGE[model]}; check the datasheet.", file=sys.stderr)

    # Build the list of servos to calibrate: config names, explicit ids, then scan results.
    targets: Dict[str, ServoConfig] = {}
    try:
        for name in args.servo or []:
            if name not in SERVOS:
                raise ConfigError(f"unknown servo '{name}'; configured: {sorted(SERVOS)}")
            targets[name] = SERVOS[name]
        for servo_id in parse_ids(args.ids) if args.ids else []:
            targets.setdefault(f"servo_{servo_id}", ServoConfig(f"servo_{servo_id}", servo_id, model))
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.sim:
        bus: BaseBus = SimulatedBus(ids=[c.servo_id for c in targets.values()] or [1])
    else:
        bus = FeetechBus(args.port, args.baud)

    try:
        with bus:
            if args.scan or not targets:
                found = bus.scan(parse_ids(args.scan_range), model)
                print(f"scan found {len(found)} servo(s): "
                      + (", ".join(f"id {i} (raw model {n})" for i, n in found) or "none"))
                for servo_id, _ in found:
                    targets.setdefault(f"servo_{servo_id}", ServoConfig(f"servo_{servo_id}", servo_id, model))
            if not targets:
                print("nothing to calibrate (no servos answered). Check power, port, baud, and wiring.")
                return 1

            print(SAFETY_BANNER)
            if input("Type 'yes' to confirm the tendons are slack and the joints are supported: ").strip().lower() != "yes":
                print("aborted; nothing changed.")
                return 1

            for cfg in targets.values():
                choice = input(f"\nCalibrate {cfg.name} (id {cfg.servo_id})? [Y/n/q] ").strip().lower()
                if choice == "q":
                    break
                if choice in ("n", "no"):
                    continue
                try:
                    entry = calibrate_servo(bus, cfg)
                except ConfigError as exc:
                    print(f"  not saved: {exc}")
                    continue
                if entry:
                    entries[cfg.name] = entry
                    save_calibration(entries, args.file)  # save after each servo so progress is never lost
                    print(f"  saved to {args.file}")
    except BusError as exc:
        print(f"bus error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted; servos calibrated so far were already saved.")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())