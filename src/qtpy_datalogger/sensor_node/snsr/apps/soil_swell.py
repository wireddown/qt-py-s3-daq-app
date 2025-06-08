"""Node-side soil_swell app that reads AI and I2C channels."""

import struct
import time

import adafruit_adxl37x
import analogio
import board
import busio

from snsr.node.classes import ActionInformation


def handle_message(received_action: ActionInformation) -> ActionInformation:
    """Handle a received action from the controlling host."""
    parameters = received_action.parameters["input"]
    samples_to_average = parameters["samples_to_average"]

    adc_codes = do_analog_scan(channels=[], count=samples_to_average)
    xyz_codes = do_accelerometer_read(hardware_offset=(0, 0, 0), count=samples_to_average)
    sensor_readings = adc_codes
    sensor_readings.append(xyz_codes[-1])

    response_action = ActionInformation(
        command=received_action.command,
        parameters={
            "output": sensor_readings,
            "complete": True,
        },
        message_id=received_action.message_id,
    )
    return response_action


def do_analog_scan(channels: list[str], count: int) -> list[float]:
    """Read the specified AI channels 'count' times each and return a list of averaged codes."""
    results = []
    with ReserveAnalogChannels() as analog_input_channels:
        for channel_name, analog_input in sorted(analog_input_channels.items()):
            average_channel_code = adc_take_n(analog_input, count)
            results.append(average_channel_code)
    return results


def do_accelerometer_read(hardware_offset: tuple[int, int, int], count: int) -> tuple[float, float, float]:
    """Read the acceleration from the I2C g_level sensor 'count' times and return a tuple of averaged codes."""
    results = (-1000.0, -1000.0, -1000.0)
    with ReserveStemma() as i2c:
        if not i2c:
            return results
        accelerometer = initialize_accelerometer(i2c, hardware_offset)
        results = xl3d_take_n(accelerometer, count)
    return results


class ReserveAnalogChannels:
    """A context manager that reserves and releases the specified AI channels."""

    def _reserve_all_channels(self) -> dict[str, analogio.AnalogIn]:
        self.all_channels = {
            "AI0": analogio.AnalogIn(board.A0),
            "AI1": analogio.AnalogIn(board.A1),
            "AI2": analogio.AnalogIn(board.A2),
            "AI3": analogio.AnalogIn(board.A3),
            "AI4": analogio.AnalogIn(board.A4),
            "AI5": analogio.AnalogIn(board.A5),
            "AI6": analogio.AnalogIn(board.A6),
            "AI7": analogio.AnalogIn(board.A7),
        }
        return self.all_channels

    def _release_all_channels(self) -> None:
        """De-initialize all AI channels."""
        for pin in self.all_channels.values():
            pin.deinit()

    def __enter__(self) -> dict[str, analogio.AnalogIn]:
        """Reserve AI channels on context enter."""
        return self._reserve_all_channels()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """Release AI channels on context exit."""
        self._release_all_channels()


def adc_take_n(ai_pin: analogio.AnalogIn, count: int) -> float:
    """Read ai_pin 'count' times and return the average code."""
    total = 0
    for _ in range(count):
        total = total + ai_pin.value
    average = total / count
    return average


class ReserveStemma:
    """A context manager that reserves and releases the Stemma I2C bus."""

    def __enter__(self) -> busio.I2C | None:
        """Reserve AI channels on context enter."""
        try:
            self.stemma = board.STEMMA_I2C()  # Singleton, lock-free atomic facade
        except RuntimeError:
            self.stemma = None
        return self.stemma

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """Release AI channels on context exit."""
        if self.stemma:
            self.stemma.deinit()


def initialize_accelerometer(i2c: busio.I2c, hardware_xyz_offset: tuple[int, int, int] | None = None) -> adafruit_adxl37x.ADXL375:
    """Initialize a 200 g measurement session with the ADXL375 connected via Stemma QT. Return None if the bus cannot initialize."""
    accelerometer = adafruit_adxl37x.ADXL375(i2c)
    accelerometer.range = adafruit_adxl37x.Range.RANGE_200_G
    accelerometer.offset = hardware_xyz_offset if hardware_xyz_offset else (0, 0, 0)
    return accelerometer


def xl3d_take_n(from_accelerometer: adafruit_adxl37x.ADXL375, count: int) -> tuple[float, float, float]:
    """Read the accelerometer 'count' times and return a tuple of averaged codes."""
    xl3d_data_rate = 100
    xl3d_clock_period = 1 / xl3d_data_rate
    spacial_axes = ("raw_x", "raw_y", "raw_z")
    xl3d_total = dict.fromkeys(spacial_axes, 0)
    for _ in range(count):
        all_raw_3dxl = xl3d_read_all_axes(from_accelerometer)
        for spacial_axis, raw_value in zip(spacial_axes, all_raw_3dxl):
            xl3d_total[spacial_axis] += raw_value
        time.sleep(xl3d_clock_period)
    average = tuple(
        xl3d_total[spacial_axis] / count
        for spacial_axis in spacial_axes
    )
    return average


def xl3d_read_all_axes(from_accelerometer: adafruit_adxl37x.ADXL375) -> list[int]:
    """Read the acceleration on the X, Y, and Z axes and return the raw codes."""
    byte_count = 6
    raw_bytes = from_accelerometer._read_register(adafruit_adxl37x._REG_DATAX0, byte_count)
    x, y, z = struct.unpack("<hhh", raw_bytes)
    return [x, y, z]
