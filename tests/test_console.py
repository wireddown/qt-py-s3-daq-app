"""Tests for the qtpy_datalogger command line interface."""

import logging
import pathlib

import click
import pytest
from click.testing import CliRunner

from qtpy_datalogger import console


def test_console() -> None:
    """Does it invoke the base command group?"""
    runner = CliRunner()
    result = runner.invoke(console.cli)
    assert result.exit_code == 0
    assert "Show this message and exit." in result.output


def test_subcommand() -> None:
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
def test_verbosity_truth_table(quiet: bool, verbose: bool, expected_log_level: int, assert_message: str) -> None:
    """Validate all combinations of --quiet and --verbose."""
    log_level = console.get_logging_level(quiet, verbose)
    assert log_level == expected_log_level, assert_message


def test_generate_notice_option(tmp_path: pathlib.Path) -> None:
    """Does it correctly generate the notice.toml text?"""
    output_file = tmp_path.joinpath("test-notice.toml")
    runner = CliRunner()
    result = runner.invoke(
        console.cli,
        args=["--generate-notice", str(output_file)],
    )

    assert result.exit_code == 0
    assert output_file.exists()
    all_lines = output_file.read_text().splitlines()
    assert all_lines[0] == "comment = \"Generated by 'qtpy_datalogger.datatypes.py'\""
    assert all_lines[-1].startswith("timestamp = ")


def test_list_builtin_modules(tmp_path: pathlib.Path) -> None:
    """Does it correctly generate the builtin module text?"""
    output_file = tmp_path.joinpath("test-modules.toml")
    runner = CliRunner()
    result = runner.invoke(
        console.cli,
        args=["--list-builtin-modules", "Adafruit QT Py ESP32-S3 no psram", str(output_file)],
    )

    assert result.exit_code == 0
    assert output_file.exists()
    all_lines = output_file.read_text().splitlines()
    assert all_lines[0].startswith('reference = "Adafruit CircuitPython')
    assert all_lines[-1].startswith('"Adafruit QT Py ESP32-S3 no psram" = [ "_asyncio",')
