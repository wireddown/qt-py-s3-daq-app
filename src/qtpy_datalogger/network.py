"""Functions for communicating with QT Py sensor nodes on the network."""

import asyncio
import contextlib
import json
import logging
from collections.abc import Generator
from typing import Any

import gmqtt

from .equip import _get_package_notice_info
from .sensor_node.snsr.node import classes as node_classes
from .sensor_node.snsr.node import mqtt as node_mqtt

logger = logging.getLogger(__name__)


class MqttClientWithContext(gmqtt.Client):
    """Wrap a gmqtt.Client with a context property."""

    def __init__(self, client_id: str, context: object) -> None:
        """
        Create a gmqtt.Client and attach any custom object or class as a new property named context.

        Use this context in client callbacks to access application specific information.
        """
        super().__init__(client_id)
        self.context = context


class QTPyController:
    """Class for controlling QT Py nodes."""

    def __init__(self) -> None:
        """Return a QTPyController."""
        self.mac_address = "MUXaddr"
        self.pid = "0"
        self.mqtt_client_id = f"host-{self.mac_address}-{self.pid}"

        self.broker_host = "localhost"
        self.group_id = "centrifuge"

        self.data_queue = asyncio.Queue()

        # Define these at runtime because
        #   we cannot change their parameters and make them instance methods (ie we cannot add 'self')
        #   we don't want to make make them static methods and share them across all instances
        def on_mqtt_connect(client, flags, rc, properties) -> None:
            """Handle connection to the MQTT broker."""
            logger.debug(f"Connected with flags='{flags}' rc='{rc}' properties='{properties}'")

        async def on_mqtt_message(client, topic, payload, qos, properties) -> None:
            """Handle a message on topic with payload."""
            payload_string = payload.decode("UTF-8")
            logger.debug(f"Received '{payload_string}' on '{topic}' with qos='{qos}' properties='{properties}'")
            await client.context.data_queue.put(payload_string)

        def on_mqtt_disconnect(client, packet) -> None:
            """Handle disconnection from the MQTT broker."""
            logger.debug(f"Disconnected with packet='{packet}'")

        def on_mqtt_subscribe(client, mid, qos, properties) -> None:
            """Handle subscription from the MQTT broker."""
            logger.debug(f"Subscribed with mid='{mid}' qos='{qos}' properties='{properties}'")

        self.client = MqttClientWithContext(self.mqtt_client_id, self)
        self.client.on_connect = on_mqtt_connect
        self.client.on_message = on_mqtt_message
        self.client.on_disconnect = on_mqtt_disconnect
        self.client.on_subscribe = on_mqtt_subscribe


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

    controller = QTPyController()
    client = controller.client

    with suppress_unless_debug():
        await client.connect(broker_host)
        client.subscribe(broadcast_topic)
        client.subscribe(command_topic)
        client.subscribe(all_descriptors_in_group_topic)
        await asyncio.sleep(0.2)  # Wait long enough to receive the subscription acknowledgements

    snsr_notice = _get_package_notice_info(allow_dev_version=True)
    descriptor_payload = node_classes.DescriptorPayload(
        descriptor=node_classes.DescriptorInformation(
            node_id="mux",
            hardware_name="pc_host",
            system_name="windows11",
            python_implementation="3.11.3",
            ip_address="hardwired",
            notice=node_classes.NoticeInformation(
                comment=snsr_notice.comment,
                version=snsr_notice.version,
                commit=snsr_notice.commit,
                timestamp=snsr_notice.timestamp.isoformat(),
            ),
        ),
        sender=node_classes.SenderInformation(
            descriptor_topic=descriptor_topic,
            sent_at="host-time",
            status=node_classes.StatusInformation(
                used_memory="host-used",
                free_memory="host-free",
                cpu_temperature="host-cpu-temp",
            ),
        )
    )
    client.publish(descriptor_topic, json.dumps(descriptor_payload.as_dict()))

    sender_information = node_classes.SenderInformation(
        descriptor_topic=descriptor_topic,
        sent_at="host-time",
        status=node_classes.StatusInformation(
            used_memory="host-used",
            free_memory="host-free",
            cpu_temperature="host-cpu-temp",
        ),
    )
    identify_command = node_classes.ActionPayload(
        action=node_classes.ActionInformation(
            command="identify",
            parameters={},
            message_id="identify-1",
        ),
        sender=sender_information,
    )
    client.publish(broadcast_topic, json.dumps(identify_command.as_dict()))

    action_command = node_classes.ActionPayload(
        action=node_classes.ActionInformation(
            command="custom",
            parameters={
                "input": "command line interface parameters",
            },
            message_id="action-1"
        ),
        sender=sender_information,
    )
    client.publish("qtpy/v1/centrifuge/node-42cea4d12c8b/command", json.dumps(action_command.as_dict()))
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
    while not controller.data_queue.empty():
        response_json = await controller.data_queue.get()
        try:
            response = json.loads(response_json)
            if "action" in response:
                action = node_classes.ActionPayload.from_dict(response)
                pass
            elif "descriptor" in response:
                descriptor = node_classes.DescriptorPayload.from_dict(response)
                pass
            pass
        except json.JSONDecodeError:
            pass
        # discovered_sensor_nodes[response["node_identifier"]] = response["node_group"]
        controller.data_queue.task_done()
    return discovered_sensor_nodes
