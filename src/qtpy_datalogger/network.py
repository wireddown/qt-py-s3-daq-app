"""Functions and classes for communicating with QT Py sensor nodes on the network."""

import asyncio
import json
import logging
import os
import platform
import socket
import uuid
from typing import NamedTuple

import gmqtt
import psutil

from .datatypes import CaptionCorrections, DetailKey, SnsrNotice, suppress_unless_debug
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
        self.subscribed_topics: set[str] = set()

    async def connect_and_subscribe(self) -> None:
        """Connect the MQTT broker and subscribe to the topics in the sensor_node API."""

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

        with suppress_unless_debug():
            await self.client.connect(self.broker_host)
        self._publish_descriptor()
        await self._subscribe(
            [
                self.broadcast_topic,
                self.command_topic,
                self.all_descriptors_in_group_topic,
            ]
        )

    async def scan_for_nodes(self, discovery_timeout: float = 0.5) -> dict[str, dict[DetailKey, str]]:
        """
        Scan the group for sensor_nodes and return a dictionary of discovered devices indexed by serial_number.

        Returned entries, grouped by serial_number:
        - device_description
        - ip_address
        - mqtt_group_id
        - node_id
        - python_implementation
        - serial_number
        - snsr_commit
        - snsr_timestamp
        - snsr_version
        - system_name
        """
        self._broadcast_identify_command()
        discovered_sensor_nodes = await self._collect_identify_responses(discovery_timeout)

        node_information = {
            node.descriptor.serial_number: {
                DetailKey.device_description: CaptionCorrections.get_corrected(node.descriptor.hardware_name),
                DetailKey.ip_address: node.descriptor.ip_address,
                DetailKey.mqtt_group_id: self.group_id,
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

    async def send_action(self, node_id: str, command_name: str, parameters: dict) -> node_classes.ActionInformation:
        """
        Send a command with the specified parameters to the node in the group with node_id and return the sent ActionInformation.

        Use the returned ActionInformation with 'get_matching_result()' to await the result.
        """
        action = node_classes.ActionInformation(
            command=command_name,
            parameters=parameters,
            message_id=self._format_message_id(command_name),
        )

        await self._publish_action_payload(node_id, action)
        return action

    async def get_matching_result(
        self,
        node_id: str,
        action: node_classes.ActionInformation,
        timeout: float = 5.0,
    ) -> tuple[dict, node_classes.SenderInformation]:
        """
        Monitor the MQTT messages for a matching result to the specified action.

        Returns a tuple with
        - the dictionary of parameters from the result's matching ActionInformation
        - the SenderInformation from the matching payload
        """
        parameters_and_sender = ()
        other_messages = []
        action_id = action.message_id
        logger.debug(f"Monitoring MQTT messages for the '{action_id}' result from '{node_id}'")
        async with asyncio.timeout(timeout):
            while not parameters_and_sender:
                topic_and_message = await self.message_queue.get()
                response_json = topic_and_message.message
                response = json.loads(response_json)
                if "action" in response:
                    payload = node_classes.ActionPayload.from_dict(response)
                    sending_node = node_mqtt.node_from_topic(payload.sender.descriptor_topic)
                    result_id = payload.action.message_id
                    if sending_node == node_id and result_id == action_id:
                        logger.debug(f"Matched result '{payload.action.parameters}'")
                        parameters_and_sender = (payload.action.parameters, payload.sender)
                    else:
                        other_messages.append(topic_and_message)
                else:
                    other_messages.append(topic_and_message)
                self.message_queue.task_done()
        for other_message in other_messages:
            self._requeue_or_discard(other_message)
        return parameters_and_sender

    async def disconnect(self) -> None:
        """Disconnect from the MQTT broker."""
        if not self.message_queue.empty():
            logger.warning(
                f"Leaving {self.message_queue.qsize()} MQTT messages unprocessed. Add '--verbose' to see them."
            )
            while not self.message_queue.empty():
                unprocessed_message = self.message_queue.get_nowait()
                logger.debug(unprocessed_message._asdict())
                self.message_queue.task_done()
        with suppress_unless_debug():
            await self.client.disconnect()
        self.subscribed_topics.clear()

    def _publish_descriptor(self) -> None:
        """Publish the descriptor to the topic for this controller."""
        descriptor_payload = node_classes.DescriptorPayload(
            descriptor=self.descriptor,
            sender=_build_sender_information(self.descriptor_topic),
        )
        self.client.publish(self.descriptor_topic, json.dumps(descriptor_payload.as_dict()))

    async def _subscribe(self, topics: list[str]) -> None:
        """Subscribe to the specified topics."""
        new_topics = set(topics) - self.subscribed_topics
        if not new_topics:
            return
        with suppress_unless_debug():
            for new_topic in new_topics:
                self.subscribed_topics.add(new_topic)
                self.client.subscribe(new_topic)
            await asyncio.sleep(0.2)  # Wait long enough to receive the subscription acknowledgements

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

    async def _collect_identify_responses(self, discovery_timeout: float) -> list[node_classes.DescriptorPayload]:
        """Get the messages sent by sensor_nodes in response to the identify command."""
        identify_responses = []
        other_messages = []

        try:
            logger.debug("Monitoring MQTT messages for 'identify' responses")
            async with asyncio.timeout(discovery_timeout):
                while True:
                    topic_and_message: MqttMessage = await self.message_queue.get()
                    response_json = topic_and_message.message
                    response = json.loads(response_json)
                    if "descriptor" in response:
                        payload = node_classes.DescriptorPayload.from_dict(response)
                        logger.debug(f"Matched response '{payload.descriptor.node_id}'")
                        identify_responses.append(payload)
                    else:
                        other_messages.append(topic_and_message)
                    self.message_queue.task_done()
        except TimeoutError:
            # Expected because the loop never exits and the timeout always expires
            pass

        for other_message in other_messages:
            self._requeue_or_discard(other_message)
        return identify_responses

    def _requeue_or_discard(self, topic_and_message: MqttMessage) -> None:
        """Scan the specified message and requeue it if it should be processed. Discard otherwise."""
        message = json.loads(topic_and_message.message)

        should_discard = False
        discard_reason = ""
        if "descriptor" in message:
            descriptor_payload = node_classes.DescriptorPayload.from_dict(message)
            sender = descriptor_payload.sender
            if sender.descriptor_topic == self.descriptor_topic:
                should_discard = True
                discard_reason = "ignore messages from self"
        elif "action" in message:
            action_payload = node_classes.ActionPayload.from_dict(message)
            sender = action_payload.sender
            if sender.descriptor_topic == self.descriptor_topic:
                should_discard = True
                discard_reason = "ignore messages from self"
        else:
            logger.warning(f"Cannot analyze response '{topic_and_message}'")
            should_discard = False

        if should_discard:
            logger.debug(f"Discarding response '{topic_and_message}' with reason '{discard_reason}'")
        else:
            logger.debug(f"Requeueing response '{topic_and_message}'")
            self.message_queue.put_nowait(topic_and_message)

    async def _publish_action_payload(self, node_id: str, action: node_classes.ActionInformation) -> None:
        """Send the specified action to the specified node_id's command topic."""
        action_payload = node_classes.ActionPayload(
            action=action,
            sender=_build_sender_information(self.descriptor_topic),
        )

        result_topic = node_mqtt.get_result_topic(self.group_id, node_id)
        await self._subscribe([result_topic])

        command_topic = node_mqtt.get_command_topic(self.group_id, node_id)
        self.client.publish(command_topic, json.dumps(action_payload.as_dict()))

    def _format_message_id(self, action_name: str) -> str:
        """Return a unique message ID for the action_name."""
        return f"{action_name}-{self.named_counter.count(action_name)}"


def query_nodes_from_mqtt(group_id: str) -> dict[str, dict[DetailKey, str]]:
    """
    Scan the MQTT broker on the network for sensor nodes and return a dictionary of information.

    Returned entries, grouped by serial_number:
    - device_description
    - ip_address
    - mqtt_group_id
    - node_id
    - python_implementation
    - serial_number
    - snsr_commit
    - snsr_timestamp
    - snsr_version
    - system_name
    """
    discovered_nodes = asyncio.run(query_nodes_from_mqtt_async(group_id))
    return discovered_nodes


def open_session_on_node(group_id: str, node_id: str) -> None:
    """Open a terminal connection to the sensor_node with the specified node_id."""
    asyncio.run(_open_session_on_node(group_id, node_id))


async def query_nodes_from_mqtt_async(group_id: str) -> dict[str, dict[DetailKey, str]]:
    """Use a new QTPyController to scan the network for sensor_nodes."""
    broker_host = "localhost"
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


async def _open_session_on_node(group_id: str, node_id: str) -> None:
    """Use a new QTPyController to open a terminal session on the specified node_id."""
    broker_host = "localhost"
    mac_address = hex(uuid.getnode())[2:]
    ip_address = socket.gethostbyname(socket.gethostname())
    controller = QTPyController(
        broker_host=broker_host,
        group_id=group_id,
        mac_address=mac_address,
        ip_address=ip_address,
    )

    exit_commands = ["exit", "quit"]
    exit_options = "' or '".join(exit_commands)
    exit_help = f"Use any of '{exit_options}' to exit."
    print(exit_help)  # noqa: T201 -- use direct IO for user REPL

    await controller.connect_and_subscribe()
    while True:
        user_input = await asyncio.to_thread(input, f"{node_id} > ")
        if user_input in exit_commands:
            break
        if user_input == "help":
            print(exit_help)  # noqa: T201 -- use direct IO for user REPL
            continue

        command_name = "custom"
        custom_parameters = {
            "input": user_input,
        }
        sent_action = await controller.send_action(node_id, command_name, custom_parameters)

        response_complete = False
        while not response_complete:
            try:
                response_parameters, sender_information = await controller.get_matching_result(node_id, sent_action)
                response_complete = response_parameters["complete"]
                response = response_parameters["output"]
                used_kb = sender_information.status.used_memory
                free_kb = sender_information.status.free_memory
                cpu_degc = sender_information.status.cpu_temperature
                print(  # noqa: T201 -- use direct IO for user REPL
                    f"Received '{response}' from node with {used_kb} kB used, {free_kb} kB remaining, at temperature {cpu_degc} degC"
                )
            except TimeoutError:
                logger.error("Node did not respond! Is it online or correctly spelled?")  # noqa: TRY400 -- user-facing, known error condition
                logger.error(exit_help)  # noqa: TRY400 -- user-facing, known error condition
                break

    await controller.disconnect()


def _build_sender_information(descriptor_topic: str) -> node_classes.SenderInformation:
    """Return a SenderInformation instance describing the system's current state."""
    memory_information = psutil.virtual_memory()

    return node_classes.SenderInformation(
        descriptor_topic=descriptor_topic,
        sent_at="host-time",
        status=node_classes.StatusInformation(
            used_memory=str(memory_information.used),
            free_memory=str(memory_information.available),
            cpu_temperature="NaN",  # No simple way to query this on Windows
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
