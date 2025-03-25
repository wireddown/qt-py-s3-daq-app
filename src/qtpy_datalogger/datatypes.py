"""
Shared constants and classes used by the host.

This module uses CPython features not available in the CircuitPython implementation.
"""

import enum

import toml


class Links(enum.StrEnum):
    """URLs for references and help."""

    Homepage = "https://github.com/wireddown/qt-py-s3-daq-app/wiki"
    New_Bug = "https://github.com/wireddown/qt-py-s3-daq-app/issues/new?template=bug-report.md"
    Board_Support_Matrix = "https://docs.circuitpython.org/en/stable/shared-bindings/support_matrix.html"


class ExitCode(enum.IntEnum):
    """Exit codes for commands."""

    Success = 0
    Discovery_Failure = 41
    COM1_Failure = 42
    Board_Lookup_Failure = 51


class CaptionCorrections:
    """Corrections for abbreviated or malformatted device descriptions."""

    @staticmethod
    def get_corrected(caption: str) -> str:
        """Return the corrected string for the specified input caption."""
        caption_corrections = {
            "Adafruit QT Py ESP32S3 no USB Device": "Adafruit QT Py ESP32-S3 no PSRAM",
            "adafruit_qtpy_esp32s3_nopsram": "Adafruit QT Py ESP32-S3 no PSRAM",
            "Adafruit QT Py ESP32S3 4M USB Device": "Adafruit QT Py ESP32-S3 2MB PSRAM",
            "adafruit_qtpy_esp32s3_4mbflash_2mbpsram": "Adafruit QT Py ESP32-S3 2MB PSRAM",
        }
        return caption_corrections.get(caption, caption)

