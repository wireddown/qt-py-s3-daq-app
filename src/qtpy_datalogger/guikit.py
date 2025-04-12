"""Shared classes and helpers for creating GUIs."""

import asyncio
import tkinter as tk

import ttkbootstrap as ttk
import ttkbootstrap.icons as ttk_icons
from ttkbootstrap import constants as bootstyle


class AsyncApp:
    """A Tk application wrapper that cooperates with asyncio."""

    @staticmethod
    async def create_and_run(ui_window_type: type) -> None:
        """
        Run the Tk Window cooperatively with asyncio.

        Create a new instance of ui_window within an asynchronous function so that
        the new instance can use the asyncio event loop. Creating one outside an
        asynchronous function prevents the new instance from using async code
        because asyncio has not created or started an event loop.

        The base type of ui_window must be an AsyncWindow to use cooperative event handling.
        """
        window = ui_window_type()
        window.create_user_interface()
        await window.show()


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
        self.root_window = ttk.Window(iconphoto=None)  # pyright: ignore reportArgumentType -- the type hint for library is incorrect
        self.io_loop = asyncio.get_running_loop()

        self.should_run_loop = True

        def __on_closing() -> None:
            self.on_closing()
            self.exit()

        self.root_window.protocol("WM_DELETE_WINDOW", __on_closing)

    async def show(self) -> None:
        """Show the UI and cooperatively run with asyncio."""
        while self.should_run_loop:
            await asyncio.sleep(0)
            await self.on_loop()
            self.root_window.update()
        self.root_window.quit()

    def create_user_interface(self) -> None:
        """Create the layout and widget event handlers."""

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

        self.label = ttk.Label(self.root, text="")
        self.label.grid(
            row=0,
            columnspan=2,
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
            columnspan=2,
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

        button_non_block = ttk.Button(
            self.root,
            text="Async",
            width=10,
            style=bootstyle.INFO,
            command=lambda: self.io_loop.create_task(self.calculate_async()),
        )
        button_non_block.grid(
            row=2,
            column=1,
            sticky=tk.E,
            padx=8,
            pady=8,
        )

        self.root.pack()

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


if __name__ == "__main__":
    asyncio.run(AsyncApp.create_and_run(DemoWithAnimation))
