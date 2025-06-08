"""Node-side soil_swell app that reads AI and I2C channels."""

import analogio
import board

from snsr.node.classes import ActionInformation


def handle_message(received_action: ActionInformation) -> ActionInformation:
    """Handle a received action from the controlling host."""
    parameters = received_action.parameters["input"]
    adc_codes = do_analog_scan(channels=[], samples_to_average=parameters["samples_to_average"])
    response_action = ActionInformation(
        command=received_action.command,
        parameters={
            "output": adc_codes,
            "complete": True,
        },
        message_id=received_action.message_id,
    )
    return response_action


def do_analog_scan(channels: list[str], samples_to_average: int) -> list[float]:
    """Read the specified AI channels and return a list of averaged values."""
    results = []
    with Reserve_AI_Channels() as analog_input_channels:
        for channel_name, analog_input in sorted(analog_input_channels.items()):
            average_channel_code = adc_take_n(analog_input, samples_to_average)
            results.append(average_channel_code)
    return results


class Reserve_AI_Channels():
    def _reserve_all_channels(self):
        self.all_channels = {
            "AI0": analogio.AnalogIn(board.A0),
            "AI1": analogio.AnalogIn(board.A1),
            "AI2": analogio.AnalogIn(board.A2),
            "AI3": analogio.AnalogIn(board.A3),
            "AI4": analogio.AnalogIn(board.A4),
            "AI5": analogio.AnalogIn(board.A5),
            "AI6": analogio.AnalogIn(board.A6),
            "AI7": analogio.AnalogIn(board.A7),
        }
        return self.all_channels

    def _release_all_channels(self):
        for name, pin in self.all_channels.items():
            pin.deinit()

    def __enter__(self):
        return self._reserve_all_channels()

    def __exit__(self, exc_type, exc_value, traceback):
        self._release_all_channels()


def adc_take_n(from_ai_pin, count):
    total = 0
    for _ in range(count):
        total = total + from_ai_pin.value
    average = total / count
    return average
