"""An app that scans for QT Py sensor_nodes."""

import asyncio
import logging
import pathlib
import socket
import tkinter as tk
import uuid
import webbrowser
from enum import StrEnum
from tkinter import font

import ttkbootstrap as ttk
import ttkbootstrap.icons as ttk_icons
import ttkbootstrap.tableview as ttk_tableview
from ttkbootstrap import constants as bootstyle

from qtpy_datalogger import discovery, guikit, network
from qtpy_datalogger.datatypes import Default, Links

logger = logging.getLogger(pathlib.Path(__file__).stem)


class Constants(StrEnum):
    """Constants for the scanner app."""

    AppName = "QT Py Sensor Node Scanner"
    NoneChoice = "(none)"


class ScannerData:
    """A model class for holding the state of a ScannerApp instance."""

    def __init__(self) -> None:
        """Initialize a new model class for a ScannerApp instance."""
        self.devices_by_group: dict[str, dict[str, discovery.QTPyDevice]] = {}

    def get_node(self, serial_number: str) -> discovery.QTPyDevice | None:
        """Return the sensor_node that matches the specified serial_number."""
        for devices_in_group in self.devices_by_group.values():
            for device_serial_number, device_info in devices_in_group.items():
                if serial_number == device_serial_number:
                    return device_info
        return None

    def process_group_scan(self, group_id: str, discovered_devices: dict[str, discovery.QTPyDevice]) -> None:
        """Update known devices with a new group scan."""
        known_group_devices = self.devices_by_group.get(group_id, {})
        known_group_node_serial_numbers = set(known_group_devices.keys())
        discovered_node_serial_numbers_in_group = {
            serial_number for serial_number, device in discovered_devices.items() if device.mqtt_group_id == group_id
        }

        # Identify new devices
        new_serial_numbers = discovered_node_serial_numbers_in_group - known_group_node_serial_numbers

        # Identify removed devices
        offline_serial_numbers = known_group_node_serial_numbers - discovered_node_serial_numbers_in_group

        # Apply changes
        for new_serial_number in new_serial_numbers:
            new_device_info = discovered_devices[new_serial_number]
            known_group_devices[new_device_info.serial_number] = new_device_info
        for offline_serial_number in offline_serial_numbers:
            offline_device_info = known_group_devices[offline_serial_number]
            _ = known_group_devices.pop(offline_device_info.serial_number)
        for refreshed_serial_number in discovered_node_serial_numbers_in_group - new_serial_numbers:
            refreshed_device_info = discovered_devices[refreshed_serial_number]
            known_group_devices[refreshed_device_info.serial_number] = refreshed_device_info
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
        style.theme_use("cosmo")
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
        title_label = ttk.Label(
            main,
            text=f"{icon_emoji} {Constants.AppName}",
            font=title_font,
            padding=16,
            borderwidth=0,
            relief=tk.SOLID,
        )
        title_label.grid(column=0, row=0)

        # Scan group
        scan_frame = ttk.Frame(main, name="scan_frame", borderwidth=0, relief=tk.SOLID)
        group_input_label = ttk.Label(scan_frame, text="Group name")
        self.group_input = ttk.Entry(scan_frame)
        self.group_input.insert(0, Default.MqttGroup)
        self.group_input.bind("<KeyPress>", self.run_command_on_enter)
        scan_button = ttk.Button(scan_frame, text="Scan group", command=self.start_scan)
        clear_button = ttk.Button(
            scan_frame,
            text="Clear results",
            command=self.clear_results,
            style=(bootstyle.OUTLINE, bootstyle.WARNING),  # pyright: ignore reportArgumentType -- the type hint for library uses strings
        )
        group_input_label.pack(side=tk.LEFT)
        self.group_input.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(8, 0))
        scan_button.pack(side=tk.LEFT, padx=(8, 0))
        clear_button.pack(side=tk.LEFT, padx=(8, 0))
        scan_frame.grid(column=0, row=1, sticky=(tk.N, tk.E, tk.W), pady=(8, 0))  # pyright: ignore reportArgumentType -- the type hint for library uses strings

        # Results group
        results_frame = ttk.Frame(main, name="result_frame", borderwidth=0, relief=tk.SOLID)
        result_columns = [
            {"text": "Group", "stretch": False, "width": 60},
            {"text": "Node ID", "stretch": False, "width": 150},
            {"text": "Device", "stretch": True, "width": 220},
            {"text": "Snsr Version", "stretch": False, "width": 100},
            {"text": "UART Port", "stretch": False, "width": 70},
            {"text": "Serial Number", "stretch": False, "width": 0},  # Hide the key used to correlate with scan_db
        ]
        self.scan_results_table = ttk_tableview.Tableview(
            results_frame,
            coldata=result_columns,
            height=9,  # Unit is lines of text
            stripecolor=(colors.light, None),  # pyright: ignore reportAttributeAccessIssue -- the type hint for bootstrap omits its own additions
        )
        self.scan_results_table.view.configure(selectmode=tk.BROWSE)
        self.scan_results_table.hbar.pack_forget()  # Hide the horizontal scroll bar because it's unnecessary
        self.scan_results_table.view.bind("<<TreeviewSelect>>", self.on_row_selected)
        self.scan_results_table.view.unbind("<Double-Button-1>")  # Disable header-row handlers added by ttkbootstrap
        self.scan_results_table.view.unbind("<Button-1>")
        self.scan_results_table.view.unbind("<Button-3>")
        self.scan_results_table.pack(expand=True, fill=tk.X)
        results_frame.grid(column=0, row=2, sticky=(tk.N, tk.E, tk.W), pady=(8, 0))  # pyright: ignore reportArgumentType -- the type hint for library uses strings

        # Node communication
        comms_frame = ttk.Frame(main, name="comms_frame", borderwidth=0, relief=tk.SOLID)
        selection_status_frame = ttk.Frame(comms_frame, name="selection_frame", borderwidth=0, relief=tk.SOLID)
        self.status_icon_label = ttk.Label(selection_status_frame)
        self.status_message = ttk.Label(selection_status_frame, borderwidth=0, relief=tk.SOLID)
        self.selected_node_combobox = ttk.Combobox(
            selection_status_frame,
            width=20,
            state=ttk.READONLY,
            style=bootstyle.PRIMARY,
        )
        self.selected_node_combobox.bind("<<ComboboxSelected>>", self.on_combobox_selected)
        self.status_icon_label.pack(side=tk.LEFT)
        self.status_message.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(8, 0))
        self.selected_node_combobox.pack(side=tk.LEFT, padx=(8, 0))
        selection_status_frame.pack(side=tk.TOP, expand=True, fill=tk.X)

        message_frame = ttk.Frame(comms_frame, name="message_frame")
        self.message_input = ttk.Entry(message_frame)
        self.message_input.bind("<KeyPress>", self.run_command_on_enter)
        self.send_message_button = ttk.Button(message_frame, text="Send message", command=self.send_message)
        self.message_input.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.send_message_button.pack(side=tk.LEFT, padx=(8, 0))
        message_frame.pack(side=tk.TOP, pady=(8, 0), expand=True, fill=tk.X)

        self.message_log = ttk.ScrolledText(comms_frame, state=tk.DISABLED, wrap="word")
        # Add handlers for 'Ctrl-A' / select all
        self.message_log.select_range = self.select_message_log_range  # pyright: ignore reportAttributeAccessIssue -- we are adding this at run time
        self.message_log.icursor = self.set_message_log_cursor  # pyright: ignore reportAttributeAccessIssue -- we are adding this at run time
        self.message_log.pack(side=tk.TOP, expand=True, fill=tk.BOTH)
        comms_frame.grid(column=0, row=3, sticky=(tk.N, tk.E, tk.W))  # pyright: ignore reportArgumentType -- the type hint for library uses strings

        # App commands
        action_frame = ttk.Frame(main, name="action_frame", borderwidth=0, relief=tk.SOLID)
        help_button = ttk.Button(action_frame, text="Online help", command=self.launch_help, style=bootstyle.OUTLINE)
        copy_log_button = ttk.Button(
            action_frame,
            text="Copy all",
            command=self.copy_log,
            style=(bootstyle.OUTLINE, bootstyle.PRIMARY),  # pyright: ignore reportArgumentType -- the type hint for library uses strings
        )
        clear_log_button = ttk.Button(
            action_frame,
            text="Clear all",
            command=self.clear_log,
            style=(bootstyle.OUTLINE, bootstyle.WARNING),  # pyright: ignore reportArgumentType -- the type hint for library uses strings
        )
        help_button.pack(side=tk.RIGHT, padx=(8, 0))
        copy_log_button.pack(side=tk.LEFT)
        clear_log_button.pack(side=tk.LEFT, padx=(8, 0))
        action_frame.grid(column=0, row=5, sticky=(tk.S, tk.E, tk.W), pady=(8, 0))  # pyright: ignore reportArgumentType -- the type hint for library uses strings

        # Finalize layout
        main.grid(column=0, row=0, sticky=(tk.N, tk.S, tk.E, tk.W))  # pyright: ignore reportArgumentType -- the type hint for library uses strings
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=0)
        main.rowconfigure(1, weight=0)
        main.rowconfigure(2, weight=1, minsize=190)
        main.rowconfigure(3, weight=1, minsize=200)
        main.rowconfigure(
            4,
            weight=10000,  # Extra strong row so that the results stable remains in place when vertically resizing
        )
        main.rowconfigure(5, weight=0)
        self.root_window.columnconfigure(0, weight=1)
        self.root_window.rowconfigure(0, weight=1)

        self.group_input.after(100, self.group_input.focus)  # Give the main window time to appear and focus input on the group name
        self.update_scan_results_table()
        self.update_combobox_values()
        self.update_send_message_button()
        self.update_status_message_and_style("Waiting for scan.", bootstyle.SUCCESS)

    async def on_loop(self) -> None:
        """Update the UI with new information."""
        await asyncio.sleep(10e-6)  # Yield the CPU to prevent high-but-idle spin-wait consumption

    def run_command_on_enter(self, event_args: tk.Event) -> None:
        """Handle the Enter key press for an Entry widget and run its associated command."""
        key_character = event_args.char
        if key_character not in ["\r"]:
            return
        if key_character == "\r":
            parent = event_args.widget.winfo_parent()
            if "scan_frame" in parent:
                self.start_scan()
            elif "message_frame" in parent:
                self.send_message()

    def on_row_selected(self, event_args: tk.Event) -> None:
        """Handle the user selecting a row in the results table."""
        selected_rows = event_args.widget.selection()
        if not selected_rows:
            return

        new_selected_index = selected_rows[0]  # selectmode=tk.BROWSE ensures only one row
        selected_row = self.scan_results_table.iidmap[new_selected_index]
        selected_serial_number = selected_row.values[-1]  # The key cell is last
        if selected_serial_number == self.selected_node:
            return  # Prevent an infinite event handler loop with on_node_selected()

        self.on_node_selected(selected_serial_number)

    def on_combobox_selected(self, event_args: tk.Event) -> None:
        """Handle the user selecting a new entry in the combobox."""
        selected_value = event_args.widget.get()
        selected_serial_number = Constants.NoneChoice
        for _, devices_in_group in self.scan_db.devices_by_group.items():
            for serial_number, device_info in devices_in_group.items():
                if selected_value in [device_info.node_id, device_info.com_port]:
                    selected_serial_number = serial_number
        self.on_node_selected(selected_serial_number)

    def on_node_selected(self, node_serial_number: str) -> None:
        """Update the UI state for the selected node."""
        self.selected_node = node_serial_number

        # Always clear table selection
        selected = self.scan_results_table.view.selection()
        self.scan_results_table.view.selection_remove(selected)
        if node_serial_number != Constants.NoneChoice:
            index_for_node = {
                row.values[-1]: index  # The key cell is last
                for index, row in self.scan_results_table.iidmap.items()
            }
            self.scan_results_table.view.selection_add(index_for_node[node_serial_number])

        selected_resource_name = Constants.NoneChoice
        selected_device = self.scan_db.get_node(node_serial_number)
        if selected_device:
            selected_resource_name = selected_device.node_id if selected_device.node_id else selected_device.com_port
        self.selected_node_combobox.set(selected_resource_name)
        self.selected_node_combobox.configure(state=ttk.READONLY)
        self.selected_node_combobox.selection_clear()

        self.update_send_message_button()
        self.update_status_message_and_style(f"Selected {selected_resource_name}.", bootstyle.SUCCESS)

    def update_status_message_and_style(self, new_message: str, new_style: str) -> None:
        """Set the status message to a new string and style."""
        status_emoji = ttk_icons.Emoji.get("white heavy check mark")
        if new_style in [bootstyle.WARNING, bootstyle.DANGER]:
            status_emoji = ttk_icons.Emoji.get("cross mark")
        self.status_icon_label.configure(text=status_emoji, bootstyle=new_style)  # pyright: ignore callIssue -- the type hint for bootstrap omits its own additions
        self.status_message.configure(text=new_message, bootstyle=new_style)  # pyright: ignore callIssue -- the type hint for bootstrap omits its own additions

    def update_scan_results_table(self) -> None:
        """Update the contents of the result stable depending on the app's state."""
        new_selection = Constants.NoneChoice
        rows = []
        ordered_by_group = sorted(self.scan_db.devices_by_group.keys())
        for group_id in ordered_by_group:
            nodes_by_serial_number = self.scan_db.devices_by_group[group_id]
            ordered_by_serial_number = sorted(nodes_by_serial_number.keys())
            for serial_number in ordered_by_serial_number:
                node_info = nodes_by_serial_number[serial_number]
                if serial_number == self.selected_node:
                    new_selection = self.selected_node  # Retain the original selection
                rows.append(
                    (
                        group_id,
                        node_info.node_id,
                        node_info.device_description,
                        node_info.snsr_version,
                        node_info.com_port,
                        node_info.serial_number,
                    )
                )
        self.scan_results_table.delete_rows()
        for row in rows:
            self.scan_results_table.insert_row("end", row)
        self.scan_results_table.load_table_data()
        if len(rows) == 1:
            new_selection = rows[0][-1]
            self.message_input.focus()
        self.on_node_selected(new_selection)

    def update_combobox_values(self) -> None:
        """Enable or disable the combobox and update its choices depending on the app's state."""
        none_choice = (Constants.NoneChoice,)
        if self.scan_db.devices_by_group:
            node_resource_names = []
            for group_nodes in self.scan_db.devices_by_group.values():
                for entry in group_nodes.values():
                    resource_name = entry.node_id if entry.node_id else entry.com_port
                    node_resource_names.append(resource_name)
            self.selected_node_combobox.configure(state=tk.NORMAL)
            self.selected_node_combobox["values"] = sorted([*none_choice, *node_resource_names])
        else:
            self.selected_node_combobox.configure(state=tk.DISABLED)
            self.selected_node_combobox["values"] = none_choice
            self.selected_node_combobox.current(0)
        self.selected_node_combobox.configure(state=ttk.READONLY)
        self.selected_node_combobox.selection_clear()

    def update_send_message_button(self) -> None:
        """Enable or disable the send message button depending on the app's state."""
        choice = self.selected_node_combobox.get()
        if choice == Constants.NoneChoice:
            self.send_message_button.configure(state=tk.DISABLED)
        else:
            self.send_message_button.configure(state=tk.NORMAL)

    def append_text_to_log(self, line: str) -> None:
        """Add the specified text to the end of the log."""
        self.message_log.configure(state=tk.NORMAL)
        self.message_log.insert("end", line)
        self.message_log.configure(state=tk.DISABLED)
        self.message_log.see("end")

    def start_scan(self) -> None:
        """Start a scan for QT Py sensor_nodes in the group specified by the user."""
        group_id = self.group_input.get()
        if not group_id:
            self.update_status_message_and_style("Cannot scan: specify a group name.", bootstyle.WARNING)
            return

        self.update_status_message_and_style("Scanning....", bootstyle.INFO)

        async def report_new_scan() -> None:
            qtpy_devices_in_group = await discovery.discover_qtpy_devices_async(group_id)
            self.process_new_scan(group_id, qtpy_devices_in_group)

        def finalize_task(task_coroutine: asyncio.Task) -> None:
            self.background_tasks.discard(task_coroutine)
            self.update_status_message_and_style(
                f"Scan complete: found {len(self.scan_db.devices_by_group[group_id])} nodes in {group_id}.",
                bootstyle.SUCCESS,
            )

        update_task = asyncio.create_task(report_new_scan())
        self.background_tasks.add(update_task)
        update_task.add_done_callback(finalize_task)

    def process_new_scan(self, group_id: str, discovered_devices: dict[str, discovery.QTPyDevice]) -> None:
        """Update the discovered devices with details from a new scan."""
        self.scan_db.process_group_scan(group_id, discovered_devices)
        self.update_scan_results_table()
        self.update_combobox_values()
        self.update_send_message_button()

    def clear_results(self) -> None:
        """Clear the scan results."""
        self.scan_db.devices_by_group.clear()
        self.update_scan_results_table()
        self.update_combobox_values()
        self.update_send_message_button()
        self.update_status_message_and_style("Waiting for scan.", bootstyle.SUCCESS)

    def send_message(self) -> None:
        """Send the message text to the node specified by the user."""
        message = self.message_input.get()
        self.message_input.delete(0, "end")
        if not message:
            self.update_status_message_and_style("Cannot send: enter a message.", bootstyle.WARNING)
            return
        if self.selected_node in [Constants.NoneChoice, ""]:
            self.update_status_message_and_style("Cannot send: select a node.", bootstyle.WARNING)
            return

        self.update_status_message_and_style("Sending....", bootstyle.INFO)
        qtpy_device = self.scan_db.get_node(self.selected_node)
        if not qtpy_device:
            return
        qtpy_resource = self.selected_node_combobox.get()

        async def send_message_and_get_response() -> tuple[str, str]:
            controller = network.QTPyController(
                broker_host="localhost",
                group_id=qtpy_device.mqtt_group_id,
                mac_address=hex(uuid.getnode())[2:],
                ip_address=socket.gethostbyname(socket.gethostname()),
            )
            await controller.connect_and_subscribe()
            command_name = "custom"
            custom_parameters = {
                "input": message,
            }
            sent_emoji = ttk_icons.Emoji.get("black large square")
            received_emoji = ttk_icons.Emoji.get("leftwards black arrow")
            status_emoji = ttk_icons.Emoji.get("white large square")
            self.append_text_to_log(f"{sent_emoji} {message}\n")
            sent_action = await controller.send_action(qtpy_device.node_id, command_name, custom_parameters)
            response_complete = False
            new_status_message = "Communication successful."
            new_status_style = bootstyle.SUCCESS
            while not response_complete:
                try:
                    response_parameters, sender_information = await controller.get_matching_result(
                        qtpy_device.node_id, sent_action
                    )
                    response_complete = response_parameters["complete"]
                    response = response_parameters["output"]
                    used_bytes = sender_information.status.used_memory
                    free_bytes = sender_information.status.free_memory
                    cpu_degc = sender_information.status.cpu_temperature
                    self.append_text_to_log(f"{received_emoji} {response}\n")
                    self.append_text_to_log(
                        f"{status_emoji} with {used_bytes} bytes used, {free_bytes} bytes remaining, at temperature {cpu_degc} degC\n"
                    )
                except TimeoutError:
                    new_status_message = (
                        f"Node did not respond! Is it online? Scan group {qtpy_device.mqtt_group_id} to verify."
                    )
                    new_status_style = bootstyle.WARNING
                    break
            await controller.disconnect()
            return new_status_message, new_status_style

        def finalize_task(task_coroutine: asyncio.Task) -> None:
            self.background_tasks.discard(task_coroutine)
            new_status, new_style = task_coroutine.result()
            self.update_status_message_and_style(new_status, new_style)

        if qtpy_resource == qtpy_device.node_id:
            communicate_task = asyncio.create_task(send_message_and_get_response())
            self.background_tasks.add(communicate_task)
            communicate_task.add_done_callback(finalize_task)
        else:
            self.update_status_message_and_style("Serial communication is not implemented.", bootstyle.WARNING)

    def launch_help(self) -> None:
        """Open online help for the app."""
        webbrowser.open_new_tab(Links.Homepage)

    def copy_log(self) -> None:
        """Copy the full log to the clipboard."""
        all_log = self.message_log.get("1.0", "end")
        self.root_window.clipboard_clear()
        self.root_window.clipboard_append(all_log)
        self.update_status_message_and_style("Copied message log to clipboard.", bootstyle.SUCCESS)

    def clear_log(self) -> None:
        """Clear the log contents."""
        self.message_log.configure(state=tk.NORMAL)
        self.message_log.delete("1.0", "end")
        self.message_log.configure(state=tk.DISABLED)
        self.update_status_message_and_style("Cleared message log.", bootstyle.SUCCESS)

    def select_message_log_range(self, start_index: int | str, end_index: int | str) -> None:
        """Select the text in the specified range."""
        # Assume select all
        self.message_log.selection_clear()
        if start_index == 0:
            start_index = "1.0"
        self.message_log.tag_add("sel", start_index, end_index)

    def set_message_log_cursor(self, index: int | str) -> None:
        """Move the cursor to the specified index."""
        # Assume select all
        self.message_log.mark_set("insert", index)


if __name__ == "__main__":
    logger.debug(f"Launching {__package__}")
    asyncio.run(guikit.AsyncApp.create_and_run(ScannerApp))
