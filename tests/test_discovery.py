"""Acceptance tests for the discovery module."""

import click
import pytest
import serial

from qtpy_datalogger import discovery


def no_qtpy_devices() -> list[dict[str, str]]:
    """Override discovery.discover_qtpy_devices() to return zero results."""
    return []


def one_qtpy_device() -> list[dict[str, str]]:
    """Override discovery.discover_qtpy_devices() to return one result."""
    return [
        {
            "drive_letter": "Q:",
            "drive_label": "CIRCUITPY",
            "disk_description": "Adafruit QT Py ESP32S3 no PSRAM",
            "serial_number": "00AA00AA00AA",
            "com_port": "COMxx",
            "com_id": "USB VID:PID=239A:811A SER=00AA00AA00AA LOCATION=1-7:x.0",
        },
    ]


def two_qtpy_devices() -> list[dict[str, str]]:
    """Override discovery.discover_qtpy_devices() to return two results."""
    return [
        {
            "drive_letter": "Q:",
            "drive_label": "CIRCUITPY",
            "disk_description": "Adafruit QT Py ESP32S3 no PSRAM",
            "serial_number": "00AA00AA00AA",
            "com_port": "COMxx",
            "com_id": "USB VID:PID=239A:811A SER=00AA00AA00AA LOCATION=1-7:x.0",
        },
        {
            "drive_letter": "T:",
            "drive_label": "CIRCUITPY",
            "disk_description": "Adafruit QT Py ESP32S3 2MB PSRAM",
            "serial_number": "11CC11CC11CC",
            "com_port": "COMyy",
            "com_id": "USB VID:PID=239A:8144 SER=11CC11CC11CC LOCATION=1-8:x.0",
        },
    ]


def select_last_from_prompt(text: str, type: click.Choice, default: str, show_default: bool) -> str:  # noqa: A002 -- we must hide 'type' to match the click API
    """Override click.prompt() to select the last item from the type parameter."""
    return type.choices[-1]


# These cases are always true for connect() no matter how many devices have been discovered, 0 to many
universal_test_cases = [
    # Arguments:    behavior,   port,   raised_exception,   expected_exit_code
    # Using --discover-only always exits successfully because --port is ignored
    (discovery.Behavior.DiscoverOnly, "", SystemExit, discovery._EXIT_SUCCESS),
    (discovery.Behavior.DiscoverOnly, "COM2", SystemExit, discovery._EXIT_SUCCESS),
    (discovery.Behavior.DiscoverOnly, "COM1", SystemExit, discovery._EXIT_SUCCESS),
    (discovery.Behavior.DiscoverOnly, "99", SystemExit, discovery._EXIT_SUCCESS),
    # Using '--port COM1' always exits with error because it is not supported
    (discovery.Behavior.AutoConnect, "COM1", SystemExit, discovery._EXIT_COM1_FAILURE),
    # Using a name for --port that doesn't start with 'COM' always exits with error because only Windows is supported
    (discovery.Behavior.AutoConnect, "88", click.BadParameter, 2),
]


def assert_universal_test_cases(excinfo: pytest.ExceptionInfo, expected_exit_code: int, expected_com_port: str) -> None:
    """Validate the output results from the universal_test_cases."""
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
        *universal_test_cases,
        (
            discovery.Behavior.AutoConnect,
            "",
            SystemExit,
            discovery._EXIT_DISCOVERY_FAILURE,
        ),  # This exception means connect() failed because no serial ports were discovered
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
        *universal_test_cases,
        (
            discovery.Behavior.AutoConnect,
            "",
            serial.SerialException,
            -1,
        ),  # This exception means connect() tried to correctly open the (monkeypatched) port
    ],
)
def test_handle_connect_with_one_device(
    monkeypatch: pytest.MonkeyPatch,
    behavior: discovery.Behavior,
    port: str,
    raised_exception: type,
    expected_exit_code: int,
) -> None:
    """Does it correctly handle connect() when there is only one QT Py device?"""
    monkeypatch.setattr(discovery, "discover_qtpy_devices", one_qtpy_device)
    expected_port = port if port else discovery.discover_qtpy_devices()[0][discovery._INFO_KEY_com_port]

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
        *universal_test_cases,
        (
            discovery.Behavior.AutoConnect,
            "",
            serial.SerialException,
            -1,
        ),  # This exception means connect() tried to correctly open the (monkeypatched) port
    ],
)
def test_handle_connect_with_two_devices(
    monkeypatch: pytest.MonkeyPatch,
    behavior: discovery.Behavior,
    port: str,
    raised_exception: type,
    expected_exit_code: int,
) -> None:
    """Does it correctly handle connect() when there are two QT Py devices?"""
    monkeypatch.setattr(discovery, "discover_qtpy_devices", two_qtpy_devices)
    monkeypatch.setattr(click, "prompt", select_last_from_prompt)
    expected_port = port if port else two_qtpy_devices()[-1][discovery._INFO_KEY_com_port]

    with pytest.raises(raised_exception) as excinfo:
        discovery.handle_connect(behavior, port)

    assert_universal_test_cases(excinfo, expected_exit_code, expected_port)
    if excinfo.value is serial.SerialException:
        assert excinfo.value.errno is None
        assert (
            excinfo.value.args[0]
            == f"could not open port '{expected_port}': FileNotFoundError(2, 'The system cannot find the file specified.', None, 2)"
        )
