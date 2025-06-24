"""An app that collects data from a soil swell test."""

import asyncio
import contextlib
import datetime
import functools
import importlib.resources
import logging
import multiprocessing
import pathlib
import textwrap
import tkinter as tk
from enum import StrEnum
from tkinter import filedialog, font
from typing import Any, Callable, NamedTuple

import click
import matplotlib.axes as mpl_axes
import matplotlib.backend_bases as mpl_backend_bases
import matplotlib.figure as mpl_figure
import pandas as pd
import toml
import ttkbootstrap as ttk
import ttkbootstrap.themes.standard as ttk_themes
import ttkbootstrap.tooltip as ttk_tooltip
from tkfontawesome import icon_to_image, svg_to_image
from ttkbootstrap import constants as bootstyle

import qtpy_datalogger.apps.scanner
from qtpy_datalogger import datatypes, discovery, guikit, network, ttkbootstrap_matplotlib

logger = logging.getLogger(pathlib.Path(__file__).stem)

app_icon_color = "#07a000"


class StyleKey(StrEnum):
    """A class that extends the palette names of ttkbootstrap styles."""

    Fg = "fg"
    SelectFg = "selectfg"


class BatteryLevel(StrEnum):
    """An ordered enumeration that represents the sensor node's battery level."""

    Unset = "Unset"
    Unknown = "Unknown"
    Low = "Low"
    Half = "Half"
    High = "High"
    Full = "Full"


class SampleRate(StrEnum):
    """Supported settings for the app's sample rate."""

    Unset = "Unset"
    Live = "Live"
    Fast = "Fast"
    Normal = "Normal"
    Slow = "Slow"


class Range(NamedTuple):
    """A class that represents a numerical range."""

    lower: float
    """The lower bound of the range."""

    upper: float
    """The upper bound of the range."""


class Tristate(StrEnum):
    """An enumeration that models a tristate boolean."""

    BoolUnset = "Unset"
    BoolTrue = "True"
    BoolFalse = "False"


class NumericInput:
    """A class that takes text input as a numeric value."""

    class Event(StrEnum):
        """Events emitted by this control."""

        ValueChanged = "<<ValueChanged>>"

    def __init__(self, parent: tk.Widget, limits: Range, default_value: float) -> None:  # noqa: PLR0915 -- allow long function to initialize the control
        """Initialize a new NumericInput widget."""
        self._value = default_value

        def value_is_indeterminate(candidate_value: str) -> bool:
            """Return True if the value is not a fully formed floating point number."""
            # Allow empty and minus sign to support keyboard entry
            return len(candidate_value) == 0 or candidate_value == "-"

        def try_as_float(string_value: str) -> float | None:
            """If string_value is a float, return its value as a float. Otherwise return None."""
            try:
                as_float = float(string_value)
            except ValueError:
                return None
            else:
                return as_float

        def check_float_in_range(sender: tk.Entry, limits: Range, candidate_value: str, operation: str) -> bool:
            """Return True if candidate_value is a float and in range."""
            if value_is_indeterminate(candidate_value):
                return True

            as_float = try_as_float(candidate_value)
            if as_float is None:
                return False

            is_valid = limits.lower <= as_float <= limits.upper
            new_style = bootstyle.DEFAULT if is_valid else bootstyle.DANGER
            sender.configure(bootstyle=new_style)  # pyright: ignore callIssue -- the type hint for bootstrap omits its own additions
            return is_valid

        def handle_new_value(sender: tk.Entry, variable_name: str, empty: str, operation: str) -> None:
            """Process a new value that passed input validation."""
            new_value = sender.get()
            if value_is_indeterminate(new_value):
                return
            as_float = float(new_value)
            self.value = as_float

        def handle_entry_complete(fallback_value: float, decimal_places: int, event_args: tk.Event) -> None:
            """Handle the Enter key and FocusOut events."""
            sender = event_args.widget
            if not isinstance(sender, ttk.Spinbox):
                raise TypeError()
            try:
                sender.set(f"{float(sender.get()):.{decimal_places}f}")
                self._input_control.event_generate(NumericInput.Event.ValueChanged)
            except ValueError:
                sender.set(f"{fallback_value:.{decimal_places}f}")
            finally:
                sender.icursor(tk.END)
                sender.after(0, sender.selection_clear)

        decimal_places_for_max = {
            100: 0,
            10: 1,
            1: 2,
        }
        decimal_places = get_first_in_range(limits.upper, decimal_places_for_max)

        increment_for_max = {
            100: 10.0,
            20: 1.0,
            2: 0.1,
        }
        increment = get_first_in_range(limits.upper, increment_for_max)

        self._input_variable = tk.StringVar(value=f"{default_value:.{decimal_places}f}")
        self._input_control = ttk.Spinbox(master=parent, from_=limits.lower, to=limits.upper, increment=increment, format=f"%.{decimal_places}f", width=5, justify=tk.RIGHT, textvariable=self._input_variable)

        input_validator = parent.register(functools.partial(check_float_in_range, self._input_control, limits))
        self._input_variable.trace_add("write", functools.partial(handle_new_value, self._input_control))
        self._input_control.configure(validate=tk.ALL, validatecommand=(input_validator, "%P", "%V"))
        self._input_control.bind("<<Increment>>", functools.partial(handle_entry_complete, default_value, decimal_places))
        self._input_control.bind("<<Decrement>>", functools.partial(handle_entry_complete, default_value, decimal_places))
        self._input_control.bind("<KeyPress-Return>", functools.partial(handle_entry_complete, default_value, decimal_places))
        self._input_control.bind("<MouseWheel>", functools.partial(handle_entry_complete, default_value, decimal_places))
        self._input_control.bind("<FocusOut>", functools.partial(handle_entry_complete, default_value, decimal_places))

    @property
    def widget(self) -> ttk.Spinbox:
        """Return the Tk widget for this NumericInput."""
        return self._input_control

    @property
    def value(self) -> float:
        """Return the value of the NumericInput as a float."""
        return self._value

    @value.setter
    def value(self, new_value: float) -> None:
        """Set a new value and notify ValueChanged subscribers."""
        if new_value == self._value:
            return
        self._value = new_value


class ToolWindow(guikit.AsyncDialog):
    """A class that shows a window with tools that apply to its origin."""

    def __init__(self, parent: ttk.Toplevel | ttk.Window, title: str | None = None) -> None:
        """Initialize a new ToolWindow."""
        self.tool_frames: dict[str, ttk.Frame] = {}
        super().__init__(parent=parent, title=title if title else "")

    async def on_loop(self) -> None:
        """Update UI elements."""
        await asyncio.sleep(20e-3)

    def attach_to_axis(self, refresh_graph: Callable[[], None], axes: mpl_axes.Axes, axis: str, limits: tuple[float, float]) -> None:
        """Present a UI that configures the specified axis."""
        self.root_window.title("Axis settings")
        self.root_window.columnconfigure(0, weight=1)
        self.root_window.rowconfigure(0, weight=1)
        self.root_window.minsize(width=170, height=166)
        self.root_window.maxsize(width=170, height=400)

        frame_key = f"{repr(axes)}.{axis}" # noqa: RUF010 -- TypeError: unsupported format string passed to Axes.__format__
        if frame_key not in self.tool_frames:
            tool_frame = self.create_axis_tool_frame(refresh_graph, axes, axis, limits)
            self.root_window.update_idletasks()
            self.tool_frames[frame_key] = tool_frame
        tool_frame = self.tool_frames[frame_key]
        tool_frame.grid(column=0, row=0, sticky=tk.NSEW)
        for child in self.root_window.children.values():
            if child is tool_frame:
                continue
            child.grid_forget()
            self.root_window.update_idletasks()
        self.root_window.focus()

    def create_axis_tool_frame(self, refresh_graph: Callable[[], None], axes: mpl_axes.Axes, axis: str, limits: tuple[float, float]) -> ttk.Frame:  # noqa: PLR0915 -- allow long function to create the UI
        """Create a ttk.Frame that shows configuration settings and handles user input."""
        tool_frame = ttk.Frame(self.root_window, padding=16)
        tool_frame.columnconfigure(0, weight=1)  # Labels
        tool_frame.columnconfigure(1, weight=1)  # Controls
        tool_frame.rowconfigure(0, weight=0)  # Name of axis under edit
        tool_frame.rowconfigure(1, weight=0)  # Upper limit
        tool_frame.rowconfigure(2, weight=0)  # Lower limit
        tool_frame.rowconfigure(3, weight=1)  # Scale

        if axis == "xaxis":
            plot_axis = axes.xaxis
            axis_view_limits = axes.get_xlim()
            axis_scale = axes.get_xscale()
            set_axis_limits = axes.set_xlim
            set_axis_scale = axes.set_xscale
        else:
            plot_axis = axes.yaxis
            axis_view_limits = axes.get_ylim()
            axis_scale = axes.get_yscale()
            set_axis_limits = axes.set_ylim
            set_axis_scale = axes.set_yscale

        axis_name = ttk.Label(tool_frame, text=plot_axis.get_label().get_text(), font=font.Font(family="Segoe UI", size=10, weight=font.BOLD))
        axis_name.grid(column=0, columnspan=2, row=0, pady=(0, 8), sticky=tk.W)

        max_limit_label = ttk.Label(tool_frame, text="Maximum")
        max_limit_label.grid(column=0, row=1, padx=(0, 12), pady=(8, 8), sticky=tk.EW)
        min_limit_label = ttk.Label(tool_frame, text="Minimum")
        min_limit_label.grid(column=0, row=2, padx=(0, 12), pady=(8, 8), sticky=tk.EW)
        scale_label = ttk.Label(tool_frame, text="Scale")
        scale_label.grid(column=0, row=3, padx=(0, 12), pady=(8, 8), sticky=(tk.EW, tk.N))  # pyright: ignore reportArgumentType -- the type hint for library is incorrect

        limits_range = Range(lower=limits[0], upper=limits[1])
        viewing_range = Range(lower=axis_view_limits[0], upper=axis_view_limits[1])

        axis_max_input = NumericInput(tool_frame, limits=limits_range, default_value=viewing_range.upper)
        ttk_tooltip.ToolTip(axis_max_input.widget, text=f"Cannot be greater than {limits_range.upper}", bootstyle=bootstyle.DEFAULT)
        axis_max_input.widget.grid(column=1, row=1, sticky=tk.EW)

        axis_min_input = NumericInput(tool_frame, limits=limits_range, default_value=viewing_range.lower)
        ttk_tooltip.ToolTip(axis_min_input.widget, text=f"Cannot be less than {limits_range.lower}", bootstyle=bootstyle.DEFAULT)
        axis_min_input.widget.grid(column=1, row=2, sticky=tk.EW)

        def on_new_upper_or_lower_bound(event_args: tk.Event) -> None:
            """Handle the ValueChanged event for the input control."""
            lower_bound = axis_min_input.value
            upper_bound = axis_max_input.value
            set_axis_limits(lower_bound, upper_bound)
            refresh_graph()
        axis_max_input.widget.bind(NumericInput.Event.ValueChanged, on_new_upper_or_lower_bound)
        axis_min_input.widget.bind(NumericInput.Event.ValueChanged, on_new_upper_or_lower_bound)

        scale_input = ttk.Combobox(master=tool_frame, values=["Linear", "Log"], state="readonly", width=5, justify=tk.RIGHT)
        scale_input.grid(column=1, row=3, sticky=(tk.EW, tk.N))  # pyright: ignore reportArgumentType -- the type hint for library is incorrect
        scale_input.set(axis_scale.capitalize())
        def handle_scale_selection(event_args: tk.Event) -> None:
            """Handle the selection event for the linear/log scale combobox."""
            sender = event_args.widget
            if not isinstance(sender, ttk.Combobox):
                raise TypeError()
            sender.selection_clear()
            selected_value = sender.get()
            if selected_value == axis_scale:
                return
            if selected_value == "Log":
                safe_minimum = max(0.01, axis_view_limits[0])
                set_axis_limits(safe_minimum, axis_max_input.value)
                axis_min_input.value = safe_minimum
                axis_min_input.widget.configure(state=tk.DISABLED)
            else:
                axis_min_input.widget.configure(state=tk.NORMAL)
            set_axis_scale(selected_value.lower())
            refresh_graph()

        scale_input.bind("<<ComboboxSelected>>", handle_scale_selection)
        scale_input.selection_clear()

        return tool_frame


class SettingsWindow(guikit.AsyncDialog):
    """A class that shows a windows for configuring the app's settings."""

    def __init__(self, parent: ttk.Toplevel | ttk.Window, title: str, settings: dict) -> None:
        """Initialize a new SettingsWindow."""
        self.settings = settings
        self.group_input_variable = tk.StringVar(value=settings["startup"]["group"])
        super().__init__(parent=parent, title=title)

    def create_user_interface(self) -> None:  # noqa: PLR0915 -- allow long function to create the UI
        """Create the layout and widget event handlers."""
        self.root_window.columnconfigure(0, weight=1)
        self.root_window.rowconfigure(0, weight=1)
        self.root_window.minsize(width=220, height=201)
        self.root_window.maxsize(width=800, height=201)

        settings_frame = ttk.Frame(self.root_window, padding=16)
        settings_frame.columnconfigure(0, weight=0)  # Labels
        settings_frame.columnconfigure(1, weight=1)  # Controls
        settings_frame.rowconfigure(0, weight=0)  # Start-up settings group name
        settings_frame.rowconfigure(1, weight=0)  # Start-up theme
        settings_frame.rowconfigure(2, weight=0)  # Start-up group name
        settings_frame.rowconfigure(3, weight=0)  # Start-up sample rate
        settings_frame.rowconfigure(4, weight=1)  # Start-up calibration file and create-new
        settings_frame.grid(column=0, row=0, sticky=tk.NSEW)

        startup_label = ttk.Label(settings_frame, text="Startup", font=font.Font(family="Segoe UI", size=10, weight=font.BOLD))
        startup_label.grid(column=0, columnspan=2, row=0, pady=(0, 8), sticky=tk.W)

        theme_label = ttk.Label(settings_frame, text="Theme")
        theme_label.grid(column=0, row=1, padx=(0, 12), pady=(8, 8), sticky=tk.EW)
        def update_theme(new_theme: str) -> None:
            self.settings["startup"]["theme"] = new_theme.lower()

        theme_input = guikit.create_dropdown_combobox(settings_frame, values=["Cosmo", "Flatly", "Cyborg", "Darkly"], width=10, justify=ttk.LEFT, completion=update_theme)
        theme_input.set(self.settings["startup"]["theme"].capitalize())
        theme_input.grid(column=1, row=1, sticky=tk.W)

        group_label = ttk.Label(settings_frame, text="Sensor group")
        group_label.grid(column=0, row=2, padx=(0, 12), pady=(8, 8), sticky=tk.EW)

        sensor_node_group = ttk.Entry(settings_frame, width=12, textvariable=self.group_input_variable)
        def check_valid_group_name(sender: tk.Entry, candidate_value: str, operation: str) -> bool:
            """Return True if candidate_value is a valid sensor group name."""
            illegal_chars = [" ", "/", "#", "+"]
            has_illegal_char = any(char in candidate_value for char in illegal_chars)
            return not has_illegal_char

        def handle_new_value(sender: tk.Entry, variable_name: str, empty: str, operation: str) -> None:
            """Process a new value that passed input validation."""
            self.settings["startup"]["group"] = sender.get()

        input_validator = self.parent.register(functools.partial(check_valid_group_name, sensor_node_group))
        self.group_input_variable.trace_add("write", functools.partial(handle_new_value, sensor_node_group))
        sensor_node_group.configure(validate=tk.ALL, validatecommand=(input_validator, "%P", "%V"))
        sensor_node_group.grid(column=1, row=2, sticky=tk.W)

        sample_rate_label = ttk.Label(settings_frame, text="Sample rate")
        sample_rate_label.grid(column=0, row=3, padx=(0, 12), pady=(8, 8), sticky=tk.EW)
        def update_sample_rate(new_sample_rate: str) -> None:
            self.settings["startup"]["sample rate"] = new_sample_rate

        sample_rate_options = SampleRate._member_names_.copy()
        sample_rate_options.remove(SampleRate.Unset)
        sample_rate_input = guikit.create_dropdown_combobox(settings_frame, values=sample_rate_options, width=10, justify=ttk.LEFT, completion=update_sample_rate)
        sample_rate_input.set(self.settings["startup"]["sample rate"])
        sample_rate_input.grid(column=1, row=3, sticky=tk.W)

        calibration_file_label = ttk.Label(settings_frame, text="Calibration file")
        calibration_file_label.grid(column=0, row=4, padx=(0, 12), pady=(8, 8), sticky=(tk.N, tk.EW))  # pyright: ignore reportArgumentType -- the type hint for library is incorrect
        calibration_input_frame = ttk.Frame(settings_frame)
        calibration_input_frame.columnconfigure(0, weight=1)
        calibration_input_frame.columnconfigure(1, weight=0)
        calibration_input_frame.columnconfigure(2, weight=0)
        calibration_input_frame.rowconfigure(0, weight=1)
        calibration_input_frame.grid(column=1, row=4, pady=(3, 0), sticky=(tk.N, tk.EW))  # pyright: ignore reportArgumentType -- the type hint for library is incorrect
        def update_calibration_file(new_file_path: str) -> None:
            self.settings["startup"]["calibration file"] = new_file_path

        previous_files = [str(SoilSwell.CommandName.DefaultCalibrationFile)]
        previous_files.extend(self.settings["calibration file history"])
        calibration_file_name = guikit.create_dropdown_combobox(calibration_input_frame, values=previous_files, width=20, justify=ttk.LEFT, completion=update_calibration_file)
        calibration_file_name.set(self.settings["startup"]["calibration file"])
        calibration_file_name.grid(column=0, row=0, padx=(0, 8), sticky=tk.EW)

    async def on_loop(self) -> None:
        """Update UI elements."""
        await asyncio.sleep(20e-3)


class RawDataProcessor:
    """A class that calculates derived data from raw sensor samples."""

    DEFAULT_SENSOR_PARAMETERS = {  # noqa: RUF012 -- dict is mutable but treated as a constant
        "lvdt": { "gain": 1.0, "offset": 0.0, "units": "cm" },
        "thrm_mcp9700": { "gain": 1.0, "offset": 0.0, "units": "degC"},
        "battery_sense": { "gain": 1.0, "offset": 0.0, "units": "V"},
        "xl3d_adxl375": { "gain": 49e-3, "offset": 0, "units": "g" },
    }

    DEFAULT_NODE_PARAMETERS = {  # noqa: RUF012 -- dict is mutable but treated as a constant
        "A0": { "gain": 3.3 / 2**16, "offset": 0.0, "sensor_id": "lvdt" },
        "A1": { "gain": 3.3 / 2**16, "offset": 0.0, "sensor_id": "lvdt" },
        "A2": { "gain": 3.3 / 2**16, "offset": 0.0, "sensor_id": "lvdt" },
        "A3": { "gain": 3.3 / 2**16, "offset": 0.0, "sensor_id": "lvdt" },
        "A4": { "gain": 3.3 / 2**16, "offset": 0.0, "sensor_id": "lvdt" },
        "A5": { "gain": 3.3 / 2**16, "offset": 0.0, "sensor_id": "lvdt" },
        "A6": { "gain": 3.3 / 2**16, "offset": 0.0, "sensor_id": "thrm_mcp9700" },
        "A7": { "gain": 3.3 / 2**16, "offset": 0.0, "sensor_id": "battery_sense" },
        "xl3d": { "gain": 1.0, "offset": 0.0, "sensor_id": "xl3d_adxl375"},
    }

    @staticmethod
    def get_calibration_file_comments() -> str:
        """Return a formatted string to use as comments in a calibration file."""
        return textwrap.dedent("""\
            # Calibration coefficients for the QT Py Soil Swell app

            # Sensor collection
            #   Name format:  [sensors.{sensor_identifier}]
            #   Example:  [sensors.lvdt_10cm_1]
            #   The value of {sensor_identifier} must be used in the 'sensor_id' for a node's channel to apply scaling to that channel
            #   The same {sensor_identifier} may used on multiple channels to apply the same scaling to each
            #   The scaling is linear and converts the innate measurement from the channel to the sensor's physical units:  physical = {gain} * volts + {offset}

            # Node collection
            #   Name format:  [nodes.{node_identifier}.{node_channel}]
            #   Example:  [nodes.node-77aa77aa77aa-0].A0]
            #   The {node_identifier} must match the 'Node ID' reported by the QT Py Scanner app
            #   To use a sensor node, 8 analog input channels and the accelerometer channel must be specified
            #     {node_channel} values:  A0  A1  A2  A3  A4  A5  A6  A7  xl3d
            #   The scaling is linear and converts the raw codes from the channel to its innate measurement:  measurement = {gain} * code + {offset}

            """
        )

    @staticmethod
    def get_default_scaling_coefficients() -> dict:
        """Return the default scaling coefficients used by the RawDataProcessor."""
        return {
            "nodes": {
                "node-77aa77aa77aa-0": RawDataProcessor.DEFAULT_NODE_PARAMETERS,
            },
            "sensors": RawDataProcessor.DEFAULT_SENSOR_PARAMETERS,
        }

    def __init__(self) -> None:
        """Initialize a new RawDataProcessor instance."""
        self._sensor_parameters = {
            # Loaded from file
        }
        self._sensor_node_parameters = {
            # Loaded from file
        }

        self._frame_columns = []
        self._lvdt_position_columns = []
        self._lvdt_displacement_columns = []
        self._relative_time_column = "relative_time_minutes"
        self._build_column_information()

    @property
    def frame_columns(self) -> list:
        """Return a list of the column names returned by 'process_new_data'."""
        return self._frame_columns

    @property
    def relative_time_column(self) -> str:
        """Return the name of the column that holds relative timestamps."""
        return self._relative_time_column

    @property
    def lvdt_position_columns(self) -> list[str]:
        """Return the names of the columns that hold the absolute LVDT positions."""
        return self._lvdt_position_columns

    @property
    def lvdt_displacement_columns(self) -> list[str]:
        """Return the names of the columns that hold the relative LVDT movements."""
        return self._lvdt_displacement_columns

    @property
    def temperature_column(self) -> str:
        """Return the name of the column that holds the temperature."""
        return self._temperature_column

    @property
    def battery_column(self) -> str:
        """Return the name of the column that holds the battery voltage."""
        return self._battery_column

    @property
    def g_level_column(self) -> str:
        """Return the name of the column that holds the acceleration."""
        return self._g_level_column

    @property
    def logged_columns(self) -> list[str]:
        """Return the names of the columns written to the data log file."""
        return [
            self.relative_time_column,
            *self.lvdt_position_columns,
            self.g_level_column,
        ]

    def load_scaling_coefficients_from_file(self, calibration_file: pathlib.Path) -> None:
        """Load the scaling coefficients from the specified calibration_file."""
        scaling_information = toml.load(calibration_file)
        self._sensor_node_parameters.clear()
        self._sensor_node_parameters.update(scaling_information["nodes"])
        self._sensor_parameters.clear()
        self._sensor_parameters.update(scaling_information["sensors"])

    def _build_column_information(self) -> None:
        """Iterate over the channels and initialize the column properties."""
        self._frame_columns.extend(["timestamp", self._relative_time_column])
        self._frame_columns.extend(["node_id", "node_name"])
        for index, channel_name in enumerate(RawDataProcessor.DEFAULT_NODE_PARAMETERS):
            match index:
                case i if 0 <= i <= 5:
                    sensor_parameters = RawDataProcessor.DEFAULT_SENSOR_PARAMETERS["lvdt"]
                    sensor_units = sensor_parameters["units"]
                    lvdt_position_column = f"lvdt{index+1}_position_{sensor_units}"  # 6 LVDTs, index them starting at 1
                    lvdt_displacement_column = f"lvdt{index+1}_displacement_{sensor_units}"
                    self._lvdt_position_columns.append(lvdt_position_column)
                    self._lvdt_displacement_columns.append(lvdt_displacement_column)
                    self._frame_columns.extend(
                        [
                            f"{channel_name}_average_code",
                            f"{channel_name}_volts",
                            lvdt_position_column,
                            lvdt_displacement_column,
                        ]
                    )
                case 6:
                    sensor_parameters = RawDataProcessor.DEFAULT_SENSOR_PARAMETERS["thrm_mcp9700"]
                    sensor_units = sensor_parameters["units"]
                    self._temperature_column = f"temperature_{sensor_units}"  # No index, only one temp sensor
                    self._frame_columns.extend(
                        [
                            f"{channel_name}_average_code",
                            f"{channel_name}_volts",
                            self._temperature_column,
                        ]
                    )
                case 7:
                    sensor_parameters = RawDataProcessor.DEFAULT_SENSOR_PARAMETERS["battery_sense"]
                    sensor_units = sensor_parameters["units"]
                    self._battery_column = f"battery_sense_{sensor_units}"  # No index, only one battery sense channel
                    self._frame_columns.extend(
                        [
                            f"{channel_name}_average_code",
                            f"{channel_name}_volts",
                            self._battery_column,
                        ]
                    )
                case 8:
                    sensor_parameters = RawDataProcessor.DEFAULT_SENSOR_PARAMETERS["xl3d_adxl375"]
                    sensor_units = sensor_parameters["units"]
                    self._g_level_column = f"z_accel_{sensor_units}"
                    self._frame_columns.extend(
                        [
                            "z_accel_average_code",
                            self._g_level_column,
                        ]
                    )

    def process_raw_data(self, first_row: pd.Series | None, data_timestamp: datetime.datetime, node_id: str, raw_data: list) -> pd.Series:
        """Scale the raw data to Volts and physical units and return a Series of the new row."""
        first_timestamp = first_row.loc["timestamp"] if first_row is not None else data_timestamp
        relative_timestamp = (data_timestamp - first_timestamp).seconds / 60

        new_row = []
        new_row.extend([data_timestamp, relative_timestamp])
        new_row.extend([node_id, node_id])
        if node_id not in self._sensor_node_parameters:
            print(f"No calibration information for node '{node_id}'")
        node_parameters = self._sensor_node_parameters.get(node_id, RawDataProcessor.DEFAULT_NODE_PARAMETERS)
        for index, channel_name in enumerate(node_parameters):
            channel_parameters = node_parameters[channel_name]
            sensor_id = channel_parameters["sensor_id"]
            if sensor_id not in self._sensor_parameters:
                print(f"  No calibration information for sensor '{sensor_id}'")
            raw_sample = raw_data[index]
            match index:
                case i if 0 <= i <= 5:
                    default_sensor_parameters = RawDataProcessor.DEFAULT_SENSOR_PARAMETERS["lvdt"]
                    sensor_parameters = self._sensor_parameters.get(sensor_id, default_sensor_parameters)
                    scaled_sample = raw_sample * channel_parameters["gain"] + channel_parameters["offset"]
                    physical_measurement = scaled_sample * sensor_parameters["gain"] + sensor_parameters["offset"]
                    first_measurement = first_row.loc[self.lvdt_position_columns[index]] if first_row is not None else physical_measurement
                    new_row.extend(
                        [
                            raw_sample,
                            scaled_sample,
                            physical_measurement,
                            physical_measurement - first_measurement,
                        ]
                    )
                case 6:
                    default_sensor_parameters = RawDataProcessor.DEFAULT_SENSOR_PARAMETERS["thrm_mcp9700"]
                    sensor_parameters = self._sensor_parameters.get(sensor_id, default_sensor_parameters)
                    scaled_sample = raw_sample * channel_parameters["gain"] + channel_parameters["offset"]
                    physical_measurement = scaled_sample * sensor_parameters["gain"] + sensor_parameters["offset"]
                    new_row.extend(
                        [
                            raw_sample,
                            scaled_sample,
                            physical_measurement,
                        ]
                    )
                case 7:
                    default_sensor_parameters = RawDataProcessor.DEFAULT_SENSOR_PARAMETERS["battery_sense"]
                    sensor_parameters = self._sensor_parameters.get(sensor_id, default_sensor_parameters)
                    scaled_sample = raw_sample * channel_parameters["gain"] + channel_parameters["offset"]
                    physical_measurement = scaled_sample * sensor_parameters["gain"] + sensor_parameters["offset"]
                    new_row.extend(
                        [
                            raw_sample,
                            scaled_sample,
                            physical_measurement,
                        ]
                    )
                case 8:
                    default_sensor_parameters = RawDataProcessor.DEFAULT_SENSOR_PARAMETERS["xl3d_adxl375"]
                    sensor_parameters = self._sensor_parameters.get(sensor_id, default_sensor_parameters)
                    physical_measurement = raw_sample * sensor_parameters["gain"] + sensor_parameters["offset"]
                    new_row.extend(
                        [
                            raw_sample,
                            physical_measurement,
                        ]
                    )
                case _:
                    # If a sensor reaches this code path, then the column headers likely won't match
                    unknown_sensor_parameters = { "gain": 1.0, "offset": 0.0, "units": "unknown_units" }
                    sensor_parameters = self._sensor_parameters.get(sensor_id, unknown_sensor_parameters)
                    scaled_sample = raw_sample * channel_parameters["gain"] * channel_parameters["offset"]
                    physical_measurement = scaled_sample * sensor_parameters["gain"] + sensor_parameters["offset"]
                    new_row.extend(
                        [
                            raw_sample,
                            scaled_sample,
                            physical_measurement,
                        ]
                    )
        new_row_series = pd.Series(new_row, index=self.frame_columns)
        return new_row_series


class AppState:
    """A class that models and controls the app's settings and runtime state."""

    canceled_file = pathlib.Path()
    settings_file = pathlib.Path(
        click.get_app_dir(app_name="qtpy-datalogger", roaming=False)
    ).joinpath(pathlib.Path(__file__).stem).joinpath("settings.toml")

    @staticmethod
    def ensure_settings_file() -> None:
        """Guarantee that the settings file for the app exists and parses correctly."""
        if AppState.settings_file.exists():
            precheck = toml.load(AppState.settings_file)
            if "startup" in precheck:
                return
        pathlib.Path.mkdir(AppState.settings_file.parent, parents=True, exist_ok=True)
        with AppState.settings_file.open("w") as file:
            default_settings = {
                "startup": {
                    "theme": "cosmo",
                    "group": str(datatypes.Default.MqttGroup),
                    "sample rate": str(SampleRate.Fast),
                    "calibration file": str(SoilSwell.CommandName.DefaultCalibrationFile),
                },
                "calibration file history": []
            }
            toml.dump(default_settings, file)
        default_scaling_file = AppState.settings_file.with_name(f"{SoilSwell.CommandName.DefaultCalibrationFile}.toml")
        with default_scaling_file.open("w") as file:
            file.write(RawDataProcessor.get_calibration_file_comments())
            toml.dump(RawDataProcessor.get_default_scaling_coefficients(), file)

    class Event(StrEnum):
        """Events emitted when properties change."""

        AcquireDataChanged = "<<AcquireDataChanged>>"
        BatteryLevelChanged = "<<BatteryLevelChanged>>"
        BatteryVoltageChanged = "<<BatteryVoltageChanged>>"
        CalibrationFileChanged = "<<CalibrationFileChanged>>"
        CalibrationFileHistoryChanged = "<<CalibrationFileHistoryChanged>>"
        CanAcquireDataChanged = "<<CanAcquireDataChanged>>"
        CanLogDataChanged = "<<CanLogDataChanged>>"
        CanSetSensorGroupChanged = "<<CanSetSensorGroupChanged>>"
        LogDataChanged = "<<LogDataChanged>>"
        SampleRateChanged = "<<SampleRateChanged>>"
        SensorGroupChanged = "<<SensorGroupChanged>>"
        DemoModeChanged = "<<DemoModeChanged>>"
        NewDataProcessed = "<<NewDataProcessed>>"

    def __init__(self, tk_root: tk.Tk, post_processor: RawDataProcessor) -> None:
        """Initialize a new AppState instance."""
        self._tk_notifier = tk_root
        self._post_processor = post_processor
        self._theme_name = ""
        self._sensor_group = ""
        self._sample_rate = SampleRate.Unset
        self._acquire_active = Tristate.BoolUnset
        self._log_data_active = Tristate.BoolUnset
        self._battery_voltage = 0.0
        self._battery_level = BatteryLevel.Unset
        self._most_recent_timestamp = datetime.datetime.min.replace(tzinfo=datetime.UTC)
        self._acquired_data = pd.DataFrame()
        self._demo_active = False
        self._log_file_path = AppState.canceled_file
        self._index_when_log_enabled = -1
        self._calibration_file = ""
        self._calibration_file_history = []

    @property
    def active_theme(self) -> str:
        """Return the name of the active ttkbootstrap theme."""
        return self._theme_name

    @active_theme.setter
    def active_theme(self, new_value: str) -> None:
        """Set a new value for active_theme and change themes to match."""
        if new_value == self._theme_name:
            return
        self._theme_name = new_value
        ttk.Style().theme_use(new_value)

    @property
    def sensor_group(self) -> str:
        """Get the active sensor_group."""
        return self._sensor_group

    @sensor_group.setter
    def sensor_group(self, new_value: str) -> None:
        """Set a new value for sensor_group and notify SensorGroupChanged event subscribers."""
        if new_value == self._sensor_group:
            return
        self._sensor_group = new_value
        self._tk_notifier.event_generate(AppState.Event.SensorGroupChanged)
        self._tk_notifier.event_generate(AppState.Event.CanAcquireDataChanged)

    @property
    def can_change_group(self) -> bool:
        """Return True when the app can change the sensor group name."""
        return self._acquire_active != Tristate.BoolTrue

    @property
    def sample_rate(self) -> SampleRate:
        """Get the active sample_rate."""
        return self._sample_rate

    @sample_rate.setter
    def sample_rate(self, new_value: SampleRate) -> None:
        """Set a new value for sample_rate and notify SampleRateChanged event subscribers."""
        if new_value == self._sample_rate:
            return
        self._sample_rate = new_value
        self._tk_notifier.event_generate(AppState.Event.SampleRateChanged)

    @property
    def acquire_active(self) -> Tristate:
        """Return True when the app is acquiring data."""
        return self._acquire_active

    @acquire_active.setter
    def acquire_active(self, new_value: Tristate) -> None:
        """Set a new value for acquire_active and notify AcquireDataChanged event subscribers."""
        if new_value == self.acquire_active:
            return
        self._acquire_active = new_value
        self._tk_notifier.event_generate(AppState.Event.AcquireDataChanged)
        if self.log_data_active:
            # Disable logging on stop (start is noop)
            self.log_data_active = False
        self._tk_notifier.event_generate(AppState.Event.CanLogDataChanged)
        self._tk_notifier.event_generate(AppState.Event.CanSetSensorGroupChanged)

    @property
    def can_acquire(self) -> bool:
        """Return True when the app can acquire data."""
        has_group_name = len(self.sensor_group) > 0
        return has_group_name

    @property
    def log_data_active(self) -> bool:
        """Return True when the app is logging data."""
        return self._log_data_active == Tristate.BoolTrue

    @log_data_active.setter
    def log_data_active(self, new_value: bool) -> None:
        """Set a new value for log_data_active and notify LogDataChanged event subscribers."""
        as_tristate = Tristate.BoolTrue if new_value else Tristate.BoolFalse
        if as_tristate == self._log_data_active:
            return
        self._log_data_active = as_tristate
        self._index_when_log_enabled = len(self.data.index) if self.log_data_active else -1
        self._tk_notifier.event_generate(AppState.Event.LogDataChanged)

    @property
    def log_file_path(self) -> pathlib.Path:
        """Return the path to the log file."""
        return self._log_file_path

    @log_file_path.setter
    def log_file_path(self, new_value: pathlib.Path) -> None:
        """Set a new value for the log file path."""
        if str(new_value) == str(self._log_file_path):
            return
        self._log_file_path = new_value

    @property
    def index_when_log_enabled(self) -> int:
        """Return the index of the row when the user enabled logging."""
        return self._index_when_log_enabled

    @property
    def can_log_data(self) -> bool:
        """Return True when the app can log data."""
        acquire_is_active = self.acquire_active
        return acquire_is_active == Tristate.BoolTrue

    @property
    def battery_level(self) -> BatteryLevel:
        """Return the battery level."""
        return self._battery_level

    @battery_level.setter
    def battery_level(self, new_value: BatteryLevel) -> None:
        """Set a new value for battery_level and notify BatteryLevelChanged event subscribers."""
        if new_value == self._battery_level:
            return
        self._battery_level = new_value
        self._tk_notifier.event_generate(AppState.Event.BatteryLevelChanged)

    @property
    def battery_voltage(self) -> float:
        """Return the most recently measured voltage for the sensor_node's battery."""
        return self._battery_voltage

    @battery_voltage.setter
    def battery_voltage(self, new_value: float) -> None:
        """Set a new value for battery_voltage and notify BatteryVoltageChanged event subscribers."""
        if new_value == self._battery_voltage:
            return
        self._battery_voltage = new_value
        self._tk_notifier.event_generate(AppState.Event.BatteryVoltageChanged)

    @property
    def demo_active(self) -> bool:
        """Return True if the demo is active."""
        return self._demo_active

    @demo_active.setter
    def demo_active(self, new_value: bool) -> None:
        """Set a new value for demo_active and notify DemoModeChanged event subscribers."""
        if new_value == self._demo_active:
            return
        self._demo_active = new_value
        self._tk_notifier.event_generate(AppState.Event.DemoModeChanged)

    @property
    def most_recent_timestamp(self) -> datetime.datetime:
        """Return the UTC time of the most recently acquired sensor scan."""
        return self._most_recent_timestamp

    @property
    def data(self) -> pd.DataFrame:
        """Return the data that the app has collected since acquisition started."""
        return self._acquired_data

    @data.setter
    def data(self, new_value: pd.DataFrame) -> None:
        """Set a new value for the acquired data and notify NewDataProcessed subscribers."""
        # maybe use an 'is' test
        if new_value.shape == self._acquired_data.shape:
            return
        self._acquired_data = new_value
        self._tk_notifier.event_generate(AppState.Event.NewDataProcessed)

    @property
    def calibration_file(self) -> str:
        """Return the path to the calibration file."""
        return self._calibration_file

    @calibration_file.setter
    def calibration_file(self, new_value: str) -> None:
        """Set a new value for the calibration file and notify CalibrationFileChanged and CalibrationFileHistoryChanged subscribers."""
        if new_value == self._calibration_file:
            return
        self._calibration_file = new_value
        self.load_calibration()
        self._tk_notifier.event_generate(AppState.Event.CalibrationFileChanged)

        if new_value == SoilSwell.CommandName.DefaultCalibrationFile:
            return

        settings = self.load_app_settings()
        history: list[str] = settings["calibration file history"]
        try:
            old_index = history.index(new_value)
            history.pop(old_index)
        except ValueError:
            pass
        history.insert(0, new_value)
        self.save_app_settings(settings)
        self._calibration_file_history.clear()
        self._calibration_file_history.extend(history)
        self._tk_notifier.event_generate(AppState.Event.CalibrationFileHistoryChanged)

    @property
    def calibration_file_history(self) -> list[str]:
        """Return the list of previously used calibration files."""
        valid_files = []
        for file in self._calibration_file_history:
            file_as_path = pathlib.Path(file)
            if file_as_path.exists():
                valid_files.append(file)
        return valid_files

    def reset(self) -> None:
        """Reset the properties to default on-launch values."""
        app_settings = self.load_app_settings()
        user_settings = app_settings["startup"]
        self._battery_level = BatteryLevel.Unknown
        self._battery_voltage = 0.0
        self._sensor_group = user_settings.get("group", datatypes.Default.MqttGroup)
        self._sample_rate = SampleRate(user_settings.get("sample rate", SampleRate.Fast))
        self._acquire_active = Tristate.BoolFalse
        self._log_data_active = False
        self._demo_active = False
        self._acquired_data = pd.DataFrame()
        self._most_recent_timestamp = datetime.datetime.min.replace(tzinfo=datetime.UTC)
        self._log_file_path = AppState.canceled_file
        self._index_when_log_enabled = -1
        self._calibration_file = user_settings["calibration file"]
        self._calibration_file_history = app_settings["calibration file history"]

        self.load_calibration()
        self.active_theme = user_settings.get("theme", "cosmo")  # Propagate theme first
        def notify_all() -> None:
            self._tk_notifier.event_generate(AppState.Event.BatteryLevelChanged)
            self._tk_notifier.event_generate(AppState.Event.BatteryVoltageChanged)
            self._tk_notifier.event_generate(AppState.Event.SensorGroupChanged)
            self._tk_notifier.event_generate(AppState.Event.CanSetSensorGroupChanged)
            self._tk_notifier.event_generate(AppState.Event.SampleRateChanged)
            self._tk_notifier.event_generate(AppState.Event.AcquireDataChanged)
            self._tk_notifier.event_generate(AppState.Event.CanAcquireDataChanged)
            self._tk_notifier.event_generate(AppState.Event.DemoModeChanged)
            self._tk_notifier.event_generate(AppState.Event.LogDataChanged)
            self._tk_notifier.event_generate(AppState.Event.CanLogDataChanged)
            self._tk_notifier.event_generate(AppState.Event.NewDataProcessed)
            self._tk_notifier.event_generate(AppState.Event.CalibrationFileChanged)
            self._tk_notifier.event_generate(AppState.Event.CalibrationFileHistoryChanged)
        self._tk_notifier.after(0, notify_all)

    def load_app_settings(self) -> dict:
        """Load the user's configured settings and return a dictionary of their values."""
        AppState.ensure_settings_file()
        user_settings = toml.load(AppState.settings_file)
        return user_settings

    def save_app_settings(self, new_settings: dict) -> None:
        """Save the user's configured settings."""
        with AppState.settings_file.open("w") as file:
            toml.dump(new_settings, file)

    def load_calibration(self) -> None:
        """Load the scaling coefficients."""
        file = self.calibration_file
        if file == SoilSwell.CommandName.DefaultCalibrationFile:
            file = AppState.settings_file.with_name(f"{SoilSwell.CommandName.DefaultCalibrationFile}.toml")
        self._post_processor.load_scaling_coefficients_from_file(pathlib.Path(file))

    def toggle_demo(self) -> None:
        """Start a demonstration session."""
        if self.acquire_active == Tristate.BoolTrue and not self.demo_active:
            # Do not interrupt a genuine session
            return
        if self.demo_active:
            self.demo_active = False
            self.acquire_active = Tristate.BoolFalse
            return
        self.sensor_group = "<< DEMO >>"
        package = importlib.resources.files(qtpy_datalogger)
        assets = package.joinpath("assets")
        demo_file = assets.joinpath("soil_swell_demo.csv")
        with importlib.resources.as_file(demo_file) as demo_data:
            self._demo_data = pd.read_csv(demo_data)
        self.demo_active = True
        self.acquire_active = Tristate.BoolTrue

    def process_new_data(self, node_id: str, new_data: list[float]) -> None:
        """Take the new_data and process it for plotting and logging."""
        first_row_series = self.data.iloc[0] if self.data.size > 0 else None
        self._most_recent_timestamp = datetime.datetime.now(tz=datetime.UTC)
        new_frame_row = self._post_processor.process_raw_data(
            first_row_series,
            self.most_recent_timestamp,
            node_id,
            new_data,
        )
        self.data = pd.concat([self.data, new_frame_row.to_frame().T], ignore_index=True)


class SoilSwell(guikit.AsyncWindow):
    """A GUI that acquires, plots, and logs data from a soil swell test."""

    app_name = "Soil Swell Test"

    class CommandName(StrEnum):
        """Names used for menus and commands in the app."""

        File = "File"
        SaveFullLog = "Save full log..."
        Exit = "Exit"
        Settings = "Settings"
        CalibrationFile = "Calibration file"
        DefaultCalibrationFile = "Default scaling"
        BrowseCalibrationFile = "Browse..."
        NewCalibrationFile = "New..."
        AppSettings = "App settings..."
        View = "View"
        Theme = "Theme"
        Help = "Help"
        Demo = "Demo"
        About = "About"
        Acquire = "Acquire"
        LogData = "Log Data"
        Reset = "Reset"

    def create_user_interface(self) -> None:  # noqa: PLR0915 -- allow long function to create the UI
        """Create the main window and connect event handlers."""
        # Supports UI widget state
        self.theme_variable = tk.StringVar()
        self.demo_variable = tk.BooleanVar()
        self.sensor_node_group_variable = tk.StringVar()
        self.sample_rate_variable = tk.StringVar()
        self.calibration_file_variable = tk.StringVar()
        self.log_data_variable = tk.BooleanVar()
        self.svg_images: dict[str, tk.Image] = {}
        self.menu_text_for_theme = {
            "cosmo": "  Cosmo",
            "flatly": "  Flatly",
            "cyborg": "   Cyborg",
            "darkly": "   Darkly",
            "vapor": "  Debug",
        }
        self.icon_name_for_battery_level = {
            BatteryLevel.Unset: "battery-empty",
            BatteryLevel.Unknown: "battery-empty",
            BatteryLevel.Low: "battery-quarter",
            BatteryLevel.Half: "battery-half",
            BatteryLevel.High: "battery-three-quarters",
            BatteryLevel.Full: "battery-full",
        }
        BATTERY_COUNT = 1
        # https://www.powerstream.com/AA-tests.htm for 100 mA
        self.battery_level_for_voltage = {
            1.40 * BATTERY_COUNT: BatteryLevel.Full,
            1.30 * BATTERY_COUNT: BatteryLevel.High,
            1.22 * BATTERY_COUNT: BatteryLevel.Half,
            1.00 * BATTERY_COUNT: BatteryLevel.Low,
            -1.0: BatteryLevel.Unset,
        }
        self.tooltip_message_for_battery_level = {
            BatteryLevel.Unset: "The battery doesn't have a level",
            BatteryLevel.Unknown: "The battery's level is unknown",
            BatteryLevel.Low: "The battery is critically low and cannot sustain DAQ functions",
            BatteryLevel.Half: "The battery is low and requires recharging soon",
            BatteryLevel.High: "The battery is discharging",
            BatteryLevel.Full: "The battery is full",
        }
        self.battery_level_tooltip = None
        self.tool_window = None
        self.settings_window = None
        self.scanner_process = None
        self.position_axis_limits = (-0.1, 2.6)
        self.displacement_axis_limits = (-2.6, 2.6)
        self.g_level_axis_limits = (-1, 255)
        self.time_axis_limits = (-1, 60000)

        # Supports app state
        self.data_processor = RawDataProcessor()
        self.state = AppState(self.root_window, self.data_processor)
        self.background_tasks: set[asyncio.Task] = set()

        # The MQTT connection
        self.qtpy_controller: network.QTPyController | None = None
        self.nodes_in_group : list[discovery.QTPyDevice] = []
        self.snsr_app_name = pathlib.Path(__file__).stem

        # arrow-up-from-ground-water droplet
        app_icon = icon_to_image("arrow-up-from-ground-water", fill=app_icon_color, scale_to_height=256)
        self.root_window.iconphoto(True, app_icon)
        self.build_window_menu()

        figure_dpi = 112
        # self.root_window.minsize
        self.root_window.columnconfigure(0, weight=1)
        self.root_window.rowconfigure(0, weight=1)

        main = ttk.Frame(self.root_window, name="main_frame", style=bootstyle.DEFAULT)
        main.grid(column=0, row=0, sticky=tk.NSEW)
        main.columnconfigure(0, weight=1)  # Graph frame
        main.columnconfigure(1, weight=0)  # Control frame
        main.rowconfigure(0, weight=1)

        # matplotlib elements must be created before setting the theme or the button icons initialize with poor color contrast
        self.graph_frame = ttk.Frame(main, name="graph_frame", style=bootstyle.LIGHT)
        self.graph_frame.grid(column=0, row=0, sticky=tk.NSEW, padx=(16, 0), pady=16)
        self.graph_frame.columnconfigure(0, weight=1)
        self.graph_frame.rowconfigure(0, weight=1)
        plot_figure = mpl_figure.Figure(figsize=(7, 5), dpi=figure_dpi)
        self.canvas_figure = ttkbootstrap_matplotlib.create_styled_plot_canvas(plot_figure, self.graph_frame)
        self.canvas_figure.mpl_connect("button_press_event", self.on_graph_mouse_down)
        self.canvas_figure.mpl_connect("pick_event", self.on_graph_pick)
        plot_figure.subplots_adjust(
            left=0.12,
            bottom=0.10,
            right=0.95,
            top=0.97,
        )

        all_subplots = plot_figure.subplots(
            nrows=3,
            ncols=1,
            sharex=True,
        )
        self.position_axes: mpl_axes.Axes = all_subplots[0]
        self.displacement_axes: mpl_axes.Axes = all_subplots[1]
        self.g_level_axes: mpl_axes.Axes = all_subplots[2]
        self.configure_all_axes()

        self.tool_frame = ttk.Frame(main, name="tool_panel")
        self.tool_frame.grid(column=1, row=0, sticky=tk.NSEW)
        self.tool_frame.columnconfigure(0, weight=1)
        self.tool_frame.rowconfigure(0, weight=0, minsize=36)  # Filler
        self.tool_frame.rowconfigure(1, weight=0)  # Status
        self.tool_frame.rowconfigure(2, weight=0, minsize=24)  # Filler
        self.tool_frame.rowconfigure(3, weight=0)  # Settings
        self.tool_frame.rowconfigure(4, weight=0, minsize=24)  # Filler
        self.tool_frame.rowconfigure(5, weight=0)  # Action

        status_panel = ttk.Frame(self.tool_frame, name="status_panel", style=bootstyle.SECONDARY)
        status_panel.columnconfigure(0, weight=1)
        status_panel.rowconfigure(0, weight=1)
        status_panel.grid(column=0, row=1, sticky=tk.NSEW, padx=(26, 24))
        status_contents = self.create_status_panel()
        status_contents.grid(in_=status_panel, column=0, row=0, padx=2, pady=2, sticky=tk.NSEW)

        settings_panel = ttk.Frame(self.tool_frame, name="settings_panel", style=bootstyle.SECONDARY)
        settings_panel.columnconfigure(0, weight=1)
        settings_panel.rowconfigure(0, weight=1)
        settings_panel.grid(column=0, row=3, sticky=tk.NSEW, padx=(26, 24))
        settings_contents = self.create_settings_panel()
        settings_contents.grid(in_=settings_panel, column=0, row=0, padx=2, pady=2, sticky=tk.NSEW)

        action_panel = ttk.Frame(self.tool_frame, name="action_panel", style=bootstyle.SECONDARY)
        action_panel.columnconfigure(0, weight=1)
        action_panel.rowconfigure(0, weight=1)
        action_panel.grid(column=0, row=5, sticky=tk.NSEW, padx=(26, 24))
        self.action_contents = self.create_action_panel()
        self.action_contents.grid(in_=action_panel, column=0, row=0, sticky=tk.NSEW)

        self.root_window.bind("<<ThemeChanged>>", self.on_theme_changed)
        self.root_window.bind(AppState.Event.AcquireDataChanged, self.on_acquire_changed)
        self.root_window.bind(AppState.Event.CanAcquireDataChanged, self.on_can_acquire_changed)
        self.root_window.bind(AppState.Event.LogDataChanged, self.on_log_data_changed)
        self.root_window.bind(AppState.Event.CanLogDataChanged, self.on_can_log_data_changed)
        self.root_window.bind(AppState.Event.BatteryLevelChanged, self.on_battery_level_changed)
        self.root_window.bind(AppState.Event.BatteryVoltageChanged, self.on_battery_voltage_changed)
        self.root_window.bind(AppState.Event.SampleRateChanged, self.on_sample_rate_changed)
        self.root_window.bind(AppState.Event.SensorGroupChanged, self.on_sensor_group_changed)
        self.root_window.bind(AppState.Event.CanSetSensorGroupChanged, self.on_can_set_sensor_group_changed)
        self.root_window.bind(AppState.Event.DemoModeChanged, self.on_demo_mode_changed)
        self.root_window.bind(AppState.Event.NewDataProcessed, self.on_new_data_processed)
        self.root_window.bind(AppState.Event.CalibrationFileChanged, self.on_calibration_file_changed)
        self.root_window.bind(AppState.Event.CalibrationFileHistoryChanged, self.on_calibration_file_history_changed)

        self.update_window_title(SoilSwell.app_name)
        self.handle_reset(sender=self.reset_button)
        self.root_window.update_idletasks()

        self.icon_index = 0
        self.cycle_battery_icon()

    def build_window_menu(self) -> None:
        """Create the entries for the window menu bar."""
        self.menubar = tk.Menu(
            self.root_window,
        )
        self.root_window.config(menu=self.menubar)

        # File menu
        self.file_menu = tk.Menu(self.menubar, name="file_menu")
        self.menubar.add_cascade(
            label=SoilSwell.CommandName.File,
            menu=self.file_menu,
            underline=0,
        )
        self.file_menu.add_command(
            command=self.save_full_log,
            label=SoilSwell.CommandName.SaveFullLog,
            underline=0,
        )
        self.file_menu.add_separator()
        self.file_menu.add_command(
            command=functools.partial(self.safe_exit, tk.Event()),
            label=SoilSwell.CommandName.Exit,
            accelerator="Alt-F4",
        )
        self.root_window.bind("<Alt-F4>", self.safe_exit)

        # Settings menu
        self.settings_menu = tk.Menu(self.menubar, name="settings_menu")
        self.menubar.add_cascade(
            label="Settings",
            menu=self.settings_menu,
            underline=0,
        )
        # Calibration submenu
        self.calibration_menu = tk.Menu(self.settings_menu, name="calibration_menu")
        self.settings_menu.add_cascade(
            label=SoilSwell.CommandName.CalibrationFile,
            menu=self.calibration_menu,
            underline=0,
        )

        self.settings_menu.add_separator()
        self.settings_menu.add_command(
            command=functools.partial(self.open_settings_dialog, tk.Event()),
            label=SoilSwell.CommandName.AppSettings,
            underline=0,
        )

        # View menu
        self.view_menu = tk.Menu(self.menubar, name="view_menu")
        self.menubar.add_cascade(
            label=SoilSwell.CommandName.View,
            menu=self.view_menu,
            underline=0,
        )
        # Themes submenu
        icon_color = guikit.hex_string_for_style(StyleKey.Fg)
        light_mode_icon = icon_to_image("sun", fill=icon_color, scale_to_height=15)
        dark_mode_icon = icon_to_image("moon", fill=icon_color, scale_to_height=15)
        debug_mode_icon = icon_to_image("bolt", fill=icon_color, scale_to_height=15)
        self.svg_images["sun"] = light_mode_icon
        self.svg_images["moon"] = dark_mode_icon
        self.svg_images["bolt"] = debug_mode_icon
        self.themes_menu = tk.Menu(self.view_menu, name="themes_menu")
        self.view_menu.add_cascade(
            label=SoilSwell.CommandName.Theme,
            menu=self.themes_menu,
            underline=0,
        )
        self.themes_menu.add_radiobutton(
            command=functools.partial(self.change_theme, "cosmo"),
            label=self.menu_text_for_theme["cosmo"],
            image=light_mode_icon,
            compound=tk.LEFT,
            variable=self.theme_variable,
        )
        self.themes_menu.add_radiobutton(
            command=functools.partial(self.change_theme, "flatly"),
            label=self.menu_text_for_theme["flatly"],
            image=light_mode_icon,
            compound=tk.LEFT,
            variable=self.theme_variable,
        )
        self.themes_menu.add_separator()
        self.themes_menu.add_radiobutton(
            command=functools.partial(self.change_theme, "cyborg"),
            label=self.menu_text_for_theme["cyborg"],
            image=dark_mode_icon,
            compound=tk.LEFT,
            variable=self.theme_variable,
        )
        self.themes_menu.add_radiobutton(
            command=functools.partial(self.change_theme, "darkly"),
            label=self.menu_text_for_theme["darkly"],
            image=dark_mode_icon,
            compound=tk.LEFT,
            variable=self.theme_variable,
        )
        self.themes_menu.add_separator()
        self.themes_menu.add_radiobutton(
            command=functools.partial(self.change_theme, "vapor"),
            label=self.menu_text_for_theme["vapor"],
            image=debug_mode_icon,
            compound=tk.LEFT,
            variable=self.theme_variable,
        )

        # Help menu
        self.help_menu = tk.Menu(self.menubar, name="help_menu")
        self.menubar.add_cascade(
            label=SoilSwell.CommandName.Help,
            menu=self.help_menu,
            underline=0,
        )
        self.help_menu.add_checkbutton(
            command=self.toggle_demo,
            label=SoilSwell.CommandName.Demo,
            variable=self.demo_variable,
        )
        self.help_menu.add_separator()
        self.help_menu.add_command(
            command=self.show_about,
            label=SoilSwell.CommandName.About,
            accelerator="F1",
        )
        self.root_window.bind("<F1>", lambda e: self.show_about())

    def create_status_panel(self) -> ttk.Frame:
        """Create teh status panel region of the app."""
        panel = ttk.Frame()
        panel.columnconfigure(0, weight=1)
        panel.columnconfigure(1, weight=1)
        panel.rowconfigure(0, weight=1)

        font_family = "Consolas"
        if font_family in font.families():
            the_font = font.Font(family=font_family, name="custom_fixed")
        else:
            the_font = font.nametofont("fixed")
        the_font.configure(weight=font.BOLD, size=12)
        self.battery_voltage_indicator = ttk.Label(panel, font=the_font)
        self.battery_voltage_indicator.grid(column=0, row=0)

        self.battery_level_indicator = ttk.Label(panel, font=font.Font(weight=font.BOLD), compound=tk.CENTER)
        self.battery_level_indicator.grid(column=1, row=0)
        return panel

    def refresh_battery_icons(self) -> None:
        """Create the icon images for the battery level indicator."""
        full_battery_icon = icon_to_image(self.icon_name_for_battery_level[BatteryLevel.Full], fill=guikit.hex_string_for_style(bootstyle.SUCCESS), scale_to_height=24)
        self.svg_images[self.icon_name_for_battery_level[BatteryLevel.Full]] = full_battery_icon

        high_battery_icon = icon_to_image(self.icon_name_for_battery_level[BatteryLevel.High], fill=guikit.hex_string_for_style(bootstyle.SUCCESS), scale_to_height=24)
        self.svg_images[self.icon_name_for_battery_level[BatteryLevel.High]] = high_battery_icon

        half_battery_icon = icon_to_image(self.icon_name_for_battery_level[BatteryLevel.Half], fill=guikit.hex_string_for_style(bootstyle.WARNING), scale_to_height=24)
        self.svg_images[self.icon_name_for_battery_level[BatteryLevel.Half]] = half_battery_icon

        low_battery_icon = icon_to_image(self.icon_name_for_battery_level[BatteryLevel.Low], fill=guikit.hex_string_for_style(bootstyle.DANGER), scale_to_height=24)
        self.svg_images[self.icon_name_for_battery_level[BatteryLevel.Low]] = low_battery_icon

        unknown_battery_icon = icon_to_image(self.icon_name_for_battery_level[BatteryLevel.Unknown], fill=guikit.hex_string_for_style(bootstyle.SECONDARY), scale_to_height=24)
        self.svg_images[self.icon_name_for_battery_level[BatteryLevel.Unknown]] = unknown_battery_icon

        self.battery_level_indicator.configure(image=self.svg_images[self.icon_name_for_battery_level[self.state.battery_level]])


    def create_settings_panel(self) -> ttk.Frame:
        """Create the settings panel region of the app."""
        panel = ttk.Frame()
        panel.columnconfigure(0, weight=1)
        panel.columnconfigure(1, weight=1)
        panel.rowconfigure(0, weight=1)

        sensor_node_group_label = ttk.Label(panel, text="Sensor node group")
        sensor_node_group_label.grid(column=0, row=0, padx=8, pady=(8, 2), sticky=tk.NSEW)

        self.sensor_node_group = ttk.Entry(panel, textvariable=self.sensor_node_group_variable, width=14, style=bootstyle.PRIMARY)
        self.sensor_node_group.grid(column=0, row=1, padx=(16, 4), pady=(2, 8), sticky=tk.NSEW)
        self.sensor_node_group_variable.trace_add("write", self.handle_change_sensor_group)

        package = importlib.resources.files(qtpy_datalogger)
        assets = package.joinpath("assets")
        telescope_data = assets.joinpath("telescope.svg").read_text()
        telescope_image = svg_to_image(telescope_data, fill="#FFFFFF", scale_to_height=15)
        self.svg_images["telescope"] = telescope_image
        launch_scanner_button = ttk.Button(panel, image=telescope_image, command=self.handle_launch_scanner)
        launch_scanner_button.grid(column=1, row=1, padx=(4, 16), pady=(2, 8), sticky=tk.NSEW)
        ttk_tooltip.ToolTip(launch_scanner_button, text="Launch the QT Py Sensor Node Scanner app", bootstyle=bootstyle.DEFAULT)

        sample_rate_label = ttk.Label(panel, text="Sample rate")
        sample_rate_label.grid(column=0, row=2, padx=8, pady=(8, 2), sticky=tk.NSEW)

        slow_option = ttk.Radiobutton(panel, command=self.handle_change_sample_rate, text=SampleRate.Slow, variable=self.sample_rate_variable, value=SampleRate.Slow)
        slow_option.grid(column=0, row=3, padx=(16, 8), pady=4, sticky=tk.NSEW)
        normal_option = ttk.Radiobutton(panel, command=self.handle_change_sample_rate, text=SampleRate.Normal, variable=self.sample_rate_variable, value=SampleRate.Normal)
        normal_option.grid(column=0, row=4, padx=(16, 8), pady=4, sticky=tk.NSEW)
        fast_option = ttk.Radiobutton(panel, command=self.handle_change_sample_rate, text=SampleRate.Fast, variable=self.sample_rate_variable, value=SampleRate.Fast)
        fast_option.grid(column=0, row=5, padx=(16, 8), pady=4, sticky=tk.NSEW)
        live_option = ttk.Radiobutton(panel, command=self.handle_change_sample_rate, text=SampleRate.Live, variable=self.sample_rate_variable, value=SampleRate.Live)
        live_option.grid(column=0, row=6, padx=(16, 8), pady=(4, 12), sticky=tk.NSEW)

        return panel

    def create_action_panel(self) -> ttk.Frame:
        """Create the action panel region of the app."""
        panel = ttk.Frame()
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(0, weight=1)

        self.acquire_button = self.create_icon_button(
            panel,
            text=SoilSwell.CommandName.Acquire,
            icon_name="satellite-dish",
            spaces=3,
        )
        self.acquire_button.configure(command=functools.partial(self.handle_acquire, self.acquire_button))
        self.acquire_button.grid(column=0, row=0, padx=8, pady=8, sticky=tk.NSEW)
        self.no_nodes_tooltip = ttk_tooltip.ToolTip(
            self.acquire_button,
            text="Connect to the sensor group and start taking measurements.",
            bootstyle=bootstyle.DEFAULT
        )

        self.log_data_button = self.create_icon_button(
            panel,
            text=SoilSwell.CommandName.LogData,
            icon_name="file-waveform",
            spaces=3,
        )
        self.log_data_button.configure(command=functools.partial(self.handle_log_data, self.log_data_button))
        self.log_data_button.grid(column=0, row=1, padx=8, pady=8, sticky=tk.NSEW)

        self.reset_button = self.create_icon_button(
            panel,
            text=SoilSwell.CommandName.Reset,
            icon_name="rotate-left",
            icon_fill=guikit.hex_string_for_style(bootstyle.WARNING),
            spaces=5,
            bootstyle=(bootstyle.OUTLINE, bootstyle.WARNING),  # pyright: ignore reportArgumentType -- the type hint for library uses strings
        )
        self.svg_images["hover-rotate-left"] = icon_to_image("rotate-left", fill=guikit.hex_string_for_style(StyleKey.SelectFg), scale_to_height=24)
        self.reset_button.configure(command=functools.partial(self.handle_reset, self.reset_button))
        self.reset_button.bind("<Enter>", self.on_mouse_enter)
        self.reset_button.bind("<Leave>", self.on_mouse_leave)
        self.reset_button.grid(column=0, row=2, padx=8, pady=8, sticky=tk.NSEW)

        return panel

    def create_icon_button(  # noqa PLR0913 -- allow many parameters for a factory method
        self,
        parent: tk.Widget,
        text: str,
        icon_name: str,
        icon_fill: str = "",
        char_width: int = 15,
        spaces: int = 2,
        bootstyle: str = bootstyle.DEFAULT,
    ) -> ttk.Button:
        """Create a ttk.Button using the specified text and FontAwesome icon_name."""
        text_spacing = 3 * " "
        fill = icon_fill if icon_fill else guikit.hex_string_for_style(StyleKey.SelectFg)
        button_image = icon_to_image(icon_name, fill=fill, scale_to_height=24)
        self.svg_images[icon_name] = button_image
        button = ttk.Button(
            parent,
            text=text + spaces * text_spacing,
            image=button_image,
            compound=tk.RIGHT,
            width=char_width,
            padding=(4, 6, 4, 4),
            bootstyle=bootstyle,  # pyright: ignore callIssue -- the type hint for bootstrap omits its own additions
        )
        return button

    def configure_all_axes(self) -> None:
        """Configure the labels and ticks for every axes plot."""
        self.position_label = self.position_axes.set_ylabel("LVDT position (cm)", picker=True)
        self.position_axes.set_ylim(ymin=-0.1, ymax=2.6)
        self.position_axes.yaxis.set_major_formatter("{x:.2f}")

        self.displacement_label = self.displacement_axes.set_ylabel("Displacement (cm)", picker=True)
        self.displacement_axes.set_ylim(ymin=-2.6, ymax=2.6)
        self.displacement_axes.yaxis.set_major_formatter("{x:.2f}")

        self.g_level_label = self.g_level_axes.set_ylabel("Acceleration (g)", picker=True)
        self.g_level_axes.set_ylim(ymin=-1, ymax=255)
        self.g_level_axes.set_xlim(xmin=-1, xmax=200)

        self.time_label = self.g_level_axes.set_xlabel("Time (minutes)", picker=True)

    async def on_loop(self) -> None:
        """Update the UI with new information."""
        await asyncio.sleep(1e-6)

        self.poll_acquire()

        done_tasks = [task for task in self.background_tasks if task.done()]
        for done_task in done_tasks:
            did_error = done_task.exception()
            if did_error:
                print(did_error)
            had_result = done_task.result()
            if had_result:
                print(had_result)
            self.background_tasks.remove(done_task)

    def safe_exit(self, event_args: tk.Event) -> None:
        """Safely exit the app."""
        if len(self.background_tasks):
            print(f"warning! {len(self.background_tasks)} remain!")
        self.on_closing()
        self.exit()

    def on_closing(self) -> None:
        """Handle the app closing event."""
        if self.scanner_process and self.scanner_process.is_alive():
            self.scanner_process.terminate()
        self.state.acquire_active = Tristate.BoolFalse

    def save_full_log(self) -> None:
        """Handle the 'Save full log' command."""
        if not self.state.data.size:
            return
        time_zero = self.state.data.loc[0, "timestamp"]
        if not isinstance(time_zero, datetime.datetime):
            raise TypeError()
        time_zero_string = time_zero.astimezone().strftime("%Y.%m.%d_%H.%M.%S")
        file_name = filedialog.asksaveasfilename(
            parent=self.root_window,
            title="Specify a CSV file to use for exported data",
            initialfile=f"SoilSwell full log - {time_zero_string}.csv",
            filetypes=[
                ("CSV files", "*.csv"),
            ],
        )
        file_path = pathlib.Path(file_name)
        if file_path == AppState.canceled_file:
            return

        file_path = file_path.with_suffix(".csv")
        self.state.data.to_csv(file_path)

    def open_settings_dialog(self, event_args: tk.Event) -> None:
        """Handle the Settings::AppSettings menu command."""
        if not self.settings_window:
            self.settings_window = SettingsWindow(
                parent=self.root_window,
                title=f"{SoilSwell.app_name} {SoilSwell.CommandName.Settings}".capitalize(),
                settings=self.state.load_app_settings(),
            )
            open_settings_window_task = asyncio.create_task(self.settings_window.show(guikit.DialogBehavior.Modeless))
            self.background_tasks.add(open_settings_window_task)
            open_settings_window_task.add_done_callback(self.finalize_settings_window)

    def finalize_settings_window(self, task: asyncio.Task) -> None:
        """Finalize the SettingsWindow after the user closes it."""
        if not self.settings_window:
            raise RuntimeError()
        self.state.save_app_settings(self.settings_window.settings)
        self.settings_window = None
        self.background_tasks.discard(task)

    def on_calibration_file_changed(self, event_args: tk.Event) -> None:
        """Handle the CalibrationFileChanged event."""
        self.calibration_file_variable.set(self.state.calibration_file)

    def on_calibration_file_history_changed(self, event_args: tk.Event) -> None:
        """Handle the CalibrationFileHistoryChanged event."""
        self.remake_calibration_submenu()

    def remake_calibration_submenu(self) -> None:
        """Remake the submenu that holds the recently used calibration files."""
        self.calibration_menu.delete(0, tk.LAST)
        if self.state.calibration_file_history:
            for entry in self.state.calibration_file_history[:10]:
                entry_name = f"{entry!s}"
                self.calibration_menu.add_radiobutton(
                    command=functools.partial(self.select_calibration_file, entry_name),
                    label=entry_name,
                    variable=self.calibration_file_variable,
                )
        else:
            self.calibration_menu.add_command(
                label="(No recent files)",
                state=tk.DISABLED,
            )
        self.calibration_menu.add_separator()
        self.calibration_menu.add_radiobutton(
            command=functools.partial(self.select_calibration_file, SoilSwell.CommandName.DefaultCalibrationFile),
            label=SoilSwell.CommandName.DefaultCalibrationFile,
            variable=self.calibration_file_variable,
        )
        self.calibration_menu.add_separator()
        self.calibration_menu.add_command(
            command=self.browse_for_calibration_file,
            label=SoilSwell.CommandName.BrowseCalibrationFile,
        )
        self.calibration_menu.add_command(
            command=self.create_new_calibration_file,
            label=SoilSwell.CommandName.NewCalibrationFile,
        )
        self.style_menu(self.calibration_menu)

    def select_calibration_file(self, new_file: str) -> None:
        """Set a new value for the calibration file."""
        self.state.calibration_file = new_file

    def browse_for_calibration_file(self) -> None:
        """Browse for a calibration file."""
        file_name = filedialog.askopenfilename(
            parent=self.root_window,
            title="Specify a calibration file to use for scaling data",
            filetypes=[
                ("TOML files", "*.toml"),
            ],
        )
        file_path = pathlib.Path(file_name)
        if file_path == AppState.canceled_file:
            return
        if not self.calibration_file_is_valid(file_path):
            return
        self.state.calibration_file = f"{file_path!s}"

    def calibration_file_is_valid(self, file_path: pathlib.Path) -> bool:
        """Return True if the specified file is a valid calibration file."""
        return True

    def create_new_calibration_file(self) -> None:
        """Create a new calibration file from the default template."""
        home_folder = pathlib.Path.home()
        new_file = home_folder.joinpath(f"Soil Swell sensor calibration for {self.state.sensor_group}.toml")
        with new_file.open("w") as file:
            file.write(self.data_processor.get_calibration_file_comments())
            toml.dump(self.data_processor.get_default_scaling_coefficients(), file)
        try:
            click.edit(filename=str(new_file), editor="code")
        except click.ClickException:
            click.edit(filename=str(new_file))

    def toggle_demo(self) -> None:
        """Start a demonstration session."""
        self.state.toggle_demo()

    def on_demo_mode_changed(self, event_args: tk.Event) -> None:
        """Handle the DemoCodeChanged event."""
        demo_mode_active = self.state.demo_active
        self.demo_variable.set(demo_mode_active)

    def show_about(self) -> None:
        """Handle the Help::About menu command."""

    def change_theme(self, theme_name: str) -> None:
        """Handle the View::Theme selection command."""
        self.state.active_theme = theme_name

    def on_theme_changed(self, event_args: tk.Event) -> None:
        """Handle the ThemeChanged event."""
        if event_args.widget is not self.root_window:
            return
        theme_kind = ttk_themes.STANDARD_THEMES[self.state.active_theme]["type"]
        new_tool_frame_style = bootstyle.LIGHT if theme_kind == "light" else bootstyle.DARK
        self.tool_frame.configure(bootstyle=new_tool_frame_style)  # pyright: ignore callIssue -- the type hint for bootstrap omits its own additions
        self.action_contents.configure(bootstyle=new_tool_frame_style)  # pyright: ignore callIssue -- the type hint for bootstrap omits its own additions

        # Style the menus
        all_menus = [
            self.file_menu,
            self.settings_menu,
            self.calibration_menu,
            self.view_menu,
            self.themes_menu,
            self.help_menu,
        ]
        for menu in all_menus:
            self.style_menu(menu)

        # Select the active theme in the menu
        self.theme_variable.set(self.menu_text_for_theme[self.state.active_theme])

        # Update image colors -- these could be cached rather than recalculated
        self.svg_images["rotate-left"] = icon_to_image("rotate-left", guikit.hex_string_for_style(bootstyle.WARNING), scale_to_height=24)
        self.reset_button.configure(image=self.svg_images["rotate-left"])
        self.refresh_battery_icons()

    def style_menu(self, menu: tk.Menu) -> None:
        """Style every entry in the specified menu."""
        last_entry = menu.index(tk.END)
        if last_entry is None:
            return
        for index in range(last_entry + 1):
            self.style_menu_entry(menu, index)

    def style_menu_entry(self, menu: tk.Menu, index: int) -> None:
        """Style the specified menu entry."""
        # Force light theme for menus
        with contextlib.suppress(tk.TclError):
            menu.entryconfigure(
                index,
                background="grey94",
            )
        with contextlib.suppress(tk.TclError):
            menu.entryconfigure(
                index,
                foreground="grey5",
            )
        with contextlib.suppress(tk.TclError):
            menu.entryconfigure(
                index,
                selectcolor="grey5",
            )
        with contextlib.suppress(tk.TclError):
            menu.entryconfigure(
                index,
                activebackground="grey42",
            )

    def is_left_double_click(self, mouse_args: mpl_backend_bases.MouseEvent) -> bool:
        """Return True when the mouse_args represent a double-left-click."""
        if mouse_args.button != mpl_backend_bases.MouseButton.LEFT:
            return False
        return mouse_args.dblclick

    def finalize_tool_window(self, task: asyncio.Task) -> None:
        """Finalize the ToolWindow after the user closes it."""
        self.tool_window = None

    def on_graph_mouse_down(self, event_args: mpl_backend_bases.Event) -> None:
        """Handle mouse-down events from the graph."""
        if type(event_args) is not mpl_backend_bases.MouseEvent:
            return
        if not self.is_left_double_click(event_args):
            return

        clicked = event_args.inaxes
        if clicked is self.position_axes:
            axes = self.position_axes
            axis = "yaxis"
            limits = self.position_axis_limits
        elif clicked is self.displacement_axes:
            axes = self.displacement_axes
            axis = "yaxis"
            limits = self.displacement_axis_limits
        elif clicked is self.g_level_axes:
            axes = self.g_level_axes
            axis = "yaxis"
            limits = self.g_level_axis_limits
        else:
            return

        if not self.tool_window:
            self.tool_window = ToolWindow(self.root_window)
            open_tool_window_task = asyncio.create_task(self.tool_window.show(guikit.DialogBehavior.Modeless))
            self.background_tasks.add(open_tool_window_task)
            open_tool_window_task.add_done_callback(self.finalize_tool_window)
        self.tool_window.attach_to_axis(event_args.canvas.draw_idle, axes, axis, limits)

    def on_graph_pick(self, event_args: mpl_backend_bases.Event) -> None:
        """Handle pick events from the graph."""
        if type(event_args) is not mpl_backend_bases.PickEvent:
            return
        if not self.is_left_double_click(event_args.mouseevent):
            return
        if event_args.artist is self.position_label:
            axes = self.position_axes
            axis = "yaxis"
            limits =self.position_axis_limits
        elif event_args.artist is self.displacement_label:
            axes = self.displacement_axes
            axis = "yaxis"
            limits = self.displacement_axis_limits
        elif event_args.artist is self.g_level_label:
            axes = self.g_level_axes
            axis = "yaxis"
            limits = self.g_level_axis_limits
        elif event_args.artist is self.time_label:
            axes = self.g_level_axes
            axis = "xaxis"
            limits = self.time_axis_limits
        else:
            return
        if not self.tool_window:
            self.tool_window = ToolWindow(self.root_window)
            open_tool_window_task = asyncio.create_task(self.tool_window.show(guikit.DialogBehavior.Modeless))
            self.background_tasks.add(open_tool_window_task)
            open_tool_window_task.add_done_callback(self.finalize_tool_window)
        self.tool_window.attach_to_axis(event_args.canvas.draw_idle, axes, axis, limits)

    def handle_change_sensor_group(self, sender: str, empty: str, operation: str) -> None:
        """Handle the text change event for the sensor_group Entry."""
        self.state.sensor_group = self.sensor_node_group_variable.get()

    def on_can_set_sensor_group_changed(self, event_args: tk.Event) -> None:
        """Handle the CanSetSensorGroupChanged event."""
        new_state = tk.NORMAL if self.state.can_change_group else tk.DISABLED
        self.sensor_node_group.configure(state=new_state)

    def on_sensor_group_changed(self, event_args: tk.Event) -> None:
        """Handle the SensorGroupChanged event."""
        new_group = self.state.sensor_group
        self.sensor_node_group_variable.set(new_group)

    def handle_launch_scanner(self) -> None:
        """Handle the launch scanner command."""
        if self.scanner_process and self.scanner_process.is_alive():
            return
        self.scanner_process = multiprocessing.Process(target=qtpy_datalogger.apps.scanner.main, name="QT Py Scanner")
        self.scanner_process.start()

    def handle_change_sample_rate(self) -> None:
        """Handle the selection event for the sample rate Radiobuttons."""
        new_rate = self.sample_rate_variable.get()
        self.state.sample_rate = SampleRate(new_rate)

    def on_sample_rate_changed(self, event_args: tk.Event) -> None:
        """Handle the SampleRateChanged event."""
        new_rate = self.state.sample_rate
        self.sample_rate_variable.set(new_rate)

    def handle_acquire(self, sender: tk.Widget) -> None:
        """Handle the Acquire command."""
        current_acquire = self.state.acquire_active

        match current_acquire:
            case Tristate.BoolUnset:
                # Still attempting to connect, take no action on mouse button click
                return
            case Tristate.BoolFalse:
                new_acquire = Tristate.BoolUnset  # We'll learn more if we connect and find nodes
            case Tristate.BoolTrue:
                new_acquire = Tristate.BoolFalse
        self.state.acquire_active = new_acquire

    def on_can_acquire_changed(self, event_args: tk.Event) -> None:
        """Handle the CanAcquireDataChanged event."""
        new_state = tk.NORMAL if self.state.can_acquire else tk.DISABLED
        self.acquire_button.configure(state=new_state)

    def on_acquire_changed(self, event_args: tk.Event) -> None:
        """Handle the AcquireDataChanged event."""
        match self.state.acquire_active:

            case Tristate.BoolUnset:
                new_style = bootstyle.SECONDARY

                async def try_start_acquire() -> None:
                    """Try to connect to the sensor group."""
                    self.qtpy_controller = network.QTPyController.for_localhost_server(self.state.sensor_group)
                    try:
                        await self.qtpy_controller.connect_and_subscribe()
                    except ConnectionRefusedError:
                        await self.on_server_offline()
                        return
                    nodes_in_group = await self.qtpy_controller.scan_for_nodes()
                    if not nodes_in_group:
                        await self.on_no_nodes_in_group()
                        return
                    self.nodes_in_group.clear()
                    self.nodes_in_group = [
                        discovery.QTPyDevice(
                            com_id="",
                            com_port="",
                            device_description=sensor_node[datatypes.DetailKey.device_description],
                            drive_label="",
                            drive_root="",
                            ip_address=sensor_node[datatypes.DetailKey.ip_address],
                            mqtt_group_id=sensor_node[datatypes.DetailKey.mqtt_group_id],
                            node_id=sensor_node[datatypes.DetailKey.node_id],
                            python_implementation=sensor_node[datatypes.DetailKey.python_implementation],
                            serial_number=sensor_node[datatypes.DetailKey.serial_number],
                            snsr_version=sensor_node[datatypes.DetailKey.snsr_version],
                        )
                        for sensor_node in nodes_in_group.values()
                    ]
                    nodes_support_app = await self.confirm_app_support()
                    if not nodes_support_app:
                        await self.on_app_unsupported()
                        return
                    self.state.acquire_active = Tristate.BoolTrue

                try_start_task = asyncio.create_task(try_start_acquire(), name="try start new acquisition")
                self.background_tasks.add(try_start_task)
                try_start_task.add_done_callback(self.background_tasks.discard)

            case Tristate.BoolFalse:
                new_style = bootstyle.DEFAULT
                self.no_nodes_tooltip.leave()
                self.no_nodes_tooltip = ttk_tooltip.ToolTip(
                    self.acquire_button,
                    text="Connect to the sensor group and start taking measurements.",
                    bootstyle=bootstyle.DEFAULT
                )
                if self.qtpy_controller:
                    async def disconnect_mqtt() -> None:
                        """Disconnect from the MQTT server."""
                        if not self.qtpy_controller:
                            raise RuntimeError()
                        await self.qtpy_controller.disconnect()
                        self.qtpy_controller = None
                        self.nodes_in_group.clear()

                    disconnect_task = asyncio.create_task(disconnect_mqtt(), name="disconnect MQTT")
                    self.background_tasks.add(disconnect_task)
                    disconnect_task.add_done_callback(self.background_tasks.discard)

            case Tristate.BoolTrue:
                new_style = bootstyle.SUCCESS
                self.no_nodes_tooltip.leave()
                self.no_nodes_tooltip = ttk_tooltip.ToolTip(
                    self.acquire_button,
                    text="Disconnect from the sensor group and stop taking measurements.",
                    bootstyle=bootstyle.DEFAULT
                )
        self.acquire_button.configure(bootstyle=new_style)  # pyright: ignore reportArgumentType -- the type hint for library uses strings

    def on_can_log_data_changed(self, event_args: tk.Event) -> None:
        """Handle the CanLogDataChanged event."""
        new_state = tk.NORMAL if self.state.can_log_data else tk.DISABLED
        self.log_data_button.configure(state=new_state)

    def handle_log_data(self, sender: tk.Widget) -> None:
        """Handle the Acquire command."""
        current_log_data = self.state.log_data_active
        new_log_data = not current_log_data
        self.state.log_data_active = new_log_data

    def on_log_data_changed(self, event_args: tk.Event) -> None:
        """Handle the LogDataChanged event."""
        log_data_active = self.state.log_data_active
        if log_data_active:
            new_style = bootstyle.SUCCESS
            new_log_file_timestamp = self.state.most_recent_timestamp.astimezone().strftime("%Y.%m.%d_%H.%M.%S")
            new_log_file_name = f"Centrifuge test_{new_log_file_timestamp}"
            home_path = pathlib.Path.home()
            new_log_file_path = home_path.joinpath(f"Documents\\qtpy-datalogger\\{new_log_file_name}.csv")
            new_log_file_path.parent.mkdir(parents=True, exist_ok=True)
            new_log_file_path.touch()
            self.state.log_file_path = new_log_file_path
            self.append_row_to_log(self.data_processor.logged_columns)
        else:
            new_style = bootstyle.DEFAULT
            self.state.log_file_path = AppState.canceled_file

        self.log_data_button.configure(bootstyle=new_style)  # pyright: ignore reportArgumentType -- the type hint for library uses strings
        self.log_data_variable.set(log_data_active)

    def on_battery_level_changed(self, event_args: tk.Event) -> None:
        """Handle the BatteryLevelChanged event."""
        battery_level = self.state.battery_level
        battery_image = self.svg_images[self.icon_name_for_battery_level[battery_level]]
        if battery_level == BatteryLevel.Unknown:
            args = {
                "image": battery_image,
                "text": "?",
            }
        else:
            args = {
                "image": battery_image,
                "text": "",
            }
        self.battery_level_indicator.configure(args)
        if self.battery_level_tooltip:
            self.battery_level_tooltip.leave()
        self.battery_level_tooltip = ttk_tooltip.ToolTip(self.battery_level_indicator, text=self.tooltip_message_for_battery_level[battery_level], bootstyle=bootstyle.DEFAULT)

    def on_battery_voltage_changed(self, event_args: tk.Event) -> None:
        """Handle the BatteryVoltageChanged event."""
        new_voltage = f"{self.state.battery_voltage:.3f}" if self.state.battery_voltage > 0 else "-.---"
        self.battery_voltage_indicator.configure(text=f"{new_voltage} V")

    def on_mouse_enter(self, event_args: tk.Event) -> None:
        """Handle the mouse Enter event."""
        self.reset_button.configure(image=self.svg_images["hover-rotate-left"])

    def on_mouse_leave(self, event_args: tk.Event) -> None:
        """Handle the mouse Leave event."""
        self.reset_button.configure(image=self.svg_images["rotate-left"])

    def handle_reset(self, sender: tk.Widget) -> None:
        """Handle the Acquire command."""
        self.state.reset()

    def update_window_title(self, new_title: str) -> None:
        """Update the application's window title."""
        self.root_window.title(new_title)

    async def confirm_app_support(self) -> bool:
        """Select the soil swell app as the node's active app and return True. Return False when the node does not support the app."""
        if not self.qtpy_controller:
            raise RuntimeError()
        node = self.nodes_in_group[0]
        node_id = node.node_id
        get_apps_command = await self.qtpy_controller.send_action(
            node_id=node_id,
            command_name="custom",
            parameters={
                "input": "qtpycmd get_apps",
            },
        )
        get_apps_result, _ = await self.qtpy_controller.get_matching_result(
            node_id=node_id,
            action=get_apps_command,
        )
        supported_apps = get_apps_result["output"]
        return self.snsr_app_name in supported_apps

    async def on_server_offline(self) -> None:
        """Handle the outcome when the MQTT server is offline."""
        if not self.qtpy_controller:
            raise RuntimeError()
        self.qtpy_controller = None
        self.nodes_in_group.clear()
        self.state.acquire_active = Tristate.BoolFalse
        self.acquire_button.configure(bootstyle=bootstyle.DANGER)  # pyright: ignore reportArgumentType -- the type hint for library is incorrect
        self.no_nodes_tooltip.leave()
        self.no_nodes_tooltip = ttk_tooltip.ToolTip(
            self.acquire_button,
            text="MQTT server did not respond. Check if it's running with 'qtpy-datalogger server'",
            bootstyle=bootstyle.DANGER,
        )

    async def on_no_nodes_in_group(self) -> None:
        """Handle the outcome when no nodes are connected to the sensor group."""
        if not self.qtpy_controller:
            raise RuntimeError()
        await self.qtpy_controller.disconnect()
        self.qtpy_controller = None
        self.nodes_in_group.clear()
        self.state.acquire_active = Tristate.BoolFalse
        self.acquire_button.configure(bootstyle=bootstyle.DANGER)  # pyright: ignore reportArgumentType -- the type hint for library uses strings
        self.no_nodes_tooltip.leave()
        self.no_nodes_tooltip = ttk_tooltip.ToolTip(
            self.acquire_button,
            text="No nodes in group. Check group name and node configuration.",
            bootstyle=bootstyle.DANGER,
        )

    async def on_app_unsupported(self) -> None:
        """Handle the outcome when no nodes support this app."""
        if not self.qtpy_controller:
            raise RuntimeError()
        await self.qtpy_controller.disconnect()
        self.qtpy_controller = None
        self.nodes_in_group.clear()
        self.state.acquire_active = Tristate.BoolFalse
        self.acquire_button.configure(bootstyle=bootstyle.DANGER)  # pyright: ignore reportArgumentType -- the type hint for library uses strings
        self.no_nodes_tooltip.leave()
        self.no_nodes_tooltip = ttk_tooltip.ToolTip(
            self.acquire_button,
            text="No nodes in the the group support this app. Update them with 'qtpy-datalogger equip'",
            bootstyle=bootstyle.DANGER,
        )

    def poll_acquire(self) -> None:
        """Check conditions for acquisition and take a new scan accordingly."""
        if self.state.acquire_active != Tristate.BoolTrue:
            return
        now = datetime.datetime.now(tz=datetime.UTC)
        sample_intervals = {
            SampleRate.Live: datetime.timedelta(seconds=0.1),
            SampleRate.Fast: datetime.timedelta(seconds=15),
            SampleRate.Normal: datetime.timedelta(seconds=60),
            SampleRate.Slow: datetime.timedelta(minutes=3),
        }
        sample_interval_elapsed = self.state.most_recent_timestamp + sample_intervals[self.state.sample_rate] < now
        do_acquire_task_name = "do acquire"
        node_handling_command = do_acquire_task_name in [task.get_name() for task in self.background_tasks]
        if sample_interval_elapsed and not node_handling_command:
            do_acquire_task = asyncio.create_task(self.do_acquire(), name=do_acquire_task_name)
            self.background_tasks.add(do_acquire_task)
            do_acquire_task.add_done_callback(self.background_tasks.discard)

    async def do_acquire(self) -> None:
        """Acquire data from the nodes in the group and return it."""
        if self.state.demo_active:
            node_id = "node-77aa77aa77aa-0"
            relative_demo_time_series = self.state._demo_data["minutes"]
            time_zero = self.state.most_recent_timestamp
            if len(self.state.data) > 0:
                time_zero = self.state.data["timestamp"][0]
            now = self.state.most_recent_timestamp
            relative_time = (now - time_zero) / datetime.timedelta(minutes=1)
            acquired_time = relative_demo_time_series < relative_time
            acquired_demo_data = self.state._demo_data[acquired_time]
            if len(acquired_demo_data) > 0:
                new_data = acquired_demo_data[-1:].to_numpy()[0].tolist()[1:]  # Get last row, dropping first column
            else:
                new_data = [0.0 for x in range(len(self.data_processor.lvdt_position_columns) + 3)]
        else:
            if not self.qtpy_controller:
                raise RuntimeError()
            # 0 g output for XOUT, YOUT, ZOUT: ±400 mg
            # X/Y/Z sensitivity: 18.4..22.6 (20.5 LSB/g typ)
            # Scale factor: 0.044..0.054 g/LSB (49 mg/LSB typ)
            # XL3D_SCALE_G_PER_LSB = 49e-3  # 44e-3 # 49e-3 # 54e-3  # How to measure?
            # XL3D_OFFSET_G_PER_LSB = 196e-3  # From spec
            # XL3D_Z_SENSITIVITY_LSB_PER_G = 1 / XL3D_SCALE_G_PER_LSB
            # XL3D_LSB_PER_OFFSET_REGISTER_LSB = XL3D_OFFSET_G_PER_LSB / XL3D_SCALE_G_PER_LSB
            # XL3D_SOFTWARE_TRIM_OFFSET = (0, 0, 0)
            XL3D_HARDWARE_OFFSET = (-3, 0, 1)

            node = self.nodes_in_group[0]
            node_id = node.node_id
            do_read_input = await self.qtpy_controller.send_action(
                node_id=node_id,
                command_name=f"{self.snsr_app_name} scan",
                parameters={
                    "channels": ["A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7"],
                    "samples_to_average": 50,
                    "xl3d_offset": XL3D_HARDWARE_OFFSET,
                },
            )
            read_input_result, _ = await self.qtpy_controller.get_matching_result(
                node_id=node_id,
                action=do_read_input,
            )

            sensor_codes = read_input_result["output"]
            new_data = sensor_codes
        self.state.process_new_data(node_id, new_data)

    def on_new_data_processed(self, event_args: tk.Event) -> None:
        """Handle new processed data."""
        all_data = self.state.data
        if len(all_data) == 0:
            self.position_axes.clear()
            self.displacement_axes.clear()
            self.g_level_axes.clear()
            self.configure_all_axes()
            requested_theme = ttk_themes.STANDARD_THEMES[self.state.active_theme]
            ttkbootstrap_matplotlib.apply_figure_style(self.canvas_figure.get_tk_widget(), requested_theme)
            self.canvas_figure.draw_idle()
            return

        def update_axes_plots(time_coordinates: pd.Series, data_series: pd.DataFrame, axes: mpl_axes.Axes) -> None:
            plot_has_lines = len(axes.lines) > 0
            for index, (name, series) in enumerate(data_series.items()):
                times = time_coordinates.to_list()
                measurements = series.to_list()
                if plot_has_lines:
                    plot = axes.lines[index]
                    plot.set_xdata(times)
                    plot.set_ydata(measurements)
                else:
                    axes.plot(
                        times,
                        measurements,
                        label=name,
                    )

        time_coordinates = all_data[self.data_processor.relative_time_column]

        position_frame = all_data[self.data_processor.lvdt_position_columns]
        displacement_frame = all_data[self.data_processor.lvdt_displacement_columns]
        temperature_frame = all_data[[self.data_processor.temperature_column]]
        battery_frame = all_data[[self.data_processor.battery_column]]
        g_level_frame = all_data[[self.data_processor.g_level_column]]

        # Consider using a running average of N samples to mimic hysteresis
        battery_voltage = battery_frame.to_numpy()[-1][0]
        new_battery_level = get_first_in_range(battery_voltage, self.battery_level_for_voltage)
        self.state.battery_voltage = battery_voltage
        self.state.battery_level = new_battery_level

        for (data_frame, axes) in [(position_frame, self.position_axes), (displacement_frame, self.displacement_axes), (g_level_frame, self.g_level_axes)]:
            update_axes_plots(time_coordinates, data_frame, axes)
        self.canvas_figure.draw_idle()

        if self.state.log_data_active:
            new_row = all_data.loc[all_data.index[-1], self.data_processor.logged_columns].to_list()  # pyright: ignore callIssue -- Series[Unknown] confuses the analyzer
            first_log_sample_timestamp = all_data.loc[all_data.index[self.state.index_when_log_enabled], self.data_processor.relative_time_column]
            adjusted_relative_timestamp = new_row[0] - first_log_sample_timestamp
            new_row[0] = adjusted_relative_timestamp
            formatted_row = [f"{entry:.3f}" for entry in new_row]
            self.append_row_to_log(formatted_row)

    def append_row_to_log(self, row: list[str]) -> None:
        """Add the row to the end of log file."""
        csv_row = ",".join(row)
        with self.state.log_file_path.open("a") as log_file:
            log_file.write(f"{csv_row}\n")

def get_first_in_range(upper_bound: float, selection: dict) -> Any:
    """Get the first value in the selection that is lower than the upper_bound."""
    descending = sorted(selection.keys(), reverse=True)
    first_in_range_index = [upper_bound > entry for entry in descending].index(True)
    first_value_in_range = selection[descending[first_in_range_index]]
    return first_value_in_range


if __name__ == "__main__":
    logger.debug(f"Launching {__package__}")
    asyncio.run(guikit.AsyncApp.create_and_run(SoilSwell))
