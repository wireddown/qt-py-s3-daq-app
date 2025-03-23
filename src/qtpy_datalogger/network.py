"""Functions for communicating with QT Py sensor nodes on the network."""

import asyncio
import json
import logging
import os
import platform
import socket
import uuid
from typing import NamedTuple

import gmqtt

from .datatypes import DetailKey, SnsrNotice, suppress_unless_debug
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

    def __init__(self, broker_host: str, group_id: str, mac_address: str, ip_address: str) -> None:
        """Return a QTPyController."""
        self.broker_host = broker_host
        self.group_id = group_id
        self.descriptor = _build_descriptor_information(
            role="host",
            serial_number=mac_address,
            ip_address=ip_address,
        )

        all_topics = node_mqtt.get_mqtt_topics(self.group_id, self.descriptor.node_id)
        self.broadcast_topic = all_topics["broadcast"]
        self.command_topic = all_topics["command"]
        self.descriptor_topic = all_topics["descriptor"]
        self.all_descriptors_in_group_topic = node_mqtt.get_descriptor_topic(group_id, node_id="+")

        self.named_counter = NamedCounter()
        self.message_queue: asyncio.Queue[MqttMessage] = asyncio.Queue()

        # Define these at runtime because
        #   we cannot change their parameters and make them instance methods (ie we cannot add 'self')
        #   we don't want to make make them static methods and share them across all instances
        def on_mqtt_connect(client: MqttClientWithContext, flags: int, rc: int, properties: dict) -> None:
            """Handle connection to the MQTT broker."""
            logger.debug(f"Connected with flags='{flags}' rc='{rc}' properties='{properties}'")

        async def on_mqtt_message(
            client: MqttClientWithContext, topic: str, payload: bytes, qos: int, properties: dict
        ) -> None:
            """Handle a message on topic with payload."""
            payload_string = payload.decode("UTF-8")
            logger.debug(f"Received '{payload_string}' on '{topic}' with qos='{qos}' properties='{properties}'")
            as_self: QTPyController = client.context  # pyright: ignore reportAssignmentType -- the type for context is client-defined
            await as_self.message_queue.put(MqttMessage(topic, payload_string))

        def on_mqtt_disconnect(client: MqttClientWithContext, packet: bytes) -> None:
            """Handle disconnection from the MQTT broker."""
            logger.debug(f"Disconnected with packet='{packet}'")

        def on_mqtt_subscribe(client: MqttClientWithContext, mid: int, qos: tuple, properties: dict) -> None:
            """Handle subscription from the MQTT broker."""
            logger.debug(f"Subscribed with mid='{mid}' qos='{qos}' properties='{properties}'")

        self.client = MqttClientWithContext(self.descriptor.node_id, self)
        self.client.on_connect = on_mqtt_connect
        self.client.on_message = on_mqtt_message
        self.client.on_disconnect = on_mqtt_disconnect
        self.client.on_subscribe = on_mqtt_subscribe

    async def connect_and_subscribe(self) -> None:
        """Connect the MQTT broker and subscribe to the topics in the sensor_node API."""
        with suppress_unless_debug():
            await self.client.connect(self.broker_host)
            self._publish_descriptor()
            self.client.subscribe(self.broadcast_topic)
            self.client.subscribe(self.command_topic)
            self.client.subscribe(self.all_descriptors_in_group_topic)
            await asyncio.sleep(0.2)  # Wait long enough to receive the subscription acknowledgements

    async def disconnect(self) -> None:
        """Disconnect from the MQTT broker."""
        with suppress_unless_debug():
            await self.client.disconnect()

    def _publish_descriptor(self) -> None:
        """Publish the descriptor to the topic for this controller."""
        descriptor_payload = node_classes.DescriptorPayload(
            descriptor=self.descriptor,
            sender=_build_sender_information(self.descriptor_topic),
        )
        self.client.publish(self.descriptor_topic, json.dumps(descriptor_payload.as_dict()))

    def _broadcast_identify_command(self) -> None:
        """Send the identify command to the broadcast topic for the group."""
        command_name = "identify"
        identify_command = node_classes.ActionPayload(
            action=node_classes.ActionInformation(
                command=command_name,
                parameters={},
                message_id=self._format_message_id(command_name),
            ),
            sender=_build_sender_information(self.descriptor_topic),
        )
        self.client.publish(self.broadcast_topic, json.dumps(identify_command.as_dict()))

    async def _collect_identify_responses(self) -> list[node_classes.DescriptorPayload]:
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

    async def scan_for_nodes(self, discovery_timeout: float = 0.5) -> dict[str, dict[DetailKey, str]]:
        """
        Scan the group for sensor_nodes and return a dictionary of discovered devices indexed by serial_number.

        Returned entries, grouped by serial_number:
        - device_description
        - ip_address
        - node_id
        - python_implementation
        - serial_number
        - snsr_commit
        - snsr_timestamp
        - snsr_version
        - system_name
        """
        self._broadcast_identify_command()
        await _yield_async_event_loop(discovery_timeout)
        discovered_sensor_nodes = await self._collect_identify_responses()
        node_information = {
            node.descriptor.serial_number: {
                DetailKey.device_description: node.descriptor.hardware_name,
                DetailKey.ip_address: node.descriptor.ip_address,
                DetailKey.node_id: node.descriptor.node_id,
                DetailKey.python_implementation: node.descriptor.python_implementation,
                DetailKey.serial_number: node.descriptor.serial_number,
                DetailKey.snsr_commit: node.descriptor.notice_information.commit,
                DetailKey.snsr_timestamp: node.descriptor.notice_information.timestamp,
                DetailKey.snsr_version: node.descriptor.notice_information.version,
                DetailKey.system_name: node.descriptor.system_name,
            }
            for node in discovered_sensor_nodes
        }
        return node_information

    async def send_custom_command(self, node_id: str, command: str) -> node_classes.ActionInformation:
        """
        Send a command to the node in the group with node_id and return the sent ActionInformation.

        Use the returned ActionInformation with 'get_matching_result()' to await the result.
        """
        command_name = "custom"
        action_command = node_classes.ActionInformation(
            command=command_name,
            parameters={
                "input": command,
            },
            message_id=self._format_message_id(command_name),
        )

        action_payload = node_classes.ActionPayload(
            action=action_command,
            sender=_build_sender_information(self.descriptor_topic),
        )

        with suppress_unless_debug():
            result_topic = node_mqtt.get_result_topic(self.group_id, node_id)
            self.client.subscribe(result_topic)
            await asyncio.sleep(0.2)  # Wait long enough to receive the subscription acknowledgements

        command_topic = node_mqtt.get_command_topic(self.group_id, node_id)
        self.client.publish(command_topic, json.dumps(action_payload.as_dict()))

        return action_command

    async def get_custom_result(self, node_id: str, action_command: node_classes.ActionInformation) -> str:
        """Monitor the MQTT messages for a matching response to the specified custom command."""
        custom_result_response = []
        other_messages = []
        command_id = action_command.message_id
        while not custom_result_response:
            topic_and_message: MqttMessage = await self.message_queue.get()
            response_json = topic_and_message.message
            response = json.loads(response_json)
            if "action" in response:
                payload = node_classes.ActionPayload.from_dict(response)
                sending_node = node_mqtt.node_from_topic(payload.sender.descriptor_topic)
                result_id = payload.action.message_id
                if sending_node == node_id and result_id == command_id:
                    custom_result_response.append(payload.action.parameters["output"])
                    break
                logger.debug(f"Requeueing response '{topic_and_message}'")
                other_messages.append(topic_and_message)
            else:
                logger.debug(f"Requeueing response '{topic_and_message}'")
                other_messages.append(topic_and_message)
            self.message_queue.task_done()
        for other_message in other_messages:
            self.message_queue.put_nowait(other_message)
        return custom_result_response[0]

    def _format_message_id(self, command_name: str) -> str:
        """Return a unique message ID for the command_name."""
        return f"{command_name}-{self.named_counter.count(command_name)}"


def query_nodes_from_mqtt() -> dict[str, dict[DetailKey, str]]:
    """
    Scan the MQTT broker on the network for sensor nodes and return a dictionary of information.

    Returned entries, grouped by serial_number:
    - device_description
    - ip_address
    - node_id
    - python_implementation
    - serial_number
    - snsr_commit
    - snsr_timestamp
    - snsr_version
    - system_name
    """
    discovered_nodes = asyncio.run(_query_nodes_from_mqtt())
    return discovered_nodes


def open_session_on_node(node_id: str) -> None:
    """Open a terminal connection to the node with the specified node_id."""
    asyncio.run(_open_session_on_node(node_id))


async def _query_nodes_from_mqtt() -> dict[str, dict[DetailKey, str]]:
    broker_host = "localhost"
    group_id = "centrifuge"
    mac_address = hex(uuid.getnode())[2:]
    ip_address = socket.gethostbyname(socket.gethostname())
    controller = QTPyController(
        broker_host=broker_host,
        group_id=group_id,
        mac_address=mac_address,
        ip_address=ip_address,
    )

    await controller.connect_and_subscribe()
    node_information = await controller.scan_for_nodes()
    await controller.disconnect()

    return node_information


async def _open_session_on_node(node_id: str) -> None:
    broker_host = "localhost"
    group_id = "centrifuge"
    mac_address = hex(uuid.getnode())[2:]
    ip_address = socket.gethostbyname(socket.gethostname())
    controller = QTPyController(
        broker_host=broker_host,
        group_id=group_id,
        mac_address=mac_address,
        ip_address=ip_address,
    )

    await controller.connect_and_subscribe()
    user_input = ""
    while user_input not in ["exit", "quit"]:
        user_input = input(f"{node_id} > ")
        command = await controller.send_custom_command(node_id, user_input)
        response = await controller.get_custom_result(node_id, command)
        print(response)  # noqa: T201 -- use direct IO for user
    await controller.disconnect()


def _build_sender_information(descriptor_topic: str) -> node_classes.SenderInformation:
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


def _build_descriptor_information(role: str, serial_number: str, ip_address: str) -> node_classes.DescriptorInformation:
    """Return a DescriptorInformation instance describing the client's current state."""
    snsr_notice = SnsrNotice.get_package_notice_info(allow_dev_version=True)
    return node_classes.DescriptorInformation(
        node_id=node_mqtt.format_mqtt_client_id(role, serial_number, os.getpid()),
        serial_number=serial_number,
        hardware_name=platform.machine(),
        system_name=f"{platform.system()}-{platform.version()}",
        python_implementation=f"{platform.python_implementation()}-{platform.python_version()}",
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
