"""A text base user interface for euporie."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, cast

from prompt_toolkit.clipboard import InMemoryClipboard
from prompt_toolkit.clipboard.pyperclip import PyperclipClipboard
from prompt_toolkit.completion import PathCompleter
from prompt_toolkit.filters import Condition, buffer_has_focus
from prompt_toolkit.formatted_text import HTML, fragment_list_to_text, to_formatted_text
from prompt_toolkit.input.defaults import create_input
from prompt_toolkit.key_binding.key_bindings import KeyBindings, merge_key_bindings
from prompt_toolkit.layout import (
    ConditionalContainer,
    DynamicContainer,
    Float,
    FloatContainer,
    HSplit,
    VSplit,
    Window,
    WindowAlign,
    to_container,
)
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.output.defaults import create_output
from prompt_toolkit.widgets import Button, Dialog, Label, SearchToolbar, TextArea
from pyperclip import determine_clipboard  # type: ignore

from euporie import __app_name__, __copyright__, __logo__, __strapline__, __version__
from euporie.app.base import EuporieApp
from euporie.commands.registry import get
from euporie.config import CONFIG_PARAMS, config
from euporie.tabs.log import LogView
from euporie.tabs.notebook import TuiNotebook
from euporie.widgets.decor import Pattern
from euporie.widgets.formatted_text_area import FormattedTextArea
from euporie.widgets.menu import MenuContainer, MenuItem
from euporie.widgets.palette import CommandPalette

if TYPE_CHECKING:
    from asyncio import AbstractEventLoop
    from typing import Any, Callable, Generator, List, Literal, Optional, Tuple, Type

    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.clipboard import Clipboard
    from prompt_toolkit.completion import Completer
    from prompt_toolkit.formatted_text import AnyFormattedText, StyleAndTextTuples
    from prompt_toolkit.input import Input
    from prompt_toolkit.key_binding.key_processor import KeyPressEvent
    from prompt_toolkit.layout.containers import AnyContainer
    from prompt_toolkit.output import Output

    from euporie.tabs.base import Tab
    from euporie.tabs.notebook import Notebook
    from euporie.widgets.cell import InteractiveCell

log = logging.getLogger(__name__)


class TuiApp(EuporieApp):
    """A text user interface euporie application."""

    menu_container: "MenuContainer"
    notebook_class: "Type[Notebook]" = TuiNotebook
    clipboard: "Clipboard"

    def __init__(self, **kwargs: "Any") -> "None":
        """Create a new euporie text user interface application instance."""
        super().__init__(
            full_screen=True,
            mouse_support=True,
            editing_mode=self.get_edit_mode(),
            **kwargs,
        )
        self.has_dialog = False

    async def _poll_terminal_colors(self) -> "None":
        """Repeatedly query the terminal for its background and foreground colours."""
        while config.terminal_polling_interval:
            await asyncio.sleep(config.terminal_polling_interval)
            self.term_info.background_color.send()
            self.term_info.foreground_color.send()

    def load_input(self) -> "Input":
        """Creates the input for this application to use.

        Returns:
            A prompt-toolkit input instance

        """
        return create_input(always_prefer_tty=True)

    def load_output(self) -> "Output":
        """Creates the output for this application to use.

        Returns:
            A prompt-toolkit output instance

        """
        return create_output(always_prefer_tty=True)

    def load_clipboard(self) -> "None":
        """Determines which clipboard mechanism to use."""
        if determine_clipboard()[0]:
            self.clipboard = PyperclipClipboard()
        else:
            self.clipboard = InMemoryClipboard()

    def post_load(self) -> "None":
        """Continues loading the app."""
        # Load a clipboard
        self.load_clipboard()

        # Ensure an opened tab is focused
        if self.tab:
            self.tab.focus()

        # Load style hooks and start polling terminal style
        if self.using_vt100:
            self.term_info.background_color.event += self.update_style
            self.term_info.foreground_color.event += self.update_style
            self.create_background_task(self._poll_terminal_colors())

    def format_title(self) -> "StyleAndTextTuples":
        """Formats the tab's title for display in the top right of the app."""
        if self.tab:
            return [("bold class:status.field", f" {self.tab.title} ")]
        else:
            return []

    def format_status(self, part: "Literal['left', 'right']") -> "StyleAndTextTuples":
        """Formats the fields in the statusbar generated by the current tab.

        Args:
            part: ``'left'`` to return the fields on the left side of the statusbar,
                and ``'right'`` to return the fields on the right

        Returns:
            A list of style and text tuples for display in the statusbar

        """
        entries: "Tuple[List[AnyFormattedText], List[AnyFormattedText]]" = ([], [])
        for container, status_func in self.container_statuses.items():
            if self.layout.has_focus(container):
                entries = status_func()
                break
        else:
            if not self.tabs:
                entries = (
                    [HTML("Press <b>Ctrl+n</b> to start a new notebook")],
                    [HTML("Press <b>Ctrl+q</b> to quit")],
                )

        output: "StyleAndTextTuples" = []
        # Show the tab's status fields
        for field in entries[0 if part == "left" else 1]:
            if field:
                if isinstance(field, tuple):
                    ft = [field]
                else:
                    ft = to_formatted_text(field, style="class:status.field")
                output += [
                    ("class:status.field", " "),
                    *ft,
                    ("class:status.field", " "),
                    ("class:status", " "),
                ]
        if output:
            output.pop()
        return output

    def tab_container(self) -> "AnyContainer":
        """Returns a container with all opened tabs.

        Returns:
            A vertical split containing the opened tab containers.

        """
        if self.tabs:
            return VSplit(
                self.tabs,
                padding=1,
                padding_char=" ",
                padding_style="class:chrome",
            )
        else:
            return Pattern(config.background_character)

    def load_container(self) -> "FloatContainer":
        """Builds the main application layout."""
        have_tabs = Condition(lambda: bool(self.tabs))

        self.logo = Window(
            FormattedTextControl(
                [("", f" {__logo__} ")],
                focusable=~have_tabs,
                show_cursor=False,
                style="class:menu-bar,logo",
            ),
            height=1,
            dont_extend_width=True,
        )

        self.title_bar = ConditionalContainer(
            Window(
                content=FormattedTextControl(self.format_title, show_cursor=False),
                height=1,
                style="class:menu.item",
                dont_extend_width=True,
                align=WindowAlign.RIGHT,
            ),
            filter=have_tabs,
        )

        tabs = DynamicContainer(self.tab_container)

        self.search_bar = SearchToolbar(
            text_if_not_searching="",
            forward_search_prompt=[("bold", "Find: ")],
            backward_search_prompt=[("", "Find (up): ")],
        )

        status_bar = ConditionalContainer(
            content=VSplit(
                [
                    Window(
                        FormattedTextControl(lambda: self.format_status(part="left")),
                        style="class:status",
                    ),
                    Window(
                        FormattedTextControl(lambda: self.format_status(part="right")),
                        style="class:status.right",
                        align=WindowAlign.RIGHT,
                    ),
                ],
                height=1,
            ),
            filter=Condition(lambda: config.show_status_bar),
        )

        body = HSplit([tabs, self.search_bar, status_bar], style="class:body")

        self.command_palette = CommandPalette()

        self.menu_container = MenuContainer(
            body=body,
            menu_items=self.load_menu_items(),  # type: ignore
            floats=[
                Float(self.command_palette, top=4),
                Float(
                    content=CompletionsMenu(
                        max_height=16,
                        scroll_offset=1,
                        extra_filter=~self.command_palette.visible,
                    ),
                    xcursor=True,
                    ycursor=True,
                ),
            ],
            left=[self.logo],
            right=[self.title_bar],
        )
        return cast("FloatContainer", to_container(self.menu_container))

    def dialog(
        self,
        title: "AnyFormattedText",
        body: "AnyContainer",
        buttons: "dict[str, Optional[Callable]]",
        to_focus: "Optional[AnyContainer]" = None,
    ) -> None:
        """Display a modal dialog above the application.

        Returns focus to the previously selected control when closed.

        Args:
            title: The title of the dialog. Can be formatted text.
            body: The container to use as the main body of the dialog.
            buttons: A dictionary mapping text to display as dialog buttons to
                callbacks to run when the button is clicked. If the callback is
                `None`, the dialog will be closed without running a callback.
            to_focus: The control to focus when the dialog is displayed.

        """
        # Only show one dialog at a time
        if self.has_dialog:
            return

        focused = self.layout.current_control

        def _make_handler(cb: "Optional[Callable]" = None) -> "Callable":
            def inner(event: "Optional[KeyPressEvent]" = None) -> "None":
                self.remove_float(dialog_float)
                self.has_dialog = False
                if focused in self.layout.find_all_controls():
                    try:
                        self.layout.focus(focused)
                    except ValueError:
                        pass
                if callable(cb):
                    cb()

            return inner

        kb = KeyBindings()
        kb.add("escape")(lambda event: _make_handler()())
        button_widgets = []
        for text, cb in buttons.items():
            handler = _make_handler(cb)
            button_widgets.append(
                Button(text, handler, left_symbol="[", right_symbol="]")
            )
            kb.add(text[:1].lower(), filter=~buffer_has_focus)(handler)

        dialog = Dialog(
            title=title,
            body=body,
            buttons=button_widgets,
            modal=True,
            with_background=False,
        )
        # Add extra key-bindings
        dialog_innards = dialog.container.container
        if (
            isinstance(dialog_innards, FloatContainer)
            and isinstance(dialog_innards.content, HSplit)
            and dialog_innards.content.key_bindings is not None
        ):
            dialog_innards.content.key_bindings = merge_key_bindings(
                [dialog_innards.content.key_bindings, kb]
            )
        dialog_float = Float(content=dialog)
        # Add to top of the float stack
        self.add_float(dialog_float)
        self.has_dialog = True

        if to_focus is None:
            to_focus = button_widgets[0]
        self.layout.focus(to_focus)

        self.invalidate()

    def ask_file(
        self,
        default: "str" = "",
        validate: "bool" = True,
        error: "Optional[str]" = None,
        completer: "Completer" = None,
    ) -> None:
        """Display a dialog asking for file name input.

        Args:
            default: The default filename to display in the text entry box
            validate: Whether to disallow files which do not exist
            error: An optional error message to display below the file name
            completer: The completer to use for the input field

        """

        def _open_cb() -> None:
            path = Path(filepath.text)
            if not validate or path.expanduser().exists():
                self.open_file(path)
            else:
                self.ask_file(
                    default=filepath.text,
                    validate=validate,
                    error="File not found",
                    completer=completer,
                )

        def _accept_text(buf: "Buffer") -> "bool":
            """Accepts the text in the file input field and focuses the next field."""
            self.layout.focus_next()
            buf.complete_state = None
            return True

        filepath = TextArea(
            text=default,
            multiline=False,
            completer=completer,
            accept_handler=_accept_text,
        )

        root_contents: "list[AnyContainer]" = [
            Label("Enter file name:"),
            filepath,
        ]
        if error:
            root_contents.append(Label(error, style="red"))
        self.dialog(
            title="Select file",
            body=HSplit(root_contents),
            buttons={
                "OK": _open_cb,
                "Cancel": None,
            },
            to_focus=filepath,
        )

    def ask_new_file(self) -> "None":
        """Prompts the user to name a file."""
        return self.ask_file(
            validate=False,
            completer=PathCompleter(),
        )

    def ask_open_file(self) -> "None":
        """Prompts the user to open a file."""
        self.ask_file(
            completer=PathCompleter(),
        )

    @staticmethod
    def _kb_info() -> "Generator":
        from euporie.commands.format import format_command_attrs

        data = format_command_attrs(
            attrs=["title", "keys"],
            groups=[
                "app",
                "config",
                "notebook",
                "cell",
                "completion",
                "suggestion",
                "micro-edit-mode",
            ],
        )
        for group, info in data.items():
            if info:
                total_w = len(info[0]["title"]) + len(info[0]["keys"][0]) + 4
                yield ("class:shortcuts.group", f"{group.center(total_w)}\n")
                for i, rec in enumerate(info):
                    for j, key in enumerate(rec["keys"]):
                        key_str = key.strip().rjust(len(key))
                        title_str = rec["title"] if j == 0 else " " * len(rec["title"])
                        style = "class:shortcuts.row" + (" class:alt" if i % 2 else "")
                        yield (style + " class:key", f" {key_str} ")
                        yield (style, f" {title_str} \n")

    def help_keys(self) -> None:
        """Displays details of registered key-bindings in a dialog."""
        key_details = list(self._kb_info())
        max_line_width = max(
            [len(line) for line in fragment_list_to_text(key_details).split("\n")]
        )
        body = FormattedTextArea(
            formatted_text=key_details,
            multiline=True,
            focusable=True,
            wrap_lines=False,
            width=Dimension(preferred=max_line_width + 1),
            scrollbar=True,
        )

        self.dialog(
            title="Keyboard Shortcuts",
            body=body,
            buttons={"OK": None},
        )

    def help_logs(self) -> None:
        """Displays a dialog with logs."""
        for tab in self.tabs:
            if isinstance(tab, LogView):
                break
        else:
            tab = LogView()
            self.tabs.append(tab)
        self.layout.focus(tab)

    def help_about(self) -> None:
        """Displays an about dialog."""
        self.dialog(
            title="About",
            body=Window(
                FormattedTextControl(
                    [
                        ("class:logo", __logo__),
                        ("", " "),
                        ("bold", __app_name__),
                        ("", f"Version {__version__}\n\n".rjust(27, " ")),
                        ("", __strapline__),
                        ("", "\n"),
                        ("class:hr", "─" * 34 + "\n\n"),
                        ("", __copyright__),
                    ]
                ),
                dont_extend_height=True,
            ),
            buttons={"OK": None},
        )

    def _handle_exception(
        self, loop: "AbstractEventLoop", context: "dict[str, Any]"
    ) -> "None":
        exception = context.get("exception")
        # Log observed exceptions to the log
        log.exception("An unhandled exception occurred", exc_info=exception)
        # Also display a dialog to the user
        self.dialog(
            title="Error",
            body=Window(
                FormattedTextControl(
                    [
                        ("bold", "An error occurred:\n\n"),
                        ("", exception.__repr__()),
                    ]
                )
            ),
            buttons={"OK": None},
        )

    def exit(self, **kwargs: "Any") -> "None":
        """Check for unsaved files before closing.

        Creates a chain of close file commands, where the callback for each triggers
        the closure of the next. The closing process can be cancelled anywhere along
        the chain.

        Args:
            **kwargs: Unused key word arguments

        """
        really_close = super().exit
        if self.tabs:

            def final_cb() -> "None":
                """Really exit after the last tab in the chain is closed."""
                self.cleanup_closed_tab(self.tabs[0])
                really_close()

            def create_cb(
                close_tab: "Tab", cleanup_tab: "Tab", cb: "Callable"
            ) -> "Callable":
                """Generate a tab close chaining callbacks.

                Cleans up after the previously closed tab, and requests to close the
                next tab in the chain.

                Args:
                    close_tab: The tab to close
                    cleanup_tab: The previously closed tab to cleanup
                    cb: The callback to call when work is complete

                Returns:
                    A callback function which cleans up `cleanup_tab` and closes
                        `close_tab`.

                """

                def inner() -> None:
                    self.cleanup_closed_tab(cleanup_tab)
                    close_tab.close(cb=cb)

                return inner

            cb = final_cb
            for close_tab, cleanup_tab in zip(self.tabs, self.tabs[1:]):
                cb = create_cb(close_tab, cleanup_tab, cb)
            self.tabs[-1].close(cb)
        else:
            really_close()

    @property
    def notebook(self) -> "Optional[TuiNotebook]":
        """Return the currently active notebook."""
        if isinstance(self.tab, TuiNotebook):
            return self.tab
        return None

    @property
    def cell(self) -> "Optional[InteractiveCell]":
        """Return the currently active cell."""
        if isinstance(self.tab, TuiNotebook):
            return self.tab.cell
        return None

    def load_menu_items(self) -> "list[MenuItem]":
        """Loads the list of menu items to display in the menu."""
        separator = MenuItem(separator=True)
        return [
            MenuItem(
                "File",
                children=[
                    get("new-notebook").menu,
                    get("open-file").menu,
                    separator,
                    get("save-notebook").menu,
                    get("close-file").menu,
                    separator,
                    get("quit").menu,
                ],
            ),
            MenuItem(
                "Edit",
                children=[
                    get("cut-cells").menu,
                    get("copy-cells").menu,
                    get("paste-cells").menu,
                    separator,
                    get("copy-outputs").menu,
                    separator,
                    get("reformat-cells").menu,
                    get("reformat-notebook").menu,
                ],
            ),
            MenuItem(
                "Run",
                children=[
                    get("run-selected-cells").menu,
                    get("run-all-cells").menu,
                ],
            ),
            MenuItem(
                "Kernel",
                children=[
                    get("interrupt-kernel").menu,
                    get("restart-kernel").menu,
                    get("change-kernel").menu,
                ],
            ),
            MenuItem(
                "Settings",
                children=[
                    MenuItem(
                        "Editor key bindings",
                        children=[
                            get(f"set-edit-mode-{choice}").menu
                            for choice in config.choices("edit_mode")
                        ],
                    ),
                    separator,
                    MenuItem(
                        "Color scheme",
                        children=[
                            get(f"set-color-scheme-{choice}").menu
                            for choice in config.choices("color_scheme")
                        ],
                    ),
                    MenuItem(
                        "Syntax Theme",
                        children=[
                            get(f"set-syntax-theme-{choice}").menu
                            for choice in sorted(
                                CONFIG_PARAMS["syntax_theme"]["schema_"]["enum"]
                            )
                        ],
                    ),
                    get("switch-background-pattern").menu,
                    get("show-cell-borders").menu,
                    get("tmux-terminal-graphics").menu,
                    separator,
                    get("use-full-width").menu,
                    get("show-line-numbers").menu,
                    get("show-status-bar").menu,
                    get("show-scroll-bar").menu,
                    separator,
                    MenuItem(
                        "Cell formatting",
                        children=[
                            get("autoformat").menu,
                            separator,
                            get("format-black").menu,
                            get("format-isort").menu,
                            get("format-ssort").menu,
                        ],
                    ),
                    get("autocomplete").menu,
                    get("autosuggest").menu,
                    get("autoinspect").menu,
                    get("run-after-external-edit").menu,
                ],
            ),
            MenuItem(
                "Help",
                children=[
                    get("show-command-palette").menu,
                    get("keyboard-shortcuts").menu,
                    get("view-documentation").menu,
                    separator,
                    get("view-logs").menu,
                    separator,
                    get("about").menu,
                ],
            ),
        ]
