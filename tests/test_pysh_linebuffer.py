"""Acceptance tests for the LineBuffer class in the pysh module."""

import pytest

from qtpy_sensor_node.snsr.pysh.linebuffer import LineBuffer


@pytest.mark.parametrize(
    ("prompt_length"),
    [
        (len("")),
        (len("qtpy $ ")),
    ],
)
def test_initial_value(prompt_length: int) -> None:
    """Does it initialize correctly?"""
    buffy = LineBuffer(prompt_length=prompt_length)

    assert buffy.input_cursor == 0
    assert buffy.get_terminal_column() == 1 + prompt_length
    assert not buffy.has_bytes()
    assert not buffy.get_decoded_bytes()


@pytest.mark.parametrize(
    ("input_characters", "expected_column"),
    [
        ("A", 2),
        ("\t", 9),
        ("abcd", 5),
        ("1234\tabcd", 13),
        ("aeio\t2468\t", 17),
    ],
)
def test_accept_characters(input_characters: str, expected_column: int) -> None:
    """Does it advance its index and column after accepting characters?"""
    prompt_length = 0
    buffy = LineBuffer(prompt_length=prompt_length)

    for character in list(input_characters):
        buffy.accept(ord(character))

    assert buffy.input_cursor == len(input_characters)
    assert buffy.get_terminal_column() == expected_column
    assert buffy.has_bytes()
    assert buffy.get_decoded_bytes() == input_characters


@pytest.mark.parametrize(
    ("input_characters"),
    [
        (""),
        ("\t"),
        ("abcd"),
        ("1234\tabcd"),  # fmt: skip -- each line holds a test case, don't flatten
    ],
)
def test_move_home(input_characters: str) -> None:
    """Does it correctly move the input cursor home?"""
    prompt_length = 0
    buffy = LineBuffer(prompt_length=prompt_length)
    for character in list(input_characters):
        buffy.accept(ord(character))

    # LineBuffer.move_home() can be called many times without changing the buffer's state
    for _ in range(2):
        buffy.move_home()

        assert buffy.input_cursor == 0
        assert buffy.get_terminal_column() == 1 + prompt_length
        assert buffy.get_decoded_bytes() == input_characters


@pytest.mark.parametrize(
    ("input_characters", "expected_column"),
    [
        ("", 1),
        ("\t", 9),
        ("abcd", 5),
        ("1234\tabcd", 13),  # fmt: skip -- each line holds a test case, don't flatten
    ],
)
def test_move_end(input_characters: str, expected_column: int) -> None:
    """Does it correctly move the input cursor to the end?"""
    prompt_length = 0
    buffy = LineBuffer(prompt_length=prompt_length)
    expected_cursor_position = len(input_characters)
    for character in list(input_characters):
        buffy.accept(ord(character))
    buffy.move_home()

    # LineBuffer.move_end() can be called many times without changing the buffer's state
    for _ in range(2):
        buffy.move_end()

        assert buffy.input_cursor == expected_cursor_position
        assert buffy.get_terminal_column() == expected_column
        assert buffy.get_decoded_bytes() == input_characters


@pytest.mark.parametrize(
    ("input_characters", "expected_cursor_and_column_after_move"),
    [
        (  # Moving left at the start of a line doesn't move the cursor or column
            "",
            [(0, 1), (0, 1)],
        ),
        (  # Moving left across characters moves both cursor and column
            "abcd",
            [(3, 4), (2, 3)],
        ),
        (  # Moving left across a tab character matches tab stops
            "1234\tabcd",
            [(8, 12), (7, 11), (6, 10), (5, 9), (4, 5)],
        ),
    ],
)
def test_move_left(input_characters: str, expected_cursor_and_column_after_move: list[tuple[int, int]]) -> None:
    """Does it correctly move the input cursor left?"""
    prompt_length = 0
    buffy = LineBuffer(prompt_length=prompt_length)
    for character in list(input_characters):
        buffy.accept(ord(character))

    for expected_column_and_cursor in expected_cursor_and_column_after_move:
        expected_cursor = expected_column_and_cursor[0]
        expected_column = expected_column_and_cursor[1]
        buffy.move_left()

        assert buffy.input_cursor == expected_cursor
        assert buffy.get_terminal_column() == expected_column
        assert buffy.get_decoded_bytes() == input_characters


@pytest.mark.parametrize(
    ("input_characters", "expected_cursor_and_column_after_move"),
    [
        (  # Moving right at the end of a line doesn't move the cursor or column
            "",
            [(0, 1), (0, 1)],
        ),
        (  # Moving right across characters moves both cursor and column
            "abcd",
            [(1, 2), (2, 3)],
        ),
        (  # Moving right across a tab character matches tab stops
            "1234\tabcd",
            [(1, 2), (2, 3), (3, 4), (4, 5), (5, 9)],
        ),
    ],
)
def test_move_right(input_characters: str, expected_cursor_and_column_after_move: list[tuple[int, int]]) -> None:
    """Does it correctly move the input cursor right?"""
    prompt_length = 0
    buffy = LineBuffer(prompt_length=prompt_length)
    for character in list(input_characters):
        buffy.accept(ord(character))
    buffy.move_home()

    for expected_column_and_cursor in expected_cursor_and_column_after_move:
        expected_cursor = expected_column_and_cursor[0]
        expected_column = expected_column_and_cursor[1]
        buffy.move_right()

        assert buffy.input_cursor == expected_cursor
        assert buffy.get_terminal_column() == expected_column
        assert buffy.get_decoded_bytes() == input_characters


@pytest.mark.parametrize(
    ("input_characters", "left_moves", "expected_column", "expected_buffer"),
    [
        ("", 2, 1, ""),  # Deleting twice at the end of a line doesn't change the buffer
        ("abcd", 2, 3, "abd"),
        ("1234\tabcd", 5, 5, "1234abcd"),
    ],
)
def test_delete(input_characters: str, left_moves: int, expected_column: int, expected_buffer: str) -> None:
    """Does it correctly delete characters at the input cursor?"""
    prompt_length = 0
    buffy = LineBuffer(prompt_length=prompt_length)
    for character in list(input_characters):
        buffy.accept(ord(character))
    for _ in range(left_moves):
        buffy.move_left()

    terminal_column, remaining_line = buffy.delete()
    assert terminal_column == expected_column
    buffer = buffy.get_decoded_bytes()
    assert buffer == expected_buffer
    assert bytes(remaining_line) == buffer[buffy.input_cursor :].encode()


@pytest.mark.parametrize(
    ("input_characters", "left_moves", "expected_column", "expected_buffer"),
    [
        ("", 2, 1, ""),  # Backspacing twice at the start of a line doesn't change the buffer
        ("abcd", 2, 2, "acd"),
        ("1234\tabcd", 4, 5, "1234abcd"),
    ],
)
def test_backspace(input_characters: str, left_moves: int, expected_column: int, expected_buffer: str) -> None:
    """Does it correctly backspace characters before the input cursor?"""
    prompt_length = 0
    buffy = LineBuffer(prompt_length=prompt_length)
    for character in list(input_characters):
        buffy.accept(ord(character))
    for _ in range(left_moves):
        buffy.move_left()

    terminal_column, remaining_line = buffy.backspace()
    assert terminal_column == expected_column
    buffer = buffy.get_decoded_bytes()
    assert buffer == expected_buffer
    assert bytes(remaining_line) == buffer[buffy.input_cursor :].encode()


@pytest.mark.parametrize(
    ("input_characters", "move_calls", "expected_column", "expected_cursor"),
    [
        ("012345", ["move_home", "move_left"], 1, 0),
        ("012345", ["move_home", "move_right"], 2, 1),
        ("012345", ["move_home", "move_end", "move_right"], 7, 6),
        ("012345", ["move_home", "move_end", "move_left"], 6, 5),
        ("\t", ["move_left", "move_right"], 9, 1),
        ("\tA", ["move_left", "move_left"], 1, 0),
        ("B\t", ["move_home", "move_right", "move_right"], 9, 2),
    ],
)
def test_line_navigation(
    input_characters: str, move_calls: list[str], expected_column: int, expected_cursor: int
) -> None:
    """Does it handle multiple move commands correctly?"""
    prompt_length = 0
    buffy = LineBuffer(prompt_length=prompt_length)
    for character in list(input_characters):
        buffy.accept(ord(character))

    new_column = -1
    for move_call in move_calls:
        do_move = getattr(buffy, move_call)
        new_column = do_move()

    assert new_column == expected_column
    assert buffy.input_cursor == expected_cursor


@pytest.mark.parametrize(
    ("input_characters", "buffer_calls", "expected_column", "expected_cursor", "expected_buffer"),
    [
        ("012345", ["move_left", "delete"], 6, 5, "01234"),
        ("012345", ["backspace", "move_right"], 6, 5, "01234"),
        ("012345", ["move_left", "delete", "move_right"], 6, 5, "01234"),
        ("012345", ["move_home", "delete"], 1, 0, "12345"),
        ("012345", ["move_home", "delete", "move_left"], 1, 0, "12345"),
        ("012345", ["move_left", "move_left", "move_left", "backspace", "delete"], 3, 2, "0145"),
        ("A\tB", ["move_left", "move_left", "delete"], 2, 1, "AB"),
        ("C\tD", ["move_home", "move_right", "move_right", "backspace"], 2, 1, "CD"),
    ],
)
def test_line_editing(
    input_characters: str, buffer_calls: list[str], expected_column: int, expected_cursor: int, expected_buffer: str
) -> None:
    """Does it handle multiple move and edit commands correctly?"""
    prompt_length = 0
    buffy = LineBuffer(prompt_length=prompt_length)
    for character in list(input_characters):
        buffy.accept(ord(character))

    for buffer_call in buffer_calls:
        do_call = getattr(buffy, buffer_call)
        do_call()

    assert buffy.get_terminal_column() == expected_column
    assert buffy.input_cursor == expected_cursor
    assert buffy.get_decoded_bytes() == expected_buffer
