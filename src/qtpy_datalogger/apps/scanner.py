"""An app that scans for QT Py sensor_nodes."""

import asyncio
import logging
import pathlib
import tkinter as tk
from tkinter import font

import ttkbootstrap as ttk
import ttkbootstrap.icons as ttk_icons
import ttkbootstrap.tableview as ttk_tableview
from ttkbootstrap import constants as bootstyle

from qtpy_datalogger import guikit

logger = logging.getLogger(pathlib.Path(__file__).stem)


class ScannerApp(guikit.AsyncWindow):
    """A GUI for discovering and communicating with QT Py sensor nodes."""

    def create_user_interface(self) -> None:
        """Create the main window and connect event handlers."""
        # Theme
        style = ttk.Style()
        bootstyle_background = bootstyle.LIGHT
        background = style.colors.get(bootstyle_background)
        style.configure("TFrame", background=background)

        # Window properties
        app_name = "QT Py Sensor Node Scanner"
        self.root_window.minsize(width=600, height=800)
        self.root_window.place_window_center()
        self.root_window.title(app_name)
        self.root = ttk.Frame(self.root_window, name="root_frame", padding=16)
        icon = tk.PhotoImage(master=self.root_window, data=ttk_icons.Icon.question)
        self.root_window.iconphoto(True, icon)

        # Title
        icon_emoji = ttk_icons.Emoji.get("telescope")
        title_font = font.Font(weight="bold", size=24)
        title_label = ttk.Label(self.root, font=title_font, text=f"{icon_emoji} {app_name}", padding=16, background=background)
        title_label.pack()

        # Scan group
        scan_frame = ttk.Frame(self.root, name="scan_frame", padding=8)
        group_input_label = ttk.Label(scan_frame, text="Group name", background=background)
        self.group_input = ttk.Entry(scan_frame)
        scan_button = ttk.Button(scan_frame, command=self.start_scan, text="Scan group")
        group_input_label.pack(side=tk.LEFT)
        self.group_input.pack(expand=True, fill=tk.X, side=tk.LEFT, padx=8)
        scan_button.pack(side=tk.LEFT)
        scan_frame.pack(expand=True, fill=tk.X)

        # Results group
        results_frame = ttk.Frame(self.root, name="result_frame", padding=8)
        self.result_menu = ttk.Menu(self.root)
        self.result_menu.add_radiobutton(label="(none)", value=-1)
        scan_results_table = ttk_tableview.Tableview(results_frame, coldata=[], rowdata=[])
        scan_results_table.pack(expand=True, fill=tk.X)
        results_frame.pack(expand=True, fill=tk.X, pady=(8, 0))

        # Node communication
        comms_frame = ttk.Frame(self.root, name="comms_frame", padding=8)
        selected_node_combobox = ttk.Combobox(comms_frame, values=["(none)"], width=20, state="readonly")
        selected_node_combobox.current(0)
        selected_node_combobox.pack(side=tk.TOP, anchor=tk.W)

        message_frame = ttk.Frame(comms_frame, name="message_frame")
        self.message_input = ttk.Entry(message_frame)
        send_message_button = ttk.Button(message_frame, command=self.send_message, text="Send message")
        self.message_input.pack(side=tk.LEFT, expand=True, fill=tk.X)
        send_message_button.pack(side=tk.LEFT, padx=(8, 0))
        message_frame.pack(side=tk.TOP, pady=(8, 0), expand=True, fill=tk.X)

        message_log = ttk.ScrolledText(comms_frame, state="disabled")
        message_log.pack(side=tk.TOP, pady=(8, 0), expand=True, fill=tk.X)
        comms_frame.pack(expand=True, fill=tk.X, pady=(8, 0))

        # App commands and status
        exit_button = ttk.Button(self.root, text="Quit", style=bootstyle.DANGER, command=self.exit)
        help_button = ttk.Button(self.root, text="Online help", style=bootstyle.OUTLINE, command=self.launch_help)
        self.status_message = ttk.Label(self.root, text="OK", style=bootstyle.SUCCESS, background=background)
        exit_button.pack(side=tk.RIGHT, padx=8, pady=(8, 0))
        help_button.pack(side=tk.RIGHT, padx=(8, 0), pady=(8, 0))
        self.status_message.pack(side=tk.RIGHT, padx=8, pady=(8, 0))

        # Finalize layout
        self.root.pack(expand=True, fill=tk.BOTH)

    async def on_loop(self) -> None:
        """Update the UI with new information."""
        await asyncio.sleep(0.01)

    def on_closing(self) -> None:
        """Clean up before exiting."""

    def start_scan(self) -> None:
        """Start a scan for QT Py sensor_nodes in the group specified by the user."""

    def send_message(self) -> None:
        """Send the message text to the node specified by the user."""

    def launch_help(self) -> None:
        """Open online help for the app."""


if __name__ == "__main__":
    logger.debug(f"Launching {__package__}")
    asyncio.run(guikit.AsyncApp.create_and_run(ScannerApp))
