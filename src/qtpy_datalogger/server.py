"""Code that is under development and experimentation."""

import logging
import pathlib
import subprocess
import sys
import textwrap
from enum import StrEnum

logger = logging.getLogger(__name__)


class Behavior(StrEnum):
    """Supported behaviors for server interaction."""

    Describe = "Describe"
    Observe = "Observe"


def handle_server(behavior: Behavior) -> None:
    """Handle the command for server."""
    mqtt_broker_information = _query_mqtt_broker_information_from_wmi()
    if not mqtt_broker_information:
        logger.warning("MQTT broker is not a registered service. Is it installed?")
        logger.warning("Visit 'https://mosquitto.org/download/' to download it.")
        return

    if behavior == Behavior.Describe:
        message_lines = textwrap.dedent(
            f"""
            {mqtt_broker_information[0]}
            {"State":>12}  {mqtt_broker_information[1]}
            {"Status":>12}  {mqtt_broker_information[2]}
            {"Startup":>12}  {mqtt_broker_information[3]}
            {"Executable":>12}  {mqtt_broker_information[4]}
            """
        ).splitlines()
        _ = [logger.info(line) for line in message_lines]
        return

    if behavior == Behavior.Observe:
        mqtt_home = mqtt_broker_information[4].parent
        subscribe_exe = mqtt_home.joinpath("mosquitto_sub.exe")
        subscribe_command = [
            str(subscribe_exe),
            "--id",
            "qtpy-datalogger",
            "--topic",
            "$SYS/#",
            "--unsubscribe",
            "$SYS/#",
            "--topic",
            "qtpy/#",
            "-F",
            "%j",
        ]
        logger.info(f"Subscribing with '{' '.join(subscribe_command)}'")
        logger.info("Use Ctrl-C to quit")
        result = subprocess.run(subscribe_command, stdout=sys.stdout, stderr=subprocess.STDOUT, check=False)  # noqa: S603 -- command is well-formed and user cannot execute arbitrary code


def _query_mqtt_broker_information_from_wmi():
    from wmi import WMI

    host_pc = WMI()
    matching_services = sorted(host_pc.Win32_Service(Name="mosquitto"))
    if matching_services:
        mqtt_broker = matching_services[0]
        broker_description = mqtt_broker.Description
        broker_state = mqtt_broker.State
        broker_status = mqtt_broker.Status
        broker_startup = mqtt_broker.StartMode
        broker_executable = _get_service_executable(mqtt_broker.PathName)
        return (broker_description, broker_state, broker_status, broker_startup, broker_executable)
    return None


def _get_service_executable(wmi_pathname: str) -> pathlib.Path:
    # Paths that have spaces use double-quotes, typically for the "Program Files" segment
    #   No-space  'C:\\WINDOWS\\System32\\svchost.exe -k LocalSystemNetworkRestricted -p'
    #   With-pace '"C:\\Program Files\\mosquitto\\mosquitto.exe" run'
    path_parts = wmi_pathname.split('"')
    executable_path = path_parts[0].split(" ")[0] if path_parts[0] else path_parts[1]
    return pathlib.Path(executable_path)
