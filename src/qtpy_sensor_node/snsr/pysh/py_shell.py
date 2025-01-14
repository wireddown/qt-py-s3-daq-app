"""Custom terminal prompt for interactive shells."""

# Reworked from https://github.com/adafruit/Adafruit_CircuitPython_Prompt_Toolkit

from .linebuffer import LineBuffer

try:  # noqa: SIM105 -- contextlib is not available for CircuitPython
    from typing import BinaryIO
except ImportError:
    pass

_ORD_NUL = 0x00
_ORD_FKEY_START = 0x01
_ORD_BACKSPACE = 0x08
_ORD_LF = 0x0A
_ORD_CR = 0x0D
_ORD_EOF = 0x1A
_ORD_ESC = 0x1B
_ORD_SPACE = 0x20
_ORD_SEMICOLON = 0x3B
_ORD_OPEN_BRACKET = 0x5B
_ORD_LOWER_B = 0x62
_ORD_TILDE = 0x7E
_ORD_DEL = 0x7F

_NOOP_ORDS = [
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
_CONTROL_PATTERN_NONE = 0
_CONTROL_PATTERN_MOVE_CURSOR_KEY = 1  # up, down, right, left, end, home: code 0x1B then '['  then the single-ord command: one of [ABCDFH]
_CONTROL_PATTERN_EDITOR_KEY = 2       # Ins Del PgUp PgDown             : code 0x1B then '['  then the single-ord command: one of [2356]                 then the close '~'
_CONTROL_PATTERN_LOWER_F_KEY = 3      # F1..F4                          : code 0x01 then 'bO' then the single-ord command: one of [PQRS]
_CONTROL_PATTERN_UPPER_F_KEY = 4      # F5..F12                         : code 0x01 then 'b[' then the   dual-ord command:        [1][5789] or [2][0123] then the close '~'
# fmt: on

_PREVIOUS_ORD = _ORD_NUL

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


def prompt(message: str = "", *, in_stream: BinaryIO, out_stream: BinaryIO) -> str:
    """Prompt the user for input with the given message."""
    return _prompt(message, in_stream, out_stream)


def _set_cursor_column(new_column: int, output: BinaryIO) -> None:
    """Set the cursor column in the remote console."""
    # ESC[##G to set cursor column
    column_number = [ord(x) for x in list(str(new_column))]
    column_number.append(ord("G"))
    _console_csi_command(column_number, output)


def _hide_cursor(output: BinaryIO) -> None:
    """Hide the cursor in the remote console."""
    # ESC[?25l to make cursor invisible
    hide_cursor = [ord(x) for x in list("?25l")]
    _console_csi_command(hide_cursor, output)


def _show_cursor(output: BinaryIO) -> None:
    """Show the cursor in the remote console."""
    # ESC[?25h to make cursor visible
    show_cursor = [ord(x) for x in list("?25h")]
    _console_csi_command(show_cursor, output)


def _console_csi_command(command_sequence_ords: list[int], output: BinaryIO) -> None:
    """Send a command prefixed with the control sequence introducer 'ESC ['."""
    full_command = [_ORD_ESC, _ORD_OPEN_BRACKET]
    full_command.extend(command_sequence_ords)
    output.write(bytes(full_command))


# CSI Ps P  Delete Ps Character(s) (default = 1)
#   - difficult to track tabs
# CSI Ps X  Erase Ps Character(s) (default = 1)
#   - untested
def _redraw_from_column(from_column: int, ords_to_draw: list[int], output: BinaryIO) -> None:
    """Erase the line starting at from_column and redraw ords_to_draw."""
    _set_cursor_column(from_column, output)

    # ESC[0K to erase from cursor to end of line
    erase_to_eol = [ord(x) for x in list("0K")]
    _console_csi_command(erase_to_eol, output)

    output.write(bytes(ords_to_draw))


# plink only sends CR (like classic macOS)
# miniterm sends CRLF on Windows
# (untested: expecting Linux to send LF)
def _prompt(message: str, in_stream: BinaryIO, out_stream: BinaryIO, history: InMemoryHistory | None = None) -> str:  # noqa: PLR0912 PLR0915 -- need many lines and statements to process control codes
    """Use a custom shell processor to prompt the user with message and return the response."""
    global _PREVIOUS_ORD  # noqa PLW0603 -- need a global to track EOL characters from Windows across calls
    out_stream.write(message.encode("UTF-8"))

    key_codes = LineBuffer(prompt_length=len(message))
    control_codes = []
    control_pattern = _CONTROL_PATTERN_NONE

    break_loop = False
    while (not key_codes.has_bytes() or _PREVIOUS_ORD not in [_ORD_CR, _ORD_LF]) and not break_loop:
        in_bytes = in_stream.read(1)
        in_ord = in_bytes[0]

        if control_codes:
            control_codes.append(in_ord)
            control_command_length = len(control_codes)
            if control_command_length == 2:  # noqa: PLR2004 -- this magic number is used as a length, has no separate meaning
                if control_codes[0] == _ORD_ESC and in_ord == _ORD_OPEN_BRACKET:
                    # Begin escape control sequence, assume cursor move until further reads show otherwise
                    control_pattern = _CONTROL_PATTERN_MOVE_CURSOR_KEY
                elif control_codes[0] == _ORD_FKEY_START and in_ord == _ORD_LOWER_B:
                    # Begin F-key control sequence, assume lower F-key until further reads show otherwise
                    control_pattern = _CONTROL_PATTERN_LOWER_F_KEY
                else:
                    # No handlers for other command sequences
                    control_codes.clear()
            elif control_command_length == 3:  # noqa: PLR2004 -- this magic number is used as a length, has no separate meaning
                if control_pattern == _CONTROL_PATTERN_MOVE_CURSOR_KEY:
                    if ord("0") <= in_ord <= ord("9"):
                        # We read more and learned we're reading an editor command
                        control_pattern = _CONTROL_PATTERN_EDITOR_KEY
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
                            _set_cursor_column(new_column, out_stream)

                        # Handling CSI control sequence complete
                        control_pattern = _CONTROL_PATTERN_NONE
                        control_codes.clear()
                elif control_pattern == _CONTROL_PATTERN_LOWER_F_KEY:
                    if in_ord == _ORD_OPEN_BRACKET:
                        # We read more and learned we're reading an upper F-key command
                        control_pattern = _CONTROL_PATTERN_UPPER_F_KEY
                    else:
                        # No handlers for lower F-key codes
                        pass
            elif control_command_length == 4:  # noqa: PLR2004 -- this magic number is used as a length, has no separate meaning
                if control_pattern == _CONTROL_PATTERN_EDITOR_KEY:
                    if in_ord == _ORD_TILDE:
                        if control_codes[2:-1] == [ord("3")]:
                            # Delete is ESC[3~
                            cursor_column, codes_to_redraw = key_codes.delete()
                            _hide_cursor(out_stream)
                            _redraw_from_column(cursor_column, codes_to_redraw, out_stream)
                            _set_cursor_column(cursor_column, out_stream)
                            _show_cursor(out_stream)
                        # Handling complete -- '~' terminated command
                        control_pattern = _CONTROL_PATTERN_NONE
                        control_codes.clear()
                elif control_pattern == _CONTROL_PATTERN_LOWER_F_KEY:
                    # Handling lower F-key control code complete -- fixed length command
                    control_pattern = _CONTROL_PATTERN_NONE
                    control_codes.clear()
            else:  # noqa: PLR5501 -- this level of if-else is for branching based on the command sequence length
                if in_ord == _ORD_TILDE:
                    # Handling upper F-key control code complete -- '~' terminated command
                    control_pattern = _CONTROL_PATTERN_NONE
                    control_codes.clear()
                else:
                    # No handlers for upper F-key codes
                    pass
            # Keep reading more control codes
            continue

        if in_ord in [_ORD_ESC, _ORD_FKEY_START]:
            # Begin a control sequence
            control_codes.append(in_ord)
            continue

        if in_ord == _ORD_LF and _PREVIOUS_ORD == _ORD_CR:
            # Throw away the line feed from Windows
            continue

        if in_ord in [_ORD_CR, _ORD_LF]:
            # Do not capture or handle EOL characters
            break_loop = True
        elif in_ord in _NOOP_ORDS:
            # No handlers for these
            pass
        elif in_ord == _ORD_BACKSPACE:
            # Handle backspace
            cursor_column, codes_to_redraw = key_codes.backspace()
            _hide_cursor(out_stream)
            _redraw_from_column(cursor_column, codes_to_redraw, out_stream)
            _set_cursor_column(cursor_column, out_stream)
            _show_cursor(out_stream)
        else:
            # Accept the user's input character
            old_column = key_codes.get_terminal_column()
            new_column, codes_to_redraw = key_codes.accept(in_ord)
            _hide_cursor(out_stream)
            _redraw_from_column(old_column, codes_to_redraw, out_stream)
            _set_cursor_column(new_column, out_stream)
            _show_cursor(out_stream)

        _PREVIOUS_ORD = in_ord

    out_stream.write(b"\n")

    decoded = key_codes.get_decoded_bytes()
    return decoded
