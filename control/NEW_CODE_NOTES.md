Original Prompt: 

with feetech-sdk, create lenient robotic hand code (compensate for lack of provided knowledge on motors and other stuff) across the following files

make sure to use the README for guidance

# Implementation Summary

I (Claude) built this around the README's constraints: slack-tendon calibration, torque off by default, and a panic stop. The implementation is designed to tolerate unknowns rather than refusing to run.

## Completion Status

All six files have been written, along with an updated `requirements.txt`.

Everything passes using the simulated bus. However, none of the code has been tested against real Feetech hardware or the actual SDK because package installation was unavailable in this environment.

I interpreted "lenient" as **working with missing information, not skipping safety**. The README explicitly warns that unmeasured limits can snap a tendon, so the safety guardrails remain in place.

## Where It's Lenient

- **Servos:** You don't need to populate `SERVOS`. Use `--ids 1,2`, `--scan`, or the calibration file.
- **Missing limits:** A servo without defined limits receives a provisional window of approximately ±14° around its starting position. A prominent warning is displayed, and `--strict` restores the previous behavior of refusing to run.
- **SCS0009:** The count range is assumed to be 0–1023 and flagged as unverified instead of blocking the model.
- **Speed and acceleration:** Slow fallback values are used until actual values are configured.
- **Bus errors:** Reads are retried and return `None` rather than crashing.

## Safety Restrictions

- Torque is disabled by default.
- Enabling torque first sets the goal position to the servo's current position to prevent sudden movement.
- Torque cannot be enabled if the servo is outside its limits.
- Motion is refused while torque is disabled or the servo is offline.
- Pressing `Space` releases torque on all servos.
- Pressing `q` or `ESC` releases torque and quits.
- Torque is also released when exceptions or Ctrl-C occur.

## File Descriptions

- **`config.py`** — Existing file, modified. I renamed `problems()` to `errors()` and `warnings()`, and changed its design rule from refusing to run when information is unknown to using fallbacks and warnings. Revert this if you prefer to retain the strict behavior.
- **`servo_bus.py`** — Wrapper around `scservo_sdk`, using `sms_sts` for the STS3215 and `scscl` for the SCS0009. Includes a simulated bus for testing without hardware.
- **`calibration.py`** — Guided calibration tool that lets you manually turn each joint to both stops with the tendons slack. It backs off by a safety margin and saves the resulting limits.
- **`calibration.json`** — Stores calibrated servo limits, which `hand.py` prioritizes over configuration values.
- **`hand.py`** — Contains the servo table, motion logic, and safety logic.
- **`hand_control.py`** — Keyboard-based bench control tool:
  - `[` / `]` — Select a servo.
  - `a` / `d` — Move in steps.
  - `t` — Toggle torque.

## How to Test

### 1. Simulated Testing

Run in a real terminal:

```bash
python hand_control.py --sim --ids 1
```

If using PyCharm, enable **Emulate terminal in output console**.

### 2. Hardware Calibration

Calibrate first using one servo:

```bash
python calibration.py --port COM3 --ids 1
```

Then run `hand_control.py` using the same `--port`.

### 3. First Hardware Movement

Test with one unloaded servo and no tendon attached.

## Items to Verify Before Trusting the Implementation

- **Package name:** Confirm that the SDK installs as `feetech-servo-sdk` and imports as `scservo_sdk`. This could not be verified.
- **SDK method signatures:** `WritePosEx`, `WritePos`, `ReadPos`, and the torque register (address 40) were implemented based on memory of the FTServo examples. Compare these against the actual SDK examples.
- **SCS0009 specifications:** Its position range, baud rate, and speed units remain unconfirmed. Check the Feetech datasheet or consult your TA before operating it under load.
- **Joint mapping:** `JOINTS` currently supports only direct servo-to-joint mapping. Antagonistic pairs and the wrist differential are intentionally excluded because the README says the actuator mapping is undocumented.

## Recommended Next Step

After the first calibration run, document the results in `docs/TEST_LOG.md`. This will also satisfy the README's requirement to measure before making claims about the hardware.