"""Tests for the qtpy_datalogger package entry points."""

import importlib
import pathlib
import runpy

this_file = pathlib.Path(__file__).resolve()


def test_import_as_module():  # noqa: ANN201
    """Can Python import it?"""
    assert importlib.import_module("qtpy_datalogger"), "cannot load qtpy_datalogger as a module"


def test_run_as_module(capsys):  # noqa: ANN001, ANN201
    """Can Python invoke the entry point?"""
    runpy.run_module("qtpy_datalogger", run_name="__main__")
    captured = capsys.readouterr()
    expected_file = this_file.parent.parent / "src" / "qtpy_datalogger" / "__main__.py"
    printed_file = pathlib.Path(captured.out.strip())
    assert printed_file == expected_file, "main did not print its file path"
