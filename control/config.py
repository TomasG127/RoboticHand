"""
Static configuration for the dexterous hand bench tools.

Design rule (lenient mode): anything we do not know is None or flagged "unverified". Code falls
back to conservative, documented defaults and prints a warning instead of refusing to run.

Code still REFUSES where a wrong guess can break hardware:
  * servo ID outside 1-253, or limits outside the model's count range;
  * enabling torque on a servo that is currently outside its soft limits;
  * any motion command while torque is off or the servo did not answer a ping.

Nothing here is a measured value unless a comment says so.
"""

from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class ConfigError(Exception):
    """Raised when configuration is missing, invalid, or unsafe to use."""


class ServoModel(Enum):
    STS3215 = "STS3215"  # sts/sms protocol (scservo_sdk.sms_sts)
    SCS0009 = "SCS0009"  # scs protocol (scservo_sdk.scscl); count range is an ASSUMPTION


# Raw count range per model.
# STS3215: 0-4095 counts over ~360 degrees (from the project brief).
# SCS0009: ASSUMED 0-1023 counts over ~300 degrees. NOT verified; check the Feetech datasheet.
MODEL_COUNT_RANGE: Dict[ServoModel, Tuple[int, int]] = {
    ServoModel.STS3215: (0, 4095),
    ServoModel.SCS0009: (0, 1023),
}
MODEL_RANGE_VERIFIED: Dict[ServoModel, bool] = {
    ServoModel.STS3215: True,
    ServoModel.SCS0009: False,
}

# --- serial / motion defaults --------------------------------------------
BAUD_RATE = 1_000_000          # STS3215 default; SCS0009 default is ASSUMED equal (verify)
SERIAL_PORT: Optional[str] = None  # set via --port; no default on purpose
DEFAULT_STEP_COUNTS = 20       # counts per keypress
MAX_STEP_COUNTS = 100          # hard cap, even if --step asks for more

# Speed/acceleration units depend on the SDK and model. Set these once verified; until then the
# slow FALLBACK values are used. They are guesses chosen to be slow, not tuned values.
DEFAULT_SPEED: Optional[int] = None
DEFAULT_ACCELERATION: Optional[int] = None
FALLBACK_SPEED: Dict[ServoModel, int] = {
    ServoModel.STS3215: 300,   # steps/s in the sms_sts examples (~26 deg/s); max is ~3400
    ServoModel.SCS0009: 300,   # UNVERIFIED units; test unloaded first
}
FALLBACK_ACCELERATION: Dict[ServoModel, int] = {
    ServoModel.STS3215: 20,    # sms_sts acceleration byte (0-254); low = gentle
    ServoModel.SCS0009: 0,     # scscl.WritePos has no acceleration argument
}

# --- unknown-limit handling ------------------------------------------------
# A servo with no calibrated limits gets a PROVISIONAL window around its startup position:
# +/- (fraction of the model's count range). 0.04 is ~164 counts (~14 deg) on an STS3215.
PROVISIONAL_WINDOW_FRACTION = 0.04

# --- calibration -----------------------------------------------------------
CALIBRATION_FILE = Path(__file__).resolve().with_name("calibration.json")
CALIBRATION_MARGIN_FRACTION = 0.05  # back off this share of the span from each hand-found stop
CALIBRATION_MIN_MARGIN = 30         # ...but never less than this many counts (STS scale)
CALIBRATION_MIN_SPAN = 20           # stops closer than this mean something went wrong

# Servo IDs on a bus are assumed to be 1-253 (conservative; 254 is commonly broadcast).
MIN_SERVO_ID, MAX_SERVO_ID = 1, 253


def resolve_speed(model: ServoModel) -> int:
    return DEFAULT_SPEED if DEFAULT_SPEED is not None else FALLBACK_SPEED[model]


def resolve_acceleration(model: ServoModel) -> int:
    return DEFAULT_ACCELERATION if DEFAULT_ACCELERATION is not None else FALLBACK_ACCELERATION[model]


@dataclass(frozen=True)
class ServoConfig:
    """One physical servo. Limits are raw counts and should come from slack-tendon testing."""

    name: str
    servo_id: int
    model: ServoModel = ServoModel.STS3215
    min_count: Optional[int] = None
    max_count: Optional[int] = None
    # Where the limits came from: "unset" | "config" | "calibration" | "provisional"
    limits_source: str = "unset"

    def __post_init__(self):
        if self.limits_source == "unset" and self.min_count is not None and self.max_count is not None:
            object.__setattr__(self, "limits_source", "config")

    @property
    def count_range(self) -> Tuple[int, int]:
        return MODEL_COUNT_RANGE[self.model]

    @property
    def has_limits(self) -> bool:
        return self.min_count is not None and self.max_count is not None

    def errors(self) -> List[str]:
        """Hard problems: the servo must not be commanded while any of these exist."""
        issues = []
        if not (MIN_SERVO_ID <= self.servo_id <= MAX_SERVO_ID):
            issues.append(f"servo_id {self.servo_id} outside {MIN_SERVO_ID}-{MAX_SERVO_ID}")
        if self.has_limits:
            lo, hi = self.count_range
            if not (lo <= self.min_count < self.max_count <= hi):
                issues.append(f"limits ({self.min_count}, {self.max_count}) invalid for range ({lo}, {hi})")
        elif (self.min_count is None) != (self.max_count is None):
            issues.append("only one of min_count/max_count is set")
        return issues

    def warnings(self) -> List[str]:
        """Soft problems: usable, but the person running the bench should know."""
        notes = []
        if not MODEL_RANGE_VERIFIED[self.model]:
            notes.append(f"count range for {self.model.value} is an unverified assumption")
        if not self.has_limits:
            notes.append("no soft limits; a provisional window will be used")
        elif self.limits_source == "provisional":
            notes.append("limits are PROVISIONAL (startup position +/- window), not measured")
        return notes

    def with_limits(self, lo: int, hi: int, source: str) -> "ServoConfig":
        return replace(self, min_count=lo, max_count=hi, limits_source=source)

    def clamp(self, value: int) -> int:
        """Clamp a count into the soft limits. Refuses if there are no valid limits."""
        problems = self.errors()
        if problems or not self.has_limits:
            raise ConfigError(f"{self.name}: " + "; ".join(problems or ["no soft limits"]))
        return max(self.min_count, min(self.max_count, int(value)))


# --- the servos ------------------------------------------------------------
# Keyed by a human name. You do NOT have to fill this in: bench tools accept --ids or --scan, and
# calibration.json (written by calibration.py) overlays measured limits. Example if you want to
# pin a servo by hand (fill from hardware):
#   "test": ServoConfig(name="test", servo_id=<real id>, model=ServoModel.STS3215)
SERVOS: Dict[str, ServoConfig] = {}

# Joint -> servo mapping. Unknown until the actuator/joint map is documented (README "Next work"),
# so this stays empty. Supported entry shape (see hand.py):
#   "index_mcp": {"servo": "<servo name>", "invert": False}
# Antagonistic pairs and the wrist differential are NOT modeled yet on purpose.
JOINTS: Dict[str, dict] = {}


def get_servo(name: str) -> ServoConfig:
    """Look up a statically configured servo by name. Unknown names raise."""
    try:
        return SERVOS[name]
    except KeyError:
        raise ConfigError(f"unknown servo '{name}'; configured: {sorted(SERVOS)}") from None


def validate_all(servos: Optional[Dict[str, ServoConfig]] = None) -> List[str]:
    """Check servos (default: SERVOS). Raise ConfigError on hard errors; return warnings."""
    table = SERVOS if servos is None else servos
    ids = [s.servo_id for s in table.values()]
    errors = [f"{s.name}: {p}" for s in table.values() for p in s.errors()]
    if len(set(ids)) != len(ids):
        errors.append("duplicate servo_id values")
    if errors:
        raise ConfigError("; ".join(errors))
    return [f"{s.name}: {w}" for s in table.values() for w in s.warnings()]


def parse_ids(text: str) -> List[int]:
    """Parse '1,2,5-7' into [1, 2, 5, 6, 7]. Raises ConfigError on junk."""
    ids: List[int] = []
    try:
        for part in text.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                a, b = part.split("-", 1)
                ids.extend(range(int(a), int(b) + 1))
            else:
                ids.append(int(part))
    except ValueError:
        raise ConfigError(f"cannot parse id list '{text}' (expected e.g. 1,2,5-7)") from None
    bad = [i for i in ids if not (MIN_SERVO_ID <= i <= MAX_SERVO_ID)]
    if bad:
        raise ConfigError(f"ids {bad} outside {MIN_SERVO_ID}-{MAX_SERVO_ID}")
    return sorted(set(ids))