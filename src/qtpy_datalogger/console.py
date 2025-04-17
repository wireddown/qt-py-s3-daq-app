"""Command line interface for qtpy_datalogger."""

import logging
import pathlib

import click

from . import apps, discovery, tracelog
from . import equip as _equip
from . import server as _server
from .datatypes import Default, Links

logger = logging.getLogger(__name__)


DEFAULT_HELP_URL = Links.Homepage


@click.group(
    invoke_without_command=True,
    epilog=f"Help and home page: {DEFAULT_HELP_URL}",
)
@click.option(
    "--generate-notice",
    type=click.Path(dir_okay=False, writable=True, resolve_path=True, path_type=pathlib.Path),
    metavar="PATH",
    help="Generate notice.toml file at PATH.",
)
@click.option(
    "--list-builtin-modules",
    nargs=2,
    type=(str, click.Path(dir_okay=False, writable=True, resolve_path=True, path_type=pathlib.Path)),
    metavar="BOARD_ID PATH",
    help="Generate modules.toml file at PATH, where BOARD_ID is a board name from https://docs.circuitpython.org/en/stable/shared-bindings/support_matrix.html",
)
@click.help_option()
@click.option("-q", "--quiet", is_flag=True, default=False, help="Show only error messages.")
@click.option("-v", "--verbose", is_flag=True, default=False, help="Enable verbose messages.")
@click.version_option()
@click.pass_context
def cli(
    ctx: click.Context,
    generate_notice: pathlib.Path,
    list_builtin_modules: tuple[str, pathlib.Path],
    quiet: bool,
    verbose: bool,
) -> None:
    """QT Py datalogger control program."""
    log_level = get_logging_level(quiet, verbose)
    tracelog.initialize(log_level)
    logger.debug(f"generate_notice: '{generate_notice}' list_builtin_modules: '{list_builtin_modules}'")

    if ctx.invoked_subcommand:
        pass
    elif generate_notice:
        if generate_notice.exists():
            logger.warning(f"Overwriting file '{generate_notice!s}'")
        notice_contents = _equip._handle_generate_notice()
        if generate_notice.name == "-":
            print(notice_contents)  # noqa: T201 -- user asked for output on stdout so use print
        else:
            logger.info(f"Writing '{generate_notice!s}' with contents\n{notice_contents}")
            generate_notice.write_text(notice_contents)
    elif list_builtin_modules:
        board_id = list_builtin_modules[0]
        output_path = list_builtin_modules[1]
        if output_path.exists():
            logger.warning(f"Overwriting file '{output_path!s}'")
        board_builtin_module_contents = _equip._handle_list_builtin_modules(board_id)
        if output_path.name == "-":
            print(board_builtin_module_contents)  # noqa: T201 -- user asked for output on stdout so use print
        else:
            logger.info(f"Writing '{output_path!s}' with contents\n{board_builtin_module_contents}")
            output_path.write_text(board_builtin_module_contents)
    else:
        cli(["--help"])


@cli.command(
    epilog=f"Help and home page: {DEFAULT_HELP_URL}",
    short_help="Connect to a serial port or MQTT sensor_node.",
)
@click.option(
    "--auto-connect",
    "behavior",
    flag_value=discovery.Behavior.AutoConnect,
    default=True,
    help="Behavior: [default] Find and open a session with a QT Py device.",
)
@click.option(
    "--discover-only",
    "behavior",
    flag_value=discovery.Behavior.DiscoverOnly,
    help="Behavior: List discovered devices and exit.",
)
@click.option("-n", "--group", default=Default.MqttGroup, metavar="GROUP-ID", help=f"MQTT group to use. Default: {Default.MqttGroup}")
@click.option("-n", "--node", default="", metavar="NODE-ID", help="MQTT node to use for connection.")
@click.option("-p", "--port", default="", metavar="COM#", help="Serial COM port to use for connection.")
@click.help_option()
def connect(behavior: str, group: str, node: str, port: str) -> None:
    """Connect to a serial port, preferring a CircuitPython device, or to an MQTT sensor_node on the network."""
    discovery_behavior = discovery.Behavior(behavior)
    discovery.handle_connect(discovery_behavior, group, node, port)


@cli.command(epilog=f"The default app is {apps.Catalog.default_app.name}\n\nHelp and home page: {DEFAULT_HELP_URL}")
@click.option(
    "--app",
    "behavior",
    flag_value=apps.Behavior.App,
    default=True,
    help="Behavior: [default] Run the specified or default app.",
)
@click.option(
    "--list",
    "behavior",
    flag_value=apps.Behavior.List,
    help="Behavior: List available apps and exit.",
)
@click.option(
    "--module",
    "behavior",
    flag_value=apps.Behavior.Module,
    help="Behavior: Run the specified MODULE as a custom app.",
)
@click.argument(
    "app_name",
    type=str,
    default=apps.Catalog.default_app.name,
)
@click.help_option()
def run(behavior: str, app_name: str) -> None:
    """Run the APP_NAME app for QT Py datalogger."""
    run_behavior = apps.Behavior(behavior)
    apps.handle_run(run_behavior, app_name)


@cli.command(epilog=f"Help and home page: {DEFAULT_HELP_URL}")
@click.option(
    "--upgrade",
    "behavior",
    flag_value=_equip.Behavior.Upgrade,
    default=True,
    help="Behavior: [default] Install the sensor_node bundle from this package onto a new device or upgrade an existing version.",
)
@click.option(
    "--compare",
    "behavior",
    flag_value=_equip.Behavior.Compare,
    help="Behavior: Show the version and date information between this package and the sensor_node bundle on the device and exit.",
)
@click.option(
    "--describe",
    "behavior",
    flag_value=_equip.Behavior.Describe,
    help="Behavior: Show the contents and dependencies of the sensor_node bundle in this package.",
)
@click.option(
    "--force",
    "behavior",
    flag_value=_equip.Behavior.Force,
    help="Behavior: Force the installation of the sensor_node bundle on the device.",
)
@click.option(
    "--newer-files-only",
    "behavior",
    flag_value=_equip.Behavior.NewerFilesOnly,
    help="Behavior: Only update sensor_node bundle files that are newer, skip installing CircuitPython support libraries.",
)
@click.option(
    "-r",
    "--root",
    type=click.Path(exists=True, file_okay=False, writable=True, resolve_path=True, path_type=pathlib.Path),
    metavar="FOLDER",
    help="Use FOLDER as the root.",
)
@click.help_option()
def equip(behavior: str, root: pathlib.Path | None) -> None:
    """Install the QT Py Sensor Node runtime on a CircuitPython device."""
    equip_behavior = _equip.Behavior(behavior)
    _equip.handle_equip(equip_behavior, root)


@cli.command(epilog=f"Detailed help online\n\n{Links.MQTT_Walkthrough}")
@click.option(
    "--describe",
    "behavior",
    flag_value=_server.Behavior.Describe,
    default=True,
    help="Behavior: [default] Show the current status of the service.",
)
@click.option(
    "--observe",
    "behavior",
    flag_value=_server.Behavior.Observe,
    help="Behavior: Monitor the service and print published messages, Ctrl-C to quit.",
)
@click.option(
    "--restart",
    "behavior",
    flag_value=_server.Behavior.Restart,
    help="Behavior: Restart the service, requires Administrator privileges.",
)
@click.option(
    "--publish",
    nargs=2,
    type=(str, str),
    metavar="TOPIC MESSAGE",
    help="Send a MESSAGE to the service on the specified TOPIC.",
)
@click.help_option()
def server(behavior: str, publish: tuple[str, str]) -> None:
    """Query and control the MQTT server."""
    server_behavior = _server.Behavior(behavior)
    _server.handle_server(server_behavior, publish)


def get_logging_level(quiet: bool, verbose: bool) -> int:
    """Get the logging level for the specified quiet and verbose options."""
    log_level = logging.INFO
    if verbose:
        log_level = logging.DEBUG
    if quiet:
        log_level = logging.ERROR
    return log_level
