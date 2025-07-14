"""Plot data from CSV files."""

import asyncio
import atexit
import contextlib
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
from tkfontawesome import icon_to_image
from ttkbootstrap import constants as bootstyle

from qtpy_datalogger import datatypes, guikit, ttkbootstrap_matplotlib

logger = logging.getLogger(pathlib.Path(__file__).stem)

app_icon_color = "#07a000"


class StyleKey(StrEnum):
    """A class that extends the palette names of ttkbootstrap styles."""

    Fg = "fg"
    SelectFg = "selectfg"


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
        self._tk_notifier: tk.Tk = tk_root
        self._theme_name: str = ""
        self._data_file: pathlib.Path = AppState.no_file
        self._replay_active: bool = False
        self._demo_folder: pathlib.Path = pathlib.Path(tempfile.mkdtemp())
        atexit.register(shutil.rmtree, self._demo_folder)

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
        guikit.ThemeChanger.use_bootstrap_theme(new_value, self._tk_notifier.winfo_toplevel())

    @property
    def data_file(self) -> pathlib.Path:
        """Return the path to the data file."""
        return self._data_file

    @data_file.setter
    def data_file(self, new_value: pathlib.Path) -> None:
        """Set a new value for data_file and notify DataFileChanged event subscribers."""
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
        """Set a new value for replay_active and notify ReplayActiveChanged event subscribers."""
        if new_value == self._replay_active:
            return
        self._replay_active = new_value
        self._tk_notifier.event_generate(AppState.Event.ReplayActiveChanged)

    @property
    def demo_folder(self) -> pathlib.Path:
        """Return the folder used for demo files."""
        return self._demo_folder

    def load_data_file(self) -> None:
        """Load the data file into memory."""
        if self.data_file in [AppState.no_file, AppState.canceled_file]:
            raise RuntimeError()
        self.data_file_df = pd.read_csv(self.data_file)

    def get_data(self) -> pd.DataFrame:
        """Return the loaded data as a DataFrame."""
        return self.data_file_df.copy()


class AboutDialog(ttk_dialogs.Dialog):
    """A class that presents information about the app."""

    def __init__(self, parent: ttk.Window, title: str = "") -> None:
        """Initialize a new AboutDialog instance."""
        super().__init__(parent, title, alert=False)

    def create_body(self, master: tk.Widget) -> None:  # noqa: PLR0915 -- allow long function to create the UI
        """Create the UI for the dialog."""
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)
        self.main_frame = ttk.Frame(master, padding=16)
        self.main_frame.grid(column=0, row=0, sticky=tk.NSEW)
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.rowconfigure(0, weight=1)

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
        message_frame.rowconfigure(2, weight=0)  # Icons and Version
        message_frame.rowconfigure(3, weight=0)  # Separator
        message_frame.rowconfigure(4, weight=0)  # Help
        message_frame.rowconfigure(5, weight=0)  # Source
        message_frame.rowconfigure(6, weight=0)  # Source2
        message_frame.rowconfigure(7, weight=0, minsize=50)  # Filler

        icon_height = 48
        icon_color = guikit.hex_string_for_style(StyleKey.Fg)
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
        self.notice_information = datatypes.SnsrNotice.get_package_notice_info(allow_dev_version=True)
        bullet = ttk_icons.Emoji.get("black medium small square")
        version_label = ttk.Label(
            message_frame,
            text=f"{self.notice_information.version} {bullet} {self.notice_information.timestamp:%Y-%m-%d} {bullet} {self.notice_information.commit}",
        )
        version_label.grid(column=5, row=2, sticky=tk.W, padx=(4, 0))
        separator = ttk.Separator(message_frame)
        separator.grid(column=1, row=3, columnspan=5, sticky=tk.EW, pady=4)
        button_text_color = guikit.hex_string_for_style(StyleKey.SelectFg)
        spacer = "   "
        self.help_icon = icon_to_image("parachute-box", fill=button_text_color, scale_to_width=16)
        help_button = ttk.Button(
            message_frame,
            compound=tk.LEFT,
            image=self.help_icon,
            text=f"{spacer}Online help ",  # The trailing space helps with internal margins
            style=bootstyle.INFO,
            width=18,
            command=functools.partial(webbrowser.open_new_tab, datatypes.Links.Homepage),
        )
        help_button.grid(column=5, row=4, sticky=tk.W, pady=(18, 0))
        self.source_icon = icon_to_image("github-alt", fill=button_text_color, scale_to_width=16)
        source_button = ttk.Button(
            message_frame,
            compound=tk.LEFT,
            image=self.source_icon,
            text=f"{spacer}Source code",
            style=bootstyle.INFO,
            width=18,
            command=functools.partial(webbrowser.open_new_tab, datatypes.Links.Source),
        )
        source_button.grid(column=5, row=5, sticky=tk.W, pady=(22, 0))

    def create_buttonbox(self, master: tk.Widget) -> None:
        """Create the bottom row of buttons."""
        if not self._toplevel:
            raise RuntimeError()
        self.main_frame.rowconfigure(1, weight=1)

        button_frame = ttk.Frame(self.main_frame)
        button_frame.grid(column=0, row=1, sticky=tk.NSEW, padx=(0, 16), pady=(8, 0))
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=0)
        button_frame.rowconfigure(0, weight=0)
        self.copy_version_button = ttk.Button(
            button_frame,
            text=DataViewer.CommandName.CopyVersion,
            style=bootstyle.OUTLINE,
            command=self.copy_version,
            width=12,
        )
        self.copy_version_button.grid(column=0, row=0, sticky=tk.E, padx=(0, 16))
        ok_button = ttk.Button(button_frame, text=DataViewer.CommandName.OK, command=self._toplevel.destroy)
        ok_button.grid(column=1, row=0, sticky=tk.E)
        self._initial_focus = ok_button

    def copy_version(self) -> None:
        """Copy the version information to the clipboard."""
        if not self._toplevel:
            raise RuntimeError()
        formatted_version = {
            "version": self.notice_information.version,
            "timestamp": str(self.notice_information.timestamp),
            "commit": self.notice_information.commit,
        }
        self._toplevel.clipboard_clear()
        self._toplevel.clipboard_append(json.dumps(formatted_version))
        status_emoji = ttk_icons.Emoji.get("white heavy check mark")
        self.copy_version_button.configure(text=f"{status_emoji}   Copied!", bootstyle=bootstyle.SUCCESS)  # pyright: ignore callIssue -- the type hint for bootstrap omits its own additions
        self.copy_version_button.after(
            850,
            functools.partial(
                self.copy_version_button.configure,
                text=DataViewer.CommandName.CopyVersion,
                bootstyle=(bootstyle.DEFAULT, bootstyle.OUTLINE),  # pyright: ignore callIssue -- the type hint for bootstrap omits its own additions
            ),
        )


class DataViewer(guikit.AsyncWindow):
    """A GUI that loads a CSV data file and plots the columns."""

    app_name = "QT Py Data Viewer"

    class CommandName(StrEnum):
        """Names used for menus and commands in the app."""

        File = "File"
        Open = "Open"
        Reload = "Reload"
        Replay = "Replay"
        Close = "Close"
        Exit = "Exit"
        Export = "Export"
        View = "View"
        Plots = "Plots"
        HideAll = "Hide all"
        ShowAll = "Show all"
        Theme = "Theme"
        Light = "Light"
        Dark = "Dark"
        Help = "Help"
        About = "About"
        OpenCSV = "Open CSV"
        Demo = "Demo"
        OK = "OK"
        CopyVersion = "Copy version"

    def create_user_interface(self) -> None:  # noqa: PLR0915 -- allow long function to create the UI
        """Create the main window and connect event handlers."""
        # Supports UI widget state
        self.theme_variable = tk.StringVar()
        self.replay_variable = tk.BooleanVar()
        self.plots_variables: list[tk.BooleanVar] = []
        self.svg_images: dict[str, tk.Image] = {}

        # Supports app state
        self.replay_index = 0
        self.next_update_time = time.time()
        self.state = AppState(self.root_window)

        app_icon = icon_to_image("chart-line", fill=app_icon_color, scale_to_height=256)
        self.root_window.iconphoto(True, app_icon)

        figure_dpi = 112
        figure_ratio = 16 / 9
        graph_min_width = 504
        graph_aspect_size = graph_min_width / figure_dpi
        figure_aspect = (graph_aspect_size, graph_aspect_size / figure_ratio)
        self.root_window.minsize(
            width=(1136 + 32),  # Measure live and account for widgets and padding
            height=(639 + 32 + 8 + 65),
        )
        self.root_window.columnconfigure(0, weight=1)
        self.root_window.rowconfigure(0, weight=1)
        self.build_window_menu()

        main = ttk.Frame(self.root_window, name="main_frame", padding=16)
        main.grid(column=0, row=0, sticky=tk.NSEW)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=1)  # Graph area
        main.rowconfigure(1, weight=0)  # Tool area

        self.canvas_frame = ttk.Frame(main, name="canvas_frame")
        self.canvas_frame.grid(column=0, row=0, sticky=tk.NSEW)
        self.canvas_frame.columnconfigure(0, weight=1)
        self.canvas_frame.rowconfigure(0, weight=1)
        plot_figure = mpl_figure.Figure(figsize=figure_aspect, dpi=figure_dpi)
        self.canvas_figure = ttkbootstrap_matplotlib.create_styled_plot_canvas(plot_figure, self.canvas_frame)
        plot_figure.subplots_adjust(
            left=0.10,  # Leave room on left and bottom for axis labels
            bottom=0.10,
            right=0.98,
            top=0.98,
        )

        self.plot_axes = plot_figure.add_subplot()

        toolbar_row = ttk.Frame(main, name="toolbar_row")
        toolbar_row.grid(column=0, row=1, sticky=tk.NSEW, padx=40, pady=(8, 0))
        toolbar_row.columnconfigure(0, weight=1)  # Action panel
        toolbar_row.columnconfigure(1, weight=0)  # Graph toolbar

        action_panel = ttk.Frame(toolbar_row, name="action_panel")
        action_panel.grid(column=0, row=0, sticky=tk.EW, padx=(0, 8))
        action_panel.columnconfigure(0, weight=0)  # Button one
        action_panel.columnconfigure(1, weight=0)  # Button two
        action_panel.columnconfigure(2, weight=1)  # Spacer
        action_panel.columnconfigure(3, weight=0)  # Button three
        action_panel.columnconfigure(4, weight=0)  # Button four
        action_panel.rowconfigure(0, weight=0)  # Buttons
        action_panel.rowconfigure(1, weight=0)  # Message

        self.reload_button = self.create_icon_button(
            action_panel, text=DataViewer.CommandName.Reload, icon_name="rotate-left", char_width=12
        )
        self.reload_button.configure(command=functools.partial(self.reload_file, self.reload_button))
        self.reload_button.grid(column=0, row=0, padx=(0, 8))

        self.replay_button = self.create_icon_button(
            action_panel, text=DataViewer.CommandName.Replay, icon_name="clock-rotate-left", char_width=12
        )
        self.replay_button.configure(command=functools.partial(self.replay_data, self.replay_button))
        self.replay_button.grid(column=1, row=0, padx=8)

        self.export_csv_button = self.create_icon_button(
            action_panel, text=DataViewer.CommandName.Export, icon_name="table", char_width=12
        )
        self.export_csv_button.grid(column=4, row=0, padx=(8, 0))
        self.export_csv_button.configure(command=functools.partial(self.export_canvas, self.export_csv_button))

        self.file_message = ttk.Label(action_panel)
        self.file_message.grid(row=1, columnspan=5, sticky=tk.W, pady=(8, 0))

        toolbar_frame = ttkbootstrap_matplotlib.create_styled_plot_toolbar(toolbar_row, self.canvas_figure)
        toolbar_frame.grid(column=1, row=0, sticky=(tk.EW, tk.N), padx=(8, 0))  # pyright: ignore reportArgumentType -- the type hint for library uses strings

        self.canvas_cover = ttk.Frame(main, name="canvas_cover", style=bootstyle.LIGHT)
        self.canvas_cover.grid(column=0, row=0, sticky=tk.NSEW)
        self.canvas_cover.columnconfigure(0, weight=1)
        self.canvas_cover.rowconfigure(0, weight=1)  # Name label
        self.canvas_cover.rowconfigure(1, weight=0)  # Button one
        self.canvas_cover.rowconfigure(2, weight=1)  # Button two

        self.startup_label = ttk.Label(
            self.canvas_cover, font=font.Font(weight="bold", size=24), text=DataViewer.app_name
        )
        self.startup_label.grid(column=0, row=0, pady=16)

        open_file_button = self.create_icon_button(
            self.canvas_cover,
            text=DataViewer.CommandName.OpenCSV,
            icon_name="file-csv",
            spaces=2,
            bootstyle=bootstyle.INFO,
        )
        open_file_button.grid(column=0, row=1, sticky=tk.S, pady=(0, 16))
        open_file_button.configure(command=functools.partial(self.open_file, open_file_button))

        demo_button = self.create_icon_button(
            self.canvas_cover,
            text=DataViewer.CommandName.Demo,
            icon_name="chart-line",
            spaces=4,
            bootstyle=bootstyle.INFO,
        )
        demo_button.grid(column=0, row=2, sticky=tk.N, pady=(0, 16))
        demo_button.configure(command=functools.partial(self.open_demo, demo_button))

        self.root_window.bind(AppState.Event.DataFileChanged, self.on_data_file_changed)
        self.root_window.bind(AppState.Event.ReplayActiveChanged, self.on_replay_active_changed)
        guikit.ThemeChanger.add_handler(self.root_window, self.on_theme_changed)

        self.reload_file(sender=main)

        # matplotlib elements must be created before setting the theme or the button icons initialize with poor color contrast
        self.state.active_theme = "flatly"

    def build_window_menu(self) -> None:
        """Create the entries for the window menu bar."""
        self.menubar = tk.Menu(
            self.root_window,
            # No styling support here -- Windows Settings for Light vs Dark mode control the menubar
        )
        self.root_window.config(menu=self.menubar)

        # File menu
        self.file_menu = tk.Menu(self.menubar, name="file_menu")
        self.menubar.add_cascade(
            label=DataViewer.CommandName.File,
            menu=self.file_menu,
            underline=0,
        )
        self.file_menu.add_command(
            command=functools.partial(self.open_file, self.file_menu),
            label=f"{DataViewer.CommandName.Open}...",
            accelerator="Ctrl-O",
            # Styling is supported here, but the bounding frame surrounding the menu entries follows Windows System settings
        )
        self.root_window.bind("<Control-o>", lambda e: self.open_file(self.file_menu))
        self.file_menu.add_command(
            command=functools.partial(self.reload_file, self.file_menu),
            label=DataViewer.CommandName.Reload,
            accelerator="F5",
        )
        self.root_window.bind("<F5>", lambda e: self.reload_file(self.file_menu))
        self.file_menu.add_checkbutton(
            command=functools.partial(self.replay_data, self.file_menu),
            label=DataViewer.CommandName.Replay,
            variable=self.replay_variable,
        )
        self.file_menu.add_command(
            command=functools.partial(self.export_canvas, self.file_menu),
            label=f"{DataViewer.CommandName.Export}...",
        )
        self.file_menu.add_command(
            command=functools.partial(self.close_file, self.file_menu),
            label=DataViewer.CommandName.Close,
            accelerator="Ctrl-W",
        )
        self.root_window.bind("<Control-w>", lambda e: self.close_file(self.file_menu))
        self.file_menu.add_separator()
        self.file_menu.add_command(
            command=self.exit,
            label=DataViewer.CommandName.Exit,
            accelerator="Alt-F4",
        )
        self.root_window.bind("<Alt-F4>", lambda e: self.exit())

        # View menu
        self.view_menu = tk.Menu(self.menubar, name="view_menu")
        self.menubar.add_cascade(
            label=DataViewer.CommandName.View,
            menu=self.view_menu,
            underline=0,
        )
        # Plots submenu
        self.plots_menu = tk.Menu(self.view_menu, name="plots_menu")
        self.view_menu.add_cascade(
            label=DataViewer.CommandName.Plots,
            menu=self.plots_menu,
            underline=0,
        )
        # Themes submenu
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
            label=DataViewer.CommandName.Theme,
            menu=self.themes_menu,
            underline=0,
        )
        self.light_menu = tk.Menu(self.themes_menu, name="light_themes_menu")
        self.themes_menu.add_cascade(
            label=DataViewer.CommandName.Light,
            menu=self.light_menu,
            underline=0,
        )
        self.dark_menu = tk.Menu(self.themes_menu, name="dark_themes_menu")
        self.themes_menu.add_cascade(
            label=DataViewer.CommandName.Dark,
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
            label=DataViewer.CommandName.Help,
            menu=self.help_menu,
            underline=0,
        )
        self.help_menu.add_command(
            command=self.show_about,
            label=DataViewer.CommandName.About,
            accelerator="F1",
        )
        self.root_window.bind("<F1>", lambda e: self.show_about())

    def create_icon_button(  # noqa PLR0913 -- allow many parameters for a factory method
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
        button_image = icon_to_image(icon_name, fill=guikit.hex_string_for_style(StyleKey.SelectFg), scale_to_height=24)
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

        plot_lines = self.plot_axes.lines
        times = time_coordinates[:draw_to]
        for index, (_, series) in enumerate(data_series.items()):
            measurements = series.tolist()[:draw_to]
            plot = plot_lines[index]
            plot.set_xdata(times)
            plot.set_ydata(measurements)
        self.canvas_figure.draw()
        self.update_file_message(f"Time: {times[-1]:.3f}")

    def open_demo(self, sender: tk.Widget) -> None:
        """Handle the Demo button command."""
        channel_count = 8
        trend_function = random.choice([math.log10, math.cbrt])  # noqa: S311 -- no cryptography happening here
        column_titles = ["time (s)"]
        column_titles.extend([f"v{N + 1}" for N in range(channel_count)])
        channels = list(range(1, len(column_titles)))
        random.shuffle(channels)
        data_samples = []
        for sample_number in range(101):
            scan = []
            timestamp = sample_number * 10
            scan.append(float(timestamp))
            for channel in channels:
                noise = random.random()  # noqa: S311 -- no cryptography happening here
                channel_sample = channel * trend_function(timestamp + 50) - 0.2 * noise
                scan.append(channel_sample)
            data_samples.append(scan)
        with self.state.demo_folder.joinpath("Data Viewer Demo.csv").open(
            encoding="UTF-8", mode="w", newline=""
        ) as demo_file:
            data_frame = pd.DataFrame(data_samples, columns=column_titles)  # pyright: ignore reportArgumentType
            data_frame.to_csv(demo_file, index=False)
        self.state.data_file = pathlib.Path(demo_file.name)

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

    def reload_file(self, sender: tk.Widget) -> None:
        """Handle the File::Reload menu command."""
        self.on_data_file_changed(tk.Event())

    def replay_data(self, sender: tk.Widget) -> None:
        """Handle the View::Replay menu or button command."""
        current_replay = self.state.replay_active
        new_replay = not current_replay
        self.state.replay_active = new_replay

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

        lower_bound, upper_bound = self.plot_axes.get_xbound()
        time_coordinates, full_data_set = self.get_data()
        time_series = pd.Series(time_coordinates)
        above_limit = time_series >= lower_bound
        below_limit = time_series <= upper_bound
        time_values = time_series[above_limit & below_limit]
        visible_series = [v.get() for v in self.plots_variables]

        data_to_export = full_data_set.loc[time_values.index, visible_series]  # pyright: ignore reportAttributeAccessIssue
        data_to_export = data_to_export.set_index(time_values.values)  # pyright: ignore reportAttributeAccessIssue
        data_to_export.index.name = "time"
        data_to_export.to_csv(file_path)

    def close_file(self, sender: tk.Widget) -> None:
        """Handle the File::Close menu command."""
        self.state.data_file = AppState.no_file

    def set_all_plots_visibility(self, new_visibility: bool) -> None:
        """Show or hide all plots according to new_visibility."""
        for line in self.plot_axes.lines:
            line.set_visible(new_visibility)
        self.canvas_figure.draw()
        for variable in self.plots_variables:
            variable.set(new_visibility)

    def toggle_plot(self, index: int) -> None:
        """Toggle the visibility of the plot at the specified index."""
        menu_variable = self.plots_variables[index]
        new_visibility = menu_variable.get()
        self.plot_axes.lines[index].set_visible(new_visibility)
        self.canvas_figure.draw()

    def change_theme(self, theme_name: str) -> None:
        """Handle the View::Theme selection command."""
        self.state.active_theme = theme_name

    def show_about(self) -> None:
        """Handle the Help::About menu command."""
        about_dialog = AboutDialog(parent=self.root_window, title=f"About {DataViewer.app_name}")
        about_dialog.show()

    def on_data_file_changed(self, event_args: tk.Event) -> None:
        """Handle the DataFileChanged event."""
        self.plot_axes.clear()
        self.state.replay_active = False
        self.replay_index = 0
        if self.state.data_file == AppState.no_file:
            new_enabled_state = tk.DISABLED
            new_window_title = DataViewer.app_name
            plots_entries = ["(none)"]
            self.canvas_cover.grid(column=0, row=0, sticky=tk.NSEW)
            self.update_file_message("Waiting for file")
        else:
            new_enabled_state = tk.NORMAL
            new_window_title = f"{self.state.data_file.name} - {DataViewer.app_name}"
            self.state.load_data_file()
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
            self.file_menu: [
                DataViewer.CommandName.Reload,
                DataViewer.CommandName.Replay,
                f"{DataViewer.CommandName.Export}...",
                DataViewer.CommandName.Close,
            ],
        }
        for owner, entries in menu_entries.items():
            for entry in entries:
                owner.entryconfigure(entry, state=new_enabled_state)
        self.plots_menu.delete(0, tk.END)
        self.plots_variables.clear()
        self.plots_menu.add_command(
            label=DataViewer.CommandName.HideAll,
            command=functools.partial(self.set_all_plots_visibility, new_visibility=False),
        )
        self.plots_menu.add_command(
            label=DataViewer.CommandName.ShowAll,
            command=functools.partial(self.set_all_plots_visibility, new_visibility=True),
        )
        self.plots_menu.add_separator()
        for plot_index, entry in enumerate(plots_entries):
            toggle_variable = tk.BooleanVar(self.plots_menu)
            self.plots_menu.add_checkbutton(
                label=entry,
                state=new_enabled_state,
                command=functools.partial(self.toggle_plot, plot_index),
                variable=toggle_variable,
            )
            self.plots_variables.append(toggle_variable)
            if self.state.data_file != AppState.no_file:
                toggle_variable.set(True)
        self.style_menu(self.plots_menu)
        self.update_window_title(new_window_title)

    def on_replay_active_changed(self, event_args: tk.Event) -> None:
        """Handle the ReplayActiveChanged event."""
        replay_active = self.state.replay_active
        new_style = bootstyle.SUCCESS if replay_active else bootstyle.DEFAULT
        self.replay_button.configure(bootstyle=new_style)  # pyright: ignore reportArgumentType -- the type hint for library uses strings
        self.replay_variable.set(replay_active)

    def on_theme_changed(self, event_args: tk.Event) -> None:
        """Handle the ThemeChanged event."""
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
        for menu in all_menus:
            self.style_menu(menu)

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

    def update_window_title(self, new_title: str) -> None:
        """Update the application's window title."""
        self.root_window.title(new_title)

    def update_file_message(self, new_message: str) -> None:
        """Replace the file information text with new_message."""
        self.file_message.configure(text=new_message)

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
        requested_theme = ttk_themes.STANDARD_THEMES[self.state.active_theme]
        ttkbootstrap_matplotlib.apply_legend_style(self.plot_axes.get_legend(), requested_theme)
        self.canvas_figure.draw()
        self.update_file_message(f"Duration: {time_coordinates[-1]:.3f}")
        return data_series.keys().to_list()

    def get_data(self) -> tuple[list[float], pd.DataFrame]:
        """Get the time coordinates and measurement series from the data file."""
        # Assume table format, with time in first column and data in subsequent columns
        data_file_df = self.state.get_data()
        time_index = data_file_df[data_file_df.columns[0]]
        time_coordinates = time_index.to_list()
        series_names = data_file_df.columns[1:]
        measurement_series = data_file_df[series_names]
        return time_coordinates, measurement_series  # pyright: ignore reportReturnType


if __name__ == "__main__":
    logger.debug(f"Launching {__package__}")
    asyncio.run(guikit.AsyncApp.create_and_run(DataViewer))
