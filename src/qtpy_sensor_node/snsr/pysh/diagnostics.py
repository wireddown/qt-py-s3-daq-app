"""Classes and functions for inspecting and tracing the shell's IO."""

from .linebuffer import ORD_TAB
from .py_shell import (
    _ORD_BACKSPACE,
    _ORD_CR,
    _ORD_DEL,
    _ORD_EOF,
    _ORD_ESC,
    _ORD_FKEY_START,
    _ORD_LF,
    _ORD_NUL,
    _ORD_OPEN_BRACKET,
    _ORD_SEMICOLON,
    PromptSession,
)

try:  # noqa: SIM105 -- contextlib is not available for CircuitPython
    from typing import BinaryIO, Callable
except ImportError:
    pass

_PRINTABLE_FOR_NONPRINTABLE = {
    _ORD_NUL: "(0)",
    _ORD_FKEY_START: "(F)",
    _ORD_BACKSPACE: "BS",
    ORD_TAB: "TAB",
    _ORD_LF: "LF",
    _ORD_CR: "CR",
    _ORD_EOF: "EOF",
    _ORD_ESC: "ESC",
    _ORD_DEL: "DEL",
}


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


class TracedSession:
    """A traced shell-like session for multiple interactive prompts that supports line editing."""

    def __init__(self, in_stream: BinaryIO, out_stream: BinaryIO, autoecho: bool = True) -> None:
        """."""
        self._autoecho = autoecho
        self._tracer = IOTracer(input_stream=in_stream, output_stream=out_stream)
        self._session = PromptSession(
            in_stream=self._tracer.input_stream,  # type: ignore -- we're swapping a builtin type for our own
            out_stream=self._tracer.output_stream,  # type: ignore -- we're swapping a builtin type for our own
        )

    def prompt(self, message: str) -> bytes:
        """."""
        response = self._session.prompt(message)
        if self._autoecho and self._tracer.traced_io_log:
            _ = [print(entry) for entry in self._tracer.traced_io_log]  # noqa: T201 -- use builtin to bypass self-tracing
            self._tracer.clear_log()
        return response.encode("UTF-8")

    @property
    def tracer(self) -> IOTracer:
        """."""
        return self._tracer


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
    in_ord = _ORD_NUL
    response_ords = []
    while in_ord != stop_ord:
        in_char = in_stream.read(1)
        in_ord = ord(in_char)
        response_ords.append(in_ord)
    return response_ords


def get_cursor_column(output: BinaryIO, in_stream: BinaryIO) -> int:
    """Get the cursor column from the remote console."""
    cursor_position_codes = console_query(
        query_sequence_ords=[_ORD_ESC, _ORD_OPEN_BRACKET, ord("6"), ord("n")],
        out_stream=output,
        in_stream=in_stream,
        stop_ord=ord("R"),
    )
    # Full response has format ESC[#;#R
    clipped = cursor_position_codes[2:-1]
    semicolon_index = clipped.index(_ORD_SEMICOLON)
    column_ords = clipped[semicolon_index + 1 :]
    return int(bytes(column_ords))


# Can we use input() to get a whole client-side edited line?
# - input() does     line editing
#           does     autocomplete on Python globals() with tab (not configurable)
#           does     support UTF-8 characters
#           does not support the F-keys but echoes the printable control codes and homes the cursor
def builtin_input(message: str = "") -> str:
    """Use the built-in 'input' function to prompt the user with message and return the response."""
    from_remote = input(message)
    return from_remote


# Can we set a new wrapped fuction on the serial object?
# - AttributeError: can't set attribute 'write'
def traced(traced_function: Callable, trace_list: list[str]) -> Callable:
    """When traced_function is called, add a message containing the parameters to trace_list."""

    def with_tracing(*args, **kwargs) -> Callable:  # noqa: ANN002 ANN003 -- wrapping an unknown function signature
        trace_list.append(f"{args} {kwargs}")
        return traced_function(*args, **kwargs)

    return with_tracing
