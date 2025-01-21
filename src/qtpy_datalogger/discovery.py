"""
Functions for finding and connecting to QT Py sensor nodes.

Supported host platforms
- Windows

Supported connection types
- serial / UART
"""

import contextlib
import logging
import os
import sys
from enum import StrEnum

import click
import serial
from serial.tools import miniterm as mt

logger = logging.getLogger(__name__)

_EXIT_SUCCESS = 0
_EXIT_DISCOVERY_FAILURE = 41
_EXIT_COM1_FAILURE = 42

_INFO_KEY_drive_letter = "drive_letter"
_INFO_KEY_drive_label = "drive_label"
_INFO_KEY_drive_partition = "drive_partition"
_INFO_KEY_disk_id = "disk_id"
_INFO_KEY_disk_description = "disk_description"
_INFO_KEY_serial_number = "serial_number"
_INFO_KEY_com_port = "com_port"
_INFO_KEY_com_id = "com_id"


class Behavior(StrEnum):
    """Supported discovery behaviors for QT Py devices."""

    AutoConnect = "AutoConnect"
    DiscoverOnly = "DiscoveryOnly"


def handle_connect(behavior: Behavior, port: str) -> None:
    """Connect to a QT Py sensor node."""
    logger.debug(f"behavior: '{behavior}', port: '{port}'")

    if os.name != "nt":
        logger.error(f"Support for {sys.platform} is not implemented.")
        message = f"Cannot open a connection from {sys.platform}"
        raise click.UsageError(message)

    if behavior == Behavior.DiscoverOnly:
        qtpy_devices = discover_qtpy_devices()
        if qtpy_devices:
            formatted_lines = _format_port_table(qtpy_devices)
            _ = [logger.info(line) for line in formatted_lines]
        else:
            logger.warning("No QT Py devices found!")
        raise SystemExit(_EXIT_SUCCESS)

    if not port:
        port = _discover_and_select_port()
        if not port:
            logger.error("No QT Py devices found!")
            raise SystemExit(_EXIT_DISCOVERY_FAILURE)

    if not port.startswith("COM"):
        logger.error("Format for --port argument is '--port COM#' where # is a number.")
        message = f"Cannot open a connection to '{port}'"
        raise click.BadParameter(message, param_hint="--port COM#")

    if port == "COM1":
        logger.error(f"Opening '{port}' is not supported.")
        raise SystemExit(_EXIT_COM1_FAILURE)

    open_session_on_port(port)


def discover_qtpy_devices() -> list[dict[str, str]]:
    """
    Scan for QT Py devices and return a list of information dictionaries.

    Returned entries
    - drive_letter
    - drive_label
    - disk_description
    - serial_number
    - com_port
    - com_id
    """
    # A QT Py COM port has a serial number
    logger.info("Discovering serial ports")
    discovered_serial_ports = _query_ports_from_serial()

    # And its disk drive uses the same serial number
    logger.info("Discovering disk volumes")
    discovered_disk_volumes = _query_volumes_from_wmi()

    logger.info("Identifying QT Py devices")
    qtpy_devices = []
    for drive_info in discovered_disk_volumes.values():
        drive_serial_number = drive_info[_INFO_KEY_serial_number]

        for port_info in discovered_serial_ports.values():
            port_serial_number = port_info[_INFO_KEY_serial_number]

            if port_serial_number and port_serial_number == drive_serial_number:
                qtpy_devices.append(
                    {
                        _INFO_KEY_drive_letter: drive_info[_INFO_KEY_drive_letter],
                        _INFO_KEY_drive_label: drive_info[_INFO_KEY_drive_label],
                        _INFO_KEY_disk_description: drive_info[_INFO_KEY_disk_description],
                        _INFO_KEY_serial_number: drive_info[_INFO_KEY_serial_number],
                        _INFO_KEY_com_port: port_info[_INFO_KEY_com_port],
                        _INFO_KEY_com_id: port_info[_INFO_KEY_com_id],
                    }
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


def _discover_and_select_port() -> str:
    """
    Scan for QT Py devices and return a serial port name.

    Ask the user for input when there is more than one device available.
    """
    qtpy_devices = discover_qtpy_devices()
    if qtpy_devices:
        selected_device = qtpy_devices[0]
        selected_reason = "Auto-selected"
        if len(qtpy_devices) > 1:
            logger.info(f"Found {len(qtpy_devices)} QT Py devices")
            logger.info("Select a QT Py device to open for serial communication")
            formatted_lines = _format_port_table(qtpy_devices)
            _ = [print(line) for line in formatted_lines]  # noqa: T201 -- use direct IO for user

            choices = click.Choice([f"{index + 1}" for index in range(len(qtpy_devices))])
            user_input = click.prompt(
                text="Enter a device number",
                type=choices,
                default="1",
                show_default=False,
            )
            selected_index = int(user_input) - 1
            selected_device = qtpy_devices[selected_index]
            selected_reason = "User-selected"
        logger.info(
            f"{selected_reason} {selected_device[_INFO_KEY_com_port]} from '{selected_device[_INFO_KEY_disk_description]}' on '{selected_device[_INFO_KEY_drive_letter]}\\'"
        )
        return selected_device[_INFO_KEY_com_port]
    return ""


def _query_ports_from_serial() -> dict[str, dict[str, str]]:
    """
    Scan the system for serial ports and return a dictionary of information.

    Returned entries, grouped by com_port
    - com_port
    - com_id
    - serial_number
    """
    # Other approaches include WMI's Win32_SerialPort
    from serial.tools.list_ports_windows import comports

    discovered_comports = {
        comport.device: {
            _INFO_KEY_com_port: comport.device,
            _INFO_KEY_com_id: comport.hwid,
            _INFO_KEY_serial_number: comport.serial_number,
        }
        for comport in sorted(comports())
    }
    logger.debug(discovered_comports)
    return discovered_comports


def _query_volumes_from_wmi() -> dict[str, dict[str, str]]:
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
    from wmi import WMI

    host_pc = WMI()

    drive_letters_and_labels = {}
    for volume in list(host_pc.Win32_Volume()):
        drive_letter = volume.wmi_property("DriveLetter").value
        if drive_letter:
            drive_label = volume.wmi_property("Label").value
            drive_letters_and_labels.update(
                {
                    drive_letter: {
                        _INFO_KEY_drive_letter: drive_letter,
                        _INFO_KEY_drive_label: drive_label,  # Unique to this WMI call
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
                    _INFO_KEY_drive_letter: drive_letter,
                    _INFO_KEY_drive_partition: drive_partition,
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
                    _INFO_KEY_drive_partition: partition,
                    _INFO_KEY_disk_id: disk_id,
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
                    _INFO_KEY_disk_id: disk_id,
                    _INFO_KEY_serial_number: serial_number,  # Unique to this WMI call
                }
            }
        )
    logger.debug(f"Win32_PhysicalMedia report: {disks_and_serial_numbers}")

    caption_corrections = {
        "Adafruit QT Py ESP32S3 no USB Device": "Adafruit QT Py ESP32S3 no PSRAM",
        "Adafruit QT Py ESP32S3 4M USB Device": "Adafruit QT Py ESP32S3 2MB PSRAM",
    }
    disks_and_descriptions = {}
    for drive in list(host_pc.Win32_DiskDrive()):
        # Full value has format '\\\\.\\PHYSICALDRIVE0'
        disk_id = drive.wmi_property("DeviceID").value.split("\\")[-1]
        disk_description = drive.wmi_property("Caption").value
        corrected_description = caption_corrections.get(disk_description, disk_description)
        disks_and_descriptions.update(
            {
                disk_id: {
                    _INFO_KEY_disk_id: disk_id,
                    _INFO_KEY_disk_description: corrected_description,  # Unique to this WMI call
                }
            }
        )
    logger.debug(f"Win32_DiskDrive report: {disks_and_descriptions}")

    discovered_storage_volumes = {}
    for drive_letter, _ in drive_letters_and_labels.items():
        drive_label = drive_letters_and_labels[drive_letter][_INFO_KEY_drive_label]
        drive_partition = drive_letters_and_partitions[drive_letter][_INFO_KEY_drive_partition]
        disk_id = partitions_and_disks[drive_partition][_INFO_KEY_disk_id]
        disk_serial_number = disks_and_serial_numbers[disk_id][_INFO_KEY_serial_number]
        disk_description = disks_and_descriptions[disk_id][_INFO_KEY_disk_description]
        discovered_storage_volumes.update(
            {
                drive_letter: {
                    _INFO_KEY_drive_letter: drive_letter,
                    _INFO_KEY_drive_label: drive_label,
                    _INFO_KEY_serial_number: disk_serial_number,
                    _INFO_KEY_disk_description: disk_description,
                }
            }
        )
    logger.debug(discovered_storage_volumes)
    return discovered_storage_volumes


def _format_port_table(qtpy_devices: list[dict[str, str]]) -> list[str]:
    """Return a list of text lines that present a table of the specified qtpy_devices."""
    lines = []
    lines.append("")
    lines.append("      {:5}  {:5}  {:35}".format("Port", "Drive", "QT Py device"))
    lines.append("      {:5}  {:5}  {:35}".format("-" * 5, "-" * 5, "-" * 35))
    for index, qtpy_device in enumerate(qtpy_devices):
        drive_letter = f"{qtpy_device[_INFO_KEY_drive_letter]}\\"
        lines.append(
            f"{index + 1:3}:  {qtpy_device[_INFO_KEY_com_port]:5}  {drive_letter:5}  {qtpy_device[_INFO_KEY_disk_description]:35}"
        )
    lines.append("")
    return lines
