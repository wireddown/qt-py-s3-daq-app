"""Plot data from CSV files."""

import asyncio
import atexit
import contextlib
import csv
import functools
import json
import logging
import math
import pathlib
import random
import shutil
import tempfile
import time
import tkinter as tk
import webbrowser
from enum import StrEnum
from tkinter import filedialog, font

import matplotlib.figure as mpl_figure
import pandas as pd
import ttkbootstrap as ttk
import ttkbootstrap.dialogs as ttk_dialogs
import ttkbootstrap.icons as ttk_icons
import ttkbootstrap.themes.standard as ttk_themes
from ttkbootstrap import constants as bootstyle

from qtpy_datalogger import datatypes, guikit, ttkbootstrap_matplotlib
from qtpy_datalogger.vendor.tkfontawesome import icon_to_image

logger = logging.getLogger(pathlib.Path(__file__).stem)

app_icon_color = "#07a000"


class AppState:
    """A class that models and controls the app's settings and runtime state."""

    no_file: pathlib.Path = pathlib.Path(__file__)
    canceled_file: pathlib.Path = pathlib.Path()

    class Event(StrEnum):
        """Events emitted when properties change."""

        DataFileChanged = "<<DataFileChanged>>"
        ReplayActiveChanged = "<<ReplayActiveChanged>>"

    def __init__(self, tk_root: tk.Tk) -> None:
        """Initialize a new AppState instance."""
        self._tk_notifier = tk_root
        self._theme_name: str = ""
        self._data_file = AppState.no_file
        self._replay_active: bool = False
        self._demo_folder: pathlib.Path = pathlib.Path(tempfile.mkdtemp())
        atexit.register(functools.partial(shutil.rmtree, self._demo_folder))

    @property
    def active_theme(self) -> str:
        """Return the name of the active ttkbootstrap theme."""
        return self._theme_name

    @active_theme.setter
    def active_theme(self, new_value: str) -> None:
        """Set a new value for the active_theme."""
        if new_value == self._theme_name:
            return
        self._theme_name = new_value
        ttk.Style().theme_use(new_value)

    @property
    def data_file(self) -> pathlib.Path:
        """Return the path to the data file."""
        return self._data_file

    @data_file.setter
    def data_file(self, new_value: pathlib.Path) -> None:
        """Set a new value for the data_file."""
        if new_value in [self._data_file, AppState.canceled_file]:
            return
        self._data_file = new_value
        self._tk_notifier.event_generate(AppState.Event.DataFileChanged)

    @property
    def replay_active(self) -> bool:
        """Return True when the app is replaying a data file."""
        return self._replay_active

    @replay_active.setter
    def replay_active(self, new_value: bool) -> None:
        """Set a new value for replay_active."""
        if new_value == self._replay_active:
            return
        self._replay_active = new_value
        self._tk_notifier.event_generate(AppState.Event.ReplayActiveChanged)

    @property
    def demo_folder(self) -> pathlib.Path:
        """Return the folder used for demo files."""
        return self._demo_folder


class AboutDialog(ttk_dialogs.Dialog):
    """A class that presents information about the app."""

    def __init__(self, parent: ttk.Window, title: str = "") -> None:
        """Initialize a new AboutDialog instance."""
        super().__init__(parent, title, alert=False)

    def create_body(self, master: tk.Widget) -> None:
        """Create the UI for the dialog."""
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)
        self.main_frame = ttk.Frame(master, padding=16)
        self.main_frame.grid(column=0, row=0, sticky=tk.NSEW)
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.rowconfigure(0, weight=1)
        self.main_frame.rowconfigure(1, weight=1)

        message_frame = ttk.Frame(self.main_frame)
        message_frame.grid(column=0, row=0, sticky=tk.NSEW)
        message_frame.columnconfigure(0, weight=0, minsize=40)  # Filler
        message_frame.columnconfigure(1, weight=0)  # Icon1
        message_frame.columnconfigure(2, weight=0)  # Icon2
        message_frame.columnconfigure(3, weight=0)  # Icon3
        message_frame.columnconfigure(4, weight=0, minsize=20)  # Filler
        message_frame.columnconfigure(5, weight=0)  # Text
        message_frame.columnconfigure(6, weight=0, minsize=40)  # Filler
        message_frame.rowconfigure(0, weight=0, minsize=20)  # Filler
        message_frame.rowconfigure(1, weight=0)  # Icons and Name
        message_frame.rowconfigure(2, weight=0)  # Version
        message_frame.rowconfigure(3, weight=0)  # Separator
        message_frame.rowconfigure(4, weight=0)  # Help
        message_frame.rowconfigure(5, weight=0)  # Source
        message_frame.rowconfigure(6, weight=0)  # Source2
        message_frame.rowconfigure(7, weight=0, minsize=20)  # Filler

        icon_height = 48
        icon_color = guikit.hex_string_for_style("fg")
        self.microchip_icon = icon_to_image("microchip", fill=icon_color, scale_to_height=icon_height)
        microchip_label = ttk.Label(message_frame, image=self.microchip_icon, padding=3)
        microchip_label.grid(column=1, row=1, rowspan=2)
        self.qtpy_icon = icon_to_image("worm", fill=icon_color, scale_to_height=icon_height)
        qtpy_label = ttk.Label(message_frame, image=self.qtpy_icon, padding=4)
        qtpy_label.grid(column=2, row=1, rowspan=2)
        self.chart_icon = icon_to_image("chart-line", fill=icon_color, scale_to_height=icon_height)
        chart_label = ttk.Label(message_frame, image=self.chart_icon, padding=4)
        chart_label.grid(column=3, row=1, rowspan=2, padx=(2, 0))

        name_label = ttk.Label(message_frame, font=font.Font(weight="bold", size=28), text=DataViewer.app_name)
        name_label.grid(column=5, row=1, sticky=tk.W)
        version_information = datatypes.SnsrNotice.get_package_notice_info(allow_dev_version=True)
        version_label = ttk.Label(message_frame, text=f"{version_information.version} {ttk_icons.Emoji.get('black medium small square')} {version_information.timestamp:%Y-%m-%d} {ttk_icons.Emoji.get('black medium small square')} {version_information.commit}")
        version_label.grid(column=5, row=2, sticky=tk.W, padx=(4, 0))
        separator = ttk.Separator(message_frame)
        separator.grid(column=1, row=3, columnspan=5, sticky=tk.EW, pady=4)
        self.help_icon = icon_to_image("parachute-box", fill=guikit.hex_string_for_style("selectfg"), scale_to_width=16)  # suitcase-medical
        help_button = ttk.Button(message_frame, compound=tk.LEFT, image=self.help_icon, text="   Online help ", style=bootstyle.INFO, width=18, command=functools.partial(webbrowser.open_new_tab, datatypes.Links.Homepage))
        help_button.grid(column=5, row=4, sticky=tk.W, pady=(18, 0))
        self.source_icon = icon_to_image("github-alt", fill=guikit.hex_string_for_style("selectfg"), scale_to_width=16)
        source_button = ttk.Button(message_frame, compound=tk.LEFT, image=self.source_icon, text="   Source code", style=bootstyle.INFO, width=18, command=functools.partial(webbrowser.open_new_tab, datatypes.Links.Source))
        source_button.grid(column=5, row=5, sticky=tk.W, pady=(22, 0))

    def create_buttonbox(self, master: tk.Widget) -> None:
        """Create the bottom row of buttons."""
        button_frame = ttk.Frame(self.main_frame)
        button_frame.grid(column=0, row=1, sticky=tk.NSEW, padx=(0, 16), pady=(8, 0))
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=0)
        button_frame.rowconfigure(0, weight=0)
        self.copy_version_button = ttk.Button(button_frame, text="Copy version", bootstyle=bootstyle.OUTLINE, command=self.copy_version, width=12)
        self.copy_version_button.grid(column=0, row=0, sticky=tk.E, padx=(0, 16))
        ok_button = ttk.Button(button_frame, text="OK", command=self._toplevel.destroy)
        ok_button.grid(column=1, row=0, sticky=tk.E)
        self._initial_focus = ok_button

    def copy_version(self) -> None:
        """Copy the version information to the clipboard."""
        notice = datatypes.SnsrNotice.get_package_notice_info(allow_dev_version=True)
        formatted_version = {
            "version": notice.version,
            "timestamp": str(notice.timestamp),
            "commit": notice.commit,
        }
        self._toplevel.clipboard_clear()
        self._toplevel.clipboard_append(json.dumps(formatted_version))
        status_emoji = ttk_icons.Emoji.get("white heavy check mark")
        self.copy_version_button.configure(text=f"{status_emoji}   Copied!", bootstyle=bootstyle.SUCCESS)
        self.copy_version_button.after(850, functools.partial(self.copy_version_button.configure, text="Copy version", bootstyle=(bootstyle.DEFAULT, bootstyle.OUTLINE)))

class DataViewer(guikit.AsyncWindow):
    """A GUI that loads a CSV data file and plots the columns."""

    class MenuName(StrEnum):
        """Names used for entries in the app's menus."""

        File = "File"
        Open = "Open..."
        Reload= "Reload"
        Replay = "Replay"
        Overlay = "Overlay..."
        Close = "Close"
        Exit = "Exit"
        Edit = "Edit"
        Copy = "Copy"
        Export = "Export..."
        View = "View"
        Plots = "Plots"
        HideAll = "Hide all"
        ShowAll = "Show all"
        Theme = "Theme"
        Light = "Light"
        Dark = "Dark"
        Help = "Help"
        About = "About"

    app_name = "QT Py Data Viewer"

    def create_user_interface(self) -> None:  # noqa: PLR0915 -- allow long function to create the UI
        """Create the main window and connect event handlers."""
        self.theme_variable = tk.StringVar()
        self.replay_variable = tk.BooleanVar()
        self.replay_index = 0
        self.next_update_time = time.time()
        self.state = AppState(self.root_window)

        self.svg_images: dict[str, tk.Image] = {}
        self.plots_variables: list[tk.BooleanVar] = []

        app_icon = icon_to_image("chart-line", fill=app_icon_color, scale_to_height=256)
        self.root_window.iconphoto(True, app_icon)
        self.update_window_title(DataViewer.app_name)

        figure_dpi = 112
        figure_ratio = 16 / 9
        graph_min_width = 504
        graph_aspect_size = graph_min_width / figure_dpi
        figure_aspect = (graph_aspect_size, graph_aspect_size / figure_ratio)
        self.root_window.minsize(width=(1136 + 32), height=(639 + 32 + 8 + 65))  # Account for padding
        self.root_window.columnconfigure(0, weight=1)
        self.root_window.rowconfigure(0, weight=1)
        self.build_window_menu()

        main = ttk.Frame(self.root_window, name="main_frame", padding=16)
        main.grid(column=0, row=0, sticky=tk.NSEW)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=1)
        main.rowconfigure(1, weight=0)

        self.canvas_frame = ttk.Frame(main, name="canvas_frame")
        self.canvas_frame.grid(column=0, row=0, sticky=tk.NSEW)
        self.canvas_frame.columnconfigure(0, weight=1)
        self.canvas_frame.rowconfigure(0, weight=1)
        self.plot_figure = mpl_figure.Figure(figsize=figure_aspect, dpi=figure_dpi)
        self.canvas_figure = ttkbootstrap_matplotlib.create_styled_plot_canvas(self.plot_figure, self.canvas_frame)
        self.plot_figure.subplots_adjust(left=0.06, bottom=0.08, right=0.98, top=0.98)

        self.plot_axes = self.plot_figure.add_subplot()

        toolbar_row = ttk.Frame(main, name="toolbar_row")
        toolbar_row.grid(column=0, row=1, sticky=tk.NSEW, padx=40, pady=(8, 0))
        toolbar_row.columnconfigure(0, weight=1)
        toolbar_row.columnconfigure(1, weight=0)

        action_panel = ttk.Frame(toolbar_row, name="action_panel")
        action_panel.grid(column=0, row=0, sticky=tk.EW, padx=(0, 8))
        action_panel.columnconfigure(0, weight=0)
        action_panel.columnconfigure(1, weight=0)
        action_panel.columnconfigure(2, weight=1)
        action_panel.columnconfigure(3, weight=0)
        action_panel.columnconfigure(4, weight=0)
        action_panel.rowconfigure(0, weight=0)
        action_panel.rowconfigure(1, weight=0)

        self.export_csv_button = self.create_icon_button(action_panel, text="Export", icon_name="table", char_width=12)
        self.export_csv_button.grid(column=4, row=0, padx=(8, 0))
        self.export_csv_button.configure(command=functools.partial(self.export_canvas, self.export_csv_button))

        self.reload_button = self.create_icon_button(action_panel, text="Reload", icon_name="rotate-left", char_width=12)
        self.reload_button.configure(command=functools.partial(self.reload_file, self.reload_button))
        self.reload_button.grid(column=0, row=0, padx=(0, 8))
        self.replay_button = self.create_icon_button(action_panel, text="Replay", icon_name="clock-rotate-left", char_width=12)
        self.replay_button.configure(command=functools.partial(self.replay_data, self.replay_button))
        self.replay_button.grid(column=1, row=0, padx=8)

        self.file_message = ttk.Label(action_panel, text="Waiting for load")
        self.file_message.grid(row=1, columnspan=5, pady=(8, 0))

        toolbar_frame = ttkbootstrap_matplotlib.create_styled_plot_toolbar(toolbar_row, self.canvas_figure)
        toolbar_frame.grid(column=1, row=0, sticky=(tk.EW, tk.N), padx=(8, 0))

        self.state.active_theme = "flatly"

        self.canvas_cover = ttk.Frame(main, name="canvas_cover", style=bootstyle.LIGHT)
        self.canvas_cover.grid(column=0, row=0, sticky=tk.NSEW)
        self.canvas_cover.columnconfigure(0, weight=1)
        self.canvas_cover.rowconfigure(0, weight=1)
        self.canvas_cover.rowconfigure(1, weight=0)
        self.canvas_cover.rowconfigure(2, weight=1)

        self.startup_label = ttk.Label(self.canvas_cover, font=font.Font(weight="bold", size=24), text="QT Py Data Viewer")
        self.startup_label.grid(column=0, row=0, pady=16)
        open_file_button = self.create_icon_button(self.canvas_cover, text="Open CSV", icon_name="file-csv", spaces=2, bootstyle=bootstyle.INFO)
        open_file_button.grid(column=0, row=1, sticky=tk.S, pady=(0, 16))
        open_file_button.configure(command=functools.partial(self.open_file, open_file_button))
        demo_button = self.create_icon_button(self.canvas_cover, text="Demo", icon_name="chart-line", spaces=4, bootstyle=bootstyle.INFO)
        demo_button.grid(column=0, row=2, sticky=tk.N, pady=(0, 16))
        demo_button.configure(command=functools.partial(self.open_demo, demo_button))

        self.root_window.bind(
            AppState.Event.DataFileChanged,
            lambda e: self.on_data_file_changed(e),
        )

        self.root_window.bind(
            AppState.Event.ReplayActiveChanged,
            lambda e: self.on_replay_active_changed(e),
        )
        self.root_window.bind(
            "<<ThemeChanged>>",
            lambda e: self.on_theme_changed(e),
        )

        self.on_data_file_changed(event_args=tk.Event())

    def create_icon_button(
            self,
            parent: tk.Widget,
            text: str,
            icon_name: str,
            char_width: int = 15,
            spaces: int = 2,
            bootstyle: str = bootstyle.DEFAULT,
        ) -> ttk.Button:
        """Create a ttk.Button using the specified text and FontAwesome icon_name."""
        text_spacing = 3 * " "
        button_image = icon_to_image(icon_name, fill=guikit.hex_string_for_style("selectfg"), scale_to_height=24)
        self.svg_images[icon_name] = button_image
        button = ttk.Button(
            parent,
            text=text + spaces * text_spacing,
            image=button_image,
            compound=tk.RIGHT,
            width=char_width,
            padding=(4, 6, 4, 4),
            bootstyle=bootstyle,
        )
        return button

    def on_show(self) -> None:
        """Initialize UI before entering main loop."""

    async def on_loop(self) -> None:
        """Update the UI with new information."""
        await asyncio.sleep(1e-6)
        if not self.state.replay_active:
            return
        now = time.time()
        if self.next_update_time > now:
            return
        self.next_update_time = now + 0.35
        draw_to = self.replay_index + 1
        self.replay_index = draw_to
        time_coordinates, data_series = self.get_data()
        if self.replay_index == len(time_coordinates):
            self.state.replay_active = False
            self.reload_file(self.reload_button)

        # Only draw up to index
        plot_lines = self.plot_axes.lines
        times = time_coordinates[:draw_to]
        for index, (_, series) in enumerate(data_series.items()):
            measurements = series.tolist()[:draw_to]
            plot = plot_lines[index]
            plot.set_xdata(times)
            plot.set_ydata(measurements)
        self.canvas_figure.draw()

    def on_closing(self) -> None:
        """Clean up before exiting."""

    def update_window_title(self, new_title: str) -> None:
        """Update the application's window title."""
        self.root_window.title(new_title)

    def build_window_menu(self) -> None:
        """Create the entries for the window menu bar."""
        self.root_window.option_add("*tearOff", False)
        self.menubar = tk.Menu(
            self.root_window,
            # No styling support here -- Windows Settings for Light vs Dark mode control the menubar
        )
        self.root_window.config(menu=self.menubar)

        # File menu
        self.file_menu = tk.Menu(self.menubar, name="file_menu")
        self.menubar.add_cascade(
            label=DataViewer.MenuName.File,
            menu=self.file_menu,
            underline=0,
        )
        self.file_menu.add_command(
            command=functools.partial(self.open_file, self.file_menu),
            label=DataViewer.MenuName.Open,
            accelerator="Ctrl-O",
            # Styling is supported here, but the bounding frame surrounding the menu entries follows Windows System settings
        )
        self.root_window.bind("<Control-o>", lambda e: self.open_file(self.file_menu))
        self.file_menu.add_command(
            command=functools.partial(self.reload_file, self.file_menu),
            label=DataViewer.MenuName.Reload,
            accelerator="F5",
        )
        self.root_window.bind("<F5>", lambda e: self.reload_file(self.file_menu))
        self.file_menu.add_checkbutton(
            command=functools.partial(self.replay_data, self.file_menu),
            label=DataViewer.MenuName.Replay,
            variable=self.replay_variable,
        )
        self.file_menu.add_command(
            command=functools.partial(self.export_canvas, self.file_menu),
            label=DataViewer.MenuName.Export,
        )
        self.file_menu.add_command(
            command=functools.partial(self.close_file, self.file_menu),
            label=DataViewer.MenuName.Close,
            accelerator="Ctrl-W",
            # Styling is supported here, but the bounding frame surrounding the menu entries follows Windows System settings
        )
        self.root_window.bind("<Control-w>", lambda e: self.close_file(self.file_menu))
        self.file_menu.add_separator(
            # Styling is supported here, but the bounding frame surrounding the menu entries follows Windows System settings
        )
        self.file_menu.add_command(
            command=self.exit,
            label=DataViewer.MenuName.Exit,
            accelerator="Alt-F4",
        )
        self.root_window.bind("<Alt-F4>", lambda e: self.exit())

        # View menu
        self.view_menu = tk.Menu(self.menubar, name="view_menu")
        self.menubar.add_cascade(
            label=DataViewer.MenuName.View,
            menu=self.view_menu,
            underline=0,
        )
        # Plots submenu
        self.plots_menu = tk.Menu(self.view_menu, name="plots_menu")
        self.view_menu.add_cascade(
            label=DataViewer.MenuName.Plots,
            menu=self.plots_menu,
            underline=0,
        )
        # Themes submenu
        style = ttk.Style.get_instance()
        if not (style and style.theme):
            raise ValueError()
        light_themes = []
        dark_themes = []
        for theme_name, definition in ttk_themes.STANDARD_THEMES.items():
            theme_kind = definition["type"]
            if theme_kind == "light":
                light_themes.append(theme_name)
            elif theme_kind == "dark":
                dark_themes.append(theme_name)
            else:
                raise ValueError()
        self.themes_menu = tk.Menu(self.view_menu, name="themes_menu")
        self.view_menu.add_cascade(
            label=DataViewer.MenuName.Theme,
            menu=self.themes_menu,
            underline=0,
        )
        self.light_menu = tk.Menu(self.themes_menu, name="light_themes_menu")
        self.themes_menu.add_cascade(
            label=DataViewer.MenuName.Light,
            menu=self.light_menu,
            underline=0,
        )
        self.dark_menu = tk.Menu(self.themes_menu, name="dark_themes_menu")
        self.themes_menu.add_cascade(
            label=DataViewer.MenuName.Dark,
            menu=self.dark_menu,
            underline=0,
        )
        for theme_name in sorted(light_themes):
            self.light_menu.add_radiobutton(
                command=functools.partial(self.change_theme, theme_name),
                label=theme_name.capitalize(),
                variable=self.theme_variable,
            )
        for theme_name in sorted(dark_themes):
            self.dark_menu.add_radiobutton(
                command=functools.partial(self.change_theme, theme_name),
                label=theme_name.capitalize(),
                variable=self.theme_variable,
            )

        # Help menu
        self.help_menu = tk.Menu(self.menubar, name="help_menu")
        self.menubar.add_cascade(
            label=DataViewer.MenuName.Help,
            menu=self.help_menu,
            underline=0,
        )
        self.help_menu.add_command(
            command=self.show_about,
            label=DataViewer.MenuName.About,
            accelerator="F1",
        )
        self.root_window.bind("<F1>", lambda e: self.show_about())

    def open_file(self, sender: tk.Widget) -> None:
        """Handle the File::Open menu command."""
        file_path = filedialog.askopenfilename(
            parent=self.root_window,
            title="Select a CSV data file",
            filetypes=[
                ("CSV files", "*.csv"),
            ],
        )
        self.state.data_file = pathlib.Path(file_path)

    def open_demo(self, sender: tk.Widget) -> None:
        """Handle the Demo button command."""
        channel_count = 8
        trend_function = random.choice([math.log10, math.cbrt])
        column_titles = ["time (s)"]
        column_titles.extend([f"v{N+1}" for N in range(channel_count)])
        channels = list(range(1, len(column_titles)))
        random.shuffle(channels)
        data_samples = [column_titles]
        for sample_number in range(100):
            scan = []
            timestamp = sample_number * 10
            scan.append(float(timestamp))
            for channel in channels:
                noise = random.random()
                channel_sample = channel * trend_function(timestamp + 50) - 0.2 * noise
                scan.append(channel_sample)
            data_samples.append(scan)
        with self.state.demo_folder.joinpath("Data Viewer Demo.csv").open(encoding="UTF-8", mode="w", newline="") as demo_file:
            csv_writer = csv.writer(demo_file)
            csv_writer.writerows(data_samples)
            demo_file.flush()
            self.state.data_file = pathlib.Path(demo_file.name)

    def reload_file(self, sender: tk.Widget) -> None:
        """Handle the File::Reload menu command."""
        self.replay_index = 0
        self.plot_axes.clear()
        self.on_data_file_changed(tk.Event())

    def close_file(self, sender: tk.Widget) -> None:
        """Handle the File::Close menu command."""
        self.state.data_file = AppState.no_file

    def overlay_file(self, sender: tk.Widget) -> None:
        """Handle the File::Overlay menu command."""

    def export_canvas(self, sender: tk.Widget) -> None:
        """Handle the Export CSV button command."""
        file_name = filedialog.asksaveasfilename(
            parent=self.root_window,
            title="Specify a CSV file to use for exported data",
            initialfile=f"{self.state.data_file.stem} - exported selection.csv",
            filetypes=[
                ("CSV files", "*.csv"),
            ],
        )
        file_path = pathlib.Path(file_name)
        if file_path == AppState.canceled_file:
            return

        file_path = file_path.with_suffix(".csv")

        other_lower, other_upper = self.plot_axes.get_xbound()
        time_coordinates, full_data_set = self.get_data()
        time_series = pd.Series(time_coordinates)
        above_limit = time_series >= other_lower
        below_limit = time_series <= other_upper
        time_values = time_series[above_limit & below_limit]
        visible_series = [v.get() for v in self.plots_variables]
        data_to_export = full_data_set.loc[time_values.index, visible_series]
        data_to_export.index = time_values
        data_to_export.index.name = "time"
        data_to_export.to_csv(file_path)

    def on_data_file_changed(self, event_args: tk.Event) -> None:
        """Handle the File::Open menu or button command."""
        self.plot_axes.clear()
        if self.state.data_file == AppState.no_file:
            new_enabled_state = tk.DISABLED
            new_window_title = DataViewer.app_name
            plots_entries = ["(none)"]
            self.canvas_cover.grid(column=0, row=0, sticky=tk.NSEW)
        else:
            new_enabled_state =  tk.NORMAL
            new_window_title = f"{self.state.data_file.name} - {DataViewer.app_name}"
            plots_entries = self.update_plot_axes()
            self.canvas_cover.grid_forget()
        button_list = [
            self.reload_button,
            self.replay_button,
            self.export_csv_button,
        ]
        for button in button_list:
            button.configure(state=new_enabled_state)
        menu_entries = {
            self.file_menu: [DataViewer.MenuName.Reload, DataViewer.MenuName.Replay, DataViewer.MenuName.Export, DataViewer.MenuName.Close],
        }
        for owner, entries in menu_entries.items():
            for entry in entries:
                owner.entryconfigure(entry, state=new_enabled_state)
        self.plots_menu.delete(0, "end")
        self.plots_variables.clear()
        self.plots_menu.add_command(label=DataViewer.MenuName.HideAll, command=functools.partial(self.hide_all_plots, self.plots_menu))
        self.plots_menu.add_command(label=DataViewer.MenuName.ShowAll, command=functools.partial(self.show_all_plots, self.plots_menu))
        self.plots_menu.add_separator()
        for index, entry in enumerate(plots_entries):
            toggle_variable = tk.BooleanVar(self.plots_menu)
            self.plots_menu.add_checkbutton(label=entry, state=new_enabled_state, command=functools.partial(self.toggle_plot, index), variable=toggle_variable)
            self.plots_variables.append(toggle_variable)
            if self.state.data_file != AppState.no_file:
                toggle_variable.set(True)
        for index in range(0, self.plots_menu.index("end") + 1):
            self.style_menu_entry(self.plots_menu, index)
        self.update_window_title(new_window_title)

    def hide_all_plots(self, sender:tk.Widget) -> None:
        """Hide all plots."""
        plot_lines = self.plot_axes.lines
        for line in plot_lines:
            line.set_visible(False)
        self.canvas_figure.draw()
        for variable in self.plots_variables:
            variable.set(False)

    def show_all_plots(self, sender: tk.Widget) -> None:
        """Show all plots."""
        plot_lines = self.plot_axes.lines
        for line in plot_lines:
            line.set_visible(True)
        self.canvas_figure.draw()
        for variable in self.plots_variables:
            variable.set(True)

    def toggle_plot(self, index: int) -> None:
        """Toggle the visibility of the plot for series_name."""
        menu_variable = self.plots_variables[index]
        new_visibility = menu_variable.get()
        plot_lines = self.plot_axes.lines
        plot_lines[index].set_visible(new_visibility)
        self.canvas_figure.draw()

    def replay_data(self, sender: tk.Widget) -> None:
        """Handle the View::Replay menu or button command."""
        current_replay = self.state.replay_active
        new_replay = not current_replay
        self.state.replay_active = new_replay

    def on_replay_active_changed(self, event_args: tk.Event) -> None:
        """Update UI state when replay_active changes state."""
        replay_active = self.state.replay_active
        new_style = bootstyle.SUCCESS if replay_active else bootstyle.DEFAULT
        self.replay_button.configure(bootstyle=new_style)
        self.replay_variable.set(replay_active)

    def change_theme(self, theme_name: str) -> None:
        """Handle the View::Theme selection command."""
        self.state.active_theme = theme_name

    def on_theme_changed(self, event_args: tk.Event) -> None:
        """Update UI state when active_theme changes state."""
        theme_name = self.state.active_theme
        self.theme_variable.set(theme_name.capitalize())
        self.startup_label.configure(background=guikit.hex_string_for_style(bootstyle.LIGHT))
        all_menus = [
            self.file_menu,
            self.view_menu,
            self.plots_menu,
            self.themes_menu,
            self.light_menu,
            self.dark_menu,
            self.help_menu,
        ]
        # Force light theme for menus
        for menu in all_menus:
            for index in range(0, menu.index("end") + 1):
                self.style_menu_entry(menu, index)

    def style_menu_entry(self, menu: tk.Menu, index: int) -> None:
        """Style the specified menu entry."""
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

    def show_about(self) -> None:
        """Handle the Help::About menu command."""
        about_dialog = AboutDialog(parent=self.root_window, title=f"About {DataViewer.app_name}")
        about_dialog.show()

    def update_plot_axes(self) -> list[str]:
        """Reconfigure the plot for the new data and return the names of the measurement series."""
        time_coordinates, data_series = self.get_data()
        for name, series in data_series.items():
            measurements = series.tolist()
            self.plot_axes.plot(
                time_coordinates,
                measurements,
                label=name,
            )
        self.plot_axes.set_xlabel("Time")
        self.plot_axes.set_ylabel("Measurement")
        self.plot_axes.grid(
            visible=True,
            which="major",
            axis="y",
            dashes=(3, 8),
        )
        self.plot_axes.legend(
            loc="upper left",
            draggable=True,
        )
        self.canvas_figure.draw()
        return data_series.keys().to_list()

    def get_data(self) -> tuple[list, pd.DataFrame]:
        """Get the time coordinates and measurement series from the data file."""
        data_file_df = pd.read_csv(self.state.data_file)
        # Assume table format, with time in first column and data in subsequent columns
        time_index = data_file_df[data_file_df.columns[0]]
        time_coordinates = time_index.to_list()
        series_names = data_file_df.columns[1:]
        measurement_series = data_file_df[series_names]
        return time_coordinates, measurement_series


if __name__ == "__main__":
    logger.debug(f"Launching {__package__}")
    asyncio.run(guikit.AsyncApp.create_and_run(DataViewer))
