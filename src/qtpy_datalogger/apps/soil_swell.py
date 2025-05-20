"""An app that collects data from a soil swell test."""

import asyncio
import atexit
import contextlib
import functools
import importlib.resources
import logging
import multiprocessing
import pathlib
import shutil
import tempfile
import tkinter as tk
import webbrowser
from enum import StrEnum
from tkinter import font

import matplotlib.axes as mpl_axes
import matplotlib.backend_bases as mpl_backend_bases
import matplotlib.figure as mpl_figure
import matplotlib.ticker as mpl_ticker
import pandas as pd
import ttkbootstrap as ttk
import ttkbootstrap.themes.standard as ttk_themes
import ttkbootstrap.tooltip as ttk_tooltip
from tkfontawesome import icon_to_image, svg_to_image
from ttkbootstrap import constants as bootstyle

import qtpy_datalogger.apps.scanner
from qtpy_datalogger import datatypes, guikit, ttkbootstrap_matplotlib

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
    Fast = "Fast"
    Normal = "Normal"
    Slow = "Slow"


class ToolWindow(guikit.AsyncDialog):
    """A class that shows a window with tools that apply to its origin."""

    def __init__(self, parent: ttk.Toplevel | ttk.Window, title: str, origin: object) -> None:
        """Initialize a new ToolWindow."""
        self.origin = origin
        super().__init__(parent=parent, title=title)

    def create_user_interface(self) -> None:
        """Create the layout and widget event handlers."""
        main_frame = ttk.Frame(self.root_window, style=bootstyle.INFO)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=1)
        main_frame.grid(column=0, row=0, sticky=tk.NSEW)

        self.origin_label = ttk.Label(main_frame, text=f"clicked by {self.origin}")
        self.origin_label.grid(column=0, row=0, sticky=tk.NSEW)

    async def on_loop(self) -> None:
        """Update UI elements."""
        await asyncio.sleep(20e-3)

    def update_message(self, message: str) -> None:
        """Update the message string."""
        self.origin_label.configure(text=message)


class AppState:
    """A class that models and controls the app's settings and runtime state."""

    class Tristate(StrEnum):
        """An enumeration that models a tristate boolean."""

        BoolUnset = "Unset"
        BoolTrue = "True"
        BoolFalse = "False"

    class Event(StrEnum):
        """Events emitted when properties change."""

        AcquireDataChanged = "<<AcquireDataChanged>>"
        BatteryLevelChanged = "<<BatteryLevelChanged>>"
        CanAcquireDataChanged = "<<CanAcquireDataChanged>>"
        CanLogDataChanged = "<<CanLogDataChanged>>"
        CanSetSensorGroupChanged = "<<CanSetSensorGroupChanged>>"
        LogDataChanged = "<<LogDataChanged>>"
        SampleRateChanged = "<<SampleRateChanged>>"
        SensorGroupChanged = "<<SensorGroupChanged>>"

    def __init__(self, tk_root: tk.Tk) -> None:
        """Initialize a new AppState instance."""
        self._tk_notifier = tk_root
        self._theme_name = ""
        self._sensor_group = ""
        self._sample_rate = SampleRate.Unset
        self._acquire_active = AppState.Tristate.BoolUnset
        self._log_data_active = AppState.Tristate.BoolUnset
        self._battery_level = BatteryLevel.Unset

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
        if not self.can_acquire:
            self.acquire_active = False

    @property
    def can_change_group(self) -> bool:
        """Return True when the app can change the sensor group name."""
        return self._acquire_active != AppState.Tristate.BoolTrue

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
    def acquire_active(self) -> bool:
        """Return True when the app is acquiring data."""
        return self._acquire_active == AppState.Tristate.BoolTrue

    @acquire_active.setter
    def acquire_active(self, new_value: bool) -> None:
        """Set a new value for acquire_active and notify AcquireDataChanged event subscribers."""
        as_tristate = AppState.Tristate.BoolTrue if new_value else AppState.Tristate.BoolFalse
        if as_tristate == self.acquire_active:
            return
        self._acquire_active = as_tristate
        self._tk_notifier.event_generate(AppState.Event.AcquireDataChanged)
        if self.log_data_active:
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
        return self._log_data_active == AppState.Tristate.BoolTrue

    @log_data_active.setter
    def log_data_active(self, new_value: bool) -> None:
        """Set a new value for log_data_active and notify LogDataChanged event subscribers."""
        as_tristate = AppState.Tristate.BoolTrue if new_value else AppState.Tristate.BoolFalse
        if as_tristate == self._log_data_active:
            return
        self._log_data_active = as_tristate
        self._tk_notifier.event_generate(AppState.Event.LogDataChanged)

    @property
    def can_log_data(self) -> bool:
        """Return True when the app can log data."""
        acquire_is_active = self.acquire_active
        return acquire_is_active

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


class SoilSwell(guikit.AsyncWindow):
    """A GUI that acquires, plots, and logs data from a soil swell test."""

    app_name = "Soil Swell Test"

    class CommandName(StrEnum):
        """Names used for menus and commands in the app."""

        File = "File"
        Exit = "Exit"
        View = "View"
        Theme = "Theme"
        Help = "Help"
        About = "About"
        Acquire = "Acquire"
        LogData = "Log Data"
        Reset = "Reset"

    def create_user_interface(self) -> None:  # noqa: PLR0915 -- allow long function to create the UI
        """Create the main window and connect event handlers."""
        # Supports UI widget state
        self.theme_variable = tk.StringVar()
        self.sensor_node_group_variable = tk.StringVar()
        self.sample_rate_variable = tk.StringVar()
        self.acquire_variable = tk.BooleanVar()
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
        self.scanner_process = None

        # Supports app state
        self.state = AppState(self.root_window)
        self.background_tasks: set[asyncio.Task] = set()

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
            left=0.10,
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
        self.position_label = self.position_axes.set_ylabel("LVDT position (cm)", picker=True)
        self.position_axes.set_ylim(ymin=-0.1, ymax=2.6)
        self.position_axes.yaxis.set_major_locator(mpl_ticker.MultipleLocator(0.5))
        self.position_axes.yaxis.set_major_formatter("{x:0.2f}")
        self.displacement_label = self.displacement_axes.set_ylabel("Displacement (cm)", picker=True)
        self.displacement_axes.set_ylim(ymin=-2.6, ymax=2.6)
        self.displacement_axes.yaxis.set_major_locator(mpl_ticker.MultipleLocator(1.0))
        self.displacement_axes.yaxis.set_major_formatter("{x:0.2f}")
        self.g_level_label = self.g_level_axes.set_ylabel("Acceleration (g)", picker=True)
        self.g_level_axes.set_ylim(ymin=-1, ymax=255)
        self.g_level_axes.set_xlim(xmin=-1, xmax=200)
        self.g_level_axes.yaxis.set_major_locator(mpl_ticker.MultipleLocator(50.0))
        self.time_label = self.g_level_axes.set_xlabel("Time (minutes)", picker=True)

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
        self.root_window.bind(AppState.Event.SampleRateChanged, self.on_sample_rate_changed)
        self.root_window.bind(AppState.Event.SensorGroupChanged, self.on_sensor_group_changed)
        self.root_window.bind(AppState.Event.CanSetSensorGroupChanged, self.on_can_set_sensor_group_changed)

        self.update_window_title("Centrifuge Test")
        self.state.active_theme = "cosmo"

        self.root_window.update_idletasks()
        self.handle_reset(sender=self.reset_button)

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
            command=functools.partial(self.safe_exit, tk.Event()),
            label=SoilSwell.CommandName.Exit,
            accelerator="Alt-F4",
        )
        self.root_window.bind("<Alt-F4>", self.safe_exit)

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
        self.battery_voltage_indicator = ttk.Label(panel, font=the_font, text="3.742")
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

    def cycle_battery_icon(self) -> None:
        """Rotate through the battery icons."""
        battery_levels = list(reversed(BatteryLevel))
        next_index = (self.icon_index + 1) % len(battery_levels)
        self.icon_index = next_index
        self.state.battery_level = battery_levels[next_index]
        self.battery_level_indicator.after(1500, self.cycle_battery_icon)

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
        fast_option.grid(column=0, row=5, padx=(16, 8), pady=(4, 12), sticky=tk.NSEW)

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

    async def on_loop(self) -> None:
        """Update the UI with new information."""
        await asyncio.sleep(1e-6)
        done_tasks = [task for task in self.background_tasks if task.done()]
        for done_task in done_tasks:
            did_error = done_task.exception()
            if did_error:
                print(did_error)
            had_result = done_task.result()
            if had_result:
                print(had_result)

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

    def show_about(self) -> None:
        """Handle the Help::About menu command."""

    def change_theme(self, theme_name:str) -> None:
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
            raise ValueError()
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
        message = "graph area"
        if clicked is self.position_axes:
            message = "position area"
        elif clicked is self.displacement_axes:
            message = "displacement area"
        elif clicked is self.g_level_axes:
            message = "g level area"
        if event_args.inaxes:
            if not self.tool_window:
                self.tool_window = ToolWindow(parent=self.root_window, title="in work tool window", origin=message)
                open_tool_window_task = asyncio.create_task(self.tool_window.show(guikit.DialogBehavior.Modeless))
                self.background_tasks.add(open_tool_window_task)
                open_tool_window_task.add_done_callback(self.finalize_tool_window)
            self.tool_window.update_message(message)

    def on_graph_pick(self, event_args: mpl_backend_bases.Event) -> None:
        """Handle pick events from the graph."""
        if type(event_args) is not mpl_backend_bases.PickEvent:
            return
        if not self.is_left_double_click(event_args.mouseevent):
            return
        x = event_args
        message = "pick area"
        if x.artist is self.position_label:
            message = "position label"
        elif x.artist is self.displacement_label:
            message = "displacement label"
        elif x.artist is self.g_level_label:
            message = "g level label"
        elif x.artist is self.time_label:
            message = "time label"
        if not self.tool_window:
            self.tool_window = ToolWindow(parent=self.root_window, title="in work tool window", origin=message)
            open_tool_window_task = asyncio.create_task(self.tool_window.show(guikit.DialogBehavior.Modeless))
            self.background_tasks.add(open_tool_window_task)
            open_tool_window_task.add_done_callback(self.finalize_tool_window)
        self.tool_window.update_message(message)

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
        new_acquire = not current_acquire
        self.state.acquire_active = new_acquire

    def on_can_acquire_changed(self, event_args: tk.Event) -> None:
        """Handle the CanAcquireDataChanged event."""
        new_state = tk.NORMAL if self.state.can_acquire else tk.DISABLED
        self.acquire_button.configure(state=new_state)

    def on_acquire_changed(self, event_args: tk.Event) -> None:
        """Handle the AcquireDataChanged event."""
        acquire_active = self.state.acquire_active
        new_style = bootstyle.SUCCESS if acquire_active else bootstyle.DEFAULT
        self.acquire_button.configure(bootstyle=new_style)  # pyright: ignore reportArgumentType -- the type hint for library uses strings
        self.acquire_variable.set(acquire_active)

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
        new_style = bootstyle.SUCCESS if log_data_active else bootstyle.DEFAULT
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

    def on_mouse_enter(self, event_args: tk.Event) -> None:
        """Handle the mouse Enter event."""
        self.reset_button.configure(image=self.svg_images["hover-rotate-left"])

    def on_mouse_leave(self, event_args: tk.Event) -> None:
        """Handle the mouse Leave event."""
        self.reset_button.configure(image=self.svg_images["rotate-left"])

    def handle_reset(self, sender: tk.Widget) -> None:
        """Handle the Acquire command."""
        self.state.battery_level = BatteryLevel.Unknown
        self.state.sensor_group = datatypes.Default.MqttGroup
        self.state.sample_rate = SampleRate.Fast
        self.state.acquire_active = False
        self.state.log_data_active = False

    def update_window_title(self, new_title: str) -> None:
        """Update the application's window title."""
        self.root_window.title(new_title)


if __name__ == "__main__":
    logger.debug(f"Launching {__package__}")
    asyncio.run(guikit.AsyncApp.create_and_run(SoilSwell))
