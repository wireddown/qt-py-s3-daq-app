"""Protocols and functions used by hosts and nodes."""


def get_mqtt_topics(group_id: str, node_id: str) -> dict[str, str]:
    return {
        "acquired_data": f"qtpy/v1/{group_id}/acquired_data",
        "broadcast": f"qtpy/v1/{group_id}/broadcast",
        "command": f"qtpy/v1/{group_id}/{node_id}/command",
        "descriptor": f"qtpy/v1/{group_id}/{node_id}/$DESCRIPTOR",
        "log": f"qtpy/v1/{group_id}/log",
        "result": f"qtpy/v1/{group_id}/{node_id}/result",
    }


def get_acquired_data_topic(group_id: str) -> str:
    return f"qtpy/v1/{group_id}/acquired_data"


def get_broadcast_topic(group_id: str) -> str:
    return f"qtpy/v1/{group_id}/broadcast"


def get_command_topic(group_id: str, node_id: str) -> str:
    return f"qtpy/v1/{group_id}/{node_id}/command"


def get_descriptor_topic(group_id: str, node_id: str) -> str:
    return f"qtpy/v1/{group_id}/{node_id}/$DESCRIPTOR"


def get_log_topic(group_id: str) -> str:
    return f"qtpy/v1/{group_id}/log"


def get_result_topic(group_id: str, node_id: str) -> str:
    return f"qtpy/v1/{group_id}/{node_id}/result"


def format_mqtt_client_id(role: str, mac_address: str, pid: int) -> str:
    return f"{role}-{mac_address}-{pid}"
