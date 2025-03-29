"""A user input buffer for line editing."""

ORD_TAB = 0x09


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
