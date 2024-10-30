"""Tests for the qtpy_datalogger package entry points."""

import importlib


def test_import_as_module():  # noqa: ANN201
    """Can Python import it?"""
    assert importlib.import_module("qtpy_datalogger"), "cannot load qtpy_datalogger as a module"
