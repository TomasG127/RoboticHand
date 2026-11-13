"""
Thin wrapper over the Feetech SDK (`scservo_sdk`) plus a simulated bus for testing without hardware.

Two protocol families share one serial bus:
  * STS3215 -> scservo_sdk.sms_sts  (WritePosEx: position, speed, acceleration)
  * SCS0009 -> scservo_sdk.scscl    (WritePos:   position, time, speed)

Everything here is best-effort and lenient: reads return None on failure instead of raising, and
every call is retried a few times because a shared half-duplex bus drops the occasional packet.
Method names/signatures follow the FTServo_Python examples; verify against the SDK version you
install (`pip install feetech-servo-sdk`).
"""

import time
from typing import Dict, Iterable, List, Optional, Tuple

from config import BAUD_RATE, MODEL_COUNT_RANGE, ServoModel

try:
    from scservo_sdk import COMM_SUCCESS, PortHandler, scscl, sms_sts

    SDK_IMPORT_ERROR: Optional[Exception] = None
except ImportError as exc:  # keep the module importable so --sim and tests still work
    PortHandler = sms_sts = scscl = None
    COMM_SUCCESS = 0
    SDK_IMPORT_ERROR = exc


class BusError(Exception):
    """Raised when the bus cannot be opened or is unusable."""


class BaseBus:
    """Interface shared by the real and simulated bus. Servos are addressed by (id, model)."""

    def open(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def ping(self, servo_id: int, model: ServoModel = ServoModel.STS3215, attempts: Optional[int] = None) -> Optional[int]:
        """Return the raw model number if the servo answers, else None."""
        raise NotImplementedError

    def read_position(self, servo_id: int, model: ServoModel) -> Optional[int]:
        raise NotImplementedError

    def set_torque(self, servo_id: int, model: ServoModel, enabled: bool) -> bool:
        raise NotImplementedError

    def move(self, servo_id: int, model: ServoModel, position: int, speed: int, acceleration: int) -> bool:
        raise NotImplementedError

    def read_status(self, servo_id: int, model: ServoModel) -> Dict[str, Optional[int]]:
        """Best-effort voltage/temperature/load. Missing values are None."""
        return {}

    def scan(self, ids: Iterable[int], model: ServoModel = ServoModel.STS3215) -> List[Tuple[int, int]]:
        """Ping each id once; return [(id, raw_model_number)] for those that answer."""
        found = []
        for servo_id in ids:
            number = self.ping(servo_id, model, attempts=1)
            if number is not None:
                found.append((servo_id, number))
        return found

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()


class FeetechBus(BaseBus):
    # Torque-enable register. 40 for both SMS_STS_TORQUE_ENABLE and SCSCL_TORQUE_ENABLE in the
    # SDK headers I know of; verify if you use a different SDK version.
    TORQUE_ENABLE_ADDR = 40

    def __init__(self, port: str, baud: int = BAUD_RATE, retries: int = 3):
        self.port = port
        self.baud = baud
        self.retries = retries
        self._port = None
        self._sts = None
        self._scs = None
        self.last_servo_error: Dict[int, int] = {}  # servo-reported error bits (e.g. overload)

    def open(self) -> None:
        if SDK_IMPORT_ERROR is not None:
            raise BusError(
                f"Feetech SDK not importable ({SDK_IMPORT_ERROR}). "
                "Try: pip install feetech-servo-sdk   (or use --sim to test without hardware)"
            )
        self._port = PortHandler(self.port)
        if not self._port.openPort():
            raise BusError(f"cannot open serial port {self.port} (wrong name? in use by another program?)")
        if not self._port.setBaudRate(self.baud):
            self._port.closePort()
            raise BusError(f"cannot set baud {self.baud} on {self.port}")
        self._sts = sms_sts(self._port)
        self._scs = scscl(self._port)

    def close(self) -> None:
        if self._port is not None:
            self._port.closePort()
            self._port = None

    # --- internals -----------------------------------------------------------
    def _handler(self, model: ServoModel):
        if self._port is None:
            raise BusError("bus is not open")
        return self._sts if model is ServoModel.STS3215 else self._scs

    def _txrx(self, fn, *args, attempts: Optional[int] = None, servo_id: Optional[int] = None):
        """Call an SDK method, retrying. Returns (ok, values). SDK results end with (comm, error)."""
        for _ in range(attempts or self.retries):
            result = fn(*args)
            if not isinstance(result, tuple):
                result = (result, 0)
            comm, err = result[-2], result[-1]
            if comm == COMM_SUCCESS:
                if servo_id is not None:
                    self.last_servo_error[servo_id] = err
                return True, tuple(result[:-2])
            time.sleep(0.002)
        return False, ()

    # --- public API ------------------------------------------------------------
    def ping(self, servo_id, model=ServoModel.STS3215, attempts=None):
        ok, values = self._txrx(self._handler(model).ping, servo_id, attempts=attempts)
        return values[0] if ok else None

    def read_position(self, servo_id, model):
        ok, values = self._txrx(self._handler(model).ReadPos, servo_id, servo_id=servo_id)
        if not ok:
            return None
        lo, hi = MODEL_COUNT_RANGE[model]
        position = int(values[0])
        # Out-of-range reads mean a garbled packet or a servo in a mode we do not expect.
        return position if lo <= position <= hi else None

    def set_torque(self, servo_id, model, enabled):
        ok, _ = self._txrx(
            self._handler(model).write1ByteTxRx, servo_id, self.TORQUE_ENABLE_ADDR, 1 if enabled else 0,
            servo_id=servo_id,
        )
        return ok

    def move(self, servo_id, model, position, speed, acceleration):
        handler = self._handler(model)
        if model is ServoModel.STS3215:
            ok, _ = self._txrx(handler.WritePosEx, servo_id, int(position), int(speed), int(acceleration),
                               servo_id=servo_id)
        else:
            # scscl.WritePos(id, position, time, speed): time 0 = let `speed` govern. UNVERIFIED.
            ok, _ = self._txrx(handler.WritePos, servo_id, int(position), 0, int(speed), servo_id=servo_id)
        return ok

    def read_status(self, servo_id, model):
        handler = self._handler(model)
        status: Dict[str, Optional[int]] = {}
        for key, method in (("voltage_raw", "ReadVoltage"), ("temperature_c", "ReadTemper"), ("load_raw", "ReadLoad")):
            fn = getattr(handler, method, None)
            if fn is None:
                status[key] = None
                continue
            ok, values = self._txrx(fn, servo_id, attempts=1)
            status[key] = int(values[0]) if ok else None
        return status


class SimulatedBus(BaseBus):
    """In-memory stand-in for the real bus. Torque off = the servo ignores motion (like hardware)."""

    def __init__(self, ids: Iterable[int] = (1, 2, 3), positions: Optional[Dict[int, int]] = None):
        self.present_ids = set(ids)
        self.pos: Dict[int, int] = dict(positions or {})
        self.goal: Dict[int, int] = {}
        self.torque: Dict[int, bool] = {}
        self.commands: List[tuple] = []  # every write, for assertions in tests
        self.is_open = False

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False

    def set_position(self, servo_id: int, position: int) -> None:
        """Simulate someone turning the horn by hand."""
        self.pos[servo_id] = position

    def _default(self, servo_id, model):
        lo, hi = MODEL_COUNT_RANGE[model]
        return self.pos.setdefault(servo_id, (lo + hi) // 2)

    def ping(self, servo_id, model=ServoModel.STS3215, attempts=None):
        return 0 if servo_id in self.present_ids else None

    def read_position(self, servo_id, model):
        return self._default(servo_id, model) if servo_id in self.present_ids else None

    def set_torque(self, servo_id, model, enabled):
        if servo_id not in self.present_ids:
            return False
        self.commands.append(("torque", servo_id, bool(enabled)))
        self.torque[servo_id] = bool(enabled)
        return True

    def move(self, servo_id, model, position, speed, acceleration):
        if servo_id not in self.present_ids:
            return False
        self.commands.append(("move", servo_id, int(position), int(speed), int(acceleration)))
        self.goal[servo_id] = int(position)
        if self.torque.get(servo_id, False):
            self.pos[servo_id] = int(position)
        return True

    def read_status(self, servo_id, model):
        return {"voltage_raw": 70, "temperature_c": 30, "load_raw": 0}