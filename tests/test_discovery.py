"""Acceptance tests for the discovery module."""

import click
import pytest
import serial

from qtpy_datalogger import discovery, network
from qtpy_datalogger.datatypes import Default, DetailKey, ExitCode
from qtpy_datalogger.sensor_node.snsr.node import classes as node_classes

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

mqtt_qtpy_1 = discovery.QTPyDevice(
    com_id="",
    com_port="",
    device_description="Adafruit QT Py ESP32-S3 no PSRAM",
    drive_label="",
    drive_root="",
    ip_address="192.168.0.0",
    node_id="node-00aa00aa00aa-0",
    python_implementation="circuitpython-9.2.1",
    serial_number="00aa00aa00aa",
    snsr_version="1.2.3",
)

dual_mode_qtpy_1 = discovery.QTPyDevice(
    com_id="USB VID:PID=239A:811A SER=00AA00AA00AA LOCATION=1-7:x.0",
    com_port="COMxx",
    device_description="Adafruit QT Py ESP32-S3 no PSRAM",
    drive_label="CIRCUITPY",
    drive_root="Q:",
    ip_address="192.168.0.0",
    node_id="node-00aa00aa00aa-0",
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

mqtt_qtpy_2 = discovery.QTPyDevice(
    com_id="",
    com_port="",
    device_description="Adafruit QT Py ESP32-S3 2MB PSRAM",
    drive_label="",
    drive_root="",
    ip_address="172.16.0.0",
    node_id="node-11cc11cc11cc-0",
    python_implementation="circuitpython-9.1.3",
    serial_number="11cc11cc11cc",
    snsr_version="1.1.0",
)

dual_mode_qtpy_2 = discovery.QTPyDevice(
    com_id="USB VID:PID=239A:8144 SER=11CC11CC11CC LOCATION=1-8:x.0",
    com_port="COMyy",
    device_description="Adafruit QT Py ESP32-S3 2MB PSRAM",
    drive_label="CIRCUITPY",
    drive_root="T:",
    ip_address="172.16.0.0",
    node_id="node-11cc11cc11cc-0",
    python_implementation="circuitpython-9.1.3",
    serial_number="11cc11cc11cc",
    snsr_version="1.1.0",
)


def no_qtpy_devices(group_id: str) -> dict[str, discovery.QTPyDevice]:
    """Override discovery.discover_qtpy_devices() to return zero results."""
    return {}


def one_usb_qtpy_device(group_id: str) -> dict[str, discovery.QTPyDevice]:
    """Override discovery.discover_qtpy_devices() to return one result."""
    return {
        usb_qtpy_1.serial_number: usb_qtpy_1,
    }


def two_usb_qtpy_devices(group_id: str) -> dict[str, discovery.QTPyDevice]:
    """Override discovery.discover_qtpy_devices() to return two results."""
    return {
        usb_qtpy_1.serial_number: usb_qtpy_1,
        usb_qtpy_2.serial_number: usb_qtpy_2,
    }


def one_mqtt_qtpy_device(group_id: str) -> dict[str, discovery.QTPyDevice]:
    """Override discovery.discover_qtpy_devices() to return one result."""
    return {
        mqtt_qtpy_1.serial_number: mqtt_qtpy_1,
    }


def two_dual_mode_qtpy_devices(group_id: str) -> dict[str, discovery.QTPyDevice]:
    """Override discovery.discover_qtpy_devices() to return two results."""
    return {
        dual_mode_qtpy_1.serial_number: dual_mode_qtpy_1,
        dual_mode_qtpy_2.serial_number: dual_mode_qtpy_2,
    }


def select_first_from_prompt(text: str, type: click.Choice, default: str, show_default: bool) -> str:  # noqa: A002 -- we must hide 'type' to match the click API
    """Override click.prompt() to select the first item from the type parameter."""
    return type.choices[0]


def select_last_from_prompt(text: str, type: click.Choice, default: str, show_default: bool) -> str:  # noqa: A002 -- we must hide 'type' to match the click API
    """Override click.prompt() to select the last item from the type parameter."""
    return type.choices[-1]


def raise_exception(exception_type: type, message: str) -> None:
    """Throw a new exception of the specified type with the specified message."""
    raise exception_type(message)


# These cases are always true for connect() no matter how many devices have been discovered, 0 to many
universal_discovery_test_cases = [
    # Arguments:      behavior,     node,  port,   raised_exception,   expected_exit_code
    # Using --discover-only always exits successfully because both --node and --port are ignored
    (discovery.Behavior.DiscoverOnly, "", "", SystemExit, ExitCode.Success),
    (discovery.Behavior.DiscoverOnly, "", "COM2", SystemExit, ExitCode.Success),
    (discovery.Behavior.DiscoverOnly, "", "COM1", SystemExit, ExitCode.Success),
    (discovery.Behavior.DiscoverOnly, "", "99", SystemExit, ExitCode.Success),
    (discovery.Behavior.DiscoverOnly, "node-bb88bb88bb88-0", "", SystemExit, ExitCode.Success),
]


universal_usb_test_cases = [
    # Arguments:      behavior,     node,  port,   raised_exception,   expected_exit_code
    # Using '--port COM1' always exits with error because it is not supported
    (discovery.Behavior.AutoConnect, "", "COM1", SystemExit, ExitCode.COM1_Failure),
    # Using a name for --port that doesn't start with 'COM' always exits with error because only Windows is supported
    (discovery.Behavior.AutoConnect, "", "88", click.BadParameter, 2),
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
    ("behavior", "node", "port", "raised_exception", "expected_exit_code"),
    [
        *universal_discovery_test_cases,
        *universal_usb_test_cases,
        (
            discovery.Behavior.AutoConnect,
            "",
            "",
            SystemExit,
            ExitCode.Discovery_Failure,
        ),  # This exception means connect() failed because no QT Py devices were discovered
    ],
)
def test_handle_connect_with_no_devices(  # noqa: PLR0913 -- allow more than 5 parameters
    monkeypatch: pytest.MonkeyPatch,
    behavior: discovery.Behavior,
    node: str,
    port: str,
    raised_exception: type,
    expected_exit_code: int,
) -> None:
    """Does it correctly handle connect() when there are no QT Py devices?"""
    monkeypatch.setattr(discovery, "discover_qtpy_devices", no_qtpy_devices)
    expected_port = port

    with pytest.raises(raised_exception) as excinfo:
        discovery.handle_connect(behavior, Default.MqttGroup, node, port)

    assert_universal_test_cases(excinfo, expected_exit_code, expected_port)


@pytest.mark.parametrize(
    ("behavior", "node", "port", "raised_exception", "expected_exit_code"),
    [
        *universal_discovery_test_cases,
        *universal_usb_test_cases,
        (
            discovery.Behavior.AutoConnect,
            "",
            "",
            serial.SerialException,
            -1,
        ),  # This exception means connect() tried to correctly open the (monkeypatched) port
    ],
)
def test_handle_connect_with_one_usb_device(  # noqa: PLR0913 -- allow more than 5 parameters
    monkeypatch: pytest.MonkeyPatch,
    behavior: discovery.Behavior,
    node: str,
    port: str,
    raised_exception: type,
    expected_exit_code: int,
) -> None:
    """Does it correctly handle connect() when there is only one QT Py device?"""
    monkeypatch.setattr(discovery, "discover_qtpy_devices", one_usb_qtpy_device)
    discovered_port = discovery.discover_qtpy_devices(Default.MqttGroup).popitem()[1].com_port
    expected_port = port if port else discovered_port

    with pytest.raises(raised_exception) as excinfo:
        discovery.handle_connect(behavior, Default.MqttGroup, node, port)

    assert_universal_test_cases(excinfo, expected_exit_code, expected_port)
    if excinfo.value is serial.SerialException:
        assert excinfo.value.errno is None
        assert (
            excinfo.value.args[0]
            == f"could not open port '{expected_port}': FileNotFoundError(2, 'The system cannot find the file specified.', None, 2)"
        )


@pytest.mark.parametrize(
    ("behavior", "node", "port", "raised_exception", "expected_exit_code"),
    [
        *universal_discovery_test_cases,
        *universal_usb_test_cases,
        (
            discovery.Behavior.AutoConnect,
            "",
            "",
            serial.SerialException,
            -1,
        ),  # This exception means connect() tried to correctly open the (monkeypatched) port
    ],
)
def test_handle_connect_with_two_usb_devices(  # noqa: PLR0913 -- allow more than 5 parameters
    monkeypatch: pytest.MonkeyPatch,
    behavior: discovery.Behavior,
    node: str,
    port: str,
    raised_exception: type,
    expected_exit_code: int,
) -> None:
    """Does it correctly handle connect() when there are two QT Py devices?"""
    monkeypatch.setattr(discovery, "discover_qtpy_devices", two_usb_qtpy_devices)
    monkeypatch.setattr(click, "prompt", select_last_from_prompt)  # Choose second device to exercise the user-choice
    discovered_devices = discovery.discover_qtpy_devices(Default.MqttGroup)
    selected_device = sorted(discovered_devices)[-1]
    selected_port = discovered_devices[selected_device].com_port
    expected_port = port if port else selected_port

    with pytest.raises(raised_exception) as excinfo:
        discovery.handle_connect(behavior, Default.MqttGroup, node, port)

    assert_universal_test_cases(excinfo, expected_exit_code, expected_port)
    if excinfo.value is serial.SerialException:
        assert excinfo.value.errno is None
        assert (
            excinfo.value.args[0]
            == f"could not open port '{expected_port}': FileNotFoundError(2, 'The system cannot find the file specified.', None, 2)"
        )


@pytest.mark.parametrize(
    ("behavior", "node", "port", "raised_exception", "expected_exit_code"),
    [
        *universal_discovery_test_cases,
        (
            discovery.Behavior.AutoConnect,
            "",
            "",
            RuntimeError,
            0,
        ),  # This exception means connect() tried to correctly open the (monkeypatched) node
        (
            discovery.Behavior.AutoConnect,
            "node-00aa00aa00aa-0",
            "",
            RuntimeError,
            0,
        ),  # This exception means connect() tried to correctly open the (monkeypatched) node
    ],
)
def test_handle_connect_with_one_mqtt_device(  # noqa: PLR0913 -- allow more than 5 parameters
    monkeypatch: pytest.MonkeyPatch,
    behavior: discovery.Behavior,
    node: str,
    port: str,
    raised_exception: type,
    expected_exit_code: int,
) -> None:
    """Does it correctly handle connect() when there is only one QT Py device?"""
    monkeypatch.setattr(discovery, "discover_qtpy_devices", one_mqtt_qtpy_device)
    exception_message = "connect() tried to correctly open the (monkeypatched) node"
    monkeypatch.setattr(network, "open_session_on_node", lambda group, node: raise_exception(raised_exception, exception_message))
    discovered_node = discovery.discover_qtpy_devices(Default.MqttGroup).popitem()[1].node_id
    expected_node = node if node else discovered_node

    with pytest.raises(raised_exception) as excinfo:
        discovery.handle_connect(behavior, Default.MqttGroup, node, port)

    assert_universal_test_cases(excinfo, expected_exit_code, expected_node)
    if excinfo.value is RuntimeError:
        assert excinfo.value.args[0] == exception_message


@pytest.mark.parametrize(
    ("behavior", "node", "port", "raised_exception", "expected_exit_code"),
    [
        *universal_discovery_test_cases,
        (
            discovery.Behavior.AutoConnect,
            "",
            "",
            RuntimeError,
            0,
        ),  # This exception means connect() tried to correctly open the (monkeypatched) node
    ],
)
def test_handle_connect_with_two_dual_mode_devices(  # noqa: PLR0913 -- allow more than 5 parameters
    monkeypatch: pytest.MonkeyPatch,
    behavior: discovery.Behavior,
    node: str,
    port: str,
    raised_exception: type,
    expected_exit_code: int,
) -> None:
    """Does it correctly handle connect() when there are two QT Py devices with both USB and WiFi?"""
    monkeypatch.setattr(discovery, "discover_qtpy_devices", two_dual_mode_qtpy_devices)
    exception_message = "connect() tried to correctly open the (monkeypatched) node"
    monkeypatch.setattr(network, "open_session_on_node", lambda group, node: raise_exception(raised_exception, exception_message))
    monkeypatch.setattr(click, "prompt", select_first_from_prompt)  # Choose WiFi connection
    discovered_devices = discovery.discover_qtpy_devices(Default.MqttGroup)
    selected_device = sorted(discovered_devices)[-1]
    selected_node = discovered_devices[selected_device].node_id
    expected_node = node if node else selected_node

    with pytest.raises(raised_exception) as excinfo:
        discovery.handle_connect(behavior, Default.MqttGroup, node, port)

    assert_universal_test_cases(excinfo, expected_exit_code, expected_node)
    if excinfo.value is RuntimeError:
        assert excinfo.value.args[0] == exception_message


def test_windows_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    """Does it correctly identify dual-mode and MQTT-only devices?"""

    def override_ports_from_serial() -> dict[str, dict[DetailKey, str]]:
        """Return hardcoded details for Windows serial ports."""
        return {
            "COM1": {
                DetailKey.com_port: "COM1",
                DetailKey.com_id: "ACPI\\\\PNP0501\\\\0",
                DetailKey.serial_number: "",
            },
            "COMyy": {
                DetailKey.com_port: "COMyy",
                DetailKey.com_id: "USB VID:PID=239A:8144 SER=11CC11CC11CC LOCATION=1-8:x.0",
                DetailKey.serial_number: "11CC11CC11CC",
            },
        }

    def override_volumes_from_wmi() -> dict[str, dict[DetailKey, str]]:
        """Return hardcoded details for Windows storage volumes."""
        return {
            "C:": {
                DetailKey.drive_root: "B:",
                DetailKey.drive_label: "TestWindows",
                DetailKey.serial_number: "BD64_1379.",
                DetailKey.device_description: "MSI M371",
            },
            "X:": {
                DetailKey.drive_root: "P:",
                DetailKey.drive_label: "xtra",
                DetailKey.serial_number: "E823_BF53_8FA6_0001.",
                DetailKey.device_description: "WD SN770",
            },
            "E:": {
                DetailKey.drive_root: "E:",
                DetailKey.drive_label: "ENDER",
                DetailKey.serial_number: "",
                DetailKey.device_description: "SDHC Card",
            },
            "F:": {
                DetailKey.drive_root: "F:",
                DetailKey.drive_label: "CIRCUITPY",
                DetailKey.serial_number: "11CC11CC11CC",
                DetailKey.device_description: "Adafruit QT Py ESP32S3 2MB PSRAM",
            },
        }

    def override_nodes_from_mqtt(group_id: str) -> dict[str, dict[DetailKey, str]]:
        """Return hardcoded details for MQTT nodes."""
        return {
            "00aa00aa00aa": {
                DetailKey.device_description: "adafruit_qtpy_esp32s3_nopsram",
                DetailKey.ip_address: "192.168.0.0",
                DetailKey.node_id: "node-00aa00aa00aa-0",
                DetailKey.python_implementation: "circuitpython-9.2.1",
                DetailKey.serial_number: "00aa00aa00aa",
                DetailKey.snsr_commit: "ab8dc58",
                DetailKey.snsr_timestamp: "2025-03-18T19:11:48-07:00",
                DetailKey.snsr_version: "0.2.0",
                DetailKey.system_name: "3.4.0",
            },
            "11cc11cc11cc": {
                DetailKey.device_description: "adafruit_qtpy_esp32s3_4mbflash_2mbpsram",
                DetailKey.ip_address: "172.16.0.0",
                DetailKey.node_id: "node-11cc11cc11cc-0",
                DetailKey.python_implementation: "circuitpython-9.1.3",
                DetailKey.serial_number: "11CC11CC11CC",
                DetailKey.snsr_commit: "d7efbab",
                DetailKey.snsr_timestamp: "2025-03-04T13:22:51-07:00",
                DetailKey.snsr_version: "0.1.0",
                DetailKey.system_name: "3.4.0",
            },
        }

    monkeypatch.setattr(discovery, "_query_ports_from_serial", override_ports_from_serial)
    monkeypatch.setattr(discovery, "_query_volumes_from_wmi", override_volumes_from_wmi)
    monkeypatch.setattr(network, "query_nodes_from_mqtt", override_nodes_from_mqtt)

    devices = discovery.discover_qtpy_devices(Default.MqttGroup)

    # 1 dual mode
    dual_mode_serial_number = "11cc11cc11cc"
    assert dual_mode_serial_number in devices
    assert devices[dual_mode_serial_number].com_port
    assert devices[dual_mode_serial_number].node_id

    # 1 MQTT only
    mqtt_only_serial_number = "00aa00aa00aa"
    assert mqtt_only_serial_number in devices
    assert not devices[mqtt_only_serial_number].com_port
    assert devices[mqtt_only_serial_number].node_id


def test_QTPyDevice_uses_DetailKeys() -> None:  # noqa: N802 -- allow upper case letters in function name
    """Do the properties in QTPyDevice match DetailKey names?"""
    DetailKey_names = sorted(DetailKey.__members__)  # noqa: N806 -- allow upper case letters in variable name
    instance_property_names = sorted(discovery.QTPyDevice.__annotations__)
    assert set(DetailKey_names) > set(instance_property_names)


def test_DescriptorInformation_uses_DetailKeys() -> None:  # noqa: N802 -- allow upper case letters in function name
    """Do the properties in DescriptorInformation match DetailKey names?"""
    DetailKey_names = sorted(DetailKey.__members__)  # noqa: N806 -- allow upper case letters in variable name
    instance_property_names = sorted(node_classes.DescriptorInformation.__annotations__)
    assert set(DetailKey_names) > set(instance_property_names)
