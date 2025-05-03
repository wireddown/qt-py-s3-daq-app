"""Embed matplotlib in ttk."""
# Reworked from https://github.com/matplotlib/matplotlib/blob/main/galleries/examples/user_interfaces/embedding_in_tk_sgskip.py

import asyncio
import logging
import pathlib
import tkinter as tk
from tkinter import font

import numpy as np
import ttkbootstrap as ttk
from matplotlib.backend_bases import key_press_handler  # Attach the default Matplotlib key bindings
from matplotlib.figure import Figure

from qtpy_datalogger import guikit, ttkbootstrap_matplotlib

logger = logging.getLogger(pathlib.Path(__file__).stem)


class PlottingApp(guikit.AsyncWindow):
    """Tkinter GUI demonstrating an interactive matplotlib graph."""

    def create_user_interface(self) -> None:  # noqa: PLR0915 -- allow long function to create the UI
        """Create the main window and connect event handlers."""
        self.root_window.title("Embed Matplotlib in ttk")
        self.root_window.minsize(width=870, height=600)
        self.root_window.columnconfigure(0, weight=1)
        self.root_window.rowconfigure(0, weight=1)

        main = ttk.Frame(self.root_window, name="main_frame", padding=16)
        main.grid(column=0, row=0, sticky=tk.NSEW)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=0)
        main.rowconfigure(1, weight=0)
        main.rowconfigure(2, weight=1)
        main.rowconfigure(3, weight=0)
        main.rowconfigure(4, weight=0)
        main.rowconfigure(5, weight=0)

        title_font = font.Font(weight="bold", size=16)
        title_label = ttk.Label(main, text="Matplotlib styled with ttkbootstrap", font=title_font)
        title_label.grid(column=0, row=0)

        slider_frame = ttk.Frame(main, name="slider_frame")
        slider_frame.grid(column=0, row=1, sticky=tk.N, pady=(16, 2))
        slider_frame.columnconfigure(0, weight=0)
        slider_frame.columnconfigure(1, weight=0)
        slider_frame.columnconfigure(2, weight=0)
        slider_frame.columnconfigure(3, weight=0)
        slider_frame.columnconfigure(4, weight=0)

        slider_label = ttk.Label(slider_frame, text="Frequency (f)")
        slider_label.grid(column=0, row=0, padx=(0, 4))

        slider_update = ttk.Scale(
            slider_frame,
            from_=0.001,
            to=0.01,
            value=0.005,
            orient=tk.HORIZONTAL,
            command=self.update_frequency,
        )
        slider_update.grid(column=1, row=0, padx=(4, 0))

        separator = ttk.Frame(slider_frame, style="primary", width=2, height=24)
        separator.grid(column=2, row=0, padx=(40, 32))

        combobox_label = ttk.Label(slider_frame, text="Theme")
        combobox_label.grid(column=3, row=0, sticky=tk.W, padx=(0, 4))

        self.theme_combobox = guikit.create_theme_combobox(slider_frame)
        self.theme_combobox.grid(column=4, row=0, sticky=tk.W, padx=(4, 0))

        canvas_frame = ttk.Frame(main, name="canvas_frame")
        canvas_frame.grid(column=0, row=2, sticky=tk.NSEW)
        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.rowconfigure(0, weight=1)

        figure_aspect = (4, 3)
        figure_dpi = 100
        fig = Figure(figsize=figure_aspect, dpi=figure_dpi)
        ax = fig.add_subplot()
        ax.set_title("Function plot")
        ax.set_xlabel("time (s)")
        ax.set_ylabel("y")
        ax.grid(
            visible=True,
            which="major",
            axis="y",
            dashes=(3, 8),
            zorder=-1,
        )
        self.t = np.arange(0, 1200, 0.1)
        (self.line,) = ax.plot(
            self.t,
            1000 * np.sin(2 * np.pi * self.t * float(slider_update.get())),
            label="y = 1000*sin(2*pi * f * t)",
        )
        ax.legend(
            title="Function",
            loc="upper left",
            draggable=True,
        )

        self.canvas = ttkbootstrap_matplotlib.create_styled_plot_canvas(fig, canvas_frame)
        self.canvas.mpl_connect("key_press_event", lambda event: print(f"Received {event.key}"))  # type: ignore # noqa T201 -- allow printing to demonstrate event handling
        self.canvas.mpl_connect("key_press_event", key_press_handler)  # pyright: ignore reportArgumentType -- matplotlib type annotations are also a little too strict

        toolbar_row = ttk.Frame(main, name="toolbar_row")
        toolbar_row.grid(column=0, row=3, padx=(40, 80), sticky=tk.EW)
        toolbar_row.columnconfigure(0, weight=1)
        toolbar_row.columnconfigure(1, weight=0)

        side_spacer = ttk.Frame(toolbar_row, name="side_spacer")
        side_spacer.grid(column=0, row=0, sticky=tk.NSEW)

        toolbar_frame = ttkbootstrap_matplotlib.create_styled_plot_toolbar(toolbar_row, self.canvas)
        toolbar_frame.grid(column=1, row=0, sticky=tk.EW)

    def on_show(self) -> None:
        """Initialize UI before entering main loop."""
        theme_name = "cosmo"
        style = ttk.Style.get_instance()
        if not style:
            raise ValueError()
        self.theme_combobox.set(theme_name)
        style.theme_use(theme_name)

    async def on_loop(self) -> None:
        """Update the UI with new information."""
        await asyncio.sleep(1e-6)

    def on_closing(self) -> None:
        """Clean up before exiting."""

    def update_frequency(self, new_val: str) -> None:
        """Refresh the graph using the new user input."""
        f = float(new_val)
        y = 1000 * np.sin(2 * np.pi * f * self.t)
        self.line.set_data(self.t, y)
        self.canvas.draw()


if __name__ == "__main__":
    logger.debug(f"Launching {__package__}")
    asyncio.run(guikit.AsyncApp.create_and_run(PlottingApp))
