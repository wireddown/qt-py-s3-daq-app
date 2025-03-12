"""Classes used by hosts and nodes."""

# CircuitPython json supports literals, dictionaries, and lists
# The library does not accept object hooks when creating json from objects
# Manifests as
#   TypeError: can't convert SnsrNotice to json

class StatusInformation:
    def __init__(
        self: "StatusInformation",
        used_memory: str,
        free_memory: str,
        cpu_temperature: str,
    ):
        self.information = {
            "used_memory": used_memory,
            "free_memory": free_memory,
            "cpu_temperature": cpu_temperature,
        }

    @staticmethod
    def from_dict(dictionary: dict[str, str]) -> "StatusInformation":
        return StatusInformation(**dictionary)

    def as_dict(self):
        return self.information


# SnsrNotice = namedtuple("SnsrNotice", tuple_keys)
# how to add as_ and from_dict ?
class NoticeInformation:
    def __init__(
        self: "NoticeInformation",
        comment: str,
        version: str,
        commit: str,
        timestamp: str,
    ):
        self.information = {
            "comment": comment,
            "version": version,
            "commit": commit,
            "timestamp": timestamp,
        }

    @staticmethod
    def from_dict(dictionary: dict[str, str]) -> "NoticeInformation":
        return NoticeInformation(**dictionary)

    def as_dict(self):
        return self.information


class DescriptorInformation:
    def __init__(
        self: "DescriptorInformation",
        node_id: str,
        hardware_name: str,
        system_name: str,
        python_implementation: str,
        ip_address: str,
        notice: NoticeInformation,
    ):
        self.information = {
            "node_id": node_id,
            "hardware_name": hardware_name,
            "system_name": system_name,
            "python_implementation": python_implementation,
            "ip_address": ip_address,
            "notice": notice.as_dict(),
        }

    @staticmethod
    def from_dict(dictionary: dict[str, str]) -> "DescriptorInformation":
        notice_information = NoticeInformation.from_dict(dictionary["notice"])
        return DescriptorInformation(
            dictionary["node_id"],
            dictionary["hardware_name"],
            dictionary["system_name"],
            dictionary["python_implementation"],
            dictionary["ip_address"],
            notice_information,
        )

    def as_dict(self):
        return self.information


class SenderInformation:
    def __init__(
        self: "SenderInformation",
        descriptor_topic: str,
        sent_at: str,
        status: StatusInformation
    ):
        self.information = {
            "descriptor_topic": descriptor_topic,
            "sent_at": sent_at,
            "status": status.as_dict(),
        }

    @staticmethod
    def from_dict(dictionary: dict[str, str]) -> "SenderInformation":
        status_information = StatusInformation.from_dict(dictionary["status"])
        return SenderInformation(dictionary["descriptor_topic"], dictionary["sent_at"], status_information)

    def as_dict(self):
        return self.information


class DescriptorPayload:
    def __init__(
        self: "DescriptorPayload",
        descriptor: DescriptorInformation,
        sender: SenderInformation,
    ):
        self.information = {
            "descriptor": descriptor.as_dict(),
            "sender": sender.as_dict(),
        }

    @staticmethod
    def from_dict(dictionary: dict[str, str]) -> "DescriptorPayload":
        descriptor_information = DescriptorInformation.from_dict(dictionary["descriptor"])
        sender_information = SenderInformation.from_dict(dictionary["sender"])
        return DescriptorPayload(descriptor_information, sender_information)

    def as_dict(self):
        return self.information


class ActionInformation:
    def __init__(
        self: "ActionInformation",
        command: str,
        parameters: dict[str, str],
        message_id: str,
    ):
        self.information = {
            "command": command,
            "parameters": parameters,
            "message_id": message_id,
        }

    @staticmethod
    def from_dict(dictionary: dict[str, str]) -> "ActionInformation":
        return ActionInformation(**dictionary)

    def as_dict(self):
        return self.information


class ActionPayload:
    def __init__(
        self: "ActionPayload",
        action: ActionInformation,
        sender: SenderInformation,
    ):
        self.information = {
            "action": action.as_dict(),
            "sender": sender.as_dict(),
        }

    @staticmethod
    def from_dict(dictionary: dict[str, str]) -> "ActionPayload":
        action_information = ActionInformation.from_dict(dictionary["action"])
        sender_information = SenderInformation.from_dict(dictionary["sender"])
        return ActionPayload(action_information, sender_information)

    def as_dict(self):
        return self.information
