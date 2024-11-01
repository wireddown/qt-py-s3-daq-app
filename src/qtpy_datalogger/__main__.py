"""Entry point for qtpy_datalogger package."""

from . import console


def main() -> None:
    """Run the command line interface when invoked as a module."""
    console.cli()


if __name__ == "__main__":
    main()
