"""Acceptance tests for the shared data classes."""

import json
import pathlib

import pytest

import qtpy_datalogger.sensor_node.snsr.node.classes as node_classes


@pytest.fixture
def reference_descriptor_payload() -> str:
    """Return a JSON string holding a reference DescriptorPayload."""
    return """
        {
            "descriptor": {
                "node_id": "host-12ab34cd56ef-1213",
                "serial_number": "12ab34cd56ef",
                "hardware_name": "AMD64",
                "system_name": "Windows-10.0.22631",
                "python_implementation": "CPython-3.11.9",
                "ip_address": "192.168.0.0",
                "notice": {
                    "comment": "Generated by 'qtpy_datalogger.equip.py'",
                    "version": "0.1.0",
                    "commit": "9272dd3",
                    "timestamp": "2025-03-12T22:10:22-07:00"
                }
            },
            "sender": {
                "descriptor_topic": "qtpy/v1/centrifuge/host-12ab34cd56ef-1213/$DESCRIPTOR",
                "sent_at": "2025-03-14T17:15:25-07:00",
                "status": {
                    "used_memory": "1889785610",
                    "free_memory": "15290083574",
                    "cpu_temperature": "42.0"
                }
            }
        }
    """.strip()


@pytest.fixture
def reference_identify_payload() -> str:
    """Return a JSON string holding a reference ActionPayload for the identify command."""
    return """
        {
            "action": {
                "command": "identify",
                "parameters": {},
                "message_id": "identify-1"
            },
            "sender": {
                "descriptor_topic": "qtpy/v1/centrifuge/host-12ab34cd56ef-1213/$DESCRIPTOR",
                "sent_at": "2025-03-14T17:15:25-07:00",
                "status": {
                    "used_memory": "1889785610",
                    "free_memory": "15290083574",
                    "cpu_temperature": "42.0"
                }
            }
        }
    """.strip()


def test_descriptor_deserialize(reference_descriptor_payload: str) -> None:
    """Does it correctly parse a JSON string for a DescriptorPayload?"""
    json_object = json.loads(reference_descriptor_payload)
    descriptor = node_classes.DescriptorPayload.from_dict(json_object)
    assert descriptor


def test_descriptor_serialize() -> None:
    """Does it correctly create a JSON string from a DescriptorPayload?"""
    descriptor = node_classes.DescriptorPayload(
        descriptor=node_classes.DescriptorInformation(
            node_id="test_node",
            serial_number="test_serial_number",
            hardware_name="test_hardware_name",
            system_name="test_system_name",
            python_implementation="test_python_implementation",
            ip_address="test_ip_address",
            notice=node_classes.NoticeInformation(
                comment="test_notice_comment",
                version="test_notice_version",
                commit="test_notice_commit",
                timestamp="test_notice_timestamp",
            ),
        ),
        sender=node_classes.SenderInformation(
            descriptor_topic="test_descriptor_topic",
            sent_at="test_sender_sent_at",
            status=node_classes.StatusInformation(
                used_memory="test_status_used_memory",
                free_memory="test_status_free_memory",
                cpu_temperature="test_status_cpu_temperature",
            ),
        ),
    )
    json_string = json.dumps(descriptor.as_dict())
    assert json_string


def test_action_deserialize(reference_identify_payload: str) -> None:
    """Does it correctly parse a JSON string for an ActionPayload?"""
    json_object = json.loads(reference_identify_payload)
    action = node_classes.ActionPayload.from_dict(json_object)
    assert action


def test_action_serialize() -> None:
    """Does it correctly create a JSON string from an ActionPayload?"""
    identify_action = node_classes.ActionPayload(
        action=node_classes.ActionInformation(
            command="identify",
            parameters={},
            message_id="identify-1",
        ),
        sender=node_classes.SenderInformation(
            descriptor_topic="test_descriptor_topic",
            sent_at="test_sender_sent_at",
            status=node_classes.StatusInformation(
                used_memory="test_status_used_memory",
                free_memory="test_status_free_memory",
                cpu_temperature="test_status_cpu_temperature",
            ),
        ),
    )
    json_string = json.dumps(identify_action.as_dict())
    assert json_string


def test_node_build_descriptor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Does the node-side usage match the shared classes' definitions?"""
    # Support looking up sensor_node modules from the node's perspective (where 'snsr' is a package)
    sensor_node_root = pathlib.Path(__file__).parent.parent.joinpath("src", "qtpy_datalogger", "sensor_node")
    monkeypatch.syspath_prepend(sensor_node_root)

    from qtpy_datalogger.datatypes import SnsrNotice
    from qtpy_datalogger.sensor_node.snsr.core import get_new_descriptor as node_build_descriptor

    snsr_notice = SnsrNotice.get_package_notice_info(allow_dev_version=True)
    descriptor = node_build_descriptor(
        role="node",
        serial_number="ab12cd343ef56",
        pid=0,
        hardware_name="test_hardware_name",
        micropython_base="3.4.0",
        python_implementation="circuitpython-9.2.1",
        ip_address="172.16.0.0",
        notice=node_classes.NoticeInformation(
            comment=snsr_notice.comment,
            version=snsr_notice.version,
            commit=snsr_notice.commit,
            timestamp=snsr_notice.timestamp.isoformat(),
        ),
    )
    assert descriptor
