"""Global settings used by the sensor_node runtime."""

import adafruit_adxl37x
import board


class Settings:
    """A singleton that holds the global settings used by the sensor_node runtime."""

    _instance: "Settings"

    def __new__(cls) -> "Settings":
        """Return the singleton instance, creating it beforehand if necessary."""
        if not hasattr(cls, "_instance"):
            cls._instance = super().__new__(cls)
            cls._instance._initialize_from_env()
            cls._instance._initialize_dynamic_settings()
            cls._instance._xl3d_initialized = False
        return cls._instance

    def _initialize_from_env(self) -> None:
        """Initialize the readonly settings from the environment variables."""
        from os import getenv

        self._wifi_ssid = getenv("CIRCUITPY_WIFI_SSID", "")
        self._wifi_password = getenv("CIRCUITPY_WIFI_PASSWORD", "")
        self._mqtt_broker = getenv("QTPY_BROKER_IP_ADDRESS", "")  # See https://github.com/wireddown/qt-py-s3-daq-app/issues/60
        self._node_group = getenv("QTPY_NODE_GROUP", "zone1")
        self._node_name = getenv("QTPY_NODE_NAME", "node1")

    def _initialize_dynamic_settings(self) -> None:
        """Initialize the read-write settings."""
        self._selected_app = "echo"
        self._boot_time = -1.0

    @property
    def wifi_ssid(self) -> str:
        """Return the WiFi SSID from the settings.toml file."""
        return self._wifi_ssid

    @property
    def wifi_password(self) -> str:
        """Return the WiFi password from the settings.toml file."""
        return self._wifi_password

    @property
    def mqtt_broker(self) -> str:
        """Return the MQTT broker IP address from the settings.toml file."""
        return self._mqtt_broker

    @property
    def node_group(self) -> str:
        """Return the name of the group for the sensor_node."""
        return self._node_group

    @property
    def node_name(self) -> str:
        """Return the name of the sensor_node."""
        return self._node_name

    @property
    def boot_time(self) -> float:
        """Return the node's time since boot in milliseconds."""
        return self._boot_time

    @boot_time.setter
    def boot_time(self, new_boot_time: float) -> None:
        """Set a new value for the node's boot time."""
        self._boot_time = new_boot_time

    @property
    def stemma_xl3d(self) -> adafruit_adxl37x.ADXL375:
        """Return the accelerometer on the StemmaQT port."""
        if not self._xl3d_initialized:
            self._stemma = board.STEMMA_I2C()  # Singleton, lock-free atomic facade
            self._stemma_xl3d = adafruit_adxl37x.ADXL375(self._stemma)
            self._stemma_xl3d.range = adafruit_adxl37x.Range.RANGE_200_G
            self._stemma_xl3d.offset = (0, 0, 0)
            self._xl3d_initialized = True
        return self._stemma_xl3d


settings = Settings()
