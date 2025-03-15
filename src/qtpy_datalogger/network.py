"""Functions for communicating with QT Py sensor nodes on the network."""

import asyncio
import contextlib
import json
import logging
import os
import platform
from collections.abc import Generator
from typing import Any, NamedTuple

import gmqtt

from .equip import _get_package_notice_info
from .sensor_node.snsr.node import classes as node_classes
from .sensor_node.snsr.node import mqtt as node_mqtt

logger = logging.getLogger(__name__)


class MqttMessage(NamedTuple):
    """A class that holds an MQTT message and its topic."""

    topic: str
    message: str


class MqttClientWithContext(gmqtt.Client):
    """Wrap a gmqtt.Client with a context property."""

    def __init__(self, client_id: str, context: object) -> None:
        """
        Create a gmqtt.Client and attach any custom object or class as a new property named context.

        Use this context in client callbacks to access application specific information.
        """
        super().__init__(client_id)
        self.context = context


class NamedCounter:
    """A class that increments a counter by its name."""

    def __init__(self) -> None:
        """Initialize a new NamedCounter."""
        self.named_counters: dict[str, int] = {}

    def count(self, name: str) -> int:
        """
        Increment the count for counter with name and return the value.

        If the name is new, create a new counter and return 1.
        """
        current_count = self.named_counters.get(name, 0)
        next_count = current_count + 1
        self.named_counters[name] = next_count
        return next_count


class QTPyController:
    """Class for controlling QT Py nodes."""

    def __init__(self, broker_host: str, group_id: str, mac_address: str, pid: int, hardware_name: str, ip_address: str) -> None:
        """Return a QTPyController."""
        self.broker_host = broker_host
        self.group_id = group_id
        self.mac_address = mac_address
        self.pid = pid
        self.hardware_name = hardware_name
        self.ip_address = ip_address
        self.mqtt_client_id = f"host-{self.mac_address}-{self.pid}"

        all_topics = node_mqtt.get_mqtt_topics(self.group_id, self.mqtt_client_id)
        self.broadcast_topic = all_topics["broadcast"]
        self.command_topic = all_topics["command"]
        self.descriptor_topic = all_topics["descriptor"]
        self.all_descriptors_in_group_topic = node_mqtt.get_descriptor_topic(group_id, node_id="+")

        self.named_counter = NamedCounter()
        self.message_queue: asyncio.Queue[MqttMessage] = asyncio.Queue()

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
            await client.context.message_queue.put(MqttMessage(topic, payload_string))

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

    async def connect_and_subscribe(self) -> None:
        """Connect the MQTT broker and subscribe to the topics in the sensor_node API."""
        with suppress_unless_debug():
            await self.client.connect(self.broker_host)
            self.publish_descriptor()
            self.client.subscribe(self.broadcast_topic)
            self.client.subscribe(self.command_topic)
            self.client.subscribe(self.all_descriptors_in_group_topic)
            await asyncio.sleep(0.2)  # Wait long enough to receive the subscription acknowledgements

    async def disconnect(self) -> None:
        """Disconnect from the MQTT broker."""
        with suppress_unless_debug():
            await self.client.disconnect()

    def publish_descriptor(self) -> None:
        """Publish the descriptor to the topic for this controller."""
        descriptor_payload = node_classes.DescriptorPayload(
            descriptor=_get_descriptor_information(self.mqtt_client_id, self.hardware_name, self.ip_address),
            sender=_get_sender_information(self.descriptor_topic),
        )
        self.client.publish(self.descriptor_topic, json.dumps(descriptor_payload.as_dict()))

    def broadcast_identify_command(self) -> None:
        """Send the identify command to the broadcast topic for the group."""
        command_name = "identify"
        identify_command = node_classes.ActionPayload(
            action=node_classes.ActionInformation(
                command=command_name,
                parameters={},
                message_id=self._format_message_id(command_name),
            ),
            sender=_get_sender_information(self.descriptor_topic),
        )
        self.client.publish(self.broadcast_topic, json.dumps(identify_command.as_dict()))

    async def collect_identify_responses(self) -> list[node_classes.DescriptorPayload]:
        """Get the messages sent by sensor_nodes in response to the identify command."""
        identify_responses = []
        other_messages = []
        while not self.message_queue.empty():
            topic_and_message: MqttMessage = await self.message_queue.get()
            response_json = topic_and_message.message
            response = json.loads(response_json)
            if "descriptor" in response:
                descriptor = node_classes.DescriptorPayload.from_dict(response)
                identify_responses.append(descriptor)
            else:
                logger.debug(f"Requeueing response '{topic_and_message}'")
                other_messages.append(topic_and_message)
            self.message_queue.task_done()
        for other_message in other_messages:
            self.message_queue.put_nowait(other_message)
        return identify_responses

    def send_command(self, node_id: str) -> None:
        """Send a command to node in the group."""
        command_name = "custom"
        action_command = node_classes.ActionPayload(
            action=node_classes.ActionInformation(
                command=command_name,
                parameters={
                    "input": "command line interface parameters",  # readline result here
                },
                message_id=self._format_message_id(command_name)
            ),
            sender=_get_sender_information(self.descriptor_topic),
        )
        command_topic = node_mqtt.get_command_topic(self.group_id, node_id)
        self.client.publish(command_topic, json.dumps(action_command.as_dict()))

    def _format_message_id(self, command_name: str) -> str:
        """Return a unique message ID for the command_name."""
        return f"{command_name}-{self.named_counter.count(command_name)}"


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
    controller = QTPyController(
        broker_host="localhost",
        group_id="centrifuge",
        mac_address="00:00:00:00:00",
        pid=3333,
        hardware_name="mux",
        ip_address="ip-address"
    )

    await controller.connect_and_subscribe()
    controller.broadcast_identify_command()
    await _yield_async_event_loop(0.5)
    discovered_sensor_nodes = await controller.collect_identify_responses()

    return discovered_sensor_nodes


def _get_sender_information(descriptor_topic: str) -> node_classes.SenderInformation:
    """Return a SenderInformation instance describing the system's current state."""
    return node_classes.SenderInformation(
        descriptor_topic=descriptor_topic,
        sent_at="host-time",
        status=node_classes.StatusInformation(
            used_memory="host-used",
            free_memory="host-free",
            cpu_temperature="host-cpu-temp",
        ),
    )


def _get_descriptor_information(node_id: str, hardware_name: str, ip_address: str) -> node_classes.DescriptorInformation:
    """Return a DescriptorInformation instance describing the client's current state."""
    snsr_notice = _get_package_notice_info(allow_dev_version=True)
    return node_classes.DescriptorInformation(
            node_id=node_id,
            hardware_name=hardware_name,
            system_name=os.name,
            python_implementation=f"{platform.python_implementation()} {platform.python_version()}",
            ip_address=ip_address,
            notice=node_classes.NoticeInformation(
                comment=snsr_notice.comment,
                version=snsr_notice.version,
                commit=snsr_notice.commit,
                timestamp=snsr_notice.timestamp.isoformat(),
            ),
        )


async def _yield_async_event_loop(timeout: float) -> None:
    """Yield the async event loop for the specified timeout in seconds."""
    try:
        async with asyncio.timeout(timeout):
            while True:  # noqa: ASYNC110 -- we cannot predict how many devices will respond, so we cannot know how many Events to await
                # Let other async tasks run so we can receive MQTT messages
                await asyncio.sleep(0)
    except TimeoutError:
        # Expected because the loop never exits and the timeout always expires
        pass
