"""Command line interface for qtpy_datalogger."""

import logging

import click

from . import discovery, tracelog

logger = logging.getLogger(__name__)


@click.group(invoke_without_command=True)
@click.help_option()
@click.option("-q", "--quiet", is_flag=True, default=False, help="Show only error messages.")
@click.option("-v", "--verbose", is_flag=True, default=False, help="Enable verbose messages.")
@click.version_option()
@click.pass_context
def cli(ctx: click.Context, quiet: bool, verbose: bool) -> None:
    """QT Py datalogger control program."""
    log_level = get_logging_level(quiet, verbose)
    tracelog.initialize(log_level)

    if ctx.invoked_subcommand:
        pass
    else:
        cli(["--help"])


@cli.command()
@click.option(
    "--auto-connect",
    "behavior",
    flag_value=discovery.Behavior.AutoConnect,
    default=True,
    help="Behavior: Find and open a session with a QT Py device. [default]",
)
@click.option(
    "--discover-only",
    "behavior",
    flag_value=discovery.Behavior.DiscoverOnly,
    help="Behavior: List discovered ports and exit.",
)
@click.option("-p", "--port", default="", metavar="COM#", help="COM port to open for communication.")
@click.help_option()
def connect(behavior: str, port: str) -> None:
    """Connect to a serial port."""
    discovery_behavior = discovery.Behavior(behavior)
    discovery.handle_connect(discovery_behavior, port)


@cli.command()
@click.help_option()
def run() -> None:
    """Stub entry point for 'run' command."""
    logger.warning("this is a stub command")


def get_logging_level(quiet: bool, verbose: bool) -> int:
    """Get the logging level for the specified quiet and verbose options."""
    log_level = logging.INFO
    if verbose:
        log_level = logging.DEBUG
    if quiet:
        log_level = logging.ERROR
    return log_level
