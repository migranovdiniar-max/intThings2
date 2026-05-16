import abc
import pymongo
import datetime
import threading


# ─────────────────────────────────────────────
#  Abstract base
# ─────────────────────────────────────────────
class Thing(abc.ABC):
    def __init__(self, name):
        self.name = name
        print(f'[Thing] Created: {name}')

    @abc.abstractmethod
    def connect(self, *args):
        # Закомментировал, чтобы не спамить в консоль каждые 2 секунды
        # print('[Thing] Connection start')
        pass


# ─────────────────────────────────────────────
#  Sensor
# ─────────────────────────────────────────────
class Sensor(Thing):
    MIN_VALUE = -50.0
    MAX_VALUE = 150.0

    def __init__(self, unit, name):
        super().__init__(name)
        self.unit = unit
        self.value = 0.0
        self.power = 'on'
        print('[Sensor] Created')

    # ---------- validation ----------
    def validate(self, raw_value):
        """Return (float_value, error_message_or_None)."""
        try:
            val = float(raw_value)
        except (ValueError, TypeError):
            return None, f'Not a number: {raw_value!r}'
        if not (self.MIN_VALUE <= val <= self.MAX_VALUE):
            return None, (f'Out of range [{self.MIN_VALUE}, {self.MAX_VALUE}]: {val}')
        return val, None

    def connect(self, request):
        super().connect()
        raw = request.args.get('value', '')
        val, err = self.validate(raw)
        if err:
            print(f'[Sensor] Validation failed — {err}')
            return {'power': self.power, 'error': err}
        self.value = val
        return {'power': self.power}


# ─────────────────────────────────────────────
#  Heater
# ─────────────────────────────────────────────
class Heater(Thing):
    def __init__(self, name, switch_on_temperature):
        super().__init__(name)
        self.power = 'Off'
        self.switch_on_temperature = switch_on_temperature

    def connect(self):
        super().connect()
        return {'heater_power': self.power}

    def auto_power(self, temperature):
        self.power = 'On' if temperature < self.switch_on_temperature else 'Off'


# ─────────────────────────────────────────────
#  Logger
# ─────────────────────────────────────────────
class Logger:
    """
    Writes sensor data to MongoDB.
    """

    # ── validation bounds (mirror Sensor, kept here for defence-in-depth) ──
    TEMP_MIN = -50.0
    TEMP_MAX = 150.0

    def __init__(self, db_name: str, mongo_uri: str):
        self.current_temperature = None
        self.current_heater_state = None
        
        # Подключаемся по переданному URI (теперь это облако Atlas)
        print(f'[Logger] Connecting to MongoDB...')
        self.client = pymongo.MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self._timer: threading.Timer | None = None
        print(f'[Logger] Connected to DB: {db_name}')

    # ── internal helpers ─────────────────────────────────────────────────

    @staticmethod
    def _now() -> str:
        return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def _validate_temperature(self, value):
        """Return (float_value, error_str_or_None)."""
        try:
            val = float(value)
        except (ValueError, TypeError):
            return None, f'Expected a number, got {value!r}'
        if not (self.TEMP_MIN <= val <= self.TEMP_MAX):
            return None, (
                f'Temperature {val} outside valid range '
                f'[{self.TEMP_MIN}, {self.TEMP_MAX}]'
            )
        return val, None

    def _log_error(self, source: str, message: str):
        self.db['Errors'].insert_one({
            'timeStamp': self._now(),
            'source': source,
            'message': message,
        })
        print(f'[Logger][ERROR] {source}: {message}')

    # ── public API ───────────────────────────────────────────────────────

    def insert_temperature(self, new_data):
        """Validate and persist a temperature reading (skip duplicates)."""
        val, err = self._validate_temperature(new_data)
        if err:
            self._log_error('insert_temperature', err)
            return None

        if val == self.current_temperature:
            print('[Logger] Temperature unchanged — skipping')
            return None

        self.current_temperature = val
        result = self.db['Temperature'].insert_one({
            'timeStamp': self._now(),
            'Temperature': val,
            'unit': 'C',
        })
        print(f'[Logger] Temperature logged: {val} °C')
        return result

    def insert_heater_event(self, new_state: str):
        """Persist heater state changes (On/Off)."""
        allowed = {'On', 'Off'}
        if new_state not in allowed:
            self._log_error(
                'insert_heater_event',
                f'Invalid heater state: {new_state!r}. Allowed: {allowed}',
            )
            return None

        if new_state == self.current_heater_state:
            print('[Logger] Heater state unchanged — skipping')
            return None

        self.current_heater_state = new_state
        result = self.db['HeaterEvents'].insert_one({
            'timeStamp': self._now(),
            'heaterState': new_state,
        })
        print(f'[Logger] Heater event logged: {new_state}')
        return result

    # ── periodic background logging ──────────────────────────────────────

    def start_periodic(self, sensor: 'Sensor', heater: 'Heater',
                       interval_sec: float = 10.0):
        """
        Launch a background thread that logs sensor + heater data
        every `interval_sec` seconds, regardless of HTTP activity.
        """
        def _tick():
            self.insert_temperature(sensor.value)
            self.insert_heater_event(heater.power)
            # reschedule
            self._timer = threading.Timer(interval_sec, _tick)
            self._timer.daemon = True
            self._timer.start()

        self._timer = threading.Timer(interval_sec, _tick)
        self._timer.daemon = True
        self._timer.start()
        print(f'[Logger] Periodic logging started (every {interval_sec}s)')

    def stop_periodic(self):
        if self._timer:
            self._timer.cancel()
            print('[Logger] Periodic logging stopped')