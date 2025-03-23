"""Functions to interact with the MQTT broker that handles the network communication."""

import logging
import pathlib
import re
import subprocess
import sys
import time
from enum import StrEnum
from typing import Callable, NamedTuple

from .datatypes import ExitCode, Links

logger = logging.getLogger(__name__)


class Behavior(StrEnum):
    """Supported behaviors for server interaction."""

    Describe = "Describe"
    Observe = "Observe"
    Restart = "Restart"


class BrokerOption(NamedTuple):
    """Represents an option name and value for an MQTT broker."""

    name: str
    value: str


class FirewallRule(NamedTuple):
    """Represents the settings for a firewall rule."""

    name: str
    enabled: str
    local_port: str
    remote_ip: str
    action: str


class MqttBrokerInformation(NamedTuple):
    """Holds details about the MQTT broker's service, configuration, and firewall status."""

    description: str
    server_runmode: str
    server_health: str
    server_startmode: str
    server_executable: pathlib.Path
    server_configuration: list[BrokerOption]
    firewall_rules: list[FirewallRule]

    @property
    def server_options(self) -> dict[str, str]:
        """Return server_configuration as a dictionary with (name, value) entries."""
        options = {option.name: option.value for option in self.server_configuration}
        return options

    @property
    def has_enabled_firewall_rules(self) -> bool:
        """Return True if the system has firewall rules enabled for the MQTT broker service."""
        return any(rule.enabled == "Yes" for rule in self.firewall_rules)

    @property
    def has_allowed_firewall_rules(self) -> bool:
        """Return True if the system's firewall rules for the MQTT broker service allow external connections."""
        return any(rule.action == "Allow" for rule in self.firewall_rules)


def handle_server(behavior: Behavior, publish: tuple[str, str]) -> None:
    """Handle the command for server."""
    mqtt_broker_information = _query_mqtt_broker_information_from_wmi()
    if not mqtt_broker_information:
        logger.error("MQTT broker is not a registered service. Is it installed?")
        logger.error("  Visit 'https://mosquitto.org/download/' to download it")
        raise SystemExit(ExitCode.Server_Missing_Failure)

    message_lines_with_level = _analyze_mqtt_broker(mqtt_broker_information)
    did_warn = False
    logger.info("")
    for line_and_level in message_lines_with_level:
        line = line_and_level[0]
        level = line_and_level[1]
        did_warn |= level >= logging.WARNING
        logger.log(level, line)
    logger.info("")

    if behavior == Behavior.Describe and did_warn:
        logger.error("MQTT server is not configured to support sensor nodes!")
        logger.error(f"  Visit {Links.MQTT_Walkthrough} to learn more")
        raise SystemExit(ExitCode.Server_Inaccessible_Failure)

    if behavior == Behavior.Restart:
        did_restart = _restart_mqtt_broker_with_wmi(mqtt_broker_information)
        if did_restart:
            raise SystemExit(ExitCode.Success)
        logger.error("Could not restart the MQTT broker service!")
        raise SystemExit(ExitCode.Server_Offline_Failure)

    if behavior == Behavior.Observe:
        mqtt_broker_runmode = mqtt_broker_information.server_runmode
        if mqtt_broker_runmode != "Running":
            logger.warning(f"Cannot observe: MQTT broker state is '{mqtt_broker_runmode}'")
            logger.info("Attempting to restart the service")
            did_restart = _restart_mqtt_broker_with_wmi(mqtt_broker_information)
            if not did_restart:
                logger.error("Could not restart the MQTT broker service!")
                raise SystemExit(ExitCode.Server_Offline_Failure)

        subscribe_exe = mqtt_broker_information.server_executable.with_name("mosquitto_sub.exe")
        subscribe_command = [
            str(subscribe_exe),
            "--id",
            "qtpy-datalogger-sub",
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
        _ = subprocess.run(subscribe_command, stdout=sys.stdout, stderr=subprocess.STDOUT, check=False)  # noqa: S603 -- command is well-formed and user cannot execute arbitrary code

    if publish:
        topic = publish[0]
        message = publish[1]
        publish_exe = mqtt_broker_information.server_executable.with_name("mosquitto_pub.exe")
        publish_command = [
            str(publish_exe),
            "--id",
            "qtpy-datalogger-pub",
            "--topic",
            f"{topic}",
            "--message",
            f"{message}",
        ]
        logger.info(f"Publishing with '{' '.join(publish_command)}'")
        result = subprocess.run(publish_command, stdout=sys.stdout, stderr=subprocess.STDOUT, check=False)  # noqa: S603 -- command is well-formed and user cannot execute arbitrary code
        if result.returncode != 0:
            logger.warning(f"Received exit code '{result.returncode}' from '{publish_exe.name}'")
            _ = [logger.warning(line) for line in result.stderr.decode("UTF-8")]
            raise SystemExit(result.returncode)
        raise SystemExit(ExitCode.Success)


def _analyze_mqtt_broker(broker_information: MqttBrokerInformation) -> list[tuple[str, int]]:
    """Analyze the availability and accessibility of the MQTT broker service."""
    running_line = f"{'State':>12}  {broker_information.server_runmode}"
    running_level = logging.INFO
    if broker_information.server_runmode != "Running":
        logger.warning("MQTT broker is not running!")
        logger.warning("  Try 'qtpy-datalogger server --restart'")
        running_level = logging.WARNING

    server_level = logging.INFO
    server_options = broker_information.server_options
    if not server_options:
        mqtt_conf_message = "Unconfigured"
        server_level = logging.WARNING
        logger.warning("MQTT broker is not configured to listen for connections!")
        logger.warning("  Update the configuration file to listen on port 1883 and restart the service")
    else:
        mqtt_conf_message = f"Listening on port {server_options['listener']}"
    server_line = f"{'Server':>12}  {mqtt_conf_message}"

    # Evaluate firewall rules by increasing severity
    firewall_message = "Open on port 1883"
    firewall_level = logging.INFO
    if not broker_information.has_allowed_firewall_rules:
        firewall_message = "Blocked"
        firewall_level = logging.WARNING
        logger.warning("All firewall rules for MQTT connections do not allow connections!")
        logger.warning("  Try 'wf.msc' to allow with Administrator privileges")
    if not broker_information.has_enabled_firewall_rules:
        firewall_message = "Disabled"
        firewall_level = logging.WARNING
        logger.warning("All firewall rules for MQTT connections are disabled!")
        logger.warning("  Try 'wf.msc' to enable with Administrator privileges")
    if not broker_information.firewall_rules:
        firewall_message = "Unconfigured"
        firewall_level = logging.WARNING
        logger.warning("This computer's firewall has no rules that support MQTT connections!")
        logger.warning("  Run the following in a terminal with Administrator privileges")
        firewall_rule_command = _get_firewall_rule_for_windows()
        logger.info("")
        logger.info(firewall_rule_command)
        logger.info("")
    firewall_line = f"{'Firewall':>12}  {firewall_message}"

    broker_analysis = [
        (broker_information.description, logging.INFO),
        (running_line, running_level),
        (f"{'Status':>12}  {broker_information.server_health}", logging.INFO),
        (f"{'Startup':>12}  {broker_information.server_startmode}", logging.INFO),
        (f"{'Executable':>12}  {broker_information.server_executable!s}", logging.INFO),
        (server_line, server_level),
        (firewall_line, firewall_level),
    ]
    return broker_analysis


def _query_mqtt_broker_information_from_wmi() -> MqttBrokerInformation | None:
    """Query the system for information about the MQTT broker service, configuration, and relevant firewall rules."""
    from wmi import WMI

    host_pc = WMI()
    matching_services = sorted(host_pc.Win32_Service(Name="mosquitto"))
    if not matching_services:
        return None

    mqtt_broker = matching_services[0]

    # Paths that have spaces use double-quotes, typically for the "Program Files" segment
    #   No-space  'C:\\WINDOWS\\System32\\svchost.exe -k LocalSystemNetworkRestricted -p'
    #   With-space '"C:\\Program Files\\mosquitto\\mosquitto.exe" run'
    path_parts = mqtt_broker.PathName.split('"')
    broker_executable = path_parts[0].split(" ")[0] if path_parts[0] else path_parts[1]
    broker_executable_path = pathlib.Path(broker_executable)

    server_config = _query_mqtt_broker_configuration_from_file(broker_executable_path)
    matching_port_rules = _query_firewall_port_rules_from_netsh()

    broker_information = MqttBrokerInformation(
        description=mqtt_broker.Description,
        server_runmode=mqtt_broker.State,
        server_health=mqtt_broker.Status,
        server_startmode=mqtt_broker.StartMode,
        server_executable=broker_executable_path,
        server_configuration=server_config,
        firewall_rules=matching_port_rules,
    )
    logger.debug(broker_information)
    return broker_information


def _restart_mqtt_broker_with_wmi(broker_information: MqttBrokerInformation) -> bool:
    """Stop and restart the mosquitto MQTT service and return True if the server changed states."""
    from wmi import WMI

    did_anything = False
    host_pc = WMI()
    matching_services = sorted(host_pc.Win32_Service(Name="mosquitto"))
    if not matching_services:
        return did_anything

    def _call_service_control_function(
        service_control_function: Callable,
        active_runmode: str,
        desired_runmode: str,
    ) -> str:
        """Call and handle exit codes from service_control_function() and return the updated runmode of the service."""
        service_runmode = active_runmode
        result = service_control_function()
        return_code = result[0]
        administrator_required_error = 2
        if return_code == 0:
            service_runmode = desired_runmode
            time.sleep(0.25)  # Let the service settle
        elif return_code == administrator_required_error:
            logger.warning("Cannot control any services from a user account!")
            logger.warning("  Try 'services.msc' to use Administrator privileges")
        else:
            logger.warning(
                f"Received exit code '{return_code}' from 'Win32_Service.{str(service_control_function.__doc__).split(' ')[0]}()'"
            )
        return service_runmode

    mqtt_broker = matching_services[0]
    mqtt_broker_runmode = broker_information.server_runmode
    logger.info(f"Restarting '{mqtt_broker.DisplayName}'")

    if mqtt_broker_runmode != "Stopped":
        logger.info(f"  Stopping '{mqtt_broker.DisplayName}'")
        mqtt_broker_runmode = _call_service_control_function(mqtt_broker.StopService, mqtt_broker_runmode, "Stopped")
        if mqtt_broker_runmode != "Stopped":
            return did_anything
        logger.info("  Stopped")
        did_anything = True
    else:
        logger.info("  Service already stopped")

    if mqtt_broker_runmode != "Running":
        logger.info(f"  Starting '{mqtt_broker.DisplayName}'")
        mqtt_broker_runmode = _call_service_control_function(mqtt_broker.StartService, mqtt_broker_runmode, "Running")
        if mqtt_broker_runmode != "Running":
            return did_anything
        logger.info("  Started")
        did_anything = True
    else:
        logger.info("  Service already started")

    return did_anything


def _query_mqtt_broker_configuration_from_file(broker_executable: pathlib.Path) -> list[BrokerOption]:
    """Read and parse a subset of options from the MQTT server's configuration file."""
    broker_configuration = broker_executable.with_name("mosquitto.conf")
    if not broker_configuration.exists():
        logger.warning("Could not read MQTT configuration file")
        logger.warning(f"  The file '{broker_configuration!s}' does not exist")
        return []

    # From the server configuration file, parse interesting options
    configuration_lines = broker_configuration.read_text().splitlines()
    interesting_options = [
        "listener",
        "allow_anonymous",
    ]
    found_options = []
    for line in configuration_lines:
        if any(line.startswith(option) for option in interesting_options):
            name_value_pair = [cell.strip() for cell in line.split(" ")]
            option = BrokerOption(
                name=name_value_pair[0],
                value=name_value_pair[1],
            )
            found_options.append(option)
            logger.debug(line)
    return found_options


def _query_firewall_port_rules_from_netsh(port_to_match: int = 1883) -> list[FirewallRule]:
    """Query and parse firewall rules on the system that control MQTT broker port 1883."""
    get_all_firewall_rules = [
        "netsh",
        "advfirewall",
        "firewall",
        "show",
        "rule",
        "name=all",
    ]
    result = subprocess.run(get_all_firewall_rules, capture_output=True, check=False)  # noqa: S603 -- command is well-formed and user cannot execute arbitrary code
    if result.returncode != 0:
        logger.warning("Could not query for firewall settings")
        _ = [logger.warning(line) for line in result.stderr.decode("UTF-8")]
        return []

    # The output is very large, so quickly identify the LocalPort lines with a regex match
    line_with_port_pattern = re.compile(rf"LocalPort:\s+{port_to_match}")
    full_report = result.stdout.decode("UTF-8").splitlines()
    matching_port_indexes = []
    for index, line in enumerate(full_report):
        if line_with_port_pattern.match(line):
            matching_port_indexes.append(index)

    # Using the LocalPort line as a reference point, select the preceding and following lines that describe the entire rule
    matching_rule_line_groups = []
    for matching_port_index in matching_port_indexes:
        first_line = matching_port_index - 9
        last_line = matching_port_index + 4
        rule_lines = full_report[first_line:last_line]
        _ = rule_lines.pop(1)  # Remove the "-------" title-details separator line
        matching_rule_line_groups.append(rule_lines)

    # From each rule, parse interesting fields that describe the firewall rule
    rules = []
    interesting_fields = [
        "Rule Name",
        "Enabled",
        "LocalPort",
        "RemoteIP",
        "Action",
    ]
    for rule_line_group in matching_rule_line_groups:
        rule_info = {}
        for line in rule_line_group:
            logger.debug(line)
            if any(line.startswith(field) for field in interesting_fields):
                name_value_pair = [cell.strip() for cell in line.split(":")]
                field_name = name_value_pair[0]
                field_value = name_value_pair[1]
                rule_info[field_name] = field_value
        logger.debug("")
        rule = FirewallRule(
            name=rule_info["Rule Name"],
            enabled=rule_info["Enabled"],
            local_port=rule_info["LocalPort"],
            remote_ip=rule_info["RemoteIP"],
            action=rule_info["Action"],
        )
        rules.append(rule)

    _ = [logger.debug(rule) for rule in rules]
    return rules


def _get_firewall_rule_for_windows() -> str:
    """Return the netsh command that adds a firewall rule to allow inbound connections on port 1883 from the local subnet."""
    command_as_list = [
        "netsh",
        "advfirewall",
        "firewall",
        "add",
        "rule",
        "name='Mosquitto MQTT: allow inbound on port 1883 from local subnet'",
        "program='%ProgramFiles%\\mosquitto\\mosquitto.exe'",
        "dir=in",
        "action=allow",
        "service=any",
        "description='This rule allows MQTT clients on the local subnet to connect to this host'",
        "profile=private",
        "localip=any",
        "remoteip=localsubnet",
        "localport=1883",
        "remoteport=any",
        "protocol=tcp",
        "interfacetype=any",
    ]
    return " ".join(command_as_list)
