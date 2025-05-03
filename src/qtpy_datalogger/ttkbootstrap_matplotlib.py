"""Functions for applying ttkbootstrap styling to matplotlib visuals."""

import logging
import tkinter as tk
from enum import StrEnum
from tkinter import font

import ttkbootstrap as ttk
import ttkbootstrap.colorutils as ttk_colorutils
import ttkbootstrap.themes.standard as ttk_themes
from matplotlib.axes import Axes
from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg,
    NavigationToolbar2Tk,  # pyright: ignore reportPrivateImportUsage -- matplotlib exposes this indirectly
)
from matplotlib.figure import Figure
from ttkbootstrap import constants as bootstyle

logger = logging.getLogger(__name__)


class ReservedName(StrEnum):
    """Reserved names used to implement matplotlib styling."""

    EmbeddedFigure = "mpl_figure_canvas"
    ToolbarBorder = "toolbar_border"


palette_color_key = {
    "background": bootstyle.LIGHT,  # The buttons in the toolbar only re-color themselves on creation, so force a light background color for all themes
    "foreground": bootstyle.DARK,  # Likewise, force a dark foreground color in text labels for all themes so that the (x, y) indicator remains readable
    "selectcolor": bootstyle.PRIMARY,
    "xtra_window_bg": "bg",  # bootstyle themes define "bg" but the library's constants omit them
    "xtra_window_fg": "fg",  # bootstyle themes define "fg" but the library's constants omit them
}


def create_styled_plot_canvas(
    figure: Figure,
    canvas_frame: ttk.Frame,
) -> FigureCanvasTkAgg:
    """Return a FigureCanvasTkAgg from matplotlib that responds to the ttkbootstrap '<<ThemeChanged>>' event."""
    canvas = FigureCanvasTkAgg(figure, canvas_frame)
    setattr(canvas.get_tk_widget(), ReservedName.EmbeddedFigure, canvas)
    canvas.get_tk_widget().grid(column=0, row=0, sticky=tk.NSEW)
    canvas.get_tk_widget().bind("<Expose>", handle_theme_changed)
    canvas.get_tk_widget().bind("<<ThemeChanged>>", handle_theme_changed)
    return canvas


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

    toolbar_border = tk.Frame(parent, name=ReservedName.ToolbarBorder, width=final_width, height=final_height)
    toolbar_border.columnconfigure(0, weight=0, minsize=final_width)
    toolbar_border.rowconfigure(0, weight=0, minsize=final_height)
    toolbar_border.grid_propagate(False)  # Lock the height and width by ignoring child size requests
    toolbar_border.bind("<<ThemeChanged>>", handle_theme_changed)

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
    toolbar = NavigationToolbar2Tk(
        matching_canvas,
        toolbar_frame,
        pack_toolbar=False,  # Use pack_toolbar=False for explicit placement
    )
    toolbar.grid(column=1, row=0, sticky=tk.NSEW)

    return toolbar_border


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
        apply_figure_style(sender, requested_theme)
    elif sender_is_toolbar:
        apply_toolbar_style(sender, requested_theme)
    else:
        raise TypeError()


def apply_figure_style(canvas: tk.Canvas, requested_theme: dict) -> None:
    """Apply the specified theme to the specified matplotlib figure canvas."""
    mpl_figure_canvas = getattr(canvas, ReservedName.EmbeddedFigure, None)
    if not mpl_figure_canvas:
        # Nothing to style
        return

    theme_palette = requested_theme["colors"]
    fill_color = theme_palette[palette_color_key["xtra_window_bg"]]
    plot_area_color = theme_palette[palette_color_key["background"]]
    text_color = theme_palette[palette_color_key["xtra_window_fg"]]

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


def apply_toolbar_style(tk_widget: tk.Widget, requested_theme: dict) -> None:
    """Apply the specified theme to the specified tk.Frame."""
    theme_palette = requested_theme["colors"]
    style_tree(tk_widget, theme_palette)


def style_tree(widget: tk.Widget, theme_palette: dict[str, str]) -> None:
    """Style the specified tk.Widget and its children."""
    if isinstance(widget, tk.Frame):
        style_frame(widget, theme_palette)
    elif isinstance(widget, tk.Label):
        style_label(widget, theme_palette)
    elif isinstance(widget, tk.Button):
        style_button(widget, theme_palette)
    elif isinstance(widget, tk.Checkbutton):
        style_checkbutton(widget, theme_palette)
    else:
        raise TypeError()

    if widget.children:
        for child in widget.children.values():
            style_tree(child, theme_palette)

def style_frame(frame: tk.Frame, style_palette: dict) -> None:
    """Style a tk.Frame using the specified colors."""
    frame_color = style_palette[palette_color_key["background"]]
    if frame.winfo_name() == ReservedName.ToolbarBorder:
        frame_color = style_palette[palette_color_key["xtra_window_fg"]]
    frame.configure(
        {
            "background": frame_color,
        }
    )


def style_label(label: tk.Label, style_palette: dict) -> None:
    """Style a tk.Label using the specified colors."""
    label.configure(
        {
            "background": style_palette[palette_color_key["background"]],
            "foreground": style_palette[palette_color_key["foreground"]],
            "font": font.Font(weight="bold"),
        }
    )


def style_button(button: tk.Button, style_palette: dict) -> None:
    """Style a tk.Button using the specified colors."""
    press_color = change_color_luminance(style_palette[palette_color_key["background"]], -20)
    button.configure(
        {
            "background": style_palette[palette_color_key["background"]],
            "activebackground": press_color,  # Mouse down
        }
    )


def style_checkbutton(checkbutton: tk.Checkbutton, style_palette: dict) -> None:
    """Style a tk.Checkbutton using the specified colors."""
    press_color = change_color_luminance(style_palette[palette_color_key["background"]], -20)
    checkbutton.configure(
        {
            "background": style_palette[palette_color_key["background"]],
            "activebackground": press_color,  # Mouse down
            "selectcolor": style_palette[palette_color_key["selectcolor"]],  # Active selection
        }
    )


def change_color_luminance(original_color: str, delta: int) -> str:
    """Return a new hex color code that represents the same color with a changed brightness."""
    as_hsl = ttk_colorutils.color_to_hsl(original_color, model="hex")
    new_luminance = as_hsl[-1] + delta
    new_color = ttk_colorutils.update_hsl_value(
        original_color,
        lum=new_luminance,
        inmodel="hex",
        outmodel="hex",
    )
    if not isinstance(new_color, str):
        raise TypeError()
    return new_color
