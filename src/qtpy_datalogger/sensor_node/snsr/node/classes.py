"""
Classes used by hosts and nodes to send and receive MQTT messages.

- The clients use JSON to serialize the information they send to each other through the broker
- However, the CircuitPython implementation of json only supports literals, dictionaries, and lists
- And so the methods do not accept object hooks when creating json from objects
- Without these hooks, the code raises
    TypeError: can't convert SnsrNotice to json

This module uses simple and explicit syntax to support CircuitPython clients.
"""


class StatusInformation:
    """A class that describes the status of a node in a sensor_node group."""

    def __init__(
        self: "StatusInformation",
        used_memory: str,
        free_memory: str,
        cpu_temperature: str,
    ) -> None:
        """Initialize a new StatusInformation with the specified values."""
        self.information = {
            "used_memory": used_memory,
            "free_memory": free_memory,
            "cpu_temperature": cpu_temperature,
        }

    @staticmethod
    def from_dict(dictionary: dict) -> "StatusInformation":
        """Return a new StatusInformation from the specified dictionary."""
        return StatusInformation(**dictionary)

    def as_dict(self) -> dict:
        """Return a dictionary representation."""
        return self.information

    @property
    def used_memory(self) -> str:
        """The used_memory on the node."""
        return self.information["used_memory"]

    @property
    def free_memory(self) -> str:
        """The free_memory on the node."""
        return self.information["free_memory"]

    @property
    def cpu_temperature(self) -> str:
        """The cpu_temperature of the node."""
        return self.information["cpu_temperature"]


class NoticeInformation:
    """A serializable class for the notice.toml file."""

    def __init__(
        self: "NoticeInformation",
        comment: str,
        version: str,
        commit: str,
        timestamp: str,
    ) -> None:
        """Initialize a new NoticeInformation with the specified values."""
        self.information = {
            "comment": comment,
            "version": version,
            "commit": commit,
            "timestamp": timestamp,
        }

    @staticmethod
    def from_dict(dictionary: dict) -> "NoticeInformation":
        """Return a new NoticeInformation from the specified dictionary."""
        return NoticeInformation(**dictionary)

    def as_dict(self) -> dict:
        """Return a dictionary representation."""
        return self.information

    @property
    def comment(self) -> str:
        """The comment from notice.toml."""
        return self.information["comment"]

    @property
    def version(self) -> str:
        """The version from notice.toml."""
        return self.information["version"]

    @property
    def commit(self) -> str:
        """The commit ID from notice.toml."""
        return self.information["commit"]

    @property
    def timestamp(self) -> str:
        """The timestamp from notice.toml."""
        return self.information["timestamp"]


class DescriptorInformation:
    """A class that describes a sensor_node's hardware, software, network, and version details."""

    def __init__(  # noqa: PLR0913 -- allow more than 5 parameters
        self: "DescriptorInformation",
        node_id: str,
        serial_number: str,
        hardware_name: str,
        system_name: str,
        python_implementation: str,
        ip_address: str,
        notice: NoticeInformation,
    ) -> None:
        """Initialize a new DescriptorInformation with the specified values."""
        self.information = {
            "node_id": node_id,
            "serial_number": serial_number,
            "hardware_name": hardware_name,
            "system_name": system_name,
            "python_implementation": python_implementation,
            "ip_address": ip_address,
            "notice": notice.as_dict(),
        }

    @staticmethod
    def from_dict(dictionary: dict) -> "DescriptorInformation":
        """Return a new DescriptorInformation from the specified dictionary."""
        return DescriptorInformation(
            dictionary["node_id"],
            dictionary["serial_number"],
            dictionary["hardware_name"],
            dictionary["system_name"],
            dictionary["python_implementation"],
            dictionary["ip_address"],
            NoticeInformation.from_dict(dictionary["notice"]),
        )

    def as_dict(self) -> dict:
        """Return a dictionary representation."""
        return self.information

    @property
    def node_id(self) -> str:
        """The node_id for the sensor_node."""
        return self.information["node_id"]

    @property
    def serial_number(self) -> str:
        """The serial_number for the sensor_node."""
        return self.information["serial_number"]

    @property
    def hardware_name(self) -> str:
        """The hardware_name for the sensor_node."""
        return self.information["hardware_name"]

    @property
    def system_name(self) -> str:
        """The system_name for the sensor_node."""
        return self.information["system_name"]

    @property
    def python_implementation(self) -> str:
        """The python_implementation for the sensor_node."""
        return self.information["python_implementation"]

    @property
    def ip_address(self) -> str:
        """The ip_address for the sensor_node."""
        return self.information["ip_address"]

    @property
    def notice_information(self) -> NoticeInformation:
        """The notice.toml contents from the sensor_node."""
        return NoticeInformation.from_dict(self.information["notice"])


class SenderInformation:
    """A class that describes the sender of a message in a sensor_node group."""

    def __init__(
        self: "SenderInformation",
        descriptor_topic: str,
        sent_at: str,
        status: StatusInformation,
    ) -> None:
        """Initialize a new SenderInformation with the specified values."""
        self.information = {
            "descriptor_topic": descriptor_topic,
            "sent_at": sent_at,
            "status": status.as_dict(),
        }

    @staticmethod
    def from_dict(dictionary: dict) -> "SenderInformation":
        """Return a new SenderInformation from the specified dictionary."""
        status_information = StatusInformation.from_dict(dictionary["status"])
        return SenderInformation(dictionary["descriptor_topic"], dictionary["sent_at"], status_information)

    def as_dict(self) -> dict:
        """Return a dictionary representation."""
        return self.information

    @property
    def descriptor_topic(self) -> str:
        """The descriptor_topic for the sender."""
        return self.information["descriptor_topic"]

    @property
    def sent_at(self) -> str:
        """The timestamp when the sender sent the message."""
        return self.information["sent_at"]

    @property
    def status(self) -> StatusInformation:
        """The status of the sender when the sender sent the message."""
        return StatusInformation.from_dict(self.information["status"])


class DescriptorPayload:
    """A class that represents the MQTT message payload for a sensor_node's $DESCRIPTOR topic."""

    def __init__(
        self: "DescriptorPayload",
        descriptor: DescriptorInformation,
        sender: SenderInformation,
    ) -> None:
        """Initialize a new DescriptorPayload with the specified values."""
        self.information = {
            "descriptor": descriptor.as_dict(),
            "sender": sender.as_dict(),
        }

    @staticmethod
    def from_dict(dictionary: dict) -> "DescriptorPayload":
        """Return a new DescriptorPayload from the specified dictionary."""
        descriptor_information = DescriptorInformation.from_dict(dictionary["descriptor"])
        sender_information = SenderInformation.from_dict(dictionary["sender"])
        return DescriptorPayload(descriptor_information, sender_information)

    def as_dict(self) -> dict:
        """Return a dictionary representation."""
        return self.information

    @property
    def descriptor(self) -> DescriptorInformation:
        """The descriptor in the payload."""
        return DescriptorInformation.from_dict(self.information["descriptor"])

    @property
    def sender(self) -> SenderInformation:
        """The sender of the payload."""
        return SenderInformation.from_dict(self.information["sender"])


class ActionInformation:
    """A class that describes an action message for a sensor_node."""

    def __init__(
        self: "ActionInformation",
        command: str,
        parameters: dict,
        message_id: str,
    ) -> None:
        """Initialize a new ActionInformation with the specified values."""
        self.information = {
            "command": command,
            "parameters": parameters,
            "message_id": message_id,
        }

    @staticmethod
    def from_dict(dictionary: dict) -> "ActionInformation":
        """Return a new ActionInformation from the specified dictionary."""
        return ActionInformation(**dictionary)

    def as_dict(self) -> dict:
        """Return a dictionary representation."""
        return self.information

    @property
    def command(self) -> str:
        """The command for the action."""
        return self.information["command"]

    @property
    def parameters(self) -> dict:
        """The dictionary of parameters specified for the command."""
        return self.information["parameters"]

    @property
    def message_id(self) -> str:
        """The unique message_id for the action."""
        return self.information["message_id"]


class ActionPayload:
    """A class that represents the MQTT message payload for a sensor_node's command and result topics."""

    def __init__(
        self: "ActionPayload",
        action: ActionInformation,
        sender: SenderInformation,
    ) -> None:
        """Initialize a new ActionPayload with the specified values."""
        self.information = {
            "action": action.as_dict(),
            "sender": sender.as_dict(),
        }

    @staticmethod
    def from_dict(dictionary: dict) -> "ActionPayload":
        """Return a new ActionPayload from the specified dictionary."""
        action_information = ActionInformation.from_dict(dictionary["action"])
        sender_information = SenderInformation.from_dict(dictionary["sender"])
        return ActionPayload(action_information, sender_information)

    def as_dict(self) -> dict:
        """Return a dictionary representation."""
        return self.information

    @property
    def action(self) -> ActionInformation:
        """The action in the payload."""
        return ActionInformation.from_dict(self.information["action"])

    @property
    def sender(self) -> SenderInformation:
        """The sender of the payload."""
        return SenderInformation.from_dict(self.information["sender"])
