"""
Logging handler with a formatter that uses click colors on stderr.

To use, call initialize() at the beginning of your script. Then create
a logger at the top of each file following the conventional pattern.
Likewise, call the logger's message functions for debug, warning, etc.

## Do once

main.py

```
import logging

from . import tracelog

logger = logging.getLogger(__name__)
log_level = logging.INFO
tracelog.initialize(log_level)
logger.info("Hello from main.py")
```

## Do for each file

```
import logging

logger = logging.getLogger(__name__)
logger.info("Hello from each file")
```
"""
# Reworked from https://github.com/click-contrib/click-log

import logging
import time

import click


class ClickHandler(logging.Handler):
    """A logging.Handler that uses click.echo() to emit records."""

    _use_stderr = True

    def emit(self: "ClickHandler", record: logging.LogRecord) -> None:
        """Log the specified record with click.echo() to stderr."""
        try:
            formatted_entry = self.format(record)
            click.echo(formatted_entry, err=self._use_stderr)
        except Exception:  # noqa: BLE001 Matches Python's design pattern for emit()
            self.handleError(record)


class ColorFormatter(logging.Formatter):
    """A logging.Formatter that uses click.style() to format records."""

    COLORS = {  # noqa: RUF012 Switching to tuples for immutability is too cumbersome
        "critical": "bright_magenta",
        "exception": "red",
        "error": "red",
        "warning": "yellow",
        "info": "cyan",
        "debug": "white",
    }

    def __init__(self: "ColorFormatter", level: int | str = logging.NOTSET) -> None:
        """Create a new ColorFormatter with the specified logging level."""
        self.level = self._check_level(level)

    def _check_level(self: "ColorFormatter", level: int | str) -> int:
        if isinstance(level, int):
            valid_level = level
        elif str(level) == level:
            valid_levels = logging.getLevelNamesMapping()
            if level not in valid_levels:
                exception_message = f"Unknown level: {level}"
                raise ValueError(exception_message)
            valid_level = valid_levels[level]
        else:
            exception_message = f"Level not an integer or a valid string: {level}"
            raise TypeError(exception_message)
        return valid_level

    def set_level(self: "ColorFormatter", level: int | str) -> None:
        """Set the logging verbosity level."""
        self.level = self._check_level(level)

    def format(self: "ColorFormatter", record: logging.LogRecord) -> str:
        """Format the specified record."""
        if record.exc_info:
            default_formatter = logging.Formatter()
            formatted_message = default_formatter.format(record)
        else:
            formatted_message = record.getMessage()

        level = record.levelname.lower()
        color = self.COLORS.get(level, "bright_white")

        time_string = ""
        location_string = ""
        if self.level < logging.INFO:
            timestamp = time.localtime(record.created)
            time_string = click.style(f"{time.strftime('%Y.%m.%d %H:%M:%S', timestamp)}.{record.msecs:03.0f}", fg=color)
            location_string = click.style(f"{record.name:>26}::{record.funcName:<22} {record.lineno:>4}", fg=color)

        severity_string = click.style(f"{record.levelname:<8}", fg=color)
        message_strings = [click.style(line, fg="bright_white") for line in formatted_message.splitlines()]

        entry_prefix = f"{time_string} {location_string} {severity_string}"
        return "\n".join(f"{entry_prefix} {line}".strip() for line in message_strings)


def initialize(log_level: int | str) -> None:
    """Configure the logging system to use colors and print to stderr."""
    click_handler = build_click_handler(log_level)

    logging.basicConfig(
        handlers=[click_handler],
        level=log_level,
    )


def build_click_handler(log_level: int | str) -> ClickHandler:
    """Create a logging Handler with click and color support."""
    click_handler = ClickHandler()
    click_handler.setLevel(log_level)
    color_formatter = ColorFormatter()
    color_formatter.set_level(log_level)
    click_handler.setFormatter(color_formatter)
    return click_handler
