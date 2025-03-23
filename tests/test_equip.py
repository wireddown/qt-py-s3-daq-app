"""Acceptance tests for the equip module."""

import logging
import pathlib
import shutil

import pytest
import toml

from qtpy_datalogger import discovery, equip
from qtpy_datalogger.datatypes import ExitCode, SnsrNotice, SnsrPath

from .test_discovery import one_mqtt_qtpy_device


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
    device_notice = tmp_folder.joinpath(SnsrPath.notice)
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
    device_notice = device_path.joinpath(SnsrPath.notice)
    device_toml = equip.SnsrNotice(**toml.load(device_notice))
    return device_toml


def set_device_notice(notice: equip.SnsrNotice, device_path: pathlib.Path) -> None:
    """Set the SnsrNotice information on the sensor_node at the specified path."""
    device_notice = device_path.joinpath(SnsrPath.notice)
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


def test_cannot_install_with_mqtt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Does it exit with error when the device only has MQTT transport?"""
    monkeypatch.setattr(discovery, "discover_qtpy_devices", one_mqtt_qtpy_device)

    with pytest.raises(SystemExit) as excinfo:
        equip.handle_equip(behavior=equip.Behavior.Upgrade, root=None)

    assert excinfo
    exception = excinfo.value
    exception_type = type(exception)
    assert exception_type is SystemExit
    assert exception.code == ExitCode.Equip_Without_USB_Failure


def test_install_new(tmp_path: pathlib.Path) -> None:
    """Does it install when the device isn't a sensor node?"""
    equip.handle_equip(behavior=equip.Behavior.Upgrade, root=tmp_path)

    comparison_results = get_bundle_comparison(tmp_path)
    assert_device_matches_self(comparison_results)
    assert tmp_path.joinpath("lib").exists()


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
    assert tmp_path.joinpath("lib").exists()


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
    assert not tmp_path.joinpath("lib").exists()


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
    assert tmp_path.joinpath("lib").exists()


def test_only_newer_files(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Does it skip circup packages for Behavior.OnlyNewerFiles?"""
    create_test_device_folder(tmp_path)
    newer_files = []

    def override_file_freshness(
        tree1: list[pathlib.Path], tree2: list[pathlib.Path], newer_files: list[pathlib.Path] = newer_files
    ) -> dict[pathlib.Path, str]:
        """Override equip._compare_file_trees() to make the bundle newer than than device."""
        set1 = {path.relative_to(tree1[0]) for path in tree1}
        set2 = {path.relative_to(tree2[0]) for path in tree2}
        shared_in_both = sorted(f for f in set1 & set2 if tree1[0].joinpath(f).is_file())
        equal_file = shared_in_both[0]
        older_file = shared_in_both[1]
        newer_file = shared_in_both[2]
        tree1_file_ages = {
            equal_file: "equal",
            older_file: "older",
            newer_file: "newer",
        }
        newer_files.append(newer_file)
        return tree1_file_ages

    monkeypatch.setattr(equip, "_compare_file_trees", override_file_freshness)

    with caplog.at_level(logging.INFO):
        equip.handle_equip(behavior=equip.Behavior.OnlyNewerFiles, root=tmp_path)

    comparison_results = get_bundle_comparison(tmp_path)
    assert_device_matches_self(comparison_results)
    assert not tmp_path.joinpath("lib").exists()
    updated_file = newer_files[0]
    assert f"Newer: {updated_file!s}" in caplog.text
