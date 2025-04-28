"""Shared classes and helpers for creating GUIs."""

import asyncio
import logging
import tkinter as tk

import ttkbootstrap as ttk
import ttkbootstrap.icons as ttk_icons
import ttkbootstrap.themes.standard as ttk_themes
from ttkbootstrap import constants as bootstyle

logger = logging.getLogger(__name__)


class AsyncApp:
    """A Tk application wrapper that cooperates with asyncio."""

    @staticmethod
    async def create_and_run(async_window_type: type) -> None:
        """
        Create and run an AsyncWindow cooperatively with asyncio.

        Create a new instance of async_window_type within an asynchronous function so that
        the new instance can use the asyncio event loop. Creating one outside an
        asynchronous function prevents the new instance from using async code
        because asyncio has not created or started an event loop.

        The base type of async_window_type must be an AsyncWindow to use cooperative event handling.
        """
        if not issubclass(async_window_type, AsyncWindow):
            raise TypeError()
        app = async_window_type()

        # Create and layout the UI
        app.root_window.withdraw()
        app.create_user_interface()
        app.root_window.update()

        # Present the UI
        app.root_window.deiconify()
        await app.show()


class AsyncWindow:
    """
    A Tk root window wrapper that cooperates with asyncio.

    Define a subclass of AsyncWindow to create a GUI with Tk that cooperates with asyncio code.

    Required overrides
    - create_user_interface(self) -> None

    Remaining overrides
    - async def on_loop(self) -> None
    - def on_closing(self) -> None

    Helper methods
    - self.exit()

    Example:
    asyncio.run(AsyncApp.create_and_run(AsyncWindowSubclass))

    """

    def __init__(self) -> None:
        """Initialize a new Tk root and cache the asyncio event loop."""
        # Let subclasses set the window icon
        self.root_window = ttk.Window(iconphoto=None)  # pyright: ignore reportArgumentType -- the type hint for library is incorrect
        self.io_loop = asyncio.get_running_loop()

        self.should_run_loop = True

        def __on_closing() -> None:
            self.on_closing()
            self.exit()

        self.root_window.protocol("WM_DELETE_WINDOW", __on_closing)

    async def show(self) -> None:
        """Show the UI and cooperatively run with asyncio."""
        self.root_window.wait_visibility(self.root_window)
        self.root_window.update_idletasks()
        self.on_show()
        while self.should_run_loop:
            await asyncio.sleep(0)
            await self.on_loop()
            self.root_window.update()
        self.root_window.quit()

    def create_user_interface(self) -> None:
        """Create the layout and widget event handlers."""

    def on_show(self) -> None:
        """Initialize UI before entering main loop."""

    async def on_loop(self) -> None:
        """Update UI elements."""

    def on_closing(self) -> None:
        """Handle the click event for the title bar's close button."""

    def exit(self) -> None:
        """Close the UI and exit."""
        self.should_run_loop = False


class DemoWithAnimation(AsyncWindow):
    """Compare synchronous vs asynchronous calls in Tk."""

    def __init__(self) -> None:
        """Call the parent initializer."""
        super().__init__()

    def create_user_interface(self) -> None:
        """Create text label to animate and define buttons to demonstrate blocking vs async calls."""
        self.root_window.title("Async Demo")
        icon = tk.PhotoImage(master=self.root_window, data=ttk_icons.Icon.info)
        self.root_window.iconphoto(True, icon)

        self.animation = "🤍🤍🤍🤍🤍🤍🤍🤍🤍🤍🩶🖤"
        self.root = ttk.Frame(self.root_window, padding=10)
        self.root.pack()

        self.label = ttk.Label(self.root, text="")
        self.label.grid(
            row=0,
            columnspan=3,
            padx=(8, 8),
            pady=(8, 0),
        )

        self.progressbar = ttk.Progressbar(
            self.root,
            length=280,
            style=(bootstyle.STRIPED, bootstyle.SUCCESS),  # pyright: ignore reportArgumentType -- the type hint for library uses strings
        )
        self.progressbar.grid(
            row=1,
            columnspan=3,
            padx=(8, 8),
            pady=(16, 0),
        )

        button_block = ttk.Button(
            self.root,
            text="Sync",
            width=10,
            style=bootstyle.PRIMARY,
            command=self.calculate_sync,
        )
        button_block.grid(
            row=2,
            column=0,
            sticky=tk.W,
            padx=8,
            pady=8,
        )

        theme_combobox = create_theme_combobox(self.root)
        theme_combobox.grid(
            row=2,
            column=1,
        )

        button_non_block = ttk.Button(
            self.root,
            text="Async",
            width=10,
            style=bootstyle.INFO,
            command=lambda: self.io_loop.create_task(self.calculate_async()),
        )
        button_non_block.grid(
            row=2,
            column=2,
            sticky=tk.E,
            padx=8,
            pady=8,
        )

    async def on_loop(self) -> None:
        """Update the animation."""
        self.label["text"] = self.animation
        self.animation = self.animation[-1] + self.animation[0:-1]
        await asyncio.sleep(0.06)

    def calculate_sync(self) -> None:
        """Run without yielding to other waiting tasks."""
        limit = 1200000
        for i in range(1, limit):
            self.progressbar["value"] = i / limit * 100

    async def calculate_async(self) -> None:
        """Run but regularly yield execution to other waiting tasks."""
        limit = 1200000
        for i in range(1, limit):
            self.progressbar["value"] = i / limit * 100
            if i % 1000 == 0:
                await asyncio.sleep(0)


def create_theme_combobox(parent: tk.BaseWidget) -> ttk.Combobox:
    """Create and return a Combobox that lists the available themes and handles the selection event."""
    style = ttk.Style.get_instance()
    if not (style and style.theme):
        raise ValueError()
    active_theme = style.theme
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
    sorted_by_kind = [*sorted(light_themes), *sorted(dark_themes)]

    theme_combobox = ttk.Combobox(
        parent,
        width=12,
        values=sorted_by_kind,
    )
    theme_combobox.set(active_theme.name)
    theme_combobox.configure(state=ttk.READONLY)
    theme_combobox.selection_clear()

    def handle_change_theme(event_args: tk.Event) -> None:
        """Handle the selection event for the theme Combobox."""
        sending_combobox = event_args.widget
        theme_name = sending_combobox.get()
        style = ttk.Style.get_instance()
        if not style:
            raise ValueError()
        sending_combobox.configure(state=ttk.READONLY)
        sending_combobox.selection_clear()
        style.theme_use(theme_name)

    theme_combobox.bind("<<ComboboxSelected>>", handle_change_theme)
    return theme_combobox


def toggle_visual_debug(frame: tk.Widget) -> None:
    """Show or hide the border around the specified frame for visual debugging."""
    live_borderwidth = frame.cget("borderwidth")
    new_borderwidth = 1 if live_borderwidth == 0 else 0
    frame.configure(
        {
            "borderwidth": new_borderwidth,
            "relief": tk.FLAT,
        }
    )


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
    frame_configuration = {child_name: widget.configure() for child_name, widget in frame.children.items()}
    visual_configuration = {}
    for widget_name, widget_configuration in frame_configuration.items():
        for option_name, option_configuration in widget_configuration.items():
            if option_name not in theme_properties:
                continue
            widget_visual_configuration = visual_configuration.get(widget_name, {})
            widget_visual_configuration[option_name] = option_configuration
            visual_configuration[widget_name] = widget_visual_configuration
    return visual_configuration


def show_palette(palette: dict) -> None:
    """Show the hex color codes for the specified palette."""
    color_names = sorted(ttk.Colors.label_iter())
    _ = [logger.info(f"{color:>12} {palette.get(color)}") for color in color_names]


if __name__ == "__main__":
    asyncio.run(AsyncApp.create_and_run(DemoWithAnimation))
