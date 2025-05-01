"""Plot data from CSV files."""

import asyncio
import functools
import logging
import pathlib
import tkinter as tk
from tkinter import font

import ttkbootstrap as ttk
import ttkbootstrap.themes.standard as ttk_themes
from ttkbootstrap import constants as bootstyle

from qtpy_datalogger import guikit
from qtpy_datalogger.vendor.tkfontawesome import icon_to_image

logger = logging.getLogger(pathlib.Path(__file__).stem)


class DataViewer(guikit.AsyncWindow):
    """A GUI that loads a CSV data file and plots the columns."""

    def create_user_interface(self) -> None:
        """Create the main window and connect event handlers."""
        ttk.Style().theme_use("cosmo")

        self.svg_images: dict[str, tk.Image] = {}

        self.update_window_title("QT Py Data Viewer")
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

        copy_view_button = self.create_icon_button(action_panel, text="Copy view", icon_name="image", char_width=16)
        copy_view_button.grid(column=3, row=0, padx=8)
        copy_view_button.configure(command=functools.partial(self.copy_canvas, copy_view_button))
        export_csv_button = self.create_icon_button(action_panel, text="Export", icon_name="table", char_width=12)
        export_csv_button.grid(column=4, row=0, padx=8)
        export_csv_button.configure(command=functools.partial(self.export_canvas, export_csv_button))

        reload_button = self.create_icon_button(action_panel, text="Reload", icon_name="rotate-left", char_width=12)
        reload_button.configure(command=functools.partial(self.reload_file, reload_button))
        reload_button.grid(column=0, row=0, padx=(0, 8))
        replay_button = self.create_icon_button(action_panel, text="Replay", icon_name="clock-rotate-left", char_width=12)
        replay_button.configure(command=functools.partial(self.replay_data, replay_button))
        replay_button.grid(column=1, row=0, padx=8)

        file_message = ttk.Label(action_panel, text="Waiting for load", background=guikit.hex_string_for_style(bootstyle.SUCCESS))
        file_message.grid(row=1, columnspan=5, pady=(8, 0))

        toolbar = ttk.Frame(toolbar_row, name="toolbar", height=50, width=300, style=bootstyle.SECONDARY)
        toolbar.grid(column=1, row=0, sticky=tk.N)

    def create_icon_button(
            self,
            parent: tk.Widget,
            text: str,
            icon_name: str,
            char_width: int = 15,
            spaces: int = 2
        ) -> ttk.Button:
        """Create a ttk.Button using the specified icon_name an text."""
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
        file_menu = tk.Menu(self.menubar, postcommand=self.on_file_menu)
        self.menubar.add_cascade(
            label="File",
            menu=file_menu,
            underline=0,
        )
        file_menu.add_command(
            command=functools.partial(self.open_file, file_menu),
            label="Open",
            accelerator="Ctrl-O",
            # Styling is supported here, but the bounding frame surrounding the menu entries follows Windows System settings
        )
        file_menu.add_command(
            command=functools.partial(self.reload_file, file_menu),
            label="Reload",
            accelerator="F5",
        )
        file_menu.add_checkbutton(
            command=functools.partial(self.replay_data, file_menu),
            label="Replay",
        )
        file_menu.add_command(
            command=functools.partial(self.close_file, file_menu),
            label="Close",
            accelerator="Ctrl-W",
            # Styling is supported here, but the bounding frame surrounding the menu entries follows Windows System settings
        )
        file_menu.add_separator(
            # Styling is supported here, but the bounding frame surrounding the menu entries follows Windows System settings
        )
        file_menu.add_command(
            command=self.exit,
            label="Exit",
            accelerator="Alt-F4"
        )

        # Edit menu
        edit_menu = tk.Menu(self.menubar)
        self.menubar.add_cascade(
            label="Edit",
            menu=edit_menu,
            underline=0,
        )
        edit_menu.add_command(
            command=functools.partial(self.copy_canvas, edit_menu),
            label="Copy",
            accelerator="Ctrl-C",
        )
        edit_menu.add_command(
            command=functools.partial(self.export_canvas, edit_menu),
            label="Export",
        )

        # View menu
        view_menu = tk.Menu(self.menubar)
        self.menubar.add_cascade(
            label="View",
            menu=view_menu,
            underline=0,
        )
        # Plots submenu
        plots_menu = tk.Menu(view_menu)
        view_menu.add_cascade(
            label="Plots",
            menu=plots_menu,
            underline=0,
        )
        plots_menu.add_command(
            label="(none)",
            state="disabled",
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
        themes_menu = tk.Menu(view_menu)
        view_menu.add_cascade(
            label="Theme",
            menu=themes_menu,
            underline=0,
        )
        light_menu = tk.Menu(themes_menu)
        themes_menu.add_cascade(
            label="Light",
            menu=light_menu,
            underline=0,
        )
        dark_menu = tk.Menu(themes_menu)
        themes_menu.add_cascade(
            label="Dark",
            menu=dark_menu,
            underline=0,
        )
        for theme_name in sorted(light_themes):
            light_menu.add_command(
                command=functools.partial(self.change_theme, theme_name),
                label=theme_name,
            )
        for theme_name in sorted(dark_themes):
            dark_menu.add_command(
                command=functools.partial(self.change_theme, theme_name),
                label=theme_name,
            )

        # Help menu
        help_menu = tk.Menu(self.menubar)
        self.menubar.add_cascade(
            label="Help",
            menu=help_menu,
            underline=0,
        )
        help_menu.add_command(
            command=self.show_about,
            label="About",
            accelerator="F1",
        )

    def open_file(self, sender: tk.Widget) -> None:
        """Handle the File::Open menu command."""

    def open_demo(self, sender: tk.Widget) -> None:
        """Handle the Demo button command."""

    def on_file_menu(self) -> None:
        """Handle the File menu opening."""

    def reload_file(self, sender: tk.Widget) -> None:
        """Handle the File::Reload menu command."""

    def close_file(self, sender: tk.Widget) -> None:
        """Handle the File::Close menu command."""

    def copy_canvas(self, sender: tk.Widget) -> None:
        """Handle the Edit::Copy menu command."""

    def export_canvas(self, sender: tk.Widget) -> None:
        """Handle the Export CSV button command."""

    def replay_data(self, sender: tk.Widget) -> None:
        """Handle the View::Replay menu command."""
        if isinstance(sender, ttk.Button):
            style = sender.cget("style")
            new_style = bootstyle.SUCCESS if "success" not in style else bootstyle.DEFAULT
            sender.configure(bootstyle=new_style)
        else:
            x = sender

    def change_theme(self, theme_name: str) -> None:
        """Handle the View::Theme selection command."""
        style = ttk.Style().instance
        if not style:
            raise ValueError()
        style.theme_use(theme_name)

    def show_about(self) -> None:
        """Handle the Help::About menu command."""


if __name__ == "__main__":
    logger.debug(f"Launching {__package__}")
    asyncio.run(guikit.AsyncApp.create_and_run(DataViewer))
