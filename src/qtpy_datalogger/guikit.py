"""Shared classes and helpers for creating GUIs."""

import asyncio
import enum
import functools
import json
import logging
import tkinter as tk
import webbrowser
from collections.abc import Callable
from tkinter import font

import ttkbootstrap as ttk
import ttkbootstrap.icons as ttk_icons
import ttkbootstrap.style as ttk_style
import ttkbootstrap.themes.standard as ttk_themes
from tkfontawesome import icon_to_image
from ttkbootstrap import constants as bootstyle

from qtpy_datalogger import datatypes

logger = logging.getLogger(__name__)


class StyleKey(enum.StrEnum):
    """A class that extends the palette names of ttkbootstrap styles."""

    Fg = "fg"
    SelectFg = "selectfg"


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

        Example:
        asyncio.run(AsyncApp.create_and_run(AsyncWindowSubclass))

        """
        if not issubclass(async_window_type, AsyncWindow):
            raise TypeError()

        app = async_window_type()
        app.create_user_interface()
        app.root_window.update_idletasks()
        await app.show()


class DialogBehavior(enum.StrEnum):
    """
    Supported behaviors for AsyncDialogs.

    Modal:
    Prevent input to all other app windows until dismissed. Hide the maximize and minimize buttons and the icon in the Windows task bar.

    Modeless:
    Allow input to all other app windows. Hide the maximize and minimize buttons and the icon in the Windows task bar.

    Standalone:
    Allow input to all other app windows. Show the maximize and minimize buttons and the icon in the Windows task bar.

    All dialogs close when the the main parent window closes.
    """

    Modal = "Modal"
    Modeless = "Modeless"
    Standalone = "Standalone"


class AsyncDialog:
    """
    A Tk Toplevel wrapper that cooperates with asyncio.

    Define a subclass of AsyncDialog and override both create_user_interface() and
    async on_loop() to create a dialog with Tk that cooperates with asyncio APIs.

    Call show() to present the dialog and retrieve its result after it closes. To set
    the result, assign a value to self.result in on_loop() or on_closing().

    Override set_position() to place the dialog before presentation. Call exit() to
    close the dialog.

    Required overrides
    - create_user_interface(self)

    Remaining overrides
    - set_position(self)
    - async on_loop(self)
    - on_closing(self)

    Helper methods
    - self.exit()
    """

    def __init__(self, parent: ttk.Toplevel | ttk.Window, title: str) -> None:
        """Initialize a new Tk Toplevel and cache the asyncio event loop."""
        self.parent = parent
        self.root_window = ttk.Toplevel(master=self.parent, title=title)
        self.root_window.withdraw()

        self.io_loop = asyncio.get_running_loop()
        self.should_run_loop = True

        def __on_closing(event: tk.Event | None = None) -> None:
            self.exit()

        self.root_window.protocol("WM_DELETE_WINDOW", __on_closing)
        self.root_window.bind("<Escape>", __on_closing)

        self.result = None
        self.initial_focus = self.root_window
        self.create_user_interface()
        self.root_window.update_idletasks()  # Calculate geometry and size information

    async def show(self, behavior: DialogBehavior) -> object | None:
        """Show the dialog and cooperatively run with asyncio."""
        if behavior != DialogBehavior.Standalone and self.parent.winfo_viewable():
            self.root_window.transient(self.parent)

        self.set_position()
        self.root_window.deiconify()  # Render and present
        self.initial_focus.focus_set()
        self.root_window.wait_visibility()

        if behavior == DialogBehavior.Modal:
            self.root_window.grab_set()

        while self.should_run_loop:
            await asyncio.sleep(0)
            await self.on_loop()
            self.root_window.update()

        self.on_closing()
        self.parent.focus_set()
        self.root_window.destroy()
        return self.result

    def set_position(self) -> None:
        """Set the dialog's position."""
        parent_x = self.parent.winfo_rootx()
        parent_y = self.parent.winfo_rooty()
        x_pos = parent_x + 100
        y_pos = parent_y + 50
        self.root_window.geometry(f"+{x_pos}+{y_pos}")

    def create_user_interface(self) -> None:
        """Create the layout and widget event handlers."""

    async def on_loop(self) -> None:
        """Update dialog elements and poll asyncio resources."""

    def on_closing(self) -> None:
        """Finalize the dialog result after exiting the main loop."""

    def exit(self) -> None:
        """Close the dialog and exit."""
        self.should_run_loop = False


class AsyncWindow:
    """
    A Tk root window wrapper that cooperates with asyncio.

    Define a subclass of AsyncWindow and override both create_user_interface() and
    async on_loop() to create a GUI with Tk that cooperates with asyncio APIs.

    Required overrides
    - create_user_interface(self)

    Remaining overrides
    - on_show()
    - async on_loop(self)
    - on_closing(self)

    Helper methods
    - self.exit()

    Example:
    asyncio.run(AsyncApp.create_and_run(AsyncWindowSubclass))

    """

    def __init__(self) -> None:
        """Initialize a new Tk root and cache the asyncio event loop."""
        # Let subclasses set the window icon
        self.root_window = ttk.Window(iconphoto=None)
        self.root_window.withdraw()

        self.io_loop = asyncio.get_running_loop()
        self.should_run_loop = True

        def __on_closing() -> None:
            self.exit()

        self.root_window.protocol("WM_DELETE_WINDOW", __on_closing)

    async def show(self) -> None:
        """Show the window and cooperatively run with asyncio."""
        self.on_show()
        self.root_window.deiconify()
        self.root_window.wait_visibility(self.root_window)

        while self.should_run_loop:
            await asyncio.sleep(0)
            await self.on_loop()
            self.root_window.update()

        self.on_closing()
        self.root_window.quit()

    def create_user_interface(self) -> None:
        """Create the layout and widget event handlers."""

    def on_show(self) -> None:
        """Initialize the window before entering main loop."""

    async def on_loop(self) -> None:
        """Update window elements and poll asyncio resources."""

    def on_closing(self) -> None:
        """Finalize the window after exiting main loop."""

    def exit(self) -> None:
        """Close the window and exit."""
        self.should_run_loop = False


class AboutDialog(AsyncDialog):
    """A class that presents information about the app."""

    def __init__(  # noqa PLR0913 -- allow many parameters for a framework class
        self,
        parent: ttk.Toplevel | ttk.Window,
        app_name: str = "",
        app_icon: str = "",
        all_icons: list[str] | None = None,
        help_url: str = "",
        source_url: str = "",
    ) -> None:
        """Initialize a new AboutDialog instance."""
        self.app_name = app_name
        if not app_icon:
            app_icon = "chart-line"
        if not all_icons:
            all_icons = ["microchip", "worm", app_icon]
        self.app_icons = all_icons[:3]
        self.app_icon_images = []
        self.help_url = help_url or datatypes.Links.Homepage
        self.source_url = source_url or datatypes.Links.Source
        self.copy_version_text = "Copy version"
        super().__init__(parent, f"About {app_name}".strip())

    def create_user_interface(self) -> None:  # noqa: PLR0915 -- allow long function to create the UI
        """Create the UI for the AboutDialog."""
        self.root_window.columnconfigure(0, weight=1)
        self.root_window.rowconfigure(0, weight=1)
        self.root_window.resizable(width=False, height=False)
        main_frame = ttk.Frame(self.root_window, padding=16)
        main_frame.grid(column=0, row=0, sticky=tk.NSEW)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)

        message_frame = ttk.Frame(main_frame)
        message_frame.grid(column=0, row=0, sticky=tk.NSEW)
        message_frame.columnconfigure(0, weight=0, minsize=40)  # Filler
        message_frame.columnconfigure(1, weight=0)  # Icon1
        message_frame.columnconfigure(2, weight=0)  # Icon2
        message_frame.columnconfigure(3, weight=0)  # Icon3
        message_frame.columnconfigure(4, weight=0, minsize=20)  # Filler
        message_frame.columnconfigure(5, weight=0)  # Text
        message_frame.columnconfigure(6, weight=0, minsize=40)  # Filler
        message_frame.rowconfigure(0, weight=0, minsize=20)  # Filler
        message_frame.rowconfigure(1, weight=0)  # Icons and Name
        message_frame.rowconfigure(2, weight=0)  # Icons and Version
        message_frame.rowconfigure(3, weight=0)  # Separator
        message_frame.rowconfigure(4, weight=0)  # Help
        message_frame.rowconfigure(5, weight=0)  # Source
        message_frame.rowconfigure(6, weight=0)  # Source2
        message_frame.rowconfigure(7, weight=0, minsize=50)  # Filler

        icon_height = 48
        icon_color = hex_string_for_style(StyleKey.Fg)
        icon_column = 3
        for icon_name in reversed(self.app_icons):
            icon_image = icon_to_image(icon_name, fill=icon_color, scale_to_height=icon_height)
            self.app_icon_images.append(icon_image)
            chart_label = ttk.Label(message_frame, image=icon_image, padding=4)
            chart_label.grid(column=icon_column, row=1, rowspan=2)
            icon_column = icon_column - 1

        name_label = ttk.Label(message_frame, font=font.Font(weight="bold", size=28), text=self.app_name)
        name_label.grid(column=5, row=1, sticky=tk.W)
        self.notice_information = datatypes.SnsrNotice.get_package_notice_info(allow_dev_version=True)
        bullet = ttk_icons.Emoji.get("black medium small square")
        version_label = ttk.Label(
            message_frame,
            text=f"{self.notice_information.version} {bullet} {self.notice_information.timestamp:%Y-%m-%d} {bullet} {self.notice_information.commit}",
        )
        version_label.grid(column=5, row=2, sticky=tk.W, padx=(2, 0))
        separator = ttk.Separator(message_frame)
        separator.grid(column=1, row=3, columnspan=5, sticky=tk.EW, pady=4)
        button_text_color = hex_string_for_style(StyleKey.SelectFg)
        spacer = "   "
        self.help_icon = icon_to_image("parachute-box", fill=button_text_color, scale_to_width=16)
        help_button = ttk.Button(
            message_frame,
            compound=tk.LEFT,
            image=self.help_icon,
            text=f"{spacer}Online help ",  # The trailing space helps with internal margins
            style=bootstyle.INFO,
            width=18,
            command=functools.partial(webbrowser.open_new_tab, self.help_url),
        )
        help_button.grid(column=5, row=4, sticky=tk.W, pady=(18, 0))
        self.source_icon = icon_to_image("github-alt", fill=button_text_color, scale_to_width=16)
        source_button = ttk.Button(
            message_frame,
            compound=tk.LEFT,
            image=self.source_icon,
            text=f"{spacer}Source code",
            style=bootstyle.INFO,
            width=18,
            command=functools.partial(webbrowser.open_new_tab, self.source_url),
        )
        source_button.grid(column=5, row=5, sticky=tk.W, pady=(22, 0))

        button_frame = ttk.Frame(main_frame)
        button_frame.grid(column=0, row=1, sticky=tk.NSEW, padx=(0, 16), pady=(8, 0))
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=0)
        button_frame.rowconfigure(0, weight=0)
        self.copy_version_button = ttk.Button(
            button_frame,
            text=self.copy_version_text,
            style=bootstyle.OUTLINE,
            command=self.copy_version,
            width=12,
        )
        self.copy_version_button.grid(column=0, row=0, sticky=tk.E, padx=(0, 16))
        ok_button = ttk.Button(button_frame, text="OK", command=self.exit)
        ok_button.grid(column=1, row=0, sticky=tk.E)
        self.initial_focus = ok_button

    def copy_version(self) -> None:
        """Copy the version information to the clipboard."""
        formatted_version = {
            "version": self.notice_information.version,
            "timestamp": str(self.notice_information.timestamp),
            "commit": self.notice_information.commit,
        }
        self.parent.clipboard_clear()
        self.parent.clipboard_append(json.dumps(formatted_version))
        status_emoji = ttk_icons.Emoji.get("white heavy check mark")
        self.copy_version_button.configure(text=f"{status_emoji}   Copied!", bootstyle=bootstyle.SUCCESS)
        self.copy_version_button.after(
            850,
            functools.partial(
                self.copy_version_button.configure,
                text=self.copy_version_text,
                bootstyle=(bootstyle.DEFAULT, bootstyle.OUTLINE),  # pyright: ignore callIssue -- the type hints do not understand tuples
            ),
        )

    async def on_loop(self) -> None:
        """Update UI elements."""
        await asyncio.sleep(20e-3)


class ThemeChanger:
    """A class that changes Tk themes and emits a corresponding event."""

    class Event(enum.StrEnum):
        """An enumeration of events emitted by this class."""

        BootstrapThemeChanged = "<<BootstrapThemeChanged>>"

    @staticmethod
    def add_handler(owner: tk.Misc, command: Callable[[tk.Event], None]) -> str:
        """Subscribe command as a handler for the BootstrapThemeChanged event and return a unique ID for the binding."""
        # **Must** bind to the application, emit to the root window, add to the handler list
        # - See https://stackoverflow.com/a/31798918
        return owner.winfo_toplevel().bind_all(ThemeChanger.Event.BootstrapThemeChanged, command, add="+")

    @staticmethod
    def use_bootstrap_theme(new_theme: str, owner: tk.Misc) -> None:
        """Change the ttkbootstrap theme and notify BootstrapThemeChanged subscribers."""
        ttk.Style().theme_use(new_theme)
        owner.winfo_toplevel().event_generate(ThemeChanger.Event.BootstrapThemeChanged)


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
        main_frame, self.label, self.progressbar = create_demo_ui(self.root_window, self.io_loop)

        modal_button = ttk.Button(
            main_frame,
            text="Modal",
            command=functools.partial(self.open_dialog, DialogBehavior.Modal),
            style=(bootstyle.SECONDARY, bootstyle.INFO),  # pyright: ignore reportArgumentType -- the type hints do not understand tuples
        )
        modal_button.grid(column=0, row=3, sticky=tk.EW, padx=8)

        modeless_button = ttk.Button(
            main_frame,
            text="Modeless",
            command=functools.partial(self.open_dialog, DialogBehavior.Modeless),
            style=(bootstyle.SECONDARY, bootstyle.INFO),  # pyright: ignore reportArgumentType -- the type hints do not understand tuples
        )
        modeless_button.grid(column=1, row=3, sticky=tk.EW, pady=8)

        standalone_button = ttk.Button(
            main_frame,
            text="Standalone",
            command=functools.partial(self.open_dialog, DialogBehavior.Standalone),
            style=bootstyle.SECONDARY,
        )
        standalone_button.grid(column=2, row=3, sticky=tk.EW, padx=8)

    async def on_loop(self) -> None:
        """Update the animation."""
        self.label["text"] = self.animation
        self.animation = self.animation[-1] + self.animation[0:-1]
        await asyncio.sleep(0.06)

    def open_dialog(self, behavior: DialogBehavior) -> None:
        """Open an AsyncDialog using the specified Behavior."""
        dialog = DialogWithAnimation(self.root_window, title=f"{behavior} dialog")
        self.io_loop.create_task(dialog.show(behavior))


class DialogWithAnimation(AsyncDialog):
    """Host synchronous and asynchronous calls in a dialog."""

    def __init__(self, parent: ttk.Toplevel | ttk.Window, title: str) -> None:
        """Call the parent initializer."""
        super().__init__(parent, title)

    def create_user_interface(self) -> None:
        """Create text label to animate and define buttons to demonstrate blocking vs async calls."""
        self.animation = "⬛⬛⬛⬛⬛⬛⬛⬛⬛⬜⬜"
        _, self.label, self.progressbar = create_demo_ui(self.root_window, self.io_loop)

    async def on_loop(self) -> None:
        """Update the animation."""
        self.label["text"] = self.animation
        self.animation = self.animation[-1] + self.animation[0:-1]
        await asyncio.sleep(0.06)


def create_demo_ui(
    root_window: ttk.Window | ttk.Toplevel, io_loop: asyncio.AbstractEventLoop
) -> tuple[ttk.Frame, ttk.Label, ttk.Progressbar]:
    """Create a demo UI and return its dynamic elements."""
    root = ttk.Frame(root_window, padding=10)
    root.pack()

    label = ttk.Label(root, text="")
    label.grid(
        row=0,
        columnspan=3,
        padx=(8, 8),
        pady=(8, 0),
    )

    progressbar = ttk.Progressbar(
        root,
        length=280,
        style=(bootstyle.STRIPED, bootstyle.SUCCESS),  # pyright: ignore reportArgumentType -- the type hints do not understand tuples
    )
    progressbar.grid(
        row=1,
        columnspan=3,
        padx=(8, 8),
        pady=(16, 0),
    )

    button_block = ttk.Button(
        root,
        text="Sync",
        width=10,
        style=bootstyle.PRIMARY,
        command=functools.partial(calculate_sync, progressbar),
    )
    button_block.grid(
        row=2,
        column=0,
        sticky=tk.W,
        padx=8,
        pady=8,
    )

    theme_combobox = create_theme_combobox(root)
    theme_combobox.grid(
        row=2,
        column=1,
    )

    button_non_block = ttk.Button(
        root,
        text="Async",
        width=10,
        style=bootstyle.INFO,
        command=lambda: io_loop.create_task(calculate_async(progressbar)),
    )
    button_non_block.grid(
        row=2,
        column=2,
        sticky=tk.E,
        padx=8,
        pady=8,
    )
    return root, label, progressbar


def calculate_sync(progressbar: ttk.Progressbar) -> None:
    """Run without yielding to other waiting tasks."""
    limit = 1200000
    for i in range(1, limit):
        progressbar["value"] = i / limit * 100
    progressbar.after(850, functools.partial(progressbar.configure, value=0))


async def calculate_async(progressbar: ttk.Progressbar) -> None:
    """Run but regularly yield execution to other waiting tasks."""
    limit = 1200000
    for i in range(1, limit):
        progressbar["value"] = i / limit * 100
        if i % 1000 == 0:
            await asyncio.sleep(0)
    progressbar.after(850, functools.partial(progressbar.configure, value=0))


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
            light_themes.append(theme_name.capitalize())
        elif theme_kind == "dark":
            dark_themes.append(theme_name.capitalize())
        else:
            raise ValueError()
    sorted_by_kind = [*sorted(light_themes), *sorted(dark_themes)]

    theme_combobox = ttk.Combobox(
        parent,
        width=12,
        values=sorted_by_kind,
    )
    theme_combobox.set(active_theme.name.capitalize())
    theme_combobox.configure(state=bootstyle.READONLY)
    theme_combobox.selection_clear()

    def handle_change_theme(event_args: tk.Event) -> None:
        """Handle the selection event for the theme Combobox."""
        sending_combobox = event_args.widget
        if not isinstance(sending_combobox, ttk.Combobox):
            raise TypeError()
        theme_name = sending_combobox.get().lower()
        sending_combobox.configure(state=bootstyle.READONLY)
        sending_combobox.selection_clear()
        ThemeChanger.use_bootstrap_theme(theme_name, sending_combobox)

    def on_theme_changed(themed_widget: tk.Misc, event_args: tk.Event) -> None:
        """Handle the ThemeChanger.Event.BootstrapThemeChanged event."""
        sending_combobox = themed_widget
        if not isinstance(sending_combobox, ttk.Combobox):
            raise TypeError()
        style = ttk.Style.get_instance()
        if not (style and style.theme):
            raise ValueError()
        sending_combobox.set(style.theme.name.capitalize())

    theme_combobox.bind("<<ComboboxSelected>>", handle_change_theme)
    ThemeChanger.add_handler(theme_combobox, functools.partial(on_theme_changed, theme_combobox))
    return theme_combobox


def hex_string_for_style(style_name: str, theme_name: str = "") -> str:
    """Return the '#RRGGBB' string for the specified style name for the active or specified theme."""
    if not theme_name:
        style = ttk.Style.get_instance()
        if not (style and style.theme):
            raise ValueError()
        theme_name = style.theme.name
    palette = ttk_themes.STANDARD_THEMES[theme_name]["colors"]
    return palette[style_name]


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
    color_names = sorted(ttk_style.Colors.label_iter())
    _ = [logger.info(f"{color:>12} {palette.get(color)}") for color in color_names]


if __name__ == "__main__":
    asyncio.run(AsyncApp.create_and_run(DemoWithAnimation))
