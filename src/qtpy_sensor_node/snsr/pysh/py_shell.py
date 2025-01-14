# Reworked from https://github.com/adafruit/Adafruit_CircuitPython_Prompt_Toolkit


KEY_ESCAPE = b"\x1b"
KEY_CR = b"\x0d"
KEY_LF = b"\x0a"

KEY_OPEN_BRACKET = b"["
ORD_OPEN_BRACKET = ord(KEY_OPEN_BRACKET)

KEY_DEL = b"\x7f"
ORD_DEL = ord(KEY_DEL)


_PREVIOUS_ORD = 0

def __unused(*args):
    pass


def is_printable(char_ord):
    return char_ord > 31 and char_ord < 127


def debug_str(in_charbyte):
    return in_charbyte if is_printable(ord(in_charbyte)) else "?"


# plink only sends CR (like classic macOS)
# miniterm sends CRLF on Windows
# (untested: expecting Linux to send LF)
def _prompt(message="", *, input_=None, output=None, history=None, debug=False):
    global _PREVIOUS_ORD
    debug = True
    debug = print if debug else __unused
    output.write(message.encode("utf-8"))
    key_codes = []
    control_codes = []
    break_loop = False
    while (not key_codes or _PREVIOUS_ORD not in [ord(KEY_CR), ord(KEY_LF)]) and not break_loop:
        in_char = input_.read(1)
        in_ord = in_char[0]
        debug(f"* received {in_ord:4}d {debug_str(in_char):4} previous {_PREVIOUS_ORD:4}")

        if control_codes:
            debug(f"** entering control char sequence {control_codes}")
            control_codes.append(in_ord)
            if len(control_codes) == 2:
                if in_ord != ORD_OPEN_BRACKET:
                    debug(f"*** exiting control char sequence unsupported control code {in_ord:4}")
                    control_codes.clear()
            else:
                if (ord("0") <= in_ord <= ord("9")):
                    debug(f"*** skipping control char sequence non-numeral control code {in_ord:4} {debug_str(in_char):4}")
                else:
                    debug(f"*** processing control code {in_ord:4}")
                    control_codes.clear()
            continue
        if in_char in [KEY_ESCAPE]:
            debug("** detected control char sequence")
            control_codes.append(in_ord)
            continue
        if in_char == KEY_LF and _PREVIOUS_ORD == ord(KEY_CR):
            # Throw away the line feed from Windows
            debug("** completed windows EOL")
            continue
        if in_char in [KEY_CR, KEY_LF]:
            # Do not capture EOL characters
            # Filter for more
            # - F-keys start with \x01 and are either 2 more chars like 'bOP' 5 more chars like 'b[15~'
            # - Other non-printables
            # But allow
            # - Backspace \x08
            # - TAB \x09
            # - Delete
            debug("** skipped EOL char")
            pass
        else:
            debug(f"** accepted {in_char}")
            key_codes.append(in_ord)

        if in_ord == ORD_DEL:
            key_codes.pop()  # Remove the DEL char
            key_codes.pop()  # Remove the preceding char
            output.write(b"\b\x1b[K")  # Update the line
        elif in_char in [KEY_CR, KEY_LF]:
            # Do not echo EOL characters back to the user
            debug("** matched loop exit")
            break_loop = True
        else:
            output.write(in_char)

        _PREVIOUS_ORD = in_ord
        debug(f"\n** loop conditions key_codes: {key_codes} previous_ord: {_PREVIOUS_ORD} break: {break_loop}")
    output.write(b"\n")
    debug("encoded", key_codes)

    decoded = bytes(key_codes).decode("utf-8")
    return decoded


def prompt(message="", *, input=None, output=None):
    """Prompt the user for input over the ``input`` stream with the given
    ``message`` output on ``output``. Handles control characters for value editing."""
    # "input" and "output" are only on PromptSession in upstream "prompt_toolkit" but we use it for
    # prompts without history.
    # pylint: disable=redefined-builtin
    return _prompt(message, input_=input, output=output)


class PromptSession:
    """Session for multiple prompts. Stores common arguments to `prompt()` and
    history of commands for user selection."""

    def __init__(self, message="", *, input=None, output=None, history=None):
        # "input" and "output" are names used in upstream "prompt_toolkit" so we
        # use them too.
        # pylint: disable=redefined-builtin
        self.message = message
        self._input = input
        self._output = output

        self.history = history if history else InMemoryHistory()

    def prompt(self, message=None) -> str:
        """Prompt the user for input over the session's ``input`` with the given
        message or the default message."""
        message = message if message else self.message

        decoded = _prompt(
            message, input_=self._input, output=self._output, history=self.history
        )

        return decoded


# SPDX-FileCopyrightText: Copyright (c) 2023 Scott Shawcroft for Adafruit Industries
#
# SPDX-License-Identifier: MIT

"""Various ways of storing command history."""


class InMemoryHistory:
    """Simple in-memory history of commands. It is infinite size."""

    def __init__(self):
        self._history = []

    def append_string(self, string: str) -> None:
        """Append a string to the history of commands."""
        self._history.append(string)

    def get_strings(self) -> list[str]:
        """List of all past strings. Oldest first."""
        return self._history
