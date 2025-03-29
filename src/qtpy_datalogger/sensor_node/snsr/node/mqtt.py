"""
Functions used by hosts and nodes.

This module uses simple and explicit syntax to support CircuitPython clients.
"""


def get_domain() -> str:
    """Return the root segment for all qtpy-datalogger topics."""
    return "qtpy"


def get_api_version() -> str:
    """Return the version segment for the active qtpy-datalogger topics."""
    return "v1"


def get_mqtt_topics(group_id: str, node_id: str) -> dict[str, str]:
    """Return all the MQTT topics for the node specified by its group_id and node_id."""
    return {
        "acquired_data": f"qtpy/v1/{group_id}/acquired_data",
        "broadcast": f"qtpy/v1/{group_id}/broadcast",
        "command": f"qtpy/v1/{group_id}/{node_id}/command",
        "descriptor": f"qtpy/v1/{group_id}/{node_id}/$DESCRIPTOR",
        "log": f"qtpy/v1/{group_id}/log",
        "result": f"qtpy/v1/{group_id}/{node_id}/result",
    }


def get_acquired_data_topic(group_id: str) -> str:
    """Get the acquired_data topic for the specified group_id."""
    return f"qtpy/v1/{group_id}/acquired_data"


def get_broadcast_topic(group_id: str) -> str:
    """Get the broadcast topic for the specified group_id."""
    return f"qtpy/v1/{group_id}/broadcast"


def get_command_topic(group_id: str, node_id: str) -> str:
    """Get the command topic for the specified node_id in group_id."""
    return f"qtpy/v1/{group_id}/{node_id}/command"


def get_descriptor_topic(group_id: str, node_id: str) -> str:
    """Get the descriptor topic for the specified node_id in group_id."""
    return f"qtpy/v1/{group_id}/{node_id}/$DESCRIPTOR"


def get_log_topic(group_id: str) -> str:
    """Get the log topic for the specified group_id."""
    return f"qtpy/v1/{group_id}/log"


def get_result_topic(group_id: str, node_id: str) -> str:
    """Get the result topic for the specified node_id in group_id."""
    return f"qtpy/v1/{group_id}/{node_id}/result"


def node_from_topic(topic: str) -> str:
    """Return the node_id from the specified topic. Return an empty string if the topic is a group topic."""
    parts = topic.split("/")
    if len(parts) < 5:  # noqa: PLR2004 -- do not name this constant until it needs to be shared
        # Group-level topic like 'qtpy/v1/{group_id}/broadcast'
        return ""
    return parts[3]


def format_mqtt_client_id(role: str, mac_address: str, pid: int) -> str:
    """Format a unique MQTT client ID given the specified role, mac_address, and pid."""
    return f"{role}-{mac_address}-{pid}"
