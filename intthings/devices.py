from abc import ABC, abstractmethod

class IoTDevice(ABC):
    def __init__(self, device_id: str):
        self.device_id = device_id
        self.is_connected = False

    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def get_data(self):
        pass

    def status(self):
        return f"Device {self.device_id}: {'connected' if self.is_connected else 'disconnected'}"


class TemperatureSensor(IoTDevice):
    def __init__(self, device_id: str, location: str = "room"):
        super().__init__(device_id)
        self.location = location
        self._temperature = 22.5

    def connect(self):
        self.is_connected = True
        return f"Temperature sensor {self.device_id} connected at {self.location}"

    def get_data(self):
        if not self.is_connected:
            return {"error": "Device not connected"}
        import random
        self._temperature += random.uniform(-0.5, 0.5)
        return {
            "device_id": self.device_id,
            "type": "temperature",
            "value": round(self._temperature, 1),
            "unit": "°C",
            "location": self.location
        }


class HumiditySensor(IoTDevice):
    def __init__(self, device_id: str, location: str = "room"):
        super().__init__(device_id)
        self.location = location
        self._humidity = 55.0

    def connect(self):
        self.is_connected = True
        return f"Humidity sensor {self.device_id} connected at {self.location}"

    def get_data(self):
        if not self.is_connected:
            return {"error": "Device not connected"}
        import random
        self._humidity += random.uniform(-1.0, 1.0)
        self._humidity = max(0, min(100, self._humidity))
        return {
            "device_id": self.device_id,
            "type": "humidity",
            "value": round(self._humidity, 1),
            "unit": "%",
            "location": self.location
        }