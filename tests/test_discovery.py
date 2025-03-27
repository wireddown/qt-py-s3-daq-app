"""Acceptance tests for the discovery module."""

import click
import pytest
import serial

from qtpy_datalogger import discovery
from qtpy_datalogger.datatypes import DetailKey, ExitCode

usb_qtpy_1 = discovery.QTPyDevice(
    com_id="USB VID:PID=239A:811A SER=00AA00AA00AA LOCATION=1-7:x.0",
    com_port="COMxx",
    device_description="Adafruit QT Py ESP32-S3 no PSRAM",
    drive_label="CIRCUITPY",
    drive_root="Q:",
    ip_address="",
    node_id="",
    python_implementation="circuitpython-9.2.1",
    serial_number="00aa00aa00aa",
    snsr_version="1.2.3",
)

usb_qtpy_2 = discovery.QTPyDevice(
    com_id="USB VID:PID=239A:8144 SER=11CC11CC11CC LOCATION=1-8:x.0",
    com_port="COMyy",
    device_description="Adafruit QT Py ESP32-S3 2MB PSRAM",
    drive_label="CIRCUITPY",
    drive_root="T:",
    ip_address="",
    node_id="",
    python_implementation="circuitpython-9.1.3",
    serial_number="11cc11cc11cc",
    snsr_version="1.1.0",
)


def no_qtpy_devices() -> dict[str, discovery.QTPyDevice]:
    """Override discovery.discover_qtpy_devices() to return zero results."""
    return {}


def one_usb_qtpy_device() -> dict[str, discovery.QTPyDevice]:
    """Override discovery.discover_qtpy_devices() to return one result."""
    return {
        usb_qtpy_1.serial_number: usb_qtpy_1,
    }


def two_usb_qtpy_devices() -> dict[str, discovery.QTPyDevice]:
    """Override discovery.discover_qtpy_devices() to return two results."""
    return {
        usb_qtpy_1.serial_number: usb_qtpy_1,
        usb_qtpy_2.serial_number: usb_qtpy_2,
    }


def select_first_from_prompt(text: str, type: click.Choice, default: str, show_default: bool) -> str:  # noqa: A002 -- we must hide 'type' to match the click API
    """Override click.prompt() to select the first item from the type parameter."""
    return type.choices[0]


def select_last_from_prompt(text: str, type: click.Choice, default: str, show_default: bool) -> str:  # noqa: A002 -- we must hide 'type' to match the click API
    """Override click.prompt() to select the last item from the type parameter."""
    return type.choices[-1]


# These cases are always true for connect() no matter how many devices have been discovered, 0 to many
universal_discovery_test_cases = [
    # Arguments:    behavior,   port,   raised_exception,   expected_exit_code
    # Using --discover-only always exits successfully because --port is ignored
    (discovery.Behavior.DiscoverOnly, "", SystemExit, ExitCode.Success),
    (discovery.Behavior.DiscoverOnly, "COM2", SystemExit, ExitCode.Success),
    (discovery.Behavior.DiscoverOnly, "COM1", SystemExit, ExitCode.Success),
    (discovery.Behavior.DiscoverOnly, "99", SystemExit, ExitCode.Success),
    # Using '--port COM1' always exits with error because it is not supported
    (discovery.Behavior.AutoConnect, "COM1", SystemExit, ExitCode.COM1_Failure),
    # Using a name for --port that doesn't start with 'COM' always exits with error because only Windows is supported
    (discovery.Behavior.AutoConnect, "88", click.BadParameter, 2),
]


def assert_universal_test_cases(excinfo: pytest.ExceptionInfo, expected_exit_code: int, expected_com_port: str) -> None:
    """Validate the output results from the universal_discovery_test_cases."""
    assert excinfo
    exception = excinfo.value
    exception_type = type(exception)
    if exception_type is SystemExit:
        assert exception.code == expected_exit_code
    elif exception_type is click.BadParameter:
        assert exception.exit_code == expected_exit_code
        assert exception.message == f"Cannot open a connection to '{expected_com_port}'"


@pytest.mark.parametrize(
    ("behavior", "port", "raised_exception", "expected_exit_code"),
    [
        *universal_discovery_test_cases,
        (
            discovery.Behavior.AutoConnect,
            "",
            SystemExit,
            ExitCode.Discovery_Failure,
        ),  # This exception means connect() failed because no QT Py devices were discovered
    ],
)
def test_handle_connect_with_no_devices(
    monkeypatch: pytest.MonkeyPatch,
    behavior: discovery.Behavior,
    port: str,
    raised_exception: type,
    expected_exit_code: int,
) -> None:
    """Does it correctly handle connect() when there are no QT Py devices?"""
    monkeypatch.setattr(discovery, "discover_qtpy_devices", no_qtpy_devices)
    expected_port = port

    with pytest.raises(raised_exception) as excinfo:
        discovery.handle_connect(behavior, port)

    assert_universal_test_cases(excinfo, expected_exit_code, expected_port)


@pytest.mark.parametrize(
    ("behavior", "port", "raised_exception", "expected_exit_code"),
    [
        *universal_discovery_test_cases,
        (
            discovery.Behavior.AutoConnect,
            "",
            serial.SerialException,
            -1,
        ),  # This exception means connect() tried to correctly open the (monkeypatched) port
    ],
)
def test_handle_connect_with_one_usb_device(
    monkeypatch: pytest.MonkeyPatch,
    behavior: discovery.Behavior,
    port: str,
    raised_exception: type,
    expected_exit_code: int,
) -> None:
    """Does it correctly handle connect() when there is only one QT Py device?"""
    monkeypatch.setattr(discovery, "discover_qtpy_devices", one_usb_qtpy_device)
    discovered_port = discovery.discover_qtpy_devices().popitem()[1].com_port
    expected_port = port if port else discovered_port

    with pytest.raises(raised_exception) as excinfo:
        discovery.handle_connect(behavior, port)

    assert_universal_test_cases(excinfo, expected_exit_code, expected_port)
    if excinfo.value is serial.SerialException:
        assert excinfo.value.errno is None
        assert (
            excinfo.value.args[0]
            == f"could not open port '{expected_port}': FileNotFoundError(2, 'The system cannot find the file specified.', None, 2)"
        )


@pytest.mark.parametrize(
    ("behavior", "port", "raised_exception", "expected_exit_code"),
    [
        *universal_discovery_test_cases,
        (
            discovery.Behavior.AutoConnect,
            "",
            serial.SerialException,
            -1,
        ),  # This exception means connect() tried to correctly open the (monkeypatched) port
    ],
)
def test_handle_connect_with_two_usb_devices(
    monkeypatch: pytest.MonkeyPatch,
    behavior: discovery.Behavior,
    port: str,
    raised_exception: type,
    expected_exit_code: int,
) -> None:
    """Does it correctly handle connect() when there are two QT Py devices?"""
    monkeypatch.setattr(discovery, "discover_qtpy_devices", two_usb_qtpy_devices)
    monkeypatch.setattr(click, "prompt", select_last_from_prompt)
    discovered_devices = discovery.discover_qtpy_devices()
    selected_device = sorted(discovered_devices)[-1]
    selected_port = discovered_devices[selected_device].com_port
    expected_port = port if port else selected_port

    with pytest.raises(raised_exception) as excinfo:
        discovery.handle_connect(behavior, port)

    assert_universal_test_cases(excinfo, expected_exit_code, expected_port)
    if excinfo.value is serial.SerialException:
        assert excinfo.value.errno is None
        assert (
            excinfo.value.args[0]
            == f"could not open port '{expected_port}': FileNotFoundError(2, 'The system cannot find the file specified.', None, 2)"
        )


def test_QTPyDevice_uses_DetailKeys() -> None:  # noqa: N802 -- allow upper case letters in function name
    """Do the properties in QTPyDevice match DetailKey names?"""
    DetailKey_names = sorted(DetailKey.__members__)  # noqa: N806 -- allow upper case letters in variable name
    instance_property_names = sorted(discovery.QTPyDevice.__annotations__)
    assert set(DetailKey_names) > set(instance_property_names)
