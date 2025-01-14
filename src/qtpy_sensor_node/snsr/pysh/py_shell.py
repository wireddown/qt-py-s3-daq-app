# Reworked from https://github.com/adafruit/Adafruit_CircuitPython_Prompt_Toolkit

ORD_NUL = 0x00
ORD_FKEY_START = 0x01
ORD_BACKSPACE = 0x08
ORD_TAB = 0x09
ORD_LF = 0x0A
ORD_CR = 0x0D
ORD_EOF = 0x1A
ORD_ESC = 0x1B
ORD_SPACE = 0x20
ORD_OPEN_BRACKET = 0x5B
ORD_LOWER_B = 0x62
ORD_TILDE = 0x7E
ORD_DEL = 0x7F

NOOP_ORDS = [
    # 0x00
    # 0x01
    0x02,
    0x03,
    0x04,
    0x05,
    0x06,
    0x07,
    # 0x08
    # 0x09
    # 0x0A
    0x0B,
    0x0C,
    # 0x0D
    0x0E,
    0x0F,
    0x10,
    0x11,
    0x12,
    0x13,
    0x14,
    0x15,
    0x16,
    0x17,
    0x18,
    0x19,
    # 0x1A
    # 0x1B
    0x1C,
    0x1D,
    0x1E,
    0x1F,
]

CONTROL_PATTERN_NONE = 0
CONTROL_PATTERN_MOVE_CURSOR_KEY = 1  # up, down, right, left, end, home: code 0x1B then '['  then the single-ord command: one of [ABCDFH]
CONTROL_PATTERN_EDITOR_KEY = 2       # Ins Del PgUp PgDown             : code 0x1B then '['  then the single-ord command: one of [2356]                 then the close '~'
CONTROL_PATTERN_LOWER_F_KEY = 3      # F1..F4                          : code 0x01 then 'bO' then the single-ord command: one of [PQRS]
CONTROL_PATTERN_UPPER_F_KEY = 4      # F5..F12                         : code 0x01 then 'b[' then the   dual-ord command:        [1][5789] or [2][0123] then the close '~'


_PREVIOUS_ORD = ORD_NUL

_PRINTABLE_FOR_NONPRINTABLE = {
    ORD_NUL: "(0)",
    ORD_FKEY_START: "(F)",
    ORD_BACKSPACE: "BS",
    ORD_TAB: "TAB",
    ORD_LF: "LF",
    ORD_CR: "CR",
    ORD_EOF: "EOF",
    ORD_ESC: "ESC",
    ORD_DEL: "DEL",
}

def __unused(*args):
    pass


def is_printable(char_ord):
    return char_ord > 31 and char_ord < 127


def debug_str(in_ordinal):
    return chr(in_ordinal) if is_printable(in_ordinal) else _PRINTABLE_FOR_NONPRINTABLE.get(in_ordinal, "?")


def erase_chars(count):
    erase_one = [ORD_BACKSPACE, ORD_SPACE, ORD_BACKSPACE]
    sequence = []
    for _ in range(count):
        sequence.extend(erase_one)
    return bytes(sequence).decode("UTF-8")


def console_query(query_sequence_ords, output, input, stop_ord):
    output.write(bytes(query_sequence_ords).decode("UTF-8"))
    in_ord = ORD_NUL
    response_ords = []
    while in_ord != stop_ord:
        in_char = input.read(1)
        in_ord = ord(in_char)
        response_ords.append(in_ord)
    return response_ords


# plink only sends CR (like classic macOS)
# miniterm sends CRLF on Windows
# (untested: expecting Linux to send LF)
def _prompt(message="", *, input_=None, output=None, history=None, debug=False):
    global _PREVIOUS_ORD
    debug = False
    debug = print if debug else __unused
    output.write(message.encode("UTF-8"))
    cursor_position_codes = console_query(
        query_sequence_ords=[ORD_ESC, ORD_OPEN_BRACKET, ord("6"), ord("n")],
        output=output,
        input=input_,
        stop_ord=ord("R")
    )
    #print((f"prompt length: {len(message)} cursor position: {[debug_str(x) for x in cursor_position_codes]}"))
    key_codes = LineBuffer(prompt_length=len(message))
    control_codes = []
    control_pattern = CONTROL_PATTERN_NONE
    break_loop = False
    while (not key_codes.has_bytes() or _PREVIOUS_ORD not in [ORD_CR, ORD_LF]) and not break_loop:
        in_char = input_.read(1)
        in_ord = ord(in_char)
        debug(f"* received {in_ord:4}d {debug_str(in_ord):4} previous {debug_str(_PREVIOUS_ORD):4}")

        if control_codes:
            control_codes.append(in_ord)
            control_command_length = len(control_codes)
            debug(f"** entering control char sequence {control_codes}")
            if control_command_length == 2:
                if control_codes[0] == ORD_ESC and in_ord == ORD_OPEN_BRACKET:
                    # begin escape control sequence
                    debug(f"** detected ESC control char sequence {control_codes}")
                    control_pattern = CONTROL_PATTERN_MOVE_CURSOR_KEY  # Assume until further reads show otherwise
                elif control_codes[0] == ORD_FKEY_START and in_ord == ORD_LOWER_B:
                    # begin f-key control sequence
                    debug(f"** detected F-key control char sequence {control_codes}")
                    control_pattern = CONTROL_PATTERN_LOWER_F_KEY  # Assume until further reads show otherwise
                else:
                    debug(f"*** exiting control char sequence unsupported control code {debug_str(in_ord):4}")
                    control_codes.clear()
            elif control_command_length == 3:
                if control_pattern == CONTROL_PATTERN_MOVE_CURSOR_KEY:
                    if (ord("0") <= in_ord <= ord("9")):
                        control_pattern = CONTROL_PATTERN_EDITOR_KEY  # We read more and learned we're reading an editor command
                        debug(f"*** processing editor control code {debug_str(in_ord):4}")
                    else:
                        debug(f"*** completed move-cursor control code {debug_str(in_ord):4}")
                        control_pattern = CONTROL_PATTERN_NONE
                        control_codes.clear()
                elif control_pattern == CONTROL_PATTERN_LOWER_F_KEY:
                    if in_ord == ORD_OPEN_BRACKET:
                        control_pattern = CONTROL_PATTERN_UPPER_F_KEY  # We read more and learned we're reading an upper F-key command
                        debug(f"** detected upper F-key control char sequence {control_codes}")
                    else:
                        debug(f"*** processing lower F-key control code {debug_str(in_ord):4}")
            elif control_command_length == 4:
                if control_pattern == CONTROL_PATTERN_EDITOR_KEY:
                    if in_ord == ORD_TILDE:
                        debug(f"*** completed processing editor control code {debug_str(in_ord):4}")
                        control_pattern = CONTROL_PATTERN_NONE
                        control_codes.clear()
                elif control_pattern == CONTROL_PATTERN_LOWER_F_KEY:
                    debug(f"*** completed processing lower F-key control code {debug_str(in_ord):4}")
                    control_pattern = CONTROL_PATTERN_NONE
                    control_codes.clear()
            else:
                if in_ord == ORD_TILDE:
                    debug(f"*** completed processing upper F-key control code {debug_str(in_ord):4}")
                    control_pattern = CONTROL_PATTERN_NONE
                    control_codes.clear()
                else:
                    debug(f"*** processing upper F-key control code {debug_str(in_ord):4}")
            continue

        if in_ord in [ORD_ESC, ORD_FKEY_START]:
            debug("** detected control char sequence")
            control_codes.append(in_ord)
            continue

        if in_ord == ORD_LF and _PREVIOUS_ORD == ORD_CR:
            # Throw away the line feed from Windows
            debug("** completed windows EOL")
            continue

        if in_ord in [ORD_CR, ORD_LF]:
            # Do not capture EOL characters
            debug("** skipped EOL char")
            debug("** matched loop exit")
            break_loop = True
        elif in_ord in NOOP_ORDS:
            # Filter for more
            # - Other non-printables
            # But allow
            # - Backspace \x08
            # - TAB \x09
            # - Delete
            debug(f"** skipping non printable char {in_ord}")
        elif in_ord == ORD_BACKSPACE:
            deleted_count = key_codes.backspace()
            if deleted_count:
                output.write(erase_chars(deleted_count))
        else:
            debug(f"** accepted {debug_str(in_ord)}")
            key_codes.accept(in_ord)
            output.write(in_char)

        _PREVIOUS_ORD = in_ord
        debug(f"\n** loop conditions key_codes: {key_codes.ord_codes} previous_ord: {debug_str(_PREVIOUS_ORD)} break: {break_loop}")
        response = console_query(
            query_sequence_ords=[ORD_ESC, ORD_OPEN_BRACKET, ord("6"), ord("n")],
            output=output,
            input=input_,
            stop_ord=ord("R")
        )
        debug(f"cursor position: {[debug_str(x) for x in response]}")
    output.write(b"\n")
    debug("encoded", key_codes.get_decoded_bytes())

    decoded = key_codes.get_decoded_bytes()
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


class LineBuffer:
    def __init__(self, prompt_length, tab_size=8):
        self.ord_codes = []
        self.index = 0
        self.prompt_length = prompt_length
        self.tab_size = tab_size
        self.column = self.get_column()

    def has_bytes(self):
        return len(self.ord_codes) > 0

    def get_decoded_bytes(self):
        return bytes(self.ord_codes).decode("UTF-8")

    def accept(self, ord_code):
        self.ord_codes.insert(self.index, ord_code)
        self.index += 1
        self.column = self.get_column()

    def move_right(self):
        if self.index == len(self.ord_codes):
            return False
        else:
            self.index += 1
            return True

    def move_left(self):
        if self.index == 0:
            return False
        else:
            self.index -= 1
            return True

    def move_home(self):
        while self.move_left():
            pass

    def move_end(self):
        while self.move_right():
            pass

    def get_column(self):
        first_user_column = self.prompt_length
        column = first_user_column
        for ord in self.ord_codes:
            if ord == ORD_TAB:
                tab_stops, remaining_columns = divmod(column, self.tab_size)
                to_next_tab_stop = self.tab_size - remaining_columns
                column += to_next_tab_stop
            else:
                column += 1
        return column

    def delete(self):
        if self.index == len(self.ord_codes):
            deleted_count = 0
        else:
            deleted = self.ord_codes.pop(self.index)
            deleted_count = self.column - self.get_column()
        self.column = self.get_column()
        return deleted_count

    def backspace(self):
        if self.move_left():
            return self.delete()
        else:
            return 0


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
