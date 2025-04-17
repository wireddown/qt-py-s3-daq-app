"""An app that scans for QT Py sensor_nodes."""

import asyncio
import logging
import pathlib
import tkinter as tk
from enum import StrEnum
from tkinter import font

import ttkbootstrap as ttk
import ttkbootstrap.icons as ttk_icons
import ttkbootstrap.tableview as ttk_tableview
from ttkbootstrap import constants as bootstyle

from qtpy_datalogger import discovery, guikit

logger = logging.getLogger(pathlib.Path(__file__).stem)


class Constants(StrEnum):
    """Constants for the scanner app."""

    AppName = "QT Py Sensor Node Scanner"
    DefaultGroup = "zone1"
    NoneChoice = "(none)"

class ScannerData:
    """A model class for holding the state of a ScannerApp instance."""

    def __init__(self) -> None:
        """Initialize a new model class for a ScannerApp instance."""
        self.devices_by_group: dict[str, dict[str, discovery.QTPyDevice]] = {}

    def process_group_scan(self, group_id: str, discovered_devices: dict[str, discovery.QTPyDevice]) -> None:
        """
        Update known devices with a new group scan.

        Return two sets of serial numbers as a tuple
        (added_serial_numbers, removed_serial_numbers)
        """
        known_group_devices = self.devices_by_group.get(group_id, {})
        known_group_node_serial_numbers = set(known_group_devices.keys())
        discovered_node_serial_numbers_in_group = set(discovered_devices.keys())

        # Identify new devices
        new_serial_numbers = discovered_node_serial_numbers_in_group - known_group_node_serial_numbers

        # Identify removed devices
        offline_serial_numbers = known_group_node_serial_numbers - discovered_node_serial_numbers_in_group

        # Apply changes
        for new_serial_number in new_serial_numbers:
            device_info = discovered_devices[new_serial_number]
            known_group_devices[device_info.serial_number] = device_info
        for offline_serial_number in offline_serial_numbers:
            device_info = known_group_devices[offline_serial_number]
            _ = known_group_devices.pop(device_info.serial_number)
        self.devices_by_group[group_id] = known_group_devices


class ScannerApp(guikit.AsyncWindow):
    """A GUI for discovering and communicating with QT Py sensor nodes."""

    def create_user_interface(self) -> None:  # noqa: PLR0915 -- allow long function to create the UI
        """Create the main window and connect event handlers."""
        # State
        self.scan_db = ScannerData()
        self.selected_node = Constants.NoneChoice
        self.background_tasks = set()

        # Theme
        style = ttk.Style()
        style.theme_use("sandstone")
        colors = style.colors

        # Window title bar
        self.root_window.minsize(width=560, height=572)
        self.root_window.title(Constants.AppName)
        icon = tk.PhotoImage(master=self.root_window, data=ttk_icons.Icon.question)
        self.root_window.iconphoto(True, icon)

        # Title
        main = ttk.Frame(self.root_window, name="root_frame", padding=16)
        icon_emoji = ttk_icons.Emoji.get("telescope")
        title_font = font.Font(weight="bold", size=24)
        title_label = ttk.Label(main, font=title_font, text=f"{icon_emoji} {Constants.AppName}", padding=16, borderwidth=0, relief=tk.SOLID)
        title_label.grid(column=0, row=0)

        # Scan group
        scan_frame = ttk.Frame(main, name="scan_frame", borderwidth=0, relief=tk.SOLID)
        group_input_label = ttk.Label(scan_frame, text="Group name")
        self.group_input = ttk.Entry(scan_frame)
        self.group_input.insert(0, Constants.DefaultGroup)
        scan_button = ttk.Button(scan_frame, command=self.start_scan, text="Scan group")
        group_input_label.pack(side=tk.LEFT)
        self.group_input.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=8)
        scan_button.pack(side=tk.LEFT)
        scan_frame.grid(column=0, row=1, sticky=(tk.N, tk.E, tk.W), pady=(8, 0))  # pyright: ignore reportArgumentType -- the type hint for library uses strings

        # Results group
        results_frame = ttk.Frame(main, name="result_frame", borderwidth=0, relief=tk.SOLID)
        result_columns = [
            {"text": "Group", "stretch": False, "width": 60},
            {"text": "Node ID", "stretch": False, "width": 150},
            {"text": "Device", "stretch": True, "width": 220},
            {"text": "Snsr Version", "stretch": False, "width": 100},
            {"text": "UART Port", "stretch": False, "width": 70},
        ]
        self.scan_results_table = ttk_tableview.Tableview(results_frame, coldata=result_columns, height=9, stripecolor=(colors.light, None))  # pyright: ignore reportAttributeAccessIssue -- the type hint for bootstrap omits its own additions
        self.scan_results_table.view.configure(selectmode=tk.BROWSE)
        self.scan_results_table.view.bind("<<TreeviewSelect>>", self.on_row_selected)
        self.scan_results_table.view.unbind("<Double-Button-1>")  # Disable header-row handlers added by ttkbootstrap
        self.scan_results_table.view.unbind("<Button-1>")
        self.scan_results_table.view.unbind("<Button-3>")
        self.scan_results_table.pack(expand=True, fill=tk.X)
        results_frame.grid(column=0, row=2, sticky=(tk.N, tk.E, tk.W), pady=(8, 0))  # pyright: ignore reportArgumentType -- the type hint for library uses strings

        # Node communication
        comms_frame = ttk.Frame(main, name="comms_frame", borderwidth=0, relief=tk.SOLID)
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
        action_frame = ttk.Frame(main, name="action_frame", borderwidth=0, relief=tk.SOLID)
        exit_button = ttk.Button(action_frame, text="Quit", style=bootstyle.DANGER, command=self.exit)
        help_button = ttk.Button(action_frame, text="Online help", style=bootstyle.OUTLINE, command=self.launch_help)
        self.status_message = ttk.Label(action_frame)
        exit_button.pack(side=tk.RIGHT, padx=(8, 0))
        help_button.pack(side=tk.RIGHT, padx=(8, 0))
        self.status_message.pack(side=tk.RIGHT, padx=8)
        action_frame.grid(column=0, row=5, sticky=(tk.S, tk.E, tk.W), pady=(8, 0))  # pyright: ignore reportArgumentType -- the type hint for library uses strings

        # Finalize layout
        main.grid(column=0, row=0, sticky=(tk.N, tk.S, tk.E, tk.W))  # pyright: ignore reportArgumentType -- the type hint for library uses strings
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=0)
        main.rowconfigure(1, weight=0)
        main.rowconfigure(2, weight=1, minsize=190)
        main.rowconfigure(3, weight=1, minsize=200)
        main.rowconfigure(4, weight=10000)  # Extra strong row so that the results stable remains in place when vertically resizing
        main.rowconfigure(5, weight=0)
        self.root_window.columnconfigure(0, weight=1)
        self.root_window.rowconfigure(0, weight=1)

        self.update_scan_results_table()
        self.update_combobox_values()
        self.update_send_message_button()
        self.update_status_message_and_style("OK", bootstyle.SUCCESS)

    async def on_loop(self) -> None:
        """Update the UI with new information."""
        await asyncio.sleep(0.01)

    def on_closing(self) -> None:
        """Clean up before exiting."""

    def on_row_selected(self, event_args: tk.Event) -> None:
        """Handle the user selecting a row in the results table."""
        selected_rows = event_args.widget.selection()
        if not selected_rows:
            return

        new_selected_index = selected_rows[0]
        selected_row = self.scan_results_table.iidmap[new_selected_index]
        selected_node = selected_row.values[1]
        if selected_node == self.selected_node:
            return

        self.on_node_selected(selected_node)

    def on_combobox_selected(self, event_args: tk.Event) -> None:
        """Handle the user selecting a new entry in the combobox."""
        selected_node = event_args.widget.get()
        self.on_node_selected(selected_node)

    def on_node_selected(self, selected_node: str) -> None:
        """Update the UI state for the selected node."""
        self.selected_node = selected_node

        # Always clear table selection
        selected = self.scan_results_table.view.selection()
        self.scan_results_table.view.selection_remove(selected)
        if selected_node != Constants.NoneChoice:
            index_for_node = {
                row.values[1]: index
                for index, row in self.scan_results_table.iidmap.items()
            }
            self.scan_results_table.view.selection_add(index_for_node[selected_node])

        # Update the selected combobox entry
        self.selected_node_combobox.set(selected_node)
        self.selected_node_combobox.configure(state="readonly")
        self.selected_node_combobox.selection_clear()

        self.update_send_message_button()
        self.update_status_message_and_style(f"Selected {selected_node}", bootstyle.SUCCESS)

    def update_status_message_and_style(self, new_message: str, new_style: str) -> None:
        """Set the status message to a new string and style."""
        self.status_message.configure(text=new_message, bootstyle=new_style)  # pyright: ignore callIssue -- the type hint for bootstrap omits its own additions

    def update_scan_results_table(self) -> None:
        """Update the contents of the result stable depending on the app's state."""
        new_selection = Constants.NoneChoice
        rows = []
        for group_id, nodes_by_serial_number in self.scan_db.devices_by_group.items():
            for _, node_info in nodes_by_serial_number.items():
                if node_info.node_id == self.selected_node:
                    new_selection = self.selected_node
                rows.append(
                    (
                        group_id,
                        node_info.node_id,
                        node_info.device_description,
                        node_info.snsr_version,
                        node_info.com_port,
                    )
                )
        self.scan_results_table.delete_rows()
        self.scan_results_table.insert_rows("end", rows)
        self.scan_results_table.load_table_data()
        self.on_node_selected(new_selection)

    def update_combobox_values(self) -> None:
        """Enable or disable the combobox and update its choices depending on the app's state."""
        none_choice = (Constants.NoneChoice,)
        if self.scan_db.devices_by_group:
            node_ids = [
                entry.node_id
                for group_nodes in self.scan_db.devices_by_group.values()
                for entry in group_nodes.values()
            ]
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
        if choice == Constants.NoneChoice:
            self.send_message_button.configure(state=tk.DISABLED)
        else:
            self.send_message_button.configure(state=tk.NORMAL)

    def start_scan(self) -> None:
        """Start a scan for QT Py sensor_nodes in the group specified by the user."""
        group_id = self.group_input.get()
        if not group_id:
            self.update_status_message_and_style("Cannot scan. Specify a group name.", bootstyle.WARNING)
            return

        self.update_status_message_and_style("Scanning....", bootstyle.INFO)

        async def report_new_scan() -> None:
            qtpy_devices_in_group = await discovery.discover_qtpy_devices_async()
            self.process_new_scan(group_id, qtpy_devices_in_group)

        def finalize_task(task_coroutine: asyncio.Task) -> None:
            self.background_tasks.discard(task_coroutine)
            self.update_status_message_and_style("Scan complete", bootstyle.SUCCESS)

        update_task = asyncio.create_task(report_new_scan())
        self.background_tasks.add(update_task)
        update_task.add_done_callback(finalize_task)

    def process_new_scan(self, group_id: str, discovered_devices: dict[str, discovery.QTPyDevice]) -> None:
        """Update the discovered devices with details from a new scan."""
        self.scan_db.process_group_scan(group_id, discovered_devices)
        self.update_scan_results_table()
        self.update_combobox_values()
        self.update_send_message_button()

    def send_message(self) -> None:
        """Send the message text to the node specified by the user."""

    def launch_help(self) -> None:
        """Open online help for the app."""


if __name__ == "__main__":
    logger.debug(f"Launching {__package__}")
    asyncio.run(guikit.AsyncApp.create_and_run(ScannerApp))
