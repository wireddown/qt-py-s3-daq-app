"""Custom terminal prompt for interactive shells."""

# Reworked from https://github.com/adafruit/Adafruit_CircuitPython_Prompt_Toolkit

try:  # noqa: SIM105 -- contextlib is not available for CircuitPython
    from typing import BinaryIO, Callable
except ImportError:
    pass

ORD_NUL = 0x00
ORD_FKEY_START = 0x01
ORD_BACKSPACE = 0x08
ORD_TAB = 0x09
ORD_LF = 0x0A
ORD_CR = 0x0D
ORD_EOF = 0x1A
ORD_ESC = 0x1B
ORD_SPACE = 0x20
ORD_SEMICOLON = 0x3B
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

# fmt: off
CONTROL_PATTERN_NONE = 0
CONTROL_PATTERN_MOVE_CURSOR_KEY = 1  # up, down, right, left, end, home: code 0x1B then '['  then the single-ord command: one of [ABCDFH]
CONTROL_PATTERN_EDITOR_KEY = 2       # Ins Del PgUp PgDown             : code 0x1B then '['  then the single-ord command: one of [2356]                 then the close '~'
CONTROL_PATTERN_LOWER_F_KEY = 3      # F1..F4                          : code 0x01 then 'bO' then the single-ord command: one of [PQRS]
CONTROL_PATTERN_UPPER_F_KEY = 4      # F5..F12                         : code 0x01 then 'b[' then the   dual-ord command:        [1][5789] or [2][0123] then the close '~'
# fmt: on

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


class InMemoryHistory:
    """An in-memory history of commands, infinite in size."""

    def __init__(self) -> None:
        """Create a new in-memory history buffer."""
        self._history = []

    def append_string(self, string: str) -> None:
        """Append a string to the history of commands."""
        self._history.append(string)

    def get_strings(self) -> list[str]:
        """List of all past strings. Oldest first."""
        return self._history


def is_printable(char_ord: int) -> bool:
    """Return true if the specified ordinal is printable in a terminal."""
    # https://ss64.com/ascii.html
    return char_ord > 31 and char_ord < 127  # noqa: PLR2004 -- ordinals /are/ magic numbers


def debug_str(in_ordinal: int) -> str:
    """Return a printable substitute for a non-printable ordinal."""
    return chr(in_ordinal) if is_printable(in_ordinal) else _PRINTABLE_FOR_NONPRINTABLE.get(in_ordinal, "?")


def console_query(
    query_sequence_ords: list[int], out_stream: BinaryIO, in_stream: BinaryIO, stop_ord: int
) -> list[int]:
    """Send the query_sequence_ords to the remote console and return its response."""
    out_stream.write(bytes(query_sequence_ords))
    in_ord = ORD_NUL
    response_ords = []
    while in_ord != stop_ord:
        in_char = in_stream.read(1)
        in_ord = ord(in_char)
        response_ords.append(in_ord)
    return response_ords


def get_cursor_column(output: BinaryIO, in_stream: BinaryIO) -> int:
    """Get the cursor column from the remote console."""
    cursor_position_codes = console_query(
        query_sequence_ords=[ORD_ESC, ORD_OPEN_BRACKET, ord("6"), ord("n")],
        out_stream=output,
        in_stream=in_stream,
        stop_ord=ord("R"),
    )
    # Full response has format ESC[#;#R
    clipped = cursor_position_codes[2:-1]
    semicolon_index = clipped.index(ORD_SEMICOLON)
    column_ords = clipped[semicolon_index + 1 :]
    return int(bytes(column_ords))


def set_cursor_column(new_column: int, output: BinaryIO) -> None:
    """Set the cursor column in the remote console."""
    # ESC[##G to set cursor column
    column_number = [ord(x) for x in list(str(new_column))]
    column_number.append(ord("G"))
    console_csi_command(column_number, output)


def hide_cursor(output: BinaryIO) -> None:
    """Hide the cursor in the remote console."""
    # ESC[?25l to make cursor invisible
    hide_cursor = [ord(x) for x in list("?25l")]
    console_csi_command(hide_cursor, output)


def show_cursor(output: BinaryIO) -> None:
    """Show the cursor in the remote console."""
    # ESC[?25h to make cursor visible
    show_cursor = [ord(x) for x in list("?25h")]
    console_csi_command(show_cursor, output)


def console_csi_command(command_sequence_ords: list[int], output: BinaryIO) -> None:
    """Send a command prefixed with the control sequence introducer 'ESC ['."""
    full_command = [ORD_ESC, ORD_OPEN_BRACKET]
    full_command.extend(command_sequence_ords)
    output.write(bytes(full_command))


# CSI Ps P  Delete Ps Character(s) (default = 1)
#   - difficult to track tabs
# CSI Ps X  Erase Ps Character(s) (default = 1)
#   - untested
def redraw_from_column(from_column: int, ords_to_draw: list[int], output: BinaryIO) -> None:
    """Erase the line starting at from_column and redraw ords_to_draw."""
    set_cursor_column(from_column, output)

    # ESC[0K to erase from cursor to end of line
    erase_to_eol = [ord(x) for x in list("0K")]
    console_csi_command(erase_to_eol, output)

    output.write(bytes(ords_to_draw))


# - use input() to get a whole client-side edited line?
## -- input() does     line editing
##            does     autocomplete on globals() with tab (not configurable)
##            does     support UTF-8 characters
##            does not support the F-keys but echoes the printable control codes and homes the cursor
def _prompt2(message: str = "") -> str:
    """Use the built-in 'input' function to prompt the user with message and return the response."""
    from_remote = input(message)
    return from_remote


# AttributeError: can't set attribute 'write'
def traced(traced_function: Callable, trace_list: list[str]) -> Callable:
    """When traced_function is called, add a message containing the parameters to trace_list."""

    def with_tracing(*args, **kwargs) -> Callable:  # noqa: ANN002 ANN003 -- wrapping an unknown function signature
        trace_list.append(f"{args} {kwargs}")
        return traced_function(*args, **kwargs)

    return with_tracing


# plink only sends CR (like classic macOS)
# miniterm sends CRLF on Windows
# (untested: expecting Linux to send LF)
def _prompt(message: str, in_stream: BinaryIO, out_stream: BinaryIO, history: InMemoryHistory | None = None) -> str:  # noqa: PLR0912 PLR0915 -- need many lines and statements to process control codes
    """Use a custom shell processor to prompt the user with message and return the response."""
    global _PREVIOUS_ORD  # noqa PLW0603 -- need a global to track EOL characters from Windows across calls
    out_stream.write(message.encode("UTF-8"))

    key_codes = LineBuffer(prompt_length=len(message))
    control_codes = []
    control_pattern = CONTROL_PATTERN_NONE

    break_loop = False
    while (not key_codes.has_bytes() or _PREVIOUS_ORD not in [ORD_CR, ORD_LF]) and not break_loop:
        in_bytes = in_stream.read(1)
        in_ord = in_bytes[0]

        if control_codes:
            control_codes.append(in_ord)
            control_command_length = len(control_codes)
            if control_command_length == 2:  # noqa: PLR2004 -- this magic number is used as a length, has no separate meaning
                if control_codes[0] == ORD_ESC and in_ord == ORD_OPEN_BRACKET:
                    # Begin escape control sequence, assume cursor move until further reads show otherwise
                    control_pattern = CONTROL_PATTERN_MOVE_CURSOR_KEY
                elif control_codes[0] == ORD_FKEY_START and in_ord == ORD_LOWER_B:
                    # Begin F-key control sequence, assume lower F-key until further reads show otherwise
                    control_pattern = CONTROL_PATTERN_LOWER_F_KEY
                else:
                    # No handlers for other command sequences
                    control_codes.clear()
            elif control_command_length == 3:  # noqa: PLR2004 -- this magic number is used as a length, has no separate meaning
                if control_pattern == CONTROL_PATTERN_MOVE_CURSOR_KEY:
                    if ord("0") <= in_ord <= ord("9"):
                        # We read more and learned we're reading an editor command
                        control_pattern = CONTROL_PATTERN_EDITOR_KEY
                    else:
                        # We're reading a letter or symbol command ESC[*
                        old_column = key_codes.get_terminal_column()
                        new_column = old_column
                        if in_ord == ord("C"):
                            new_column = key_codes.move_right()
                        elif in_ord == ord("D"):
                            new_column = key_codes.move_left()
                        elif in_ord == ord("F"):
                            new_column = key_codes.move_end()
                        elif in_ord == ord("H"):
                            new_column = key_codes.move_home()

                        if new_column != old_column:
                            set_cursor_column(new_column, out_stream)

                        # Handling CSI control sequence complete
                        control_pattern = CONTROL_PATTERN_NONE
                        control_codes.clear()
                elif control_pattern == CONTROL_PATTERN_LOWER_F_KEY:
                    if in_ord == ORD_OPEN_BRACKET:
                        # We read more and learned we're reading an upper F-key command
                        control_pattern = CONTROL_PATTERN_UPPER_F_KEY
                    else:
                        # No handlers for lower F-key codes
                        pass
            elif control_command_length == 4:  # noqa: PLR2004 -- this magic number is used as a length, has no separate meaning
                if control_pattern == CONTROL_PATTERN_EDITOR_KEY:
                    if in_ord == ORD_TILDE:
                        if control_codes[2:-1] == [ord("3")]:
                            # Delete is ESC[3~
                            cursor_column, codes_to_redraw = key_codes.delete()
                            hide_cursor(out_stream)
                            redraw_from_column(cursor_column, codes_to_redraw, out_stream)
                            set_cursor_column(cursor_column, out_stream)
                            show_cursor(out_stream)
                        # Handling complete -- '~' terminated command
                        control_pattern = CONTROL_PATTERN_NONE
                        control_codes.clear()
                elif control_pattern == CONTROL_PATTERN_LOWER_F_KEY:
                    # Handling lower F-key control code complete -- fixed length command
                    control_pattern = CONTROL_PATTERN_NONE
                    control_codes.clear()
            else:  # noqa: PLR5501 -- this level of if-else is for branching based on the command sequence length
                if in_ord == ORD_TILDE:
                    # Handling upper F-key control code complete -- '~' terminated command
                    control_pattern = CONTROL_PATTERN_NONE
                    control_codes.clear()
                else:
                    # No handlers for upper F-key codes
                    pass
            # Keep reading more control codes
            continue

        if in_ord in [ORD_ESC, ORD_FKEY_START]:
            # Begin a control sequence
            control_codes.append(in_ord)
            continue

        if in_ord == ORD_LF and _PREVIOUS_ORD == ORD_CR:
            # Throw away the line feed from Windows
            continue

        if in_ord in [ORD_CR, ORD_LF]:
            # Do not capture or handle EOL characters
            break_loop = True
        elif in_ord in NOOP_ORDS:
            # No handlers for these
            pass
        elif in_ord == ORD_BACKSPACE:
            # Handle backspace
            cursor_column, codes_to_redraw = key_codes.backspace()
            hide_cursor(out_stream)
            redraw_from_column(cursor_column, codes_to_redraw, out_stream)
            set_cursor_column(cursor_column, out_stream)
            show_cursor(out_stream)
        else:
            # Accept the user's input character
            old_column = key_codes.get_terminal_column()
            new_column, codes_to_redraw = key_codes.accept(in_ord)
            hide_cursor(out_stream)
            redraw_from_column(old_column, codes_to_redraw, out_stream)
            set_cursor_column(new_column, out_stream)
            show_cursor(out_stream)

        _PREVIOUS_ORD = in_ord

    out_stream.write(b"\n")

    decoded = key_codes.get_decoded_bytes()
    return decoded


def prompt(message: str = "", *, in_stream: BinaryIO, out_stream: BinaryIO) -> str:
    """Prompt the user for input with the given message."""
    return _prompt(message, in_stream, out_stream)


class TracedReader:
    """A stream reader that logs bytes read from the stream."""

    def __init__(self, input_stream: BinaryIO, shared_tracelog: list[str], log_prefix: str | None = None) -> None:
        """
        Create a TracedReader that logs all reads from input_stream into shared_tracelog.

        input_stream must support a function with signature 'read(int) -> bytes'.
        """
        self._input_stream = input_stream
        self._shared_tracelog = shared_tracelog
        self._log_prefix = log_prefix if log_prefix is not None else type(self)
        self._trace(f"tracing input from {type(input_stream)}")

    def read(self, byte_count: int) -> bytes:
        """Read from the input_stream and log it."""
        input_chars = self._input_stream.read(byte_count)
        self._trace(f" in   {input_chars}")
        return input_chars

    def _trace(self, message: str) -> None:
        self._shared_tracelog.append(f"{self._log_prefix}{message}")


class TracedWriter:
    """A stream writer that logs bytes written to the stream."""

    def __init__(self, output_stream: BinaryIO, shared_tracelog: list[str], log_prefix: str | None = None) -> None:
        """
        Create a TracedWriter that logs all writes to output_stream into shared_tracelog.

        output_stream must support a function with signature 'write(bytes) -> None'.
        """
        self._output_stream = output_stream
        self._shared_tracelog = shared_tracelog
        self._log_prefix = log_prefix if log_prefix is not None else type(self)
        self._trace(f"tracing output from {type(output_stream)}")

    def write(self, encoded_string: bytes) -> None:
        """Read to the output_stream and log it."""
        self._trace(f"out > {encoded_string}")
        self._output_stream.write(encoded_string)

    def _trace(self, message: str) -> None:
        self._shared_tracelog.append(f"{self._log_prefix}{message}")


class IOTracer:
    """An IO stream tracer that logs bytes read and written to the streams."""

    def __init__(self, input_stream: BinaryIO, output_stream: BinaryIO) -> None:
        """Create an IOTracer that logs all IO with input_stream and output_stream."""
        self._shared_tracelog = []
        self._traced_input = TracedReader(input_stream, self._shared_tracelog, log_prefix="")
        self._traced_output = TracedWriter(output_stream, self._shared_tracelog, log_prefix="")

    @property
    def input_stream(self) -> TracedReader:
        """Return the TracedReader used by the IOTracer."""
        return self._traced_input

    @property
    def output_stream(self) -> TracedWriter:
        """Return the TracedWriter used by the IOTracer."""
        return self._traced_output

    @property
    def traced_io_log(self) -> list[str]:
        """Return a copy of the logged IO traces from the streams."""
        return self._shared_tracelog.copy()

    def clear_log(self) -> None:
        """Clear the trace log."""
        self._shared_tracelog.clear()


class PromptSession:
    """A shell-like session for multiple interactive prompts that supports line editing and command history."""

    def __init__(
        self,
        in_stream: BinaryIO,
        out_stream: BinaryIO,
        default_prompt: str = "",
        history: InMemoryHistory | None = None,
    ) -> None:
        """Create a PromptSession using in_stream and out_stream for IO, with an optional default_prompt and command history buffer."""
        self.default_prompt = default_prompt
        self.in_stream = in_stream
        self.out_stream = out_stream
        self.history = history if history else InMemoryHistory()

    def prompt(self, message: str | None = None) -> str:
        """Prompt the user for input with the given message or the default message."""
        message = message if message else self.default_prompt

        decoded = _prompt(message, in_stream=self.in_stream, out_stream=self.out_stream, history=self.history)

        return decoded


class LineBuffer:
    """A user input buffer that supports tabs, moving the cursor, deleting, and backspacing."""

    def __init__(self, prompt_length: int, tab_size: int = 8) -> None:
        """Create a new LineBuffer for interactive user input."""
        self._first_terminal_column = 1
        self.prompt_length = prompt_length
        self.tab_size = tab_size
        self.ord_codes = []
        self.input_cursor = 0
        self.terminal_column = self._get_column_at_cursor()

    def has_bytes(self) -> bool:
        """Return whether the buffer has contents."""
        return len(self.ord_codes) > 0

    def get_decoded_bytes(self) -> str:
        """Get the buffer as a UTF-8 string."""
        return bytes(self.ord_codes).decode("UTF-8")

    def get_terminal_column(self) -> int:
        """Return the terminal column of the input cursor."""
        return self.terminal_column

    def accept(self, ord_code: int) -> tuple[int, list[int]]:
        """
        Insert a new ordinate at the input cursor.

        Returns a tuple of the new terminal column and a slice of the
        input buffer from the new ordinate to the end of the buffer.
        """
        self.ord_codes.insert(self.input_cursor, ord_code)
        code_with_remaining_line = self.ord_codes[self.input_cursor :]
        self.input_cursor += 1
        self.terminal_column = self._get_column_at_cursor()
        return self.terminal_column, code_with_remaining_line

    def delete(self) -> tuple[int, list[int]]:
        """
        Delete the ordinate after the input cursor.

        Returns a tuple of the new terminal column and a slice of the
        input buffer from the cursor to the end of the buffer.
        """
        if self.input_cursor < len(self.ord_codes):
            _ = self.ord_codes.pop(self.input_cursor)
            self.terminal_column = self._get_column_at_cursor()
        remaining_line = self.ord_codes[self.input_cursor :]
        return self.terminal_column, remaining_line

    def backspace(self) -> tuple[int, list[int]]:
        """
        Delete the ordinate before the input cursor.

        Returns a tuple of the new terminal column and a slice of the
        input buffer from the cursor to the end of the buffer.
        """
        old_column = self.terminal_column
        new_column = self.move_left()
        if new_column != old_column:
            self.delete()
        remaining_line = self.ord_codes[self.input_cursor :]
        return new_column, remaining_line

    def move_home(self) -> int:
        """
        Move the input cursor to the beginning of the buffer.

        Returns the new terminal column of the input cursor.
        """
        self.input_cursor = 0
        self.terminal_column = self._get_column_at_cursor()
        return self.terminal_column

    def move_end(self) -> int:
        """
        Move the input cursor to the end of the buffer.

        Returns the new terminal column of the input cursor.
        """
        self.input_cursor = len(self.ord_codes)
        self.terminal_column = self._get_column_at_cursor()
        return self.terminal_column

    def move_left(self) -> int:
        """
        Move input cursor one character to the left.

        Returns the new terminal column of the input cursor.
        """
        if self.input_cursor > 0:
            move_distance = self._get_column_move_distance_for_cursor_move(-1)
            self.input_cursor -= 1
            self.terminal_column -= move_distance
        return self.terminal_column

    def move_right(self) -> int:
        """
        Move the input cursor one character to the right.

        Returns the new terminal column of the input cursor.
        """
        if self.input_cursor < len(self.ord_codes):
            move_distance = self._get_column_move_distance_for_cursor_move(1)
            self.input_cursor += 1
            self.terminal_column += move_distance
        return self.terminal_column

    def _get_column_at_cursor(self) -> int:
        codes_to_cursor = self.ord_codes[: self.input_cursor]
        column = self._calculate_column_for_codes(codes_to_cursor)
        return column

    def _get_column_move_distance_for_cursor_move(self, cursor_move: int) -> int:
        index_after_move = self.input_cursor + cursor_move
        codes_after_move = self.ord_codes[:index_after_move]
        new_column = self._calculate_column_for_codes(codes_after_move)
        return abs(self.terminal_column - new_column)

    def _calculate_column_for_codes(self, codes: list[int]) -> int:
        first_user_column = self._first_terminal_column + self.prompt_length
        terminal_column = first_user_column
        for ord_code in codes:
            if ord_code == ORD_TAB:
                one_based_x = terminal_column - self._first_terminal_column
                one_based_remainder = one_based_x % self.tab_size
                to_next_tab_stop = self.tab_size - one_based_remainder
                terminal_column += to_next_tab_stop
            else:
                terminal_column += 1
        return terminal_column
