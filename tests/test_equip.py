"""Acceptance tests for the equip module."""

import pathlib
import shutil

import pytest
import toml

from qtpy_datalogger import equip
from qtpy_datalogger.datatypes import ExitCode, SnsrNotice


def create_test_device_folder(tmp_folder: pathlib.Path) -> None:
    """Make tmp_folder into a sensor_node."""
    this_file = pathlib.Path(__file__)
    my_device_folder = this_file.parent.parent.joinpath("src", "qtpy_datalogger", "sensor_node")

    # Copy the files
    shutil.copytree(
        src=my_device_folder,
        dst=tmp_folder,
        ignore=shutil.ignore_patterns("*.pyc", "__pycache__"),
        dirs_exist_ok=True,
    )

    # Stamp the notice file
    device_notice = tmp_folder.joinpath("snsr", "notice.toml")
    source_toml = SnsrNotice.get_package_notice_info(allow_dev_version=True)
    notice_text = toml.dumps(source_toml._asdict())
    device_notice.write_text(notice_text)


def get_bundle_comparison(device_path: pathlib.Path) -> dict[str, equip.SnsrNodeBundle]:
    """Return a dictionary of SnsrNodeBundle entries for the builtin bundle and the test bundle."""
    this_file = pathlib.Path(__file__)
    tests_folder = this_file.parent
    this_sensor_node_root = tests_folder.parent.joinpath("src", "qtpy_datalogger", "sensor_node")
    runtime_bundle = equip._detect_snsr_bundle(this_sensor_node_root)
    device_bundle = equip._detect_snsr_bundle(device_path)
    return {
        "device bundle": device_bundle,
        "runtime bundle": runtime_bundle,
    }


def get_device_notice(device_path: pathlib.Path) -> equip.SnsrNotice:
    """Get the SnsrNotice information from the sensor_node at the specified path."""
    device_notice = device_path.joinpath("snsr", "notice.toml")
    device_toml = equip.SnsrNotice(**toml.load(device_notice))
    return device_toml


def set_device_notice(notice: equip.SnsrNotice, device_path: pathlib.Path) -> None:
    """Set the SnsrNotice information on the sensor_node at the specified path."""
    device_notice = device_path.joinpath("snsr", "notice.toml")
    notice_text = toml.dumps(notice._asdict())
    device_notice.write_text(notice_text)


def assert_device_matches_self(comparison_results: dict[str, equip.SnsrNodeBundle]) -> None:
    """Assert that the version and dependency information matches between the comparison_results."""
    device_bundle = comparison_results["device bundle"]
    runtime_bundle = comparison_results["runtime bundle"]
    assert device_bundle.board_id == runtime_bundle.board_id
    assert device_bundle.circuitpy_dependencies == runtime_bundle.circuitpy_dependencies
    assert device_bundle.circuitpy_version == runtime_bundle.circuitpy_version
    # Skip comparing the file lists
    # Skip confirming that circup installed modules
    assert device_bundle.notice == runtime_bundle.notice


def test_describe(tmp_path: pathlib.Path) -> None:
    """Does it exit successfully after describing?"""
    with pytest.raises(SystemExit) as excinfo:
        equip.handle_equip(behavior=equip.Behavior.Describe, root=tmp_path)

    assert excinfo
    exception = excinfo.value
    exception_type = type(exception)
    assert exception_type is SystemExit
    assert exception.code == ExitCode.Success


def test_compare(tmp_path: pathlib.Path) -> None:
    """Does it exit successfully after comparing?"""
    create_test_device_folder(tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        equip.handle_equip(behavior=equip.Behavior.Compare, root=tmp_path)

    assert excinfo
    exception = excinfo.value
    exception_type = type(exception)
    assert exception_type is SystemExit
    assert exception.code == ExitCode.Success


def test_install_new(tmp_path: pathlib.Path) -> None:
    """Does it install when the device isn't a sensor node?"""
    equip.handle_equip(behavior=equip.Behavior.Upgrade, root=tmp_path)

    comparison_results = get_bundle_comparison(tmp_path)
    assert_device_matches_self(comparison_results)


def test_upgrade(tmp_path: pathlib.Path) -> None:
    """Does it upgrade when the device is an older sensor node?"""
    create_test_device_folder(tmp_path)
    device_toml = get_device_notice(tmp_path)
    downversion_toml = equip.SnsrNotice(
        comment=device_toml.comment,
        version="0.0.1",
        commit=device_toml.commit,
        timestamp=device_toml.timestamp,
    )
    set_device_notice(downversion_toml, tmp_path)

    equip.handle_equip(behavior=equip.Behavior.Upgrade, root=tmp_path)

    comparison_results = get_bundle_comparison(tmp_path)
    assert_device_matches_self(comparison_results)


def test_skip_upgrade(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Does it skip upgrading when the device is a newer version?"""

    def throw_on_call(behavior: equip.Behavior, comparison_information: dict[str, equip.SnsrNodeBundle]) -> None:
        message = "qtpy_datalogger incorrectly tried to upgrade"
        raise RuntimeError(message)

    monkeypatch.setattr(equip, "_equip_snsr_node", throw_on_call)
    create_test_device_folder(tmp_path)
    device_toml = get_device_notice(tmp_path)
    upversion_toml = equip.SnsrNotice(
        comment=device_toml.comment,
        version="100.0.0",
        commit=device_toml.commit,
        timestamp=device_toml.timestamp,
    )
    set_device_notice(upversion_toml, tmp_path)

    equip.handle_equip(behavior=equip.Behavior.Upgrade, root=tmp_path)


def test_force_install(tmp_path: pathlib.Path) -> None:
    """Does it install when forced?"""
    create_test_device_folder(tmp_path)
    device_toml = get_device_notice(tmp_path)
    upversion_toml = equip.SnsrNotice(
        comment=device_toml.comment,
        version="100.0.0",
        commit=device_toml.commit,
        timestamp=device_toml.timestamp,
    )
    set_device_notice(upversion_toml, tmp_path)

    equip.handle_equip(behavior=equip.Behavior.Force, root=tmp_path)

    comparison_results = get_bundle_comparison(tmp_path)
    assert_device_matches_self(comparison_results)
