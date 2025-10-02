"""
Functions for finding and connecting to QT Py sensor nodes.

Supported host platforms
- Windows

Supported connection types
- serial / UART
- network / MQTT
"""

import asyncio
import contextlib
import dataclasses
import logging
import os
import pathlib
import sys
from enum import StrEnum

import click
import serial
import toml
from serial.tools import miniterm as mt

from qtpy_datalogger import network

from .datatypes import CaptionCorrections, ConnectionTransport, DetailKey, ExitCode, SnsrNotice, SnsrPath

logger = logging.getLogger(__name__)


class Behavior(StrEnum):
    """Supported discovery behaviors for QT Py devices."""

    AutoConnect = "AutoConnect"
    DiscoverOnly = "DiscoveryOnly"


@dataclasses.dataclass
class QTPyDevice:
    """
    Information about a discovered QT Py device.

    These details are always available:
    - device_description -- Manufacturer product description for the QT Py device
    - python_implementation -- The origin and version of the Python interpreter on the QT Py device
    - serial_number:  -- The serial number for the QT Py device

    When the device has qtpy_datalogger installed, these details are available:
    - mqtt_group_id -- The MQTT group that the QT Py device joins
    - snsr_version -- The version of qtpy_datalogger installed on the QT Py device

    When the device is connected with USB, these details are available:
    - com_id -- System hardware identifiers for the QT Py device's UART port
    - com_port -- System name for the QT Py device's UART port
    - drive_label -- Name for the QT Py device's storage volume
    - drive_root -- System name for the QT Py device's storage volume

    When the device is connected to the same MQTT broker, these details are available:
    - ip_address -- The IPv4 address for the QT Py device
    - node_id -- The MQTT client identifier for the QT Py device
    """

    com_id: str
    com_port: str
    device_description: str
    drive_label: str
    drive_root: str
    ip_address: str
    mqtt_group_id: str
    node_id: str
    python_implementation: str
    serial_number: str
    snsr_version: str


def handle_connect(behavior: Behavior, group_id: str, node: str, port: str) -> None:
    """Connect to a QT Py sensor node."""
    logger.debug(f"behavior: '{behavior}', group: '{group_id}', node: '{node}', port: '{port}'")

    if os.name != "nt":
        logger.error(f"Support for {sys.platform} is not implemented.")
        message = f"Cannot open a connection from {sys.platform}"
        raise click.UsageError(message)

    if behavior == Behavior.DiscoverOnly:
        qtpy_devices = discover_qtpy_devices(group_id)
        if qtpy_devices:
            formatted_lines = _format_port_table(qtpy_devices, group_id)
            _ = [logger.info(line) for line in formatted_lines]
        else:
            logger.warning("No QT Py devices found!")
        raise SystemExit(ExitCode.Success)

    communication_transport = ConnectionTransport.AutoSelect
    if node:
        communication_transport = ConnectionTransport.MQTT_WiFi
    elif port:
        communication_transport = ConnectionTransport.UART_Serial

    if communication_transport == ConnectionTransport.AutoSelect:
        qtpy_device, communication_transport = discover_and_select_qtpy(group_id)
        if not qtpy_device:
            logger.error("No QT Py devices found!")
            raise SystemExit(ExitCode.Discovery_Failure)
        node = qtpy_device.node_id
        port = qtpy_device.com_port

    if not port.startswith("COM") and communication_transport == ConnectionTransport.UART_Serial:
        logger.error("Format for --port argument is '--port COM#' where # is a number.")
        message = f"Cannot open a connection to '{port}'"
        raise click.BadParameter(message, param_hint="--port COM#")

    if port == "COM1":
        logger.error(f"Opening '{port}' is not supported.")
        raise SystemExit(ExitCode.COM1_Failure)

    if communication_transport == ConnectionTransport.UART_Serial:
        open_session_on_port(port)
    elif communication_transport == ConnectionTransport.MQTT_WiFi:
        network.open_session_on_node(group_id, node)
        logger.info("")
        logger.info(f"Reconnect with 'qtpy-datalogger connect --node {node}'")


async def discover_qtpy_devices_async(group_id: str) -> dict[str, QTPyDevice]:
    """Scan for QT Py devices and return a dictionary of QTPyDevice instances indexed by serial_number."""
    # A QT Py COM port has a serial number
    # And its network MAC address uses the same serial number
    logger.info("Discovering serial ports")
    logger.info(f"Scanning the network for sensor_node devices in group '{group_id}'")
    discovered_serial_ports, discovered_nodes = await asyncio.gather(
        asyncio.to_thread(_query_ports_from_serial),
        network.query_nodes_from_mqtt_async(group_id),
    )

    # And its disk drive uses the same serial number
    logger.info("Discovering disk volumes")
    discovered_disk_volumes = _query_volumes_from_wmi()  # Using asyncio.to_thread confuses win32 COM

    qtpy_devices = _process_query_results(discovered_serial_ports, discovered_disk_volumes, discovered_nodes)
    return qtpy_devices


def discover_qtpy_devices(group_id: str) -> dict[str, QTPyDevice]:
    """Scan for QT Py devices and return a dictionary of QTPyDevice instances indexed by serial_number."""
    # A QT Py COM port has a serial number
    logger.info("Discovering serial ports")
    discovered_serial_ports = _query_ports_from_serial()

    # And its disk drive uses the same serial number
    logger.info("Discovering disk volumes")
    discovered_disk_volumes = _query_volumes_from_wmi()

    # And its network MAC address uses the same serial number
    logger.info(f"Scanning the network for sensor_node devices in group '{group_id}'")
    discovered_nodes = network.query_nodes_from_mqtt(group_id)

    qtpy_devices = _process_query_results(discovered_serial_ports, discovered_disk_volumes, discovered_nodes)
    return qtpy_devices


def _process_query_results(
    discovered_serial_ports: dict[str, dict[DetailKey, str]],
    discovered_disk_volumes: dict[str, dict[DetailKey, str]],
    discovered_nodes: dict[str, dict[DetailKey, str]],
) -> dict[str, QTPyDevice]:
    """Combine the results and identify QT Py devices."""
    logger.info("Identifying QT Py devices")
    qtpy_devices: dict[str, QTPyDevice] = {}
    for drive_info in discovered_disk_volumes.values():
        drive_serial_number = drive_info[DetailKey.serial_number]

        for port_info in discovered_serial_ports.values():
            port_serial_number = port_info[DetailKey.serial_number]

            if port_serial_number and port_serial_number == drive_serial_number:
                serial_number = port_serial_number.lower()
                python_implementation, snsr_version, mqtt_group = _query_node_info_from_drive(
                    drive_info[DetailKey.drive_root]
                )
                qtpy_devices[serial_number] = QTPyDevice(
                    com_id=port_info[DetailKey.com_id],
                    com_port=port_info[DetailKey.com_port],
                    device_description=drive_info[DetailKey.device_description],
                    drive_label=drive_info[DetailKey.drive_label],
                    drive_root=drive_info[DetailKey.drive_root],
                    ip_address="",
                    mqtt_group_id=mqtt_group,
                    node_id="",
                    python_implementation=python_implementation,
                    serial_number=serial_number,
                    snsr_version=snsr_version,
                )

    dual_mode_devices = set(qtpy_devices) & set(discovered_nodes)
    for dual_mode_device in dual_mode_devices:
        qtpy_devices[dual_mode_device].ip_address = discovered_nodes[dual_mode_device][DetailKey.ip_address]
        qtpy_devices[dual_mode_device].node_id = discovered_nodes[dual_mode_device][DetailKey.node_id]
        qtpy_devices[dual_mode_device].snsr_version = discovered_nodes[dual_mode_device][DetailKey.snsr_version]

    mqtt_only_devices = set(discovered_nodes) - set(qtpy_devices)
    for mqtt_only_device in [discovered_nodes[n] for n in mqtt_only_devices]:
        serial_number = mqtt_only_device[DetailKey.serial_number]
        device_description = mqtt_only_device[DetailKey.device_description]
        qtpy_devices[serial_number] = QTPyDevice(
            com_id="",
            com_port="",
            device_description=device_description,
            drive_label="",
            drive_root="",
            ip_address=mqtt_only_device[DetailKey.ip_address],
            mqtt_group_id=mqtt_only_device[DetailKey.mqtt_group_id],
            node_id=mqtt_only_device[DetailKey.node_id],
            python_implementation=mqtt_only_device[DetailKey.python_implementation],
            serial_number=serial_number,
            snsr_version=mqtt_only_device[DetailKey.snsr_version],
        )

    logger.debug(qtpy_devices)
    return qtpy_devices


def open_session_on_port(port: str) -> None:
    """Open a terminal connection to the specified serial port."""
    serial_options = {
        "url": port,
        "baudrate": 115200,
        "bytesize": 8,
        "parity": "N",
        "stopbits": 1,
        "rtscts": False,
        "xonxoff": False,
        "do_not_open": True,
    }
    logger.debug(serial_options)
    com_port = serial.serial_for_url(**serial_options)

    if not hasattr(com_port, "cancel_read"):
        # Enable timeout for alive flag polling if cancel_read is not available
        com_port.timeout = 1

    if isinstance(com_port, serial.Serial):
        com_port.exclusive = True

    com_port.open()

    miniterm_options = {
        "serial_instance": com_port,
        "echo": False,
        "eol": "crlf",
        "filters": ["direct"],
    }
    logger.debug(miniterm_options)
    miniterm = mt.Miniterm(**miniterm_options)

    miniterm.exit_character = "\x1d"
    miniterm.menu_character = "\x14"
    miniterm.raw = False
    miniterm.set_rx_encoding("UTF-8")
    miniterm.set_tx_encoding("UTF-8")

    quit_command = mt.key_description(miniterm.exit_character)
    help_command = mt.key_description(miniterm.menu_character)
    logger.info(
        f"---   Miniterm on {miniterm.serial.name}   Opts: {miniterm.serial.baudrate},{miniterm.serial.bytesize},{miniterm.serial.parity},{miniterm.serial.stopbits}    ---"
    )
    logger.info(f"---   Quit: {quit_command}        Help: {help_command} then H   ---")

    miniterm.start()
    com_port.write(b"\r\n")
    with contextlib.suppress(KeyboardInterrupt):
        miniterm.join(True)
    miniterm.join()
    miniterm.close()

    logger.info("")
    logger.info(f"Reconnect with 'qtpy-datalogger connect --port {port}'")


def discover_and_select_qtpy(
    group_id: str,
    transport: ConnectionTransport = ConnectionTransport.AutoSelect,
) -> tuple[QTPyDevice | None, ConnectionTransport | None]:
    """
    Scan for QT Py devices and return a tuple of the selected device and its communication transport.

    Ask the user for input when there is more than one device available or when a device has more than one transport available.
    """
    qtpy_devices = discover_qtpy_devices(group_id)
    if not qtpy_devices:
        return (None, None)

    selectable_devices = sorted(qtpy_devices.keys())
    selected_device = qtpy_devices[selectable_devices[0]]
    selected_reason = "Auto-selected"
    if len(selectable_devices) > 1:
        logger.info(f"Found {len(selectable_devices)} QT Py devices, select a device to continue")
        formatted_lines = _format_port_table(qtpy_devices, group_id)
        _ = [print(line) for line in formatted_lines]  # noqa: T201 -- use direct IO for user prompt

        choices = click.Choice([f"{index + 1}" for index in range(len(selectable_devices))])
        user_input = click.prompt(
            text="Enter a device number",
            type=choices,
            default="1",
            show_default=False,
        )
        selected_index = int(user_input) - 1
        selected_device = qtpy_devices[selectable_devices[selected_index]]
        selected_reason = "User-selected"

    has_uart = len(selected_device.com_port) > 0
    has_mqtt = len(selected_device.node_id) > 0

    if transport == ConnectionTransport.AutoSelect:
        if all([has_uart, has_mqtt]):
            logger.info(
                f"QT Py device '{selected_device.device_description}' has UART and MQTT available, select a connection transport to continue"
            )
            selectable_transports = sorted(ConnectionTransport)
            selectable_transports.remove(ConnectionTransport.AutoSelect)
            _ = [print(f"  {index + 1}:  {entry}") for index, entry in enumerate(selectable_transports)]  # noqa: T201 -- use direct IO for user prompt

            choices = click.Choice([f"{index + 1}" for index in range(len(selectable_transports))])
            user_input = click.prompt(
                text="Enter a transport number",
                type=choices,
                default="1",
                show_default=False,
            )
            selected_index = int(user_input) - 1
            selected_transport = selectable_transports[selected_index]
            selected_reason = "User-selected"
        elif has_uart:
            selected_transport = ConnectionTransport.UART_Serial
        else:
            selected_transport = ConnectionTransport.MQTT_WiFi
    elif transport == ConnectionTransport.UART_Serial and has_uart:
        selected_transport = ConnectionTransport.UART_Serial
    elif transport == ConnectionTransport.MQTT_WiFi and has_mqtt:
        selected_transport = ConnectionTransport.MQTT_WiFi
    else:
        return (selected_device, None)

    if selected_transport == ConnectionTransport.UART_Serial:
        transport_message = f"port '{selected_device.com_port}' on '{selected_device.drive_root}\\'"
    else:
        transport_message = f"MQTT node '{selected_device.node_id}' on '{selected_device.ip_address}'"

    logger.info(f"{selected_reason} '{selected_device.device_description}' as {transport_message}")
    return (selected_device, selected_transport)


def _query_ports_from_serial() -> dict[str, dict[DetailKey, str]]:
    """
    Scan the system for serial ports and return a dictionary of information.

    Returned entries, grouped by com_port
    - com_port
    - com_id
    - serial_number
    """
    # Other approaches include WMI's Win32_SerialPort
    from serial.tools.list_ports_windows import comports  # noqa: PLC0415 -- dynamic import at runtime for Windows

    discovered_comports = {
        comport.device: {
            DetailKey.com_port: comport.device,
            DetailKey.com_id: comport.hwid,
            DetailKey.serial_number: comport.serial_number,
        }
        for comport in sorted(comports())
    }
    logger.debug(discovered_comports)
    return discovered_comports


def _query_volumes_from_wmi() -> dict[str, dict[DetailKey, str]]:
    """
    Scan the system for disk volumes and return a dictionary of information.

    Returned entries, grouped by drive_letter:
    - drive_letter
    - drive_label
    - serial_number
    - disk_description
    """
    # Disk drive letters and labels are returned by Win32_Volume()
    #   Use wmi_property Label to retrieve the label like 'CIRCUITPY'
    #   Use wmi_property DriveLetter to retrieve the letter like 'D:'
    # To associate a physical disk with one of its disk drives, we can use the partition identifier
    #   The physical disk hosts the partition, and the partition hosts the disk drive
    #   The mapping between disk drive letters and their partitions is returned by Win32_LogicalDiskToPartition()
    #     Use wmi_property Antecedent to retrieve the partition identifier
    #     Use the corresponding wmi_property Dependent to retrieve the associated disk drive letter
    #   The mapping between physical disks and their partitions is returned by Win32_DiskDriveToDiskPartition()
    #     Use wmi_property Antecedent to retrieve the physical disk's identifier
    #     Use the corresponding wmi_property Dependent to retrieve the associated partition identifier
    # Serial numbers for physical disks are returned by Win32_PhysicalMedia()
    #   Use wmi_property SerialNumber to retrieve it
    #   Use wmi_property Tag to retrieve an identifier for the physical disk like '\\.\PHYSICALDRIVE2'
    # Finally, the description for the physical disk is returned by Win32_DiskDrive()
    #   Use wmi_property DeviceID to retrieve the identifier for the physical disk
    #   Use wmi_property Caption to retrieve its description
    # Other approaches include making Windows dll calls
    from wmi import WMI  # noqa: PLC0415 -- dynamic import at runtime for Windows

    host_pc = WMI()

    drive_letters_and_labels = {}
    for volume in list(host_pc.Win32_Volume()):
        drive_letter = volume.wmi_property("DriveLetter").value
        if drive_letter:
            drive_label = volume.wmi_property("Label").value
            drive_letters_and_labels.update(
                {
                    drive_letter: {
                        DetailKey.drive_root: drive_letter,
                        DetailKey.drive_label: drive_label,  # Unique to this WMI call
                    }
                }
            )
    logger.debug(f"Win32_Volume report: {drive_letters_and_labels}")

    drive_letters_and_partitions = {}
    for entry in list(host_pc.Win32_LogicalDiskToPartition()):
        # Full value has format '\\\\HOSTNAME\\root\\cimv2:Win32_LogicalDisk.DeviceID="C:"'
        drive_letter = entry.wmi_property("Dependent").value.split("=")[-1].replace('"', "")
        # Full value has format '\\\\HOSTNAME\\root\\cimv2:Win32_DiskPartition.DeviceID="Disk #0, Partition #2"'
        drive_partition = entry.wmi_property("Antecedent").value.split("=")[-1].replace('"', "")
        drive_letters_and_partitions.update(
            {
                drive_letter: {
                    DetailKey.drive_root: drive_letter,
                    DetailKey.drive_partition: drive_partition,
                }
            }
        )
    logger.debug(f"Win32_LogicalDiskToPartition report: {drive_letters_and_partitions}")

    partitions_and_disks = {}
    for entry in list(host_pc.Win32_DiskDriveToDiskPartition()):
        # Full value has format '\\\\HOSTNAME\\root\\cimv2:Win32_DiskPartition.DeviceID="Disk #0, Partition #0"'
        partition = entry.wmi_property("Dependent").value.split("=")[-1].replace('"', "")
        # Full value has format '\\\\HOSTNAME\\root\\cimv2:Win32_DiskDrive.DeviceID="\\\\\\\\.\\\\PHYSICALDRIVE0"'
        disk_id = entry.wmi_property("Antecedent").value.split("=")[-1].replace('"', "").split("\\")[-1]
        partitions_and_disks.update(
            {
                partition: {
                    DetailKey.drive_partition: partition,
                    DetailKey.disk_id: disk_id,
                }
            }
        )
    logger.debug(f"Win32_DiskDriveToDiskPartition report: {partitions_and_disks}")

    disks_and_serial_numbers = {}
    for disk in list(host_pc.Win32_PhysicalMedia()):
        # Full value has format '\\\\.\\PHYSICALDRIVE0'
        disk_id = disk.wmi_property("Tag").value.split("\\")[-1]
        serial_number = disk.wmi_property("SerialNumber").value
        disks_and_serial_numbers.update(
            {
                disk_id: {
                    DetailKey.disk_id: disk_id,
                    DetailKey.serial_number: serial_number,  # Unique to this WMI call
                }
            }
        )
    logger.debug(f"Win32_PhysicalMedia report: {disks_and_serial_numbers}")

    disks_and_descriptions = {}
    for drive in list(host_pc.Win32_DiskDrive()):
        # Full value has format '\\\\.\\PHYSICALDRIVE0'
        disk_id = drive.wmi_property("DeviceID").value.split("\\")[-1]
        disk_description = drive.wmi_property("Caption").value
        corrected_description = CaptionCorrections.get_corrected(disk_description)
        disks_and_descriptions.update(
            {
                disk_id: {
                    DetailKey.disk_id: disk_id,
                    DetailKey.device_description: corrected_description,  # Unique to this WMI call
                }
            }
        )
    logger.debug(f"Win32_DiskDrive report: {disks_and_descriptions}")

    discovered_storage_volumes = {}
    for drive_letter, _ in drive_letters_and_labels.items():
        drive_label = drive_letters_and_labels[drive_letter][DetailKey.drive_label]
        if drive_letter not in drive_letters_and_partitions:
            continue
        drive_partition = drive_letters_and_partitions[drive_letter][DetailKey.drive_partition]
        disk_id = partitions_and_disks[drive_partition][DetailKey.disk_id]
        disk_serial_number = disks_and_serial_numbers[disk_id][DetailKey.serial_number]
        disk_description = disks_and_descriptions[disk_id][DetailKey.device_description]
        discovered_storage_volumes.update(
            {
                drive_letter: {
                    DetailKey.drive_root: drive_letter,
                    DetailKey.drive_label: drive_label,
                    DetailKey.serial_number: disk_serial_number,
                    DetailKey.device_description: disk_description,
                }
            }
        )
    logger.debug(discovered_storage_volumes)
    return discovered_storage_volumes


def _query_node_info_from_drive(drive_root: str) -> tuple[str, str, str]:
    """Return a tuple of (python_implementation, snsr_version, mqtt_group_id) from the candidate device as drive_root."""
    as_path = pathlib.Path(drive_root)
    boot_out_info = _parse_boot_out_file(as_path)
    if not boot_out_info:
        # If there isn't a boot_out.txt file on the device, it's not a CircuitPython device
        return ("", "", "")

    python_implementation = boot_out_info[DetailKey.python_implementation]
    notice_file = as_path.joinpath(SnsrPath.notice)
    if not notice_file.exists():
        # If there isn't a notice.toml file on the device, it's not a qtpy_datalogger sensor_node
        return (python_implementation, "", "")

    notice_contents = toml.load(notice_file)
    snsr_notice = SnsrNotice(**notice_contents)
    settings_file = as_path.joinpath(SnsrPath.settings)
    if not settings_file.exists():
        # If there isn't a settings file on the device, it won't have an MQTT group_id
        return (python_implementation, snsr_notice.version, "")

    settings_contents = toml.load(settings_file)
    mqtt_group = settings_contents.get("QTPY_NODE_GROUP", "")
    return (python_implementation, snsr_notice.version, mqtt_group)


def _parse_boot_out_file(main_folder: pathlib.Path) -> dict[DetailKey, str]:
    """Return a dictionary representation of the boot_out.txt file in main_folder."""
    boot_out_file = main_folder.joinpath("boot_out.txt")
    if not boot_out_file.exists():
        return {}

    lines = boot_out_file.read_text().splitlines()
    logger.debug(f"Parsing '{boot_out_file}' with contents")
    _ = [logger.debug(line) for line in lines]
    circuitpy_version_line = lines[0]
    board_id_line = lines[1]
    circuitpy_version = circuitpy_version_line.split(";")[0].split(" ")[-3]
    board_id = board_id_line.split(":")[-1]

    return {
        DetailKey.python_implementation: f"circuitpython-{circuitpy_version}",
        DetailKey.device_description: CaptionCorrections.get_corrected(board_id),
    }


def _format_port_table(qtpy_devices: dict[str, QTPyDevice], group_id: str) -> list[str]:
    """Return a list of text lines that present a table of the specified qtpy_devices."""
    lines = []
    lines.append("")
    lines.append("      {:5}  {:5}  {:35}  {:20}  {:12}".format("Port", "Drive", "QT Py device", "Node ID", "Group ID"))
    lines.append("      {:5}  {:5}  {:35}  {:20}  {:12}".format("-" * 5, "-" * 5, "-" * 35, "-" * 20, "-" * 12))
    sorted_devices = sorted(qtpy_devices.keys())
    for index, qtpy_device in enumerate([qtpy_devices[serial_number] for serial_number in sorted_devices]):
        drive_letter = ""
        if qtpy_device.drive_root:
            drive_letter = f"{qtpy_device.drive_root}\\"
        lines.append(
            f"{index + 1:3}:  {qtpy_device.com_port:5}  {drive_letter:5}  {qtpy_device.device_description:35}  {qtpy_device.node_id:20}  {qtpy_device.mqtt_group_id:12}"
        )
    lines.append("")
    return lines
