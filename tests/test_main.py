"""Tests for the qtpy_datalogger package entry points."""

import importlib
import runpy
import sys
from contextlib import contextmanager

import pytest


@contextmanager
def program_args(args: list[str] | None = None):  # noqa: ANN201
    """Use the specified args as sys.argv[1:] during a with: statement."""
    old_sys_args = sys.argv
    try:
        args = args if args else []
        new_sys_args = [sys.argv[0], *args]
        sys.argv = new_sys_args
        yield
    finally:
        sys.argv = old_sys_args


def test_import_as_module():  # noqa: ANN201
    """Can Python import it?"""
    assert importlib.import_module("qtpy_datalogger"), "cannot load qtpy_datalogger as a module"


def test_run_as_module(capsys):  # noqa: ANN001, ANN201
    """Can Python invoke the entry point?"""
    with (
        pytest.raises(SystemExit),
        program_args(),
    ):
        runpy.run_module("qtpy_datalogger", run_name="__main__")
    captured = capsys.readouterr()
    assert "Show this message and exit" in captured.out, "main did not print the help message"
