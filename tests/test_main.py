"""Tests for the qtpy_datalogger package entry points."""

import importlib
import pathlib
import runpy

import pytest

this_file = pathlib.Path(__file__).resolve()


def test_import_as_module():  # noqa: ANN201
    """Can Python import it?"""
    assert importlib.import_module("qtpy_datalogger"), "cannot load qtpy_datalogger as a module"


def test_run_as_module(capsys):  # noqa: ANN001, ANN201
    """Can Python invoke the entry point?"""
    with pytest.raises(SystemExit):
        runpy.run_module("qtpy_datalogger", run_name="__main__")
    captured = capsys.readouterr()
    assert "Show this message and exit" in captured.out, "main did not print the help message"
