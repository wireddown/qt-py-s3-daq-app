"""Plot data from CSV files."""

import asyncio
import functools
import logging
import math
import pathlib
import tkinter as tk
from enum import StrEnum
from tkinter import filedialog, font

import matplotlib.figure as mpl_figure
import ttkbootstrap as ttk
import ttkbootstrap.themes.standard as ttk_themes
from ttkbootstrap import constants as bootstyle

from qtpy_datalogger import guikit, ttkbootstrap_matplotlib
from qtpy_datalogger.vendor.tkfontawesome import icon_to_image

logger = logging.getLogger(pathlib.Path(__file__).stem)


class AppState:
    """A class that models and controls the app's settings and runtime state."""

    no_file: pathlib.Path = pathlib.Path(__file__)
    canceled_file: pathlib.Path = pathlib.Path()
    demo_file = None

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


class DataViewer(guikit.AsyncWindow):
    """A GUI that loads a CSV data file and plots the columns."""

    class MenuName(StrEnum):
        """Names used for entries in the app's menus."""

        File = "File"
        Open = "Open"
        Reload= "Reload"
        Replay = "Replay"
        Close = "Close"
        Exit = "Exit"
        Edit = "Edit"
        Copy = "Copy"
        Export = "Export"
        View = "View"
        Plots = "Plots"
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
        self.state = AppState(self.root_window)
        self.state.active_theme = "vapor"

        self.svg_images: dict[str, tk.Image] = {}

        self.update_window_title(DataViewer.app_name)
        ##self.root_window.minsize(width=870, height=600)
        self.root_window.columnconfigure(0, weight=1)
        self.root_window.rowconfigure(0, weight=1)
        self.build_window_menu()

        main = ttk.Frame(self.root_window, name="main_frame", padding=16)
        main.grid(column=0, row=0, sticky=tk.NSEW)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=1)
        main.rowconfigure(1, weight=0)

        self.canvas_placeholder = ttk.Frame(main, name="canvas_placeholder", height=200, width=300, style=bootstyle.INFO)
        self.canvas_placeholder.grid(column=0, row=0, sticky=tk.NSEW)
        self.canvas_placeholder.columnconfigure(0, weight=1)
        self.canvas_placeholder.rowconfigure(0, weight=1)
        self.canvas_placeholder.rowconfigure(1, weight=0)
        self.canvas_placeholder.rowconfigure(2, weight=1)

        self.canvas_frame = ttk.Frame(main, name="canvas_frame")
        self.canvas_frame.grid(column=0, row=0, sticky=tk.NSEW)
        self.canvas_frame.columnconfigure(0, weight=1)
        self.canvas_frame.rowconfigure(0, weight=1)
        figure_aspect = (4, 3)
        figure_dpi = 100
        self.plot_figure = mpl_figure.Figure(figsize=figure_aspect, dpi=figure_dpi)
        self.canvas_figure = ttkbootstrap_matplotlib.create_styled_plot_canvas(self.plot_figure, self.canvas_frame)

        self.plot_axes = self.plot_figure.add_subplot()
        self.plot_axes.set_xlabel("time")
        self.plot_axes.set_ylabel("y")
        self.plot_axes.grid(
            visible=True,
            which="major",
            axis="y",
            dashes=(3, 8),
            zorder=-1,
        )

        startup_label = ttk.Label(self.canvas_placeholder, font=font.Font(weight="bold", size=16), text="QT Py Data Viewer", background=guikit.hex_string_for_style(bootstyle.INFO))
        startup_label.grid(column=0, row=0, pady=16)
        open_file_button = self.create_icon_button(self.canvas_placeholder, text="Open CSV", icon_name="file-csv", spaces=2)
        open_file_button.grid(column=0, row=1, sticky=tk.S, pady=(0, 16))
        open_file_button.configure(command=functools.partial(self.open_file, open_file_button))
        demo_button = self.create_icon_button(self.canvas_placeholder, text="Demo", icon_name="chart-line", spaces=4)
        demo_button.grid(column=0, row=2, sticky=tk.N, pady=(0, 16))
        demo_button.configure(command=functools.partial(self.open_demo, demo_button))

        toolbar_row = ttk.Frame(main, name="toolbar_row", style=bootstyle.WARNING)
        toolbar_row.grid(column=0, row=1, sticky=tk.NSEW, pady=(8, 0))
        toolbar_row.columnconfigure(0, weight=1)
        toolbar_row.columnconfigure(1, weight=0)

        action_panel = ttk.Frame(toolbar_row, name="action_panel", height=50, width=200, style=bootstyle.SUCCESS)
        action_panel.grid(column=0, row=0, sticky=tk.EW, padx=(0, 8))
        action_panel.columnconfigure(0, weight=0)
        action_panel.columnconfigure(1, weight=0)
        action_panel.columnconfigure(2, weight=1)
        action_panel.columnconfigure(3, weight=0)
        action_panel.columnconfigure(4, weight=0)
        action_panel.rowconfigure(0, weight=0)
        action_panel.rowconfigure(1, weight=0)

        self.copy_view_button = self.create_icon_button(action_panel, text="Copy view", icon_name="image", char_width=16)
        self.copy_view_button.grid(column=3, row=0, padx=8)
        self.copy_view_button.configure(command=functools.partial(self.copy_canvas, self.copy_view_button))
        self.export_csv_button = self.create_icon_button(action_panel, text="Export", icon_name="table", char_width=12)
        self.export_csv_button.grid(column=4, row=0, padx=8)
        self.export_csv_button.configure(command=functools.partial(self.export_canvas, self.export_csv_button))

        self.reload_button = self.create_icon_button(action_panel, text="Reload", icon_name="rotate-left", char_width=12)
        self.reload_button.configure(command=functools.partial(self.reload_file, self.reload_button))
        self.reload_button.grid(column=0, row=0, padx=(0, 8))
        self.replay_button = self.create_icon_button(action_panel, text="Replay", icon_name="clock-rotate-left", char_width=12)
        self.replay_button.configure(command=functools.partial(self.replay_data, self.replay_button))
        self.replay_button.grid(column=1, row=0, padx=8)

        self.file_message = ttk.Label(action_panel, text="Waiting for load", background=guikit.hex_string_for_style(bootstyle.SUCCESS))
        self.file_message.grid(row=1, columnspan=5, pady=(8, 0))

        toolbar = ttk.Frame(toolbar_row, name="toolbar", height=50, width=300, style=bootstyle.SECONDARY)
        toolbar.grid(column=1, row=0, sticky=tk.N)

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

        self.on_data_file_changed(event_args=None)

    def create_icon_button(
            self,
            parent: tk.Widget,
            text: str,
            icon_name: str,
            char_width: int = 15,
            spaces: int = 2
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
            padding=(4, 6, 4, 4)
        )
        return button

    def on_show(self) -> None:
        """Initialize UI before entering main loop."""

    async def on_loop(self) -> None:
        """Update the UI with new information."""
        await asyncio.sleep(1e-6)

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
            label="File",
            menu=self.file_menu,
            underline=0,
        )
        self.file_menu.add_command(
            command=functools.partial(self.open_file, self.file_menu),
            label="Open",
            accelerator="Ctrl-O",
            # Styling is supported here, but the bounding frame surrounding the menu entries follows Windows System settings
        )
        self.file_menu.add_command(
            command=functools.partial(self.reload_file, self.file_menu),
            label="Reload",
            accelerator="F5",
        )
        self.file_menu.add_checkbutton(
            command=functools.partial(self.replay_data, self.file_menu),
            label="Replay",
            variable=self.replay_variable,
        )
        self.file_menu.add_command(
            command=functools.partial(self.close_file, self.file_menu),
            label="Close",
            accelerator="Ctrl-W",
            # Styling is supported here, but the bounding frame surrounding the menu entries follows Windows System settings
        )
        self.file_menu.add_separator(
            # Styling is supported here, but the bounding frame surrounding the menu entries follows Windows System settings
        )
        self.file_menu.add_command(
            command=self.exit,
            label="Exit",
            accelerator="Alt-F4"
        )

        # Edit menu
        self.edit_menu = tk.Menu(self.menubar, name="edit_menu")
        self.menubar.add_cascade(
            label="Edit",
            menu=self.edit_menu,
            underline=0,
        )
        self.edit_menu.add_command(
            command=functools.partial(self.copy_canvas, self.edit_menu),
            label="Copy",
            accelerator="Ctrl-C",
        )
        self.edit_menu.add_command(
            command=functools.partial(self.export_canvas, self.edit_menu),
            label="Export",
        )

        # View menu
        self.view_menu = tk.Menu(self.menubar, name="view_menu")
        self.menubar.add_cascade(
            label="View",
            menu=self.view_menu,
            underline=0,
        )
        # Plots submenu
        self.plots_menu = tk.Menu(self.view_menu, name="plots_menu")
        self.view_menu.add_cascade(
            label="Plots",
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
            label="Theme",
            menu=self.themes_menu,
            underline=0,
        )
        self.light_menu = tk.Menu(self.themes_menu, name="light_themes_menu")
        self.themes_menu.add_cascade(
            label="Light",
            menu=self.light_menu,
            underline=0,
        )
        self.dark_menu = tk.Menu(self.themes_menu, name="dark_themes_menu")
        self.themes_menu.add_cascade(
            label="Dark",
            menu=self.dark_menu,
            underline=0,
        )
        for theme_name in sorted(light_themes):
            self.light_menu.add_radiobutton(
                command=functools.partial(self.change_theme, theme_name),
                label=theme_name,
                variable=self.theme_variable,
            )
        for theme_name in sorted(dark_themes):
            self.dark_menu.add_radiobutton(
                command=functools.partial(self.change_theme, theme_name),
                label=theme_name,
                variable=self.theme_variable,
            )

        # Help menu
        self.help_menu = tk.Menu(self.menubar, name="help_menu")
        self.menubar.add_cascade(
            label="Help",
            menu=self.help_menu,
            underline=0,
        )
        self.help_menu.add_command(
            command=self.show_about,
            label="About",
            accelerator="F1",
        )

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

    def reload_file(self, sender: tk.Widget) -> None:
        """Handle the File::Reload menu command."""

    def close_file(self, sender: tk.Widget) -> None:
        """Handle the File::Close menu command."""
        self.state.data_file = AppState.no_file

    def copy_canvas(self, sender: tk.Widget) -> None:
        """Handle the Edit::Copy menu command."""

    def export_canvas(self, sender: tk.Widget) -> None:
        """Handle the Export CSV button command."""

    def on_data_file_changed(self, event_args: tk.Event) -> None:
        """Handle the File::Open menu or button command."""
        if self.state.data_file == AppState.no_file:
            new_enabled_state = tk.DISABLED
            new_window_title = DataViewer.app_name
            plots_entries = ["(none)"]
            presented_frame = self.canvas_placeholder
            hidden_frame = self.canvas_frame
        else:
            new_enabled_state =  tk.NORMAL
            new_window_title = f"{self.state.data_file.name} - {DataViewer.app_name}"
            presented_frame = self.canvas_frame
            hidden_frame = self.canvas_placeholder
            self.update_plot_axes()
            self.canvas_figure.draw()
            plots_entries = ["(unknown)"]
        button_list = [
            self.reload_button,
            self.replay_button,
            self.copy_view_button,
            self.export_csv_button,
        ]
        for button in button_list:
            button.configure(state=new_enabled_state)
        menu_entries = {
            self.file_menu: [DataViewer.MenuName.Reload, DataViewer.MenuName.Replay, DataViewer.MenuName.Close],
            self.edit_menu: [DataViewer.MenuName.Copy, DataViewer.MenuName.Export],
        }
        for owner, entries in menu_entries.items():
            for entry in entries:
                owner.entryconfigure(entry, state=new_enabled_state)
        hidden_frame.grid_remove()
        presented_frame.grid()
        self.plots_menu.delete(0, "end")
        for entry in plots_entries:
            self.plots_menu.add_command(label=entry, state=new_enabled_state)
        self.update_window_title(new_window_title)

    def replay_data(self, sender: tk.Widget) -> None:
        """Handle the View::Replay menu or button command."""
        current_replay = self.state.replay_active
        self.state.replay_active = not current_replay

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
        self.theme_variable.set(theme_name)

    def show_about(self) -> None:
        """Handle the Help::About menu command."""

    def update_plot_axes(self) -> None:
        """Reconfigure the plot for the new data."""
        time_coordinates = range(0, 1200, 1)
        y1_coordinates = [1000 * math.sin(2 * math.pi * t * 1) for t in time_coordinates]
        self.plot_axes.clear()
        (self.line,) = self.plot_axes.plot(
            time_coordinates,
            y1_coordinates,
            label="Demo",
        )
        self.plot_axes.legend(
            title="Function",
            loc="upper left",
            draggable=True,
        )


if __name__ == "__main__":
    logger.debug(f"Launching {__package__}")
    asyncio.run(guikit.AsyncApp.create_and_run(DataViewer))
