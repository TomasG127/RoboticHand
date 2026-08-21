# Bench control

Open-loop keyboard control of the servo bank for prototype testing.

## Key map

| Key | Action |
|---|---|
| | |
| `ESC` | Release torque on all channels |

## Before first run

1. Populate `SOFT_LIMITS` in `hand_control.py`. The script refuses to run while it is empty.
2. Set limits with the tendon **slack**. Drive each joint to its mechanical stop by hand, read
   the count, back off, and record the band.
3. Verify the panic stop works before tensioning anything.
