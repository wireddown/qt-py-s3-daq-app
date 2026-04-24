"""Global settings used by the sensor_node runtime."""

import gc
from time import monotonic

import analogio
import board
import busio
import digitalio
import neopixel
import wifi
from adafruit_connection_manager import connection_manager_close_all
from microcontroller import cpu
from supervisor import runtime

from snsr.node.classes import NoticeInformation


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
        self._initialize_constants()
        self._initialize_from_env()
        self._initialize_dynamic_settings()
        self._initialized = True

    def _initialize_constants(self) -> None:
        """Initialize the readonly settings from the device."""
        from os import uname
        from sys import implementation, version_info

        from snsr.node.mqtt import format_mqtt_client_id

        self._board_id = board.board_id
        self._serial_number = cpu.uid.hex().lower()
        self._micropython_base = ".".join([str(version_segment) for version_segment in version_info])
        self._python_implementation = f"{implementation.name}-{uname().release}"
        self._notice_info = None  # Lazily loaded on first access
        self._mqtt_client_id = format_mqtt_client_id(role="node", mac_address=self._serial_number, pid=0)

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
        self._app_catalog = None  # Lazily loaded on first access
        self._wifi_radio = None
        self._board_io_pins: dict[str, digitalio.DigitalInOut | analogio.AnalogIn | neopixel.NeoPixel] = {}
        self._settings_for_app_name: dict[str, dict] = {}
        self._stemma_bus = None

    @property
    def board_id(self) -> str:
        """Return the board identifier for the sensor_node."""
        return self._board_id

    @property
    def serial_number(self) -> str:
        """Return the unique identifier for the sensor_node."""
        return self._serial_number

    @property
    def micropython_base(self) -> str:
        """Return the Python version on the sensor_node."""
        return self._micropython_base

    @property
    def python_implementation(self) -> str:
        """Return the Python implementation on the sensor_node."""
        return self._python_implementation

    @property
    def notice_info(self) -> NoticeInformation:
        """Return the NoticeInformation for this sensor_node."""
        if not self._notice_info:
            self._notice_info = get_notice_info()
        return self._notice_info

    @property
    def mqtt_client_id(self) -> str:
        """Return the unique MQTT client ID for the sensor_node."""
        return self._mqtt_client_id

    @property
    def app_catalog(self) -> list[str]:
        """Return the apps on the sensor_node."""
        if not self._app_catalog:
            self._app_catalog = discover_apps()
        return self._app_catalog

    @property
    def cpu_temperature(self) -> float:
        """Return the temperature of the CPU in degrees C."""
        if not cpu.temperature:
            return 0.0
        return cpu.temperature

    @property
    def used_kb(self) -> float:
        """Return the used memory in kB."""
        return gc.mem_alloc() / 1024.0

    @property
    def free_kb(self) -> float:
        """Return the free memory in kB."""
        return gc.mem_free() / 1024.0

    @property
    def uptime(self) -> float:
        """Return the time since the last code.py start in seconds."""
        return monotonic() - settings.boot_time

    @property
    def uart_connected(self) -> bool:
        """Return true if the sensor_node has an open UART connection."""
        return runtime.usb_connected and runtime.serial_connected

    @property
    def uart_bytes_waiting(self) -> bool:
        """Return true if the UART has bytes waiting to be read."""
        return runtime.serial_bytes_available > 0

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

    def connect_to_wifi(self) -> None:
        """Connect to the SSID from settings.toml and return the radio instance."""
        wifi.radio.enabled = True
        wifi.radio.connect(settings._wifi_ssid, settings._wifi_password)
        self._wifi_radio = wifi.radio

    @property
    def wifi_radio(self) -> wifi.Radio:
        """Return the WiFi radio instance."""
        the_radio = self._wifi_radio
        if not the_radio:
            raise ConnectionError()
        return the_radio

    @property
    def ip_address(self) -> str:
        """Return the IP address of the sensor_node."""
        return str(self.wifi_radio.ipv4_address)

    def disconnect_from_wifi(self) -> None:
        """Disconnect and disable the WiFi radio."""
        self._wifi_radio = None
        connection_manager_close_all()
        wifi.radio.enabled = False

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

    def get_app_settings(self, app_name: str) -> dict:
        """Get the settings for app_name."""
        return self._settings_for_app_name.get(app_name, {})

    def update_app_settings(self, app_name: str, settings: dict) -> None:
        """Add or update the specified settings for app_name."""
        app_settings = self._settings_for_app_name.get(app_name, {})
        app_settings.update(settings)
        self._settings_for_app_name.update({app_name: app_settings})


def get_notice_info() -> NoticeInformation:
    """Return a serializable representation of the notice.toml file."""
    notice_contents = []
    with open("/snsr/notice.toml") as notice_toml:  # noqa: PTH123 -- Path.open() is not available on CircuitPython
        notice_contents = notice_toml.read().splitlines()
    notice_info = {}
    for line in notice_contents:
        key_and_value = line.split("=")
        key = key_and_value[0].strip()
        value = key_and_value[1].strip().replace('"', "")
        notice_info[key] = value
    return NoticeInformation.from_dict(notice_info)


def discover_apps() -> list[str]:
    """Autodetect apps on the sensor_node and return a list of names."""
    from os import listdir, stat

    plain_file_stat = 0x8000
    files = listdir("/snsr/apps")  # noqa: PTH208 -- pathlib not available on CircuitPython
    apps = []
    for file in files:
        if file.startswith("__init__"):
            continue
        if stat(f"/snsr/apps/{file}")[0] != plain_file_stat:  # noqa: PTH116 -- pathlib not available on CircuitPython
            continue
        app_basename = file.split(".")[0]
        apps.append(app_basename)
    return apps


def format_wifi_information(wifi_radio: wifi.Radio) -> list[str]:
    """Print details about the WiFi connection."""
    if not wifi_radio.ap_info:
        return []

    lines = [
        "Connected to WiFi",
        "",
        "     Network information",
        f"Hostname: {wifi_radio.hostname}",
        f"Tx Power: {wifi_radio.tx_power} dBm",
        f"IP:       {wifi_radio.ipv4_address}",
        f"DNS:      {wifi_radio.ipv4_dns}",
        f"SSID:     {wifi_radio.ap_info.ssid}",
        f"RSSI:     {wifi_radio.ap_info.rssi} dBm",
        "",
    ]
    return lines


settings = Settings()
