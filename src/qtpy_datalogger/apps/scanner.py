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
from qtpy_datalogger.datatypes import DetailKey

logger = logging.getLogger(pathlib.Path(__file__).stem)


class ScannerApp(guikit.AsyncWindow):
    """A GUI for discovering and communicating with QT Py sensor nodes."""

    def create_user_interface(self) -> None:
        """Create the main window and connect event handlers."""
        self.background_tasks = set()

        # Theme
        style = ttk.Style()
        style.theme_use("sandstone")

        # Window properties
        app_name = "QT Py Sensor Node Scanner"
        self.root_window.minsize(width=560, height=572)
        self.root_window.title(app_name)
        icon = tk.PhotoImage(master=self.root_window, data=ttk_icons.Icon.question)
        self.root_window.iconphoto(True, icon)

        # Title
        self.main = ttk.Frame(self.root_window, name="root_frame", padding=16)
        icon_emoji = ttk_icons.Emoji.get("telescope")
        title_font = font.Font(weight="bold", size=24)
        title_label = ttk.Label(self.main, font=title_font, text=f"{icon_emoji} {app_name}", padding=16, borderwidth=0, relief=tk.SOLID)
        title_label.grid(column=0, row=0)

        # Scan group
        scan_frame = ttk.Frame(self.main, name="scan_frame", borderwidth=0, relief=tk.SOLID)
        group_input_label = ttk.Label(scan_frame, text="Group name")
        self.group_input = ttk.Entry(scan_frame)
        scan_button = ttk.Button(scan_frame, command=self.start_scan, text="Scan group")
        group_input_label.pack(side=tk.LEFT)
        self.group_input.pack(expand=True, fill=tk.X, side=tk.LEFT, padx=8)
        scan_button.pack(side=tk.LEFT)
        scan_frame.grid(column=0, row=1, sticky=(tk.N, tk.E, tk.W), pady=(8, 0))  # pyright: ignore reportArgumentType -- the type hint for library uses strings

        # Results group
        results_frame = ttk.Frame(self.main, name="result_frame", borderwidth=0, relief=tk.SOLID)
        result_columns = [
            {"text": "Group", "stretch": False, "width": 60},
            {"text": "Node ID", "stretch": False, "width": 100},
            {"text": "Device", "stretch": True},
            {"text": "Snsr Version", "stretch": False, "width": 80},
            {"text": "UART Port", "stretch": False, "width": 80},
        ]
        self.scan_results = {}
        self.scan_results_table = ttk_tableview.Tableview(results_frame, coldata=result_columns, height=9)
        self.scan_results_table.view.configure(selectmode=tk.BROWSE)
        self.scan_results_table.view.bind("<<TreeviewSelect>>", self.on_row_selected)
        self.scan_results_table.pack(expand=True, fill=tk.X)
        results_frame.grid(column=0, row=2, sticky=(tk.N, tk.E, tk.W), pady=(8, 0))  # pyright: ignore reportArgumentType -- the type hint for library uses strings

        # Node communication
        comms_frame = ttk.Frame(self.main, name="comms_frame", borderwidth=0, relief=tk.SOLID)
        self.selected_node_combobox = ttk.Combobox(comms_frame, width=20, state="readonly")
        self.selected_node_combobox.bind("<<ComboboxSelected>>", self.on_combobox_selected)
        self.selected_node_combobox.pack(side=tk.TOP, anchor=tk.W)

        message_frame = ttk.Frame(comms_frame, name="message_frame")
        self.message_input = ttk.Entry(message_frame)
        self.send_message_button = ttk.Button(message_frame, command=self.send_message, text="Send message")
        self.message_input.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.send_message_button.pack(side=tk.LEFT, padx=(8, 0))
        message_frame.pack(side=tk.TOP, pady=(8, 0), expand=True, fill=tk.X, anchor=tk.N)

        self.message_log = ttk.ScrolledText(comms_frame, state="disabled", wrap="word")
        self.message_log.pack(side=tk.TOP, expand=True, fill=tk.BOTH)
        comms_frame.grid(column=0, row=3, sticky=(tk.N, tk.E, tk.W), pady=(8, 0))  # pyright: ignore reportArgumentType -- the type hint for library uses strings

        # App commands and status
        action_frame = ttk.Frame(self.main, name="action_frame", borderwidth=0, relief=tk.SOLID)
        exit_button = ttk.Button(action_frame, text="Quit", style=bootstyle.DANGER, command=self.exit)
        help_button = ttk.Button(action_frame, text="Online help", style=bootstyle.OUTLINE, command=self.launch_help)
        self.status_message = ttk.Label(action_frame)
        exit_button.pack(side=tk.RIGHT, padx=(8, 0))
        help_button.pack(side=tk.RIGHT, padx=(8, 0))
        self.status_message.pack(side=tk.RIGHT, padx=8)
        action_frame.grid(column=0, row=5, sticky=(tk.S, tk.E, tk.W), pady=(8, 0))  # pyright: ignore reportArgumentType -- the type hint for library uses strings

        # Finalize layout
        self.main.grid(column=0, row=0, sticky=(tk.N, tk.S, tk.E, tk.W))  # pyright: ignore reportArgumentType -- the type hint for library uses strings
        self.main.columnconfigure(0, weight=1)
        self.main.rowconfigure(0, weight=0)
        self.main.rowconfigure(1, weight=0)
        self.main.rowconfigure(2, weight=1, minsize=190)
        self.main.rowconfigure(3, weight=1, minsize=200)
        self.main.rowconfigure(4, weight=10000)  # Extra strong row so that the results stable remains in place when vertically resizing
        self.main.rowconfigure(5, weight=0)
        self.root_window.columnconfigure(0, weight=1)
        self.root_window.rowconfigure(0, weight=1)

        self.update_scan_results()
        self.update_send_message_button()
        self.update_status_message_and_style("OK", bootstyle.SUCCESS)

    async def on_loop(self) -> None:
        """Update the UI with new information."""
        await asyncio.sleep(0.01)

    def on_closing(self) -> None:
        """Clean up before exiting."""

    # widget.exists( item )
    #   Returns 1 if the specified item is present in the tree, 0 otherwise
    # widget.selection( ?selop , itemList? )
    #   If selop is not specified, returns the list of selected items
    #   selop: set, add, remove, toggle

    def on_row_selected(self, event_args) -> None:
        """Handle the user selecting a row in the results table."""
        selected_index = event_args.widget.selection()[0]
        self.update_status_message_and_style(f"Selected {selected_index}", bootstyle.SUCCESS)

    def on_combobox_selected(self, event_args) -> None:
        """Handle the user selecting a new entry in the Combobox."""
        selected_index = event_args.widget.get()
        self.update_status_message_and_style(f"Selected {selected_index}", bootstyle.SUCCESS)
        self.update_send_message_button()
        self.selected_node_combobox.configure(state="readonly")
        self.selected_node_combobox.selection_clear()

    def update_status_message_and_style(self, new_message: str, new_style: str) -> None:
        """Set the status message to a new string and style."""
        self.status_message.configure(text=new_message, bootstyle=new_style)  # pyright: ignore callIssue -- the type hint for bootstrap omits its own additions

    def update_scan_results(self) -> None:
        """Add or update discovered sensor_nodes in the scan results table."""
        rows = [
            (
                "group-a",
                node_info[DetailKey.node_id],
                node_info[DetailKey.device_description],
                node_info[DetailKey.snsr_version],
                "(unknown)",
            )
            for _, node_info in self.scan_results.items()
        ]
        self.scan_results_table.insert_rows("end", rows)
        self.scan_results_table.load_table_data()
        self.update_selected_node_combobox()

    def update_selected_node_combobox(self) -> None:
        """Enable or disable the combobox and update its choices depending on the app's state."""
        none_choice = ("(none)",)
        if self.scan_results:
            node_ids = [entry[DetailKey.node_id] for entry in self.scan_results.values()]
            self.selected_node_combobox.configure(state=tk.NORMAL)
            self.selected_node_combobox["values"] = sorted([*none_choice, *node_ids])
        else:
            self.selected_node_combobox.configure(state=tk.DISABLED)
            self.selected_node_combobox["values"] = none_choice
            self.selected_node_combobox.current(0)
        self.selected_node_combobox.configure(state="readonly")
        self.selected_node_combobox.selection_clear()

    def update_send_message_button(self) -> None:
        """Enable or disable the send message button depending on the app's state."""
        choice = self.selected_node_combobox.get()
        if choice == "(none)":
            self.send_message_button.configure(state=tk.DISABLED)
        else:
            self.send_message_button.configure(state=tk.NORMAL)

    def start_scan(self) -> None:
        """Start a scan for QT Py sensor_nodes in the group specified by the user."""
        self.update_status_message_and_style("Scaninng....", bootstyle.INFO)
        discovered_device_1 = {
            "device_description": "CircuitPython device",
            "ip_address": "192.168.0.0",
            "node_id": "node-abcdef-0",
            "python_implementation": "9.2.1",
            "serial_number": "abcdef",
            "snsr_commit": "123abc",
            "snsr_timestamp": "",
            "snsr_version": "0.1.0",
            "system_name": "mpy 3.4",
        }
        discovered_device_2 = {
            "device_description": "SparkFun device",
            "ip_address": "172.16.0.0",
            "node_id": "node-123456-0",
            "python_implementation": "9.1.3",
            "serial_number": "123456",
            "snsr_commit": "456def",
            "snsr_timestamp": "",
            "snsr_version": "0.2.0",
            "system_name": "mpy 3.4",
        }

        discovered_devices = {
            node_info["serial_number"]: node_info
            for node_info in [discovered_device_1, discovered_device_2]
        }

        async def report_new_scan() -> None:
            await asyncio.sleep(0.5)  # Mimic the network call
            self.scan_results.update(discovered_devices)
            self.update_scan_results()
            self.update_send_message_button()

        def finalize_task(task_coroutine) -> None:
            self.background_tasks.discard(task_coroutine)
            self.update_status_message_and_style("Scan complete", bootstyle.SUCCESS)

        update_task = asyncio.create_task(report_new_scan())
        self.background_tasks.add(update_task)
        update_task.add_done_callback(finalize_task)

    def send_message(self) -> None:
        """Send the message text to the node specified by the user."""

    def launch_help(self) -> None:
        """Open online help for the app."""


if __name__ == "__main__":
    logger.debug(f"Launching {__package__}")
    asyncio.run(guikit.AsyncApp.create_and_run(ScannerApp))
