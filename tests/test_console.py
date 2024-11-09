"""Tests for the qtpy_datalogger command line interface."""

import logging

import click
import pytest
from click.testing import CliRunner

from qtpy_datalogger import console


def test_console():  # noqa: ANN201
    """Does it invoke the base command group?"""
    runner = CliRunner()
    result = runner.invoke(console.cli)
    assert result.exit_code == 0
    assert "Show this message and exit." in result.output


def test_subcommand():  # noqa: ANN201
    """Does it invoke a subcommand?"""
    command_was_invoked_message = "subcommand_name invoked"

    @click.command("subcommand_name")
    def subcommand_name() -> None:
        print(command_was_invoked_message)  # noqa: T201 Allow print for this test

    console.cli.add_command(subcommand_name)

    runner = CliRunner()
    result = runner.invoke(
        console.cli,
        args=["subcommand_name"],
    )
    assert result.exit_code == 0
    assert result.stdout.strip() == command_was_invoked_message


@pytest.mark.parametrize(
    ("quiet", "verbose", "expected_log_level", "assert_message"),
    [
        (False, False, logging.INFO, "Default logging level should be 'logging.INFO'"),
        (True, False, logging.ERROR, "Quiet logging level should be 'logging.ERROR'"),
        (False, True, logging.DEBUG, "Verbose logging level should be 'logging.DEBUG'"),
        (True, True, logging.ERROR, "--quiet should override --verbose"),
    ],
)
def test_verbosity_truth_table(quiet, verbose, expected_log_level, assert_message):  # noqa: ANN001 ANN201
    """Validate all combinations of --quiet and --verbose."""
    log_level = console.get_logging_level(quiet, verbose)
    assert log_level == expected_log_level, assert_message
