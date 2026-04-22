"""Global settings used by the sensor_node runtime."""

import analogio
import board
import busio
import digitalio
import neopixel


class Settings:
    """A singleton that holds the global settings used by the sensor_node runtime."""

    _instance: "Settings"

    def __new__(cls) -> "Settings":
        """Return the singleton instance, creating it beforehand if necessary."""
        if not hasattr(cls, "_instance"):
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize the instance."""
        if self._initialized:
            return
        self._initialize_from_env()
        self._initialize_dynamic_settings()
        self._board_io_pins: dict[str, digitalio.DigitalInOut | analogio.AnalogIn | neopixel.NeoPixel] = {}
        self._stemma_bus = None
        self._initialized = True

    def _initialize_from_env(self) -> None:
        """Initialize the readonly settings from the environment variables."""
        from os import getenv

        self._wifi_ssid = getenv("CIRCUITPY_WIFI_SSID", "")
        self._wifi_password = getenv("CIRCUITPY_WIFI_PASSWORD", "")
        self._mqtt_broker = getenv("QTPY_BROKER_IP_ADDRESS", "")
        self._node_group = getenv("QTPY_NODE_GROUP", "zone1")
        self._node_name = getenv("QTPY_NODE_NAME", "node1")

    def _initialize_dynamic_settings(self) -> None:
        """Initialize the read-write settings."""
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

    def get_neopixel(self) -> neopixel.NeoPixel:
        """Return the NeoPixel on the board."""
        pin_name = "NEOPIXEL"
        if pin_name not in self._board_io_pins:
            self._board_io_pins[pin_name] = neopixel.NeoPixel(
                pin=getattr(board, pin_name), n=1, brightness=0.2, auto_write=False, pixel_order=neopixel.GRB
            )
        the_neopixel = self._board_io_pins[pin_name]
        if not isinstance(the_neopixel, neopixel.NeoPixel):
            raise TypeError(type(the_neopixel), neopixel.NeoPixel)
        return the_neopixel

    def release_neopixel(self) -> None:
        """De-initialize the NeoPixel on the board."""
        self.release_pin("NEOPIXEL")

    def get_ai_pin(self, pin_name: str) -> analogio.AnalogIn:
        """Initialize the analog input pin instance that matches the board's pin_name."""
        if pin_name not in self._board_io_pins:
            self._board_io_pins[pin_name] = analogio.AnalogIn(getattr(board, pin_name))
        analog_input = self._board_io_pins[pin_name]
        if not isinstance(analog_input, analogio.AnalogIn):
            raise TypeError(type(analog_input), analogio.AnalogIn)
        return analog_input

    def get_dio_pin(self, pin_name: str) -> digitalio.DigitalInOut:
        """Initialize the digital io pin instance that matches the board's pin_name."""
        if pin_name not in self._board_io_pins:
            self._board_io_pins[pin_name] = digitalio.DigitalInOut(getattr(board, pin_name))
        digital_io = self._board_io_pins[pin_name]
        if not isinstance(digital_io, digitalio.DigitalInOut):
            raise TypeError(type(digital_io), digitalio.DigitalInOut)
        return digital_io

    def release_pin(self, pin_name: str) -> None:
        """De-initialize the pin instance that matches the board's pin_name."""
        if pin_name not in self._board_io_pins:
            return
        self._board_io_pins[pin_name].deinit()
        del self._board_io_pins[pin_name]

    def get_stemma_i2c(self) -> busio.I2C:
        """Initialize the Stemma as an I2C port."""
        if not self._stemma_bus:
            self._stemma_bus = board.STEMMA_I2C()
        return self._stemma_bus


settings = Settings()
