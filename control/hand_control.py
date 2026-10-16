"""
Bench control for the low-cost dexterous hand.

Open-loop keyboard control of serial-bus servos for prototype testing. Soft limits are enforced
in software; there is no position feedback loop and no collision checking. This is a bench tool,
not a controller.
"""

import argparse
import sys

# --- configuration -------------------------------------------------------
# Per-channel soft limits, in raw servo counts. Set these against a SLACK tendon
# before tensioning: drive each joint to its mechanical stop by hand, read the count,
# then back off. A wrong limit here is how you snap a tendon or strip a horn.
SOFT_LIMITS = {
    # channel_id: (min_count, max_count)
    # 1: (1024, 3072),
}

STEP = 20          # counts per keypress
BAUD = 1_000_000   # STS3215 default


def clamp(channel: int, value: int) -> int:
    """Clamp a commanded position into the channel's soft limit band."""
    lo, hi = SOFT_LIMITS.get(channel, (0, 4095))
    return max(lo, min(hi, value))


def panic_stop(bus) -> None:
    """Release torque on every configured channel. Bound to ESC."""
    for channel in SOFT_LIMITS:
        ...  # bus.torque_disable(channel)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="serial port, e.g. /dev/ttyUSB0 or COM3")
    parser.add_argument("--baud", type=int, default=BAUD)
    parser.add_argument("--step", type=int, default=STEP, help="counts per keypress")
    args = parser.parse_args()

    if not SOFT_LIMITS:
        print("Refusing to run: SOFT_LIMITS is empty. Populate it first.", file=sys.stderr)
        return 1

    # TODO: open the bus, enter the key loop, call panic_stop() on ESC and on exception.
    raise NotImplementedError("port the working bench script into this structure")


if __name__ == "__main__":
    raise SystemExit(main())
