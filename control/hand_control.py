"""
Bench control for the low-cost dexterous hand.

Open-loop keyboard control of serial-bus servos for prototype testing. Soft limits are enforced
in software; there is no position feedback loop and no collision checking. This is a bench tool,
not a controller.

Torque starts OFF. Select a servo, press `t` to enable torque (it holds where it is), then step
with `a`/`d`. SPACE releases torque on everything; ESC or `q` releases everything and quits.

Examples:
  python hand_control.py --port COM3 --ids 1          # one servo, provisional limits
  python hand_control.py --port /dev/ttyUSB0 --scan    # find servos on the bus
  python hand_control.py --sim --ids 1,2               # no hardware
Run it in a real terminal (PyCharm: enable "Emulate terminal in output console").
"""

import argparse
import sys
import time
from typing import List, Optional

from config import (
    BAUD_RATE,
    CALIBRATION_FILE,
    DEFAULT_STEP_COUNTS,
    MAX_STEP_COUNTS,
    ConfigError,
    ServoModel,
    parse_ids,
)
from hand import Hand, HandError, build_servo_table, servo_from_id
from servo_bus import BaseBus, BusError, FeetechBus, SimulatedBus

HELP = """\
keys:  [ / ]  previous / next servo      a / d   step - / +      + / -   bigger / smaller step
       t      torque on/off (selected)   r       re-read all     SPACE   RELEASE ALL TORQUE
       ?      this help                  q / ESC release everything and quit
"""


# --- keyboard (cross-platform, no third-party packages) -------------------------------------
class KeyReader:
    """Context manager yielding single keypresses without waiting for Enter."""

    def __enter__(self):
        if not sys.stdin.isatty():
            raise RuntimeError("stdin is not a terminal; run in a real terminal (PyCharm: Emulate terminal)")
        self._windows = sys.platform.startswith("win")
        if not self._windows:
            import termios
            import tty

            self._fd = sys.stdin.fileno()
            self._saved = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)  # cbreak (not raw) keeps Ctrl-C working
        return self

    def __exit__(self, *exc):
        if not self._windows:
            import termios

            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved)

    def read(self, timeout: float = 0.1) -> Optional[str]:
        """Return one character, or None if nothing was pressed within `timeout` seconds."""
        if self._windows:
            import msvcrt

            end = time.monotonic() + timeout
            while time.monotonic() < end:
                if msvcrt.kbhit():
                    ch = msvcrt.getwch()
                    if ch in ("\x00", "\xe0"):  # arrow/function key prefix: swallow the second code
                        msvcrt.getwch()
                        return None
                    return ch
                time.sleep(0.01)
            return None
        import os
        import select

        if not select.select([self._fd], [], [], timeout)[0]:
            return None
        ch = os.read(self._fd, 1).decode(errors="ignore")
        if ch == "\x1b":  # a lone ESC is panic; ESC + more bytes is an arrow key, ignore it
            if select.select([self._fd], [], [], 0.03)[0]:
                os.read(self._fd, 8)
                return None
        return ch


# --- UI ------------------------------------------------------------------------------------------
def show(hand: Hand, name: str, message: str = "") -> None:
    line = hand.status_line(name) + (f"   | {message}" if message else "")
    print("\r" + line.ljust(118), end="", flush=True)


def run_loop(hand: Hand, step: int) -> None:
    names = hand.active_names()
    index = 0
    message = ""
    last_refresh = 0.0
    print(HELP)
    with KeyReader() as keys:
        while True:
            name = names[index]
            now = time.monotonic()
            if now - last_refresh > 0.5:  # periodic read-back for display; failures are ignored
                hand.refresh(name)
                last_refresh = now
            show(hand, name, message)
            key = keys.read(0.1)
            if key is None:
                continue
            message = ""
            try:
                if key in ("q", "Q", "\x1b"):
                    return
                elif key == " ":
                    failed = hand.panic_stop()
                    message = "ALL TORQUE RELEASED" + (f"; NOT CONFIRMED: {failed}, CUT POWER" if failed else "")
                elif key == "]":
                    index = (index + 1) % len(names)
                elif key == "[":
                    index = (index - 1) % len(names)
                elif key in ("a", "A", "d", "D"):
                    target, clamped = hand.step(name, -step if key in ("a", "A") else step)
                    message = f"-> {target}" + (" (at limit)" if clamped else "")
                elif key in ("+", "="):
                    step = min(MAX_STEP_COUNTS, step + 5)
                    message = f"step {step}"
                elif key in ("-", "_"):
                    step = max(1, step - 5)
                    message = f"step {step}"
                elif key in ("t", "T"):
                    if hand.state[name].torque:
                        message = "torque off" if hand.disable_torque(name) else "torque-off FAILED, cut power"
                    else:
                        hand.enable_torque(name)
                        message = "torque on (holding current position)"
                elif key in ("r", "R"):
                    hand.refresh_all()
                    message = "refreshed"
                elif key in ("?", "h", "H"):
                    print("\n" + HELP)
            except HandError as exc:
                message = f"REFUSED: {exc}"


# --- entry point --------------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", help="serial port, e.g. /dev/ttyUSB0 or COM3 (not needed with --sim)")
    parser.add_argument("--baud", type=int, default=BAUD_RATE)
    parser.add_argument("--sim", action="store_true", help="simulated bus, no hardware")
    parser.add_argument("--step", type=int, default=DEFAULT_STEP_COUNTS, help="counts per keypress")
    parser.add_argument("--ids", help="servo ids to use, e.g. 1,2,5-7 (named servo_<id>)")
    parser.add_argument("--model", choices=[m.value for m in ServoModel], default=ServoModel.STS3215.value,
                        help="model assumed for --ids/--scan servos (default STS3215)")
    parser.add_argument("--servo", action="append", help="restrict to these servo names (repeatable)")
    parser.add_argument("--scan", action="store_true", help="scan ids 1-32 and add whatever answers")
    parser.add_argument("--scan-range", default="1-32")
    parser.add_argument("--calibration", default=str(CALIBRATION_FILE), help="calibration file to overlay")
    parser.add_argument("--speed", type=int, help="override speed (SDK units; see config.FALLBACK_SPEED)")
    parser.add_argument("--acc", type=int, help="override acceleration (STS only)")
    parser.add_argument("--strict", action="store_true",
                        help="refuse servos with no configured/calibrated limits (no provisional window)")
    args = parser.parse_args(argv)
    if not args.sim and not args.port:
        parser.error("--port is required unless --sim is used")
    if args.step > MAX_STEP_COUNTS:
        print(f"note: --step {args.step} capped to {MAX_STEP_COUNTS}", file=sys.stderr)
    step = max(1, min(args.step, MAX_STEP_COUNTS))
    model = ServoModel(args.model)

    try:
        servos, warnings = build_servo_table(args.calibration, parse_ids(args.ids) if args.ids else (), model,
                                             args.servo)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)

    bus: BaseBus = SimulatedBus(ids=[c.servo_id for c in servos.values()] or [1]) if args.sim \
        else FeetechBus(args.port, args.baud)
    try:
        with bus:
            if args.scan or not servos:
                found = bus.scan(parse_ids(args.scan_range), model)
                print(f"scan found: {', '.join(f'id {i}' for i, _ in found) or 'nothing'}")
                known = {c.servo_id for c in servos.values()}
                for servo_id, _ in found:
                    if servo_id not in known:
                        cfg = servo_from_id(servo_id, model)
                        servos[cfg.name] = cfg
            if not servos:
                print("no servos to control: none configured, none given with --ids, none answered the scan.",
                      file=sys.stderr)
                return 1

            hand = Hand(bus, servos, speed=args.speed, acceleration=args.acc)
            for message in hand.connect(strict=args.strict):
                print(message)
            if not any(s.online for s in hand.state.values()):
                print("no servo is usable; nothing to control.", file=sys.stderr)
                return 1
            # The selector skips offline servos, but panic_stop still covers every known servo.
            # Torque release MUST happen before the bus closes, so it lives inside the `with`.
            try:
                run_loop(hand, step)
            except KeyboardInterrupt:
                print("\ninterrupted")
            finally:
                try:
                    failed = hand.panic_stop()
                except Exception as exc:  # noqa: BLE001 - last line of defense, report and move on
                    failed = [f"panic_stop crashed: {exc}"]
                print("\ntorque released on all servos." if not failed else
                      f"\nWARNING: could not confirm torque release for {failed}. CUT POWER.")
    except (BusError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())