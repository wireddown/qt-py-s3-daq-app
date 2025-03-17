"""Shared constants and classes."""

import contextlib
import datetime
import enum
import logging
import pathlib
import subprocess
from collections.abc import Generator
from typing import Any, NamedTuple

import toml


class Links(enum.StrEnum):
    """URLs for references and help."""

    Homepage = "https://github.com/wireddown/qt-py-s3-daq-app/wiki"
    New_Bug = "https://github.com/wireddown/qt-py-s3-daq-app/issues/new?template=bug-report.md"
    Board_Support_Matrix = "https://docs.circuitpython.org/en/stable/shared-bindings/support_matrix.html"
    MQTT_Walkthrough = "https://github.com/wireddown/qt-py-s3-daq-app/wiki/Walkthrough-5-MQTT"


class ExitCode(enum.IntEnum):
    """Exit codes for commands."""

    Success = 0
    Discovery_Failure = 41
    COM1_Failure = 42
    Board_Lookup_Failure = 51
    Server_Missing_Failure = 61
    Server_Offline_Failure = 62
    Server_Inaccessible_Failure = 63


class ConnectionTransport(enum.StrEnum):
    """Supported communication types when connecting to a sensor_node."""

    AutoSelect = "Auto select"
    UART_Serial = "UART  (serial)"
    MQTT_WiFi = "MQTT  (WiFi)"


class DetailKey(enum.StrEnum):
    """Names of property details for QTPyDevice instances."""

    com_id = "com_id"
    com_port = "com_port"
    device_description = "device_description"
    disk_id = "disk_id"
    drive_label = "drive_label"
    drive_partition = "drive_partition"
    drive_root = "drive_root"
    ip_address = "ip_address"
    node_id = "node_id"
    python_implementation = "python_implementation"
    serial_number = "serial_number"
    snsr_commit = "snsr_commit"
    snsr_timestamp = "snsr_timestamp"
    snsr_version = "snsr_version"
    system_name = "system_name"


class SnsrPath(enum.StrEnum):
    """Reserved path names for qtpy_datalogger sensor_node bundles."""

    root = "snsr"
    notice = "snsr/notice.toml"


class SnsrNotice(NamedTuple):
    """Represents the contents of the notice.toml file for a sensor_node."""

    comment: str
    version: str
    commit: str
    timestamp: datetime.datetime

    @staticmethod
    def get_package_notice_info(allow_dev_version: bool) -> "SnsrNotice":
        """Detect and generate the information used in the notice.toml file."""
        this_file = pathlib.Path(__file__)
        this_folder = this_file.parent
        notice_toml = this_folder.joinpath("sensor_node", SnsrPath.notice)
        notice_contents = toml.load(notice_toml)
        snsr_notice = SnsrNotice(**notice_contents)
        my_comment = snsr_notice.comment
        my_version = snsr_notice.version
        my_commit = snsr_notice.commit
        my_timestamp = snsr_notice.timestamp

        if __package__:
            # We're installed
            import importlib.metadata

            my_version = importlib.metadata.version(str(__package__))

        # When we're running from the git source, we're in development mode
        this_package_parent = this_file.parent.parent
        in_dev_mode = this_package_parent.name == "src"
        if in_dev_mode:
            if allow_dev_version:
                my_version = f"{my_version}.post0.dev0"

            most_recent_commit_info = ["git", "log", "--max-count=1", "--format=%h %aI"]
            sha_with_timestamp = subprocess.check_output(most_recent_commit_info).strip()  # noqa: S603 -- command is well-formed and user cannot execute arbitrary code
            sha_and_timestamp = sha_with_timestamp.decode("UTF-8").split(" ")
            my_commit = sha_and_timestamp[0]
            my_timestamp = datetime.datetime.fromisoformat(sha_and_timestamp[1])

        my_comment = f"Generated by '{__name__}.py'"
        return SnsrNotice(my_comment, my_version, my_commit, my_timestamp)


@contextlib.contextmanager
def suppress_unless_debug() -> Generator[None, Any, None]:
    """Suppress logger.info() messages unless logging has been set to DEBUG / --verbose."""
    root_logger = logging.getLogger()
    initial_log_level = root_logger.getEffectiveLevel()
    should_suppress = initial_log_level > logging.DEBUG
    if should_suppress:
        try:
            root_logger.setLevel(logging.WARNING)
            yield
        finally:
            root_logger.setLevel(initial_log_level)
    else:
        yield
