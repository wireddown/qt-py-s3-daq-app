"""Command line interface for qtpy_datalogger."""

import logging

import click

from . import tracelog

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
@click.help_option()
def run() -> None:
    """Stub entry point for 'run' subcommand."""
    logger.warning("this is a stub command")


def get_logging_level(quiet: bool, verbose: bool) -> int:
    """Get the logging level for the specified quiet and verbose options."""
    log_level = logging.INFO
    if quiet:
        log_level = logging.ERROR
    if verbose:
        log_level = logging.DEBUG
    return log_level
