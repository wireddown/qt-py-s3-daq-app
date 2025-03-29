"""Acceptance tests for the MQTT functions."""

import qtpy_datalogger.sensor_node.snsr.node.mqtt as node_mqtt


def test_mqtt_topic_functions() -> None:
    """Do the get-topic functions agree with each other?"""
    group_id = "test-group"
    node_id = "test-node-id"

    all_mqtt_topics = node_mqtt.get_mqtt_topics(group_id, node_id)

    active_version = "/".join([node_mqtt.get_domain(), node_mqtt.get_api_version()])
    assert all(all_mqtt_topics[t].startswith(active_version) for t in all_mqtt_topics)
    assert all_mqtt_topics["acquired_data"] == node_mqtt.get_acquired_data_topic(group_id)
    assert all_mqtt_topics["broadcast"] == node_mqtt.get_broadcast_topic(group_id)
    assert all_mqtt_topics["command"] == node_mqtt.get_command_topic(group_id, node_id)
    assert all_mqtt_topics["descriptor"] == node_mqtt.get_descriptor_topic(group_id, node_id)
    assert all_mqtt_topics["log"] == node_mqtt.get_log_topic(group_id)
    assert all_mqtt_topics["result"] == node_mqtt.get_result_topic(group_id, node_id)


def test_node_from_topic() -> None:
    """Does node_from_topic() correctly get the node_id from any topic?"""
    group_id = "test-group"
    node_id = "test-node-id"
    all_mqtt_topics = node_mqtt.get_mqtt_topics(group_id, node_id)

    for name, topic in all_mqtt_topics.items():
        if name in ["acquired_data", "broadcast", "log"]:
            # Group topics have no node IDs
            assert not node_mqtt.node_from_topic(topic)
        else:
            assert node_mqtt.node_from_topic(topic) == node_id
