"""Acceptance tests for the py_shell module."""

import io
import itertools

import pytest

from qtpy_datalogger.sensor_node.snsr.pysh import py_shell

_CODES_FOR_KEY_NAME = {
    "left arrow": b"\x1b[D",
    "right arrow": b"\x1b[C",
    "up arrow": b"\x1b[A",
    "down arrow": b"\x1b[B",
    "home": b"\x1b[H",
    "end": b"\x1b[F",
    "backspace": b"\x08",
    "delete": b"\x1b[3~",
    "F1": b"\x01bOP",
    "F2": b"\x01bOQ",
    "F3": b"\x01bOR",
    "F4": b"\x01bOS",
    "F5": b"\x01b[15~",
    "F6": b"\x01b[17~",
    "F7": b"\x01b[18~",
    "F8": b"\x01b[19~",
    "F9": b"\x01b[20~",
    "F10": b"\x01b[21~",
}


def test_custom_shell_prompt() -> None:
    """Does it present the shell prompt?"""
    shell_prompt = "qtpy $"
    input_buffer = io.BytesIO(initial_bytes=b"")
    output_buffer = io.BytesIO(initial_bytes=b"")
    prompt_session = py_shell.PromptSession(in_stream=input_buffer, out_stream=output_buffer)

    with pytest.raises(IndexError):
        # Input stream is empty, and without the EOL character to end user input and exit the prompt loop,
        # the backing io.BytesIO does not block on .read(1), unlike a serial port, and instead
        # immediately returns an empty bytes array, which cannot be indexed for the first (and only) byte.
        _ = prompt_session.prompt(message=shell_prompt)

    actual_output = output_buffer.getvalue()
    assert len(actual_output) > 0
    assert actual_output == shell_prompt.encode("UTF-8")


@pytest.mark.parametrize(
    ("in_eol_bytes", "assert_message"),
    [
        (b"\n", "Linux EOL failed to complete user input"),
        (b"\r", "Classic macOS EOL failed to complete user input"),
        (b"\r\n", "Windows EOL failed to complete user input"),
    ],
)
def test_prompt_exits_on_eol(in_eol_bytes: bytes, assert_message: str) -> None:
    """Does it return a response after the EOL character?"""
    shell_prompt = "qtpy $"
    input_buffer = io.BytesIO(initial_bytes=in_eol_bytes)
    output_buffer = io.BytesIO(initial_bytes=b"")
    prompt_session = py_shell.PromptSession(in_stream=input_buffer, out_stream=output_buffer)
    response = prompt_session.prompt(message=shell_prompt)

    expected_output = f"{shell_prompt}\n"
    actual_output = output_buffer.getvalue()
    assert len(actual_output) > 0
    assert actual_output == expected_output.encode("UTF-8"), assert_message
    assert len(response) == 0


def test_printable_input() -> None:
    """Does it echo printable user input back to the sender?"""
    shell_prompt = "qtpy $"
    printable_input = b"!'# 012 ABC abc ~\r\n"
    input_buffer = io.BytesIO(initial_bytes=printable_input)
    output_buffer = io.BytesIO(initial_bytes=b"")
    prompt_session = py_shell.PromptSession(in_stream=input_buffer, out_stream=output_buffer)
    response = prompt_session.prompt(message=shell_prompt)

    # Room for improvement here -- rather than redrawing the most recent character when at the end of the buffer, just append it
    expected_output = b"qtpy $\x1b[?25l\x1b[7G\x1b[0K!\x1b[8G\x1b[?25h\x1b[?25l\x1b[8G\x1b[0K'\x1b[9G\x1b[?25h\x1b[?25l\x1b[9G\x1b[0K#\x1b[10G\x1b[?25h\x1b[?25l\x1b[10G\x1b[0K \x1b[11G\x1b[?25h\x1b[?25l\x1b[11G\x1b[0K0\x1b[12G\x1b[?25h\x1b[?25l\x1b[12G\x1b[0K1\x1b[13G\x1b[?25h\x1b[?25l\x1b[13G\x1b[0K2\x1b[14G\x1b[?25h\x1b[?25l\x1b[14G\x1b[0K \x1b[15G\x1b[?25h\x1b[?25l\x1b[15G\x1b[0KA\x1b[16G\x1b[?25h\x1b[?25l\x1b[16G\x1b[0KB\x1b[17G\x1b[?25h\x1b[?25l\x1b[17G\x1b[0KC\x1b[18G\x1b[?25h\x1b[?25l\x1b[18G\x1b[0K \x1b[19G\x1b[?25h\x1b[?25l\x1b[19G\x1b[0Ka\x1b[20G\x1b[?25h\x1b[?25l\x1b[20G\x1b[0Kb\x1b[21G\x1b[?25h\x1b[?25l\x1b[21G\x1b[0Kc\x1b[22G\x1b[?25h\x1b[?25l\x1b[22G\x1b[0K \x1b[23G\x1b[?25h\x1b[?25l\x1b[23G\x1b[0K~\x1b[24G\x1b[?25h\n"
    actual_output = output_buffer.getvalue()
    assert len(actual_output) > 0
    assert actual_output == expected_output
    assert response == printable_input.decode("UTF-8").strip()


@pytest.mark.parametrize(
    ("input_key", "additional_expected_output_bytes"),
    [
        ("left arrow", b""),
        ("right arrow", b""),
        ("up arrow", b""),
        ("down arrow", b""),
        ("home", b""),
        ("end", b""),
        (  # impl always hides cursor, erases line, shows cursor
            "backspace",
            b"\x1b[?25l\x1b[7G\x1b[0K\x1b[7G\x1b[?25h",
        ),
        (  # impl always cursor, erases line, shows cursor
            "delete",
            b"\x1b[?25l\x1b[7G\x1b[0K\x1b[7G\x1b[?25h",
        ),
        ("F1", b""),
        ("F2", b""),
        ("F3", b""),
        ("F4", b""),
        ("F5", b""),
        ("F6", b""),
        ("F7", b""),
        ("F8", b""),
        ("F9", b""),
        ("F10", b""),
    ],
)
def test_nonprintable_input_key(input_key: str, additional_expected_output_bytes: bytes) -> None:
    """Does it receive and handle non-printable user input?"""
    shell_prompt = "qtpy $"
    input_key_bytes = _CODES_FOR_KEY_NAME[input_key]
    input_buffer = io.BytesIO(initial_bytes=input_key_bytes)
    output_buffer = io.BytesIO(initial_bytes=b"")
    prompt_session = py_shell.PromptSession(in_stream=input_buffer, out_stream=output_buffer)

    with pytest.raises(IndexError):
        # Because the input stream does not have the EOL character to end user input and exit the prompt loop,
        # the backing io.BytesIO does not block on .read(1), unlike a serial port, and instead
        # immediately returns an empty bytes array, which cannot be indexed for the first (and only) byte.
        _ = prompt_session.prompt(message=shell_prompt)

    expected_output = f"{shell_prompt}{additional_expected_output_bytes.decode('UTF-8')}"
    actual_output = output_buffer.getvalue()
    assert len(actual_output) > 0
    assert actual_output == expected_output.encode("UTF-8")


@pytest.mark.parametrize(
    ("user_input", "input_command_sequence", "expected_response"),
    [
        ("012345", ["backspace"], "01234"),
        ("012345", ["backspace", "right arrow"], "01234"),
        ("012345", ["left arrow", "delete"], "01234"),
        ("012345", ["left arrow", "delete", "right arrow"], "01234"),
        ("012345", ["home", "delete"], "12345"),
        ("012345", ["home", "delete", "left arrow"], "12345"),
        ("012345", ["left arrow", "left arrow", "left arrow", "backspace", "delete"], "0145"),
        ("\tFD\t", [], "\tFD\t"),
        ("\tFD\t", ["left arrow"], "\tFD\t"),
        ("\tFD\t", ["backspace"], "\tFD"),
        ("\tFD\t", ["left arrow", "delete"], "\tFD"),
        ("\tFD\t", ["home", "delete"], "FD\t"),
    ],
)
def test_line_editing(user_input: str, input_command_sequence: list[str], expected_response: str) -> None:
    """Does it correctly handle line editing commands?"""
    shell_prompt = "qtpy $"
    user_input_bytes = user_input.encode("UTF-8")
    navigation_input_bytes = [_CODES_FOR_KEY_NAME[navkey] for navkey in input_command_sequence]
    complete_input = bytearray(user_input_bytes)
    complete_input.extend(itertools.chain.from_iterable(navigation_input_bytes))
    complete_input.extend(b"\r\n")
    complete_input_bytes = bytes(complete_input)

    input_buffer = io.BytesIO(initial_bytes=complete_input_bytes)
    output_buffer = io.BytesIO(initial_bytes=b"")
    prompt_session = py_shell.PromptSession(in_stream=input_buffer, out_stream=output_buffer)
    response = prompt_session.prompt(message=shell_prompt)

    actual_output = output_buffer.getvalue()
    assert len(actual_output) > 0
    assert len(response) > 0
    assert response == expected_response
