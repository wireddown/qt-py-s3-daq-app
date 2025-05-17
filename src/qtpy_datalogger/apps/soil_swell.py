"""An app that collects data from a soil swell test."""

import asyncio
import atexit
import contextlib
import functools
import json
import logging
import pathlib
import shutil
import tempfile
import tkinter as tk
import webbrowser
from enum import StrEnum
from tkinter import font

import matplotlib.axes as mpl_axes
import matplotlib.figure as mpl_figure
import pandas as pd
import ttkbootstrap as ttk
import ttkbootstrap.themes.standard as ttk_themes
from tkfontawesome import icon_to_image
from ttkbootstrap import constants as bootstyle

from qtpy_datalogger import datatypes, guikit, ttkbootstrap_matplotlib

logger = logging.getLogger(pathlib.Path(__file__).stem)

app_icon_color = "#07a000"


class StyleKey(StrEnum):
    """A class that extends the palette names of ttkbootstrap styles."""

    Fg = "fg"
    SelectFg = "selectfg"


class BatteryLevel(StrEnum):
    """An ordered enumeration that represents the sensor node's battery level."""

    Unknown = "Unknown"
    Low = "Low"
    Half = "Half"
    High = "High"
    Full = "Full"


class AppState:
    """A class that models and controls the app's settings and runtime state."""

    class Event(StrEnum):
        """Events emitted when properties change."""

        AcquireDataChanged = "<<AcquireDataChanged>>"
        BatteryLevelChanged = "<<BatteryLevelChanged>>"
        LogDataChanged = "<<LogDataChanged>>"
        SampleRateChanged = "<<SampleRateChanged>>"
        SensorGroupChanged = "<<SensorGroupChanged>>"

    def __init__(self, tk_root: tk.Tk) -> None:
        """Initialize a new AppState instance."""
        self._tk_notifier = tk_root
        self._theme_name = ""
        self._acquire_active = False
        self._log_data_active = False
        self._battery_level = BatteryLevel.Unknown

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
    def acquire_active(self) -> bool:
        """Return True when the app is acquiring data."""
        return self._acquire_active

    @acquire_active.setter
    def acquire_active(self, new_value: bool) -> None:
        """Set a new value for acquire_active and notify AcquireDataChanged event subscribers."""
        if new_value == self._acquire_active:
            return
        self._acquire_active = new_value
        self._tk_notifier.event_generate(AppState.Event.AcquireDataChanged)

    @property
    def log_data_active(self) -> bool:
        """Return True when the app is logging data."""
        return self._log_data_active

    @log_data_active.setter
    def log_data_active(self, new_value: bool) -> None:
        """Set a new value for log_data_active and notify LogDataChanged event subscribers."""
        if new_value == self._log_data_active:
            return
        self._log_data_active = new_value
        self._tk_notifier.event_generate(AppState.Event.LogDataChanged)


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
        Fast = "Fast"
        Normal = "Normal"
        Slow = "Slow"
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

        # Supports app state
        self.state = AppState(self.root_window)
        self.menu_text_for_theme = {
            "cosmo": "  Cosmo",
            "flatly": "  Flatly",
            "cyborg": "   Cyborg",
            "darkly": "   Darkly",
            "vapor": "  Debug",
        }
        self.menu_text_for_theme["vapor"] = "  Debug"

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
        self.position_axes.set_ylabel("LVDT position (cm)")
        self.displacement_axes.set_ylabel("Displacement (cm)")
        self.g_level_axes.set_ylabel("Acceleration (g)")
        self.g_level_axes.set_xlabel("Time (minutes)")

        tool_frame = ttk.Frame(main, name="tool_panel", style=bootstyle.LIGHT)
        tool_frame.grid(column=1, row=0, sticky=tk.NSEW)
        tool_frame.columnconfigure(0, weight=1)
        tool_frame.rowconfigure(0, weight=0, minsize=36)  # Filler
        tool_frame.rowconfigure(1, weight=0)  # Status
        tool_frame.rowconfigure(2, weight=0, minsize=24)  # Filler
        tool_frame.rowconfigure(3, weight=0)  # Settings
        tool_frame.rowconfigure(4, weight=0, minsize=24)  # Filler
        tool_frame.rowconfigure(5, weight=0)  # Action

        status_panel = ttk.Frame(tool_frame, name="status_panel", style=bootstyle.INFO)
        status_panel.columnconfigure(0, weight=1)
        status_panel.rowconfigure(0, weight=1)
        status_panel.grid(column=0, row=1, sticky=tk.NSEW, padx=(26, 24))
        status_contents = self.create_status_panel()
        status_contents.grid(in_=status_panel, column=0, row=0, padx=8, pady=8, sticky=tk.NSEW)

        settings_panel = ttk.Frame(tool_frame, name="settings_panel", style=bootstyle.WARNING)
        settings_panel.columnconfigure(0, weight=1)
        settings_panel.rowconfigure(0, weight=1)
        settings_contents = self.create_settings_panel()
        settings_contents.grid(in_=settings_panel, column=0, row=0, padx=2, pady=2, sticky=tk.NSEW)
        settings_panel.grid(column=0, row=3, sticky=tk.NSEW, padx=(26, 24))

        action_panel = ttk.Frame(tool_frame, name="action_panel", style=bootstyle.DANGER)
        action_panel.columnconfigure(0, weight=1)
        action_panel.rowconfigure(0, weight=1)
        action_panel.grid(column=0, row=5, sticky=tk.NSEW, padx=(26, 24))
        action_contents = self.create_action_panel()
        action_contents.grid(in_=action_panel, column=0, row=0, padx=2, pady=2, sticky=tk.NSEW)

        self.root_window.bind("<<ThemeChanged>>", self.on_theme_changed)
        self.root_window.bind(
            AppState.Event.AcquireDataChanged,
            self.on_acquire_changed,
        )
        self.root_window.bind(
            AppState.Event.LogDataChanged,
            self.on_log_data_changed,
        )

        self.update_window_title("Centrifuge Test")
        self.state.active_theme = "vapor"


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
            command=self.exit,
            label=SoilSwell.CommandName.Exit,
            accelerator="Alt-F4",
        )
        self.root_window.bind("<Alt-F4>", lambda e: self.exit())

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
        panel.rowconfigure(0, weight=1)

        self.refresh_battery_icons()
        self.battery_level_indicator = ttk.Label(panel, image=self.svg_images["battery-full"], font=font.Font(weight=font.BOLD), compound=tk.CENTER)
        self.battery_level_indicator.grid(column=0, row=0)
        return panel

    def refresh_battery_icons(self) -> None:
        """Create the icon images for the battery level indicator."""
        full_battery_icon = icon_to_image("battery-full", fill=guikit.hex_string_for_style(bootstyle.SUCCESS), scale_to_height=24)
        self.svg_images["battery-full"] = full_battery_icon

        high_battery_icon = icon_to_image("battery-three-quarters", fill=guikit.hex_string_for_style(bootstyle.SUCCESS), scale_to_height=24)
        self.svg_images["battery-three-quarters"] = high_battery_icon

        half_battery_icon = icon_to_image("battery-half", fill=guikit.hex_string_for_style(bootstyle.WARNING), scale_to_height=24)
        self.svg_images["battery-half"] = half_battery_icon

        low_battery_icon = icon_to_image("battery-quarter", fill=guikit.hex_string_for_style(bootstyle.DANGER), scale_to_height=24)
        self.svg_images["battery-quarter"] = low_battery_icon

        unknown_battery_icon = icon_to_image("battery-empty", fill=guikit.hex_string_for_style(bootstyle.SECONDARY), scale_to_height=24)
        self.svg_images["battery-empty"] = unknown_battery_icon

        self.battery_level_indicator = ttk.Label(panel, image=high_battery_icon, font=font.Font(weight=font.BOLD), compound=tk.CENTER)
        self.battery_level_indicator.grid(column=0, row=0)
        return panel

    def create_settings_panel(self) -> ttk.Frame:
        """Create the settings panel region of the app."""
        panel = ttk.Frame()
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(0, weight=1)

        sensor_node_group_label = ttk.Label(panel, text="Sensor node group")
        sensor_node_group_label.grid(column=0, row=0, padx=8, pady=(8, 2), sticky=tk.NSEW)

        sensor_node_group = ttk.Entry(panel, textvariable=self.sensor_node_group_variable)
        sensor_node_group.grid(column=0, row=1, padx=16, pady=(2, 8), sticky=tk.NSEW)

        sample_rate_label = ttk.Label(panel, text="Sample rate")
        sample_rate_label.grid(column=0, row=2, padx=8, pady=(8, 2), sticky=tk.NSEW)

        slow_option = ttk.Radiobutton(panel, command=self.handle_change_sample_rate, text=SoilSwell.CommandName.Slow, variable=self.sample_rate_variable, value=SoilSwell.CommandName.Slow)
        slow_option.grid(column=0, row=3, padx=(16, 8), pady=4, sticky=tk.NSEW)
        normal_option = ttk.Radiobutton(panel, command=self.handle_change_sample_rate, text=SoilSwell.CommandName.Normal, variable=self.sample_rate_variable, value=SoilSwell.CommandName.Normal)
        normal_option.grid(column=0, row=4, padx=(16, 8), pady=4, sticky=tk.NSEW)
        fast_option = ttk.Radiobutton(panel, command=self.handle_change_sample_rate, text=SoilSwell.CommandName.Fast, variable=self.sample_rate_variable, value=SoilSwell.CommandName.Fast)
        fast_option.grid(column=0, row=5, padx=(16, 8), pady=(4, 12), sticky=tk.NSEW)
        self.sample_rate_variable.set(SoilSwell.CommandName.Fast)

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
        )
        self.acquire_button.configure(command=functools.partial(self.handle_acquire, self.acquire_button))
        self.acquire_button.grid(column=0, row=0, padx=8, pady=8, sticky=tk.NSEW)

        self.log_data_button = self.create_icon_button(
            panel,
            text=SoilSwell.CommandName.LogData,
            icon_name="file-waveform",
        )
        self.log_data_button.configure(command=functools.partial(self.handle_log_data, self.log_data_button))
        self.log_data_button.grid(column=0, row=1, padx=8, pady=8, sticky=tk.NSEW)

        self.reset_button = self.create_icon_button(
            panel,
            text=SoilSwell.CommandName.Reset,
            icon_name="rotate-left",
            icon_fill=guikit.hex_string_for_style(bootstyle.WARNING),
            spaces=4,
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

    def show_about(self) -> None:
        """Handle the Help::About menu command."""

    def change_theme(self, theme_name:str) -> None:
        """Handle the View::Theme selection command."""
        self.state.active_theme = theme_name

    def on_theme_changed(self, event_args: tk.Event) -> None:
        """Handle the ThemeChanged event."""
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

        # Update image colors -- this adds a noticeable delay, should be cached rather than recalculated
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

    def handle_change_sample_rate(self) -> None:
        """Handle the selection event for the sample rate Radiobuttons."""

    def handle_acquire(self, sender: tk.Widget) -> None:
        """Handle the Acquire command."""
        current_acquire = self.state.acquire_active
        new_acquire = not current_acquire
        self.state.acquire_active = new_acquire

    def on_acquire_changed(self, event_args: tk.Event) -> None:
        """Handle the AcquireDataChanged event."""
        acquire_active = self.state.acquire_active
        new_style = bootstyle.SUCCESS if acquire_active else bootstyle.DEFAULT
        self.acquire_button.configure(bootstyle=new_style)  # pyright: ignore reportArgumentType -- the type hint for library uses strings
        self.acquire_variable.set(acquire_active)

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

    def on_mouse_enter(self, event_args: tk.Event) -> None:
        """Handle the mouse Enter event."""
        self.reset_button.configure(image=self.svg_images["hover-rotate-left"])

    def on_mouse_leave(self, event_args: tk.Event) -> None:
        """Handle the mouse Leave event."""
        self.reset_button.configure(image=self.svg_images["rotate-left"])

    def handle_reset(self, sender: tk.Widget) -> None:
        """Handle the Acquire command."""

    def update_window_title(self, new_title: str) -> None:
        """Update the application's window title."""
        self.root_window.title(new_title)


if __name__ == "__main__":
    logger.debug(f"Launching {__package__}")
    asyncio.run(guikit.AsyncApp.create_and_run(SoilSwell))
