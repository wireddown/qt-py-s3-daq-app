"""Embed matplotlib in ttk."""
# Reworked from https://github.com/matplotlib/matplotlib/blob/main/galleries/examples/user_interfaces/embedding_in_tk_sgskip.py

import asyncio
import logging
import pathlib
import tkinter as tk
from tkinter import font
from typing import Callable, ClassVar

import numpy as np
import ttkbootstrap as ttk
import ttkbootstrap.colorutils as ttk_colorutils
import ttkbootstrap.themes.standard as ttk_themes
from matplotlib.axes import Axes
from matplotlib.backend_bases import key_press_handler  # Attach the default Matplotlib key bindings
from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg,
    NavigationToolbar2Tk,  # pyright: ignore reportPrivateImportUsage -- matplotlib exposes this indirectly
)
from matplotlib.figure import Figure
from ttkbootstrap import constants as bootstyle

from qtpy_datalogger import guikit

logger = logging.getLogger(pathlib.Path(__file__).stem)


class MatplotlibBootstrap:
    """A class that applies ttkbootstrap styling to matplotlib visuals."""

    palette_color_name_for_visual: ClassVar = {
        "background": bootstyle.LIGHT,  # The buttons in the toolbar only re-color themselves on creation, so force a light background color for all themes
        "foreground": bootstyle.DARK,   # Likewise, force a dark foreground color in text labels for all themes so that the (x, y) indicator remains readable
        "selectcolor": bootstyle.PRIMARY,
        "xtra_window_bg": "bg",  # bootstyle themes define "bg" but the library's constants omit them
        "xtra_window_fg": "fg",  # bootstyle themes define "fg" but the library's constants omit them
    }

    embedded_figure_name: ClassVar = "mpl_figure_canvas"
    toolbar_border_name: ClassVar = "toolbar_border"

    @staticmethod
    def create_styled_plot_canvas(
        figure: Figure,
        canvas_frame: ttk.Frame,
    ) -> FigureCanvasTkAgg:
        """Return a FigureCanvasTkAgg from matplotlib that responds to the ttkbootstrap '<<ThemeChanged>>' event."""
        canvas = FigureCanvasTkAgg(figure, canvas_frame)
        setattr(canvas.get_tk_widget(), __class__.embedded_figure_name, canvas)
        canvas.get_tk_widget().bind("<<ThemeChanged>>", __class__.handle_theme_changed)
        return canvas

    @staticmethod
    def create_styled_plot_toolbar(
        parent: tk.BaseWidget,
        matching_canvas: FigureCanvasTkAgg,
        padleft: int = 10,
        toolbar_width: int = 500,
        border_thickness: int = 3,
        ) -> tk.Frame:
        """Return a tk.Frame that contains a NavigationToolbar from matplotlib and responds to the ttkbootstrap '<<ThemeChanged>>' event."""
        canvas_aspect = matching_canvas.get_width_height()
        toolbar_width = max(toolbar_width, canvas_aspect[0])  # Any narrower and the updates flicker
        toolbar_height = 50  # Any shorter and the updates flicker
        final_width = padleft + toolbar_width + (2 * border_thickness)
        final_height = toolbar_height + (2 * border_thickness)

        toolbar_border = tk.Frame(parent, name=__class__.toolbar_border_name, width=final_width, height=final_height)
        toolbar_border.columnconfigure(0, weight=0, minsize=final_width)
        toolbar_border.rowconfigure(0, weight=0, minsize=final_height)
        toolbar_border.grid_propagate(False)  # Lock the height and width by ignoring child size requests
        toolbar_border.bind("<<ThemeChanged>>", __class__.handle_theme_changed)

        toolbar_frame = tk.Frame(toolbar_border, name="toolbar_frame")
        toolbar_frame.grid(column=0, row=0)
        toolbar_frame.columnconfigure(0, weight=1)
        toolbar_frame.columnconfigure(1, weight=1)
        toolbar_frame.rowconfigure(0, weight=0)

        left_side_padding = tk.Frame(toolbar_frame, name="left_side_padding", width=padleft, height=toolbar_height)
        left_side_padding.grid(column=0, row=0, sticky=tk.EW)

        toolbar_constraint = tk.Frame(toolbar_frame, name="toolbar_constraint", width=toolbar_width)
        toolbar_constraint.grid(column=1, row=0)

        # Place the toolbar in the same cell, covering its constraint
        toolbar = NavigationToolbar2Tk(matching_canvas, toolbar_frame, pack_toolbar=False)  # Use pack_toolbar=False for explicit placement
        toolbar.grid(column=1, row=0, sticky=tk.NSEW)

        return toolbar_border

    @staticmethod
    def handle_theme_changed(event_args: tk.Event) -> None:
        """Handle the ttkbootstrap virtual event named <<ThemeChanged>>."""
        sender = event_args.widget
        sender_class = type(sender)
        sender_is_figure = issubclass(sender_class, tk.Canvas)
        sender_is_toolbar = issubclass(sender_class, tk.Frame)

        style = ttk.Style.get_instance()
        if not (style and style.theme):
            raise ValueError()

        default_theme = ttk_themes.STANDARD_THEMES[bootstyle.DEFAULT_THEME]
        requested_theme = ttk_themes.STANDARD_THEMES.get(style.theme.name, default_theme)
        if sender_is_figure:
            __class__.apply_figure_style(sender, requested_theme)
        elif sender_is_toolbar:
            __class__.apply_toolbar_style(sender, requested_theme)
        else:
            raise TypeError()

    @staticmethod
    def apply_figure_style(canvas: tk.Canvas, requested_theme: dict) -> None:
        """Apply the specified theme to the specified matplotlib figure canvas."""
        mpl_figure_canvas = getattr(canvas, __class__.embedded_figure_name, None)
        if not mpl_figure_canvas:
            # Nothing to style
            return

        theme_palette = requested_theme["colors"]
        color_name_for_visual = __class__.palette_color_name_for_visual
        fill_color = theme_palette[color_name_for_visual["xtra_window_bg"]]
        plot_area_color = theme_palette[color_name_for_visual["background"]]
        text_color = theme_palette[color_name_for_visual["xtra_window_fg"]]

        figure: Figure = mpl_figure_canvas.figure
        figure.set_facecolor(fill_color)

        all_axes: list[Axes] = figure.axes
        for ax in all_axes:
            ax.set_title(
                ax.get_title(),
                color=text_color,
            )
            ax.set_facecolor(plot_area_color)
            for spine in ax.spines.values():
                spine.set_color(text_color)
                spine.set_linewidth(2)
            ax.tick_params(
                color=text_color,
                labelcolor=text_color,
                grid_color=text_color,
            )
            ax.set_xlabel(
                ax.get_xlabel(),
                color=text_color,
            )
            ax.set_ylabel(
                ax.get_ylabel(),
                color=text_color,
            )

            legend = ax.get_legend()
            if not legend:
                continue
            legend_frame = legend.get_frame()
            legend_frame.set_alpha(0.9)
            legend_frame.set_facecolor(fill_color)
            legend_frame.set_edgecolor(text_color)

            legend_title = legend.get_title()
            legend_title.set_color(text_color)

            legend_labels = legend.get_texts()
            for plot_label in legend_labels:
                plot_label.set_color(text_color)

            legend_lines = legend.get_lines()
            for index, plot_line in enumerate(legend_lines):
                if not plot_line.axes:
                    continue
                owning_plot = plot_line.axes.lines[index]
                plot_line.set_color(owning_plot.get_color())
        mpl_figure_canvas.draw()

    @staticmethod
    def apply_toolbar_style(tk_widget: tk.Widget, requested_theme: dict) -> None:
        """Apply the specified theme to the specified matplotlib toolbar."""
        theme_palette = requested_theme["colors"]
        widget_stylers: dict[str, Callable] = {
            "frame": __class__.style_frame,
            "label": __class__.style_label,
            "button": __class__.style_button,
            "checkbutton": __class__.style_checkbutton,
        }

        def style_tree(widget: tk.Widget) -> None:
            """Style the specified tk.Widget and its children."""
            widget_kind = widget.widgetName
            styler = widget_stylers[widget_kind]
            styler(widget, theme_palette)

            if widget.children:
                for child in widget.children.values():
                    style_tree(child)

        style_tree(tk_widget)

    @staticmethod
    def style_frame(frame: tk.Frame, style_palette: dict) -> None:
        """Style a tk.Frame using the specified colors."""
        color_name_for_visual = __class__.palette_color_name_for_visual
        frame_color = style_palette[color_name_for_visual["background"]]
        if frame.winfo_name() == __class__.toolbar_border_name:
            frame_color = style_palette[color_name_for_visual["xtra_window_fg"]]
        frame.configure(
            {
                "background": frame_color,
            }
        )

    @staticmethod
    def style_label(label: tk.Label, style_palette: dict) -> None:
        """Style a tk.Label using the specified colors."""
        color_name_for_visual = __class__.palette_color_name_for_visual
        label.configure(
            {
                "background": style_palette[color_name_for_visual["background"]],
                "foreground": style_palette[color_name_for_visual["foreground"]],
                "font": font.Font(weight="bold"),
            }
        )

    @staticmethod
    def style_button(button: tk.Button, style_palette: dict) -> None:
        """Style a tk.Button using the specified colors."""
        color_name_for_visual = __class__.palette_color_name_for_visual
        press_color = __class__.change_color_luminance(style_palette[color_name_for_visual["background"]], -20)
        button.configure(
            {
                "background": style_palette[color_name_for_visual["background"]],
                "activebackground": press_color,  # Mouse down
            }
        )

    @staticmethod
    def style_checkbutton(checkbutton: tk.Checkbutton, style_palette: dict) -> None:
        """Style a tk.Checkbutton using the specified colors."""
        color_name_for_visual = __class__.palette_color_name_for_visual
        press_color = __class__.change_color_luminance(style_palette[color_name_for_visual["background"]], -20)
        checkbutton.configure(
            {
                "background": style_palette[color_name_for_visual["background"]],
                "activebackground": press_color,  # Mouse down
                "selectcolor": style_palette[color_name_for_visual["selectcolor"]],  # Active selection
            }
        )

    @staticmethod
    def change_color_luminance(button_neutral_color: str, delta: int) -> str:
        """Return a new hex color code that represents a pressed button's color."""
        as_hsl = ttk_colorutils.color_to_hsl(button_neutral_color, model="hex")
        new_luminance = as_hsl[-1] + delta
        press_color = ttk_colorutils.update_hsl_value(button_neutral_color, lum=new_luminance, inmodel="hex", outmodel="hex")
        if not isinstance(press_color, str):
            raise TypeError()
        return press_color

    @staticmethod
    def inspect_visual_style(frame: tk.Widget) -> dict:
        """Get visual configuration details for the specified frame and its children."""
        # >>> list(toolbar.children.keys())
        # <<< ['!button', '!button2', '!button3', '!frame', '!checkbutton-1', '!checkbutton-2', '!button4', '!frame2', '!button5', '!label', '!label2']
        #                      button       frame     checkbutton    label
        #  activebackground      x                       x             x
        #  activeforeground      x                       x             x
        #  background            x            x          x             x
        #  disabledforeground    x                       x             x
        #  foreground            x                       x             x
        #  highlightbackground   x            x          x             x
        #  highlightcolor        x            x          x             x
        #  highlightthickness    x            x          x             x
        #  selectcolor                                   x
        theme_properties = [
            "activebackground",
            "activeforeground",
            "background",
            "disabledforeground",
            "foreground",
            "highlightbackground",
            "highlightcolor",
            "highlightthickness",
            "selectcolor",
            "text",
            "command",
        ]
        frame_configuration = {
            child_name: widget.configure() for child_name, widget in frame.children.items()
        }
        visual_configuration = {}
        for widget_name, widget_configuration in frame_configuration.items():
            for option_name, option_configuration in widget_configuration.items():
                if option_name not in theme_properties:
                    continue
                widget_visual_configuration = visual_configuration.get(widget_name, {})
                widget_visual_configuration[option_name] = option_configuration
                visual_configuration[widget_name] = widget_visual_configuration
        return visual_configuration

    @staticmethod
    def show_palette(palette: dict) -> None:
        """Show the hex color codes for the specified palette."""
        color_names = sorted(ttk.Colors.label_iter())
        _ = [logger.info(f"{color:>12} {palette.get(color)}") for color in color_names]


def toggle_visual_debug(frame: tk.Widget) -> None:##
    """Show or hide the border around the specified frame for visual debugging."""
    live_borderwidth = frame.cget("borderwidth")
    new_borderwidth = 1 if live_borderwidth == 0 else 0
    frame.configure(
        {
            "borderwidth": new_borderwidth,
            "relief": tk.FLAT,
        }
    )


class PlottingApp(guikit.AsyncWindow):
    """Tkinter GUI demonstrating an interactive matplotlib graph."""

    def create_user_interface(self) -> None:  # noqa: PLR0915 -- allow long function to create the UI
        """Create the main window and connect event handlers."""
        self.root_window.title("Embed Matplotlib in ttk")
        self.root_window.minsize(width=860, height=600)
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
        title_label = ttk.Label(main, text="Matplotlib styled by ttkbootstrap", font=title_font)
        title_label.grid(column=0, row=0)

        slider_frame = ttk.Frame(main, name="slider_frame")
        slider_frame.grid(column=0, row=1, sticky=tk.N, pady=(16, 16))

        slider_label = ttk.Label(slider_frame, text="Frequency (f)")
        slider_label.grid(column=0, row=0, padx=(0, 4))

        slider_update = ttk.Scale(slider_frame, from_=.001, to=.01, orient=tk.HORIZONTAL, command=self.update_frequency)
        slider_update.grid(column=1, row=0, padx=(4, 0))

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
        self.t = np.arange(0, 1200, .1)
        self.line, = ax.plot(
            self.t,
            1000 * np.sin(2 * np.pi * self.t * .001),
            label="y = 1000*sin(2*pi * f * t)",
        )
        ax.legend(
            title="Plot",
            loc="upper left",
            draggable=True,
        )

        self.canvas = MatplotlibBootstrap.create_styled_plot_canvas(fig, canvas_frame)
        self.canvas.get_tk_widget().grid(column=0, row=0, sticky=tk.NSEW)
        self.canvas.mpl_connect("key_press_event", lambda event: print(f"Received {event.key}"))  # type: ignore # noqa T201 -- allow printing to demonstrate event handling
        self.canvas.mpl_connect("key_press_event", key_press_handler)  # pyright: ignore reportArgumentType -- matplotlib type annotations are also a little too strict

        toolbar_row = ttk.Frame(main, name="toolbar_row")
        toolbar_row.grid(column=0, row=3, padx=(40, 80), sticky=tk.EW)
        toolbar_row.columnconfigure(0, weight=1)
        toolbar_row.columnconfigure(1, weight=0)

        side_spacer = ttk.Frame(toolbar_row, name="side_spacer", width=1, height=1)
        side_spacer.grid(column=0, row=0, sticky=tk.NSEW)
        side_spacer.columnconfigure(0, weight=1)
        side_spacer.columnconfigure(1, weight=0)
        side_spacer.rowconfigure(0, weight=1)

        combobox_label = ttk.Label(side_spacer, text="Theme")
        combobox_label.grid(column=0, row=0, sticky=tk.NE, padx=(0, 8), pady=(5, 0))

        self.theme_combobox = guikit.create_theme_combobox(side_spacer)
        self.theme_combobox.grid(column=1, row=0, sticky=tk.NE, padx=(0, 32))

        toolbar_frame = MatplotlibBootstrap.create_styled_plot_toolbar(toolbar_row, self.canvas)
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
