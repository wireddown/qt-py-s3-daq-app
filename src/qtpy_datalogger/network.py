"""Functions for communicating with QT Py sensor nodes on the network."""

import asyncio
import contextlib
import json
import logging
from collections.abc import Generator
from typing import Any

import gmqtt

from .sensor_node.snsr.node import mqtt as node_mqtt

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def suppress_unless_debug() -> Generator[None, Any, None]:
    """Suppress logger.info() messages unless logging has been set to DEBUG / --verbose."""
    initial_log_level = logger.getEffectiveLevel()
    should_suppress = initial_log_level > logging.DEBUG
    if should_suppress:
        try:
            logging.getLogger().setLevel(logging.WARNING)
            yield
        finally:
            logging.getLogger().setLevel(initial_log_level)
    else:
        yield


def query_nodes_from_mqtt() -> dict[str, dict[str, str]]:
    """
    Scan the MQTT broker on the network for sensor nodes and return a dictionary of information.

    Returned entries, grouped by xxxx:
    - xxxx
    - yyyy
    """
    discovered_nodes = asyncio.run(_query_nodes_from_mqtt())
    return discovered_nodes


async def _query_nodes_from_mqtt() -> dict[str, dict[str, str]]:
    mac_address = "MUXaddr"
    pid = "0"
    client_id = f"host-{mac_address}-{pid}"
    broker_host = "localhost"
    group_id = "centrifuge"

    all_topics = node_mqtt.get_mqtt_topics(group_id, client_id)
    broadcast_topic = all_topics["broadcast"]
    command_topic = all_topics["command"]
    descriptor_topic = all_topics["descriptor"]
    all_descriptors_in_group_topic = node_mqtt.get_descriptor_topic(group_id, node_id="+")

    data_queue = asyncio.Queue()

    def on_connect(client, flags, rc, properties) -> None:
        """Handle connection to the MQTT broker."""
        logger.debug(f"Connected with flags='{flags}' rc='{rc}' properties='{properties}'")

    async def on_message(client, topic, payload, qos, properties) -> None:
        """Handle a message on topic with payload."""
        payload_string = payload.decode("UTF-8")
        logger.debug(f"Received '{payload_string}' on '{topic}' with qos='{qos}' properties='{properties}'")
        if payload_string.startswith("{"):
            await data_queue.put(payload_string)

    def on_disconnect(client, packet) -> None:
        """Handle disconnection from the MQTT broker."""
        logger.debug(f"Disconnected with packet='{packet}'")

    def on_subscribe(client, mid, qos, properties) -> None:
        """Handle subscription from the MQTT broker."""
        logger.debug(f"Subscribed with mid='{mid}' qos='{qos}' properties='{properties}'")

    client = gmqtt.Client(client_id)

    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect
    client.on_subscribe = on_subscribe

    with suppress_unless_debug():
        await client.connect(broker_host)
        client.subscribe(broadcast_topic)
        client.subscribe(command_topic)
        client.subscribe(all_descriptors_in_group_topic)
        await asyncio.sleep(0.2)  # Wait long enough to receive the subscription acknowledgements

    client.publish(descriptor_topic, "from cli")

    client.publish(broadcast_topic, "identify")
    try:
        timeout = 0.5
        async with asyncio.timeout(timeout):
            while True:  # noqa: ASYNC110 -- we cannot predict how many devices will respond, so we cannot know how many Events to await
                # Let other async tasks run so we can receive MQTT messages
                await asyncio.sleep(0)
    except TimeoutError:
        # Expected because we're waiting for callback to complete
        pass

    with suppress_unless_debug():
        await client.disconnect()

    discovered_sensor_nodes = {}
    while not data_queue.empty():
        response_json = await data_queue.get()
        response = json.loads(response_json.replace("'", '"'))
        discovered_sensor_nodes[response["node_identifier"]] = response["node_group"]
        data_queue.task_done()
    return discovered_sensor_nodes
