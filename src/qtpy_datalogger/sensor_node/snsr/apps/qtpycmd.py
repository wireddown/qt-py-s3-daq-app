"""App that queries and demonstrates board resources like IO pins."""

from snsr.apps import SnsrApp, use_echo
from snsr.node.classes import ActionInformation
from snsr.settings import settings


class QtpyCmdApp(SnsrApp):
    """Respond to 'custom' commands that start with 'qtpycmd '."""

    def handle_message(self) -> ActionInformation:
        """Handle a received action from the controlling host."""
        system_command = self.action.parameters["input"]
        parts = system_command.split(" ")
        verb = parts[1]
        if verb == "get_apps":
            return handle_get_apps(self.action, parts)
        if verb == "stats":
            return handle_get_stats(self.action, parts)
        if verb == "config":
            return handle_do_config(self.action, parts)
        if verb == "pixel":
            return handle_do_pixel(self.action, parts)
        if verb == "read":
            return handle_do_analog_read(self.action, parts)

        # Fallback to echo app
        return use_echo(self.action)

    def did_handle_message(self) -> None:
        """Update the node after handling a message."""


def create_app(received_action: ActionInformation) -> SnsrApp:
    """Return a new QtpyCmdApp."""
    return QtpyCmdApp(received_action)


def build_response(received_action: ActionInformation, message: object) -> ActionInformation:
    """Create an action response with the specified message."""
    response_action = ActionInformation(
        command=received_action.parameters["input"],
        parameters={
            "output": message,
            "complete": True,
        },
        message_id=received_action.message_id,
    )
    return response_action


def handle_get_apps(received_action: ActionInformation, command_args: list[str]) -> ActionInformation:
    """Handle the 'qtpycmd get_apps' action."""
    apps = settings.app_catalog
    return build_response(received_action, sorted(apps))


def handle_get_stats(received_action: ActionInformation, command_args: list[str]) -> ActionInformation:
    """Handle the 'qtpycmd stats' action."""
    import gc

    gc.collect()
    return build_response(
        received_action,
        f"{settings.used_kb:.3f} kB used | {settings.free_kb:.3f} kB free | {settings.uptime:.2f} s uptime",
    )


def handle_do_config(received_action: ActionInformation, command_args: list[str]) -> ActionInformation:
    """Handle the 'qtpycmd config' action."""
    arg_count = len(command_args)
    if arg_count <= 3:
        return use_echo(received_action)

    config_verb = command_args[2]
    if config_verb not in ["get", "set"]:
        return use_echo(received_action)

    config_key = command_args[3]
    if config_verb == "get":
        config_setting = settings.get_app_settings("qtpycmd").get(config_key, "")
        return build_response(received_action, message=f"{config_key}: {config_setting}")

    if command_args == 5:
        return use_echo(received_action)
    config_setting = " ".join(command_args[4:])
    settings.update_app_settings("qtpycmd", {config_key: config_setting})
    return build_response(received_action, message=f"{config_key}: {config_setting}")


def handle_do_pixel(received_action: ActionInformation, command_args: list[str]) -> ActionInformation:
    """Handle the 'qtpycmd pixel' action."""
    arg_count = len(command_args)
    if arg_count <= 2:
        return use_echo(received_action)

    pixel_verb = command_args[2]
    if pixel_verb != "blink":
        return use_echo(received_action)

    pixel_color = 0x2200AA
    if arg_count >= 4:
        try:
            pixel_color = int(command_args[3], 0)
        except ValueError:
            pass

    from snsr.core import blink_neopixel

    blink_neopixel(pixel_color)
    return build_response(received_action, f"Used color 0x{pixel_color:06x}")


def handle_do_analog_read(received_action: ActionInformation, command_args: list[str]) -> ActionInformation:
    """Handle the 'qtpycmd read' action."""
    arg_count = len(command_args)
    if arg_count <= 2:
        return use_echo(received_action)

    channels = [pin_name for pin_name in command_args[2:] if pin_name.startswith("A")]
    if not channels:
        return use_echo(received_action)

    from snsr.core import do_analog_scan

    count = 15
    voltages = do_analog_scan(channels, count)
    return build_response(received_action, f"{voltages} (raw ADC codes, {count} samples averaged)")
