import os
from typing import List, Callable

from textual import on
from textual.app import App, ComposeResult
from textual.widgets import (
    Tree,
    Header,
    Footer,
    Static,
    Button,
    Input,
    DirectoryTree,
)
from textual.containers import (
    Container,
    Vertical,
    HorizontalGroup,
    Horizontal,
    VerticalGroup,
)
from textual.reactive import reactive

from file_tracker_core import ConfigFileHandler, Tracker, OSManager


class PathBeautify:
    @staticmethod
    def simplify(paths: List[str], *, connector: str = " > ") -> List[str]:
        if not paths:
            return []

        common_prefix = os.path.commonpath(paths)

        if common_prefix.startswith(os.path.sep):
            prefix = common_prefix[1:]
        prefix = connector.join(os.path.normpath(prefix).split(os.path.sep))

        return [
            os.path.join(prefix, os.path.relpath(path, common_prefix)) for path in paths
        ]

    @staticmethod
    def truncate_path(path, max_length=30):
        if len(path) <= max_length:
            return path

        parts = path.split(os.sep)

        if len(parts) <= 1:
            return path

        root = parts[0]
        middle = parts[1:]

        if len(middle) == 0:
            return path

        fixed_length = len(root) + len(os.sep) * 2
        remaining_length = max_length - fixed_length

        kept_middle = []
        total_length = 0

        for part in reversed(middle):
            part_length = len(part) + len(os.sep)
            if total_length + part_length <= remaining_length:
                kept_middle.insert(0, part)
                total_length += part_length
            else:
                break

        return os.sep.join([root, "..."] + kept_middle)

    @staticmethod
    def get_parent_directory(path: str) -> str:
        parent = os.path.dirname(os.path.abspath(path))
        return parent if parent != path else path


class Forests:
    @staticmethod
    def build_tree_data(paths: List[str]) -> dict:
        tree = {}
        for path in paths:
            parts = os.path.normpath(path).split(os.sep)
            current = tree
            for part in parts:
                current = current.setdefault(part, {})
        return tree

    @staticmethod
    def populate_tree(node: Tree, data: dict):
        for key, subtree in sorted(data.items()):
            is_file = not subtree
            child = node.add(key, allow_expand=not is_file)
            if not is_file:
                Forests.populate_tree(child, subtree)

    @staticmethod
    def plant_tree(paths: List[str]):
        tree_data = Forests.build_tree_data(paths)
        tree = Tree("root")
        Forests.populate_tree(tree.root, tree_data)
        tree.root.expand()
        return tree


class UserConfig:
    root = "./"
    config_path = "user_config.json"
    auto_save = True
    auto_clean = True
    path_filter_pattern = r""


class UserInput:
    value = ""


class CoreInstance:
    config_file_handler: ConfigFileHandler = ConfigFileHandler(UserConfig.config_path)

    @staticmethod
    def init_tracker():
        tracker = Tracker(
            config=CoreInstance.config_file_handler.safe_read_config(),
            config_path=UserConfig.config_path,
            auto_save=UserConfig.auto_save,
            auto_clean=UserConfig.auto_clean,
        )
        return tracker


class CoreAPI:
    @staticmethod
    def get_files_tracked() -> List[str]:
        files_tracked: List[str] = CoreInstance.config_file_handler.get_files_tracked()
        files_tracked = PathBeautify.simplify(files_tracked)
        return files_tracked


class MessageBar(Static):
    def on_mount(self):
        self.display = False

    def show_message(self, message: str, duration: float = 3.0):
        self.update(message)
        self.display = True
        self.set_timer(duration, self.clear_message)

    def clear_message(self):
        self.update("")
        self.display = False


class StatusBar(Static):
    cwd: reactive[str] = reactive(
        PathBeautify.truncate_path(
            OSManager.get_abspath(
                UserConfig.root, return_path=True, force_real_path=False
            )
        )
    )
    auto_save: reactive[bool] = reactive(UserConfig.auto_save)
    auto_clean: reactive[bool] = reactive(UserConfig.auto_clean)
    filter_pattern = reactive(UserConfig.path_filter_pattern)

    def on_mount(self) -> None:
        self.update_status()

    def update_status(self) -> None:
        status_message = f'CWD: {self.cwd} | Filter Pattern: r"{self.filter_pattern}" | Auto-save: {"Enabled" if self.auto_save else "Disabled"} | Auto-clean: {"Enabled" if self.auto_clean else "Disabled"}'
        self.update(status_message)

    def watch_cwd(self, new_value: str) -> None:
        self.update_status()

    def watch_auto_save(self, new_value: bool) -> None:
        self.update_status()

    def watch_auto_clean(self, new_value: str) -> None:
        self.update_status()

    def watch_filter_pattern(self, new_value: str) -> None:
        self.update_status()


class TreeContainer(Container):
    def compose(self) -> ComposeResult:
        yield from self.build_tree()

    def build_tree(self) -> List[str]:
        paths = CoreAPI.get_files_tracked()
        if not paths:
            return [
                Static(
                    "No files are tracked", id="no-files-messages", classes="messages"
                )
            ]
        tree = Forests.plant_tree(paths)
        return [tree]

    def refresh_tree(self):
        self.remove_children()
        self.mount_all(self.build_tree())


class RefreshableDirectoryTree(DirectoryTree):
    def __init__(self, path: str = None):
        path = path or PathBeautify.get_parent_directory(os.getcwd())
        super().__init__(path)
        self.base_path = path

    def reload_tree(self) -> None:
        path = PathBeautify.get_parent_directory(os.getcwd())
        self.remove()
        new_tree = RefreshableDirectoryTree(path)
        if self.parent:
            self.parent.mount(new_tree)


class ActionButton(HorizontalGroup):
    def compose(self) -> ComposeResult:
        yield Button("Add File", id="add_file", classes="action-button")
        yield Button("Add Directory...", id="add_dir", classes="action-button")
        yield Button("Remove...", id="removes", classes="action-button")
        yield Button("Set Filter", id="set_filter", classes="action-button")
        yield Button("Change CWD", id="change_root", classes="action-button")


class PopupInfo(Static):
    def on_mount(self) -> None:
        self.message_display = Static("", classes="hidden popup-info-message")
        self.mount(self.message_display)

    def update_status(self, text: str) -> None:
        self.message_display.update(f"Additional options for {text}")


class AdditionalButton(HorizontalGroup):
    def compose(self) -> ComposeResult:
        yield Button("A", classes="hidden additional-button add-dir-popup")
        yield Button("B", classes="hidden additional-button add-dir-popup")
        yield Button("C", classes="hidden additional-button removes-popup")
        yield Button("D", classes="hidden additional-button removes-popup")


class MainApp(App):
    CSS_PATH = "file_tracker_app.tcss"
    BINDINGS = [
        ("q", "quit_app", "Quit"),
        ("d", "toggle_dark", "Toggle dark mode"),
        ("r", "refresh_tree", "Refresh tree"),
        ("s", "save_conf", "Save configuration"),
        ("i", "focus_input", "Focus on input"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalGroup(
            StatusBar(id="status-bar", classes="messages"),
            Horizontal(
                TreeContainer(id="tree-container"),
                RefreshableDirectoryTree(),
            ),
            MessageBar(id="message-bar", classes="messages"),
            Input(
                placeholder="Enter a path or regular expression here then select one of the buttons below",
                id="input-bar",
            ),
            PopupInfo(),
            AdditionalButton(),
            ActionButton(),
        )
        yield Footer()

    def action_toggle_dark(self) -> None:
        self.theme = (
            "textual-dark" if self.theme == "textual-light" else "textual-light"
        )

    def action_focus_input(self) -> None:
        self.query_one("#input-bar").focus()

    def _refresh_tree(self) -> None:
        tree_container = self.query_one(TreeContainer)
        tree_container.refresh_tree()

    def _send_message(
        self, message: str, *, noti_type: str = "Message", timeout: float = 3.0
    ) -> None:
        message_bar = self.query_one("#message-bar", MessageBar)
        message_bar.show_message(f"{noti_type}: {message}", timeout)

    def action_refresh_tree(self) -> None:
        self._refresh_tree()
        self._send_message("Reloaded directory tree")

    def action_quit_app(self) -> None:
        self.exit()

    def _get_input(self) -> UserInput.value:
        input = self.query_one(Input)
        UserInput.value = input.value
        input.value = ""

    @on(Button.Pressed, "#add_file")
    def button_add_file(self) -> None:
        self._get_input()
        tracker = CoreInstance.init_tracker()
        tracker.add_file(UserInput.value, UserConfig.root)
        self._refresh_tree()
        self._send_message("File added successfully")

    def _change_root(self) -> None:
        if os.path.exists(UserInput.value):
            UserConfig.root = OSManager.get_abspath(
                UserInput.value, return_path=True, force_real_path=False
            )
            os.chdir(UserConfig.root)
            shorten_path = PathBeautify.truncate_path(UserConfig.root)
            self.query_one(StatusBar).cwd = shorten_path
            self.query_one(RefreshableDirectoryTree).reload_tree()
            self._send_message(f"Changed working directory to {shorten_path}")
        else:
            self._send_message("Path does not exist", noti_type="Error")

    @on(Button.Pressed, "#change_root")
    def button_change_root(self) -> None:
        self._get_input()
        self._change_root()

    @on(Button.Pressed, "#set_filter")
    def button_set_filter(self) -> None:
        self._get_input()
        UserConfig.path_filter_pattern = UserInput.value
        self.query_one(StatusBar).filter_pattern = UserConfig.path_filter_pattern
        self._send_message(
            f"Changed filter pattern to {UserConfig.path_filter_pattern}"
        )

    def _toggle_popup(
        self, target_class: str, name: str, info_class: str = ".popup-info-message"
    ) -> None:
        self.query_one(PopupInfo).update_status(name)

        target_popups = list(self.query(target_class))
        info_boxes = list(self.query(info_class))
        is_showing = any(not p.has_class("hidden") for p in target_popups)

        for popup in self.query(".add-dir-popup, .removes-popup"):
            popup.add_class("hidden")

        for info in info_boxes:
            info.add_class("hidden")

        if not is_showing:
            for popup in target_popups:
                popup.remove_class("hidden")
            for info in info_boxes:
                info.remove_class("hidden")

    @on(Button.Pressed, "#add_dir")
    def button_add_dir(self) -> None:
        self._toggle_popup(".add-dir-popup", "Add Directory")

    @on(Button.Pressed, "#removes")
    def button_removes(self) -> None:
        self._toggle_popup(".removes-popup", "Remove")

    def _input_change_root(self) -> bool:
        user_input: str = UserInput.value

        if not user_input.strip():
            return False

        if user_input.startswith("cd "):
            directory = user_input[3:].strip()
        elif user_input.startswith("chdir "):
            directory = user_input[6:].strip()
        else:
            return False

        UserInput.value = directory
        self._change_root()

        return True

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.input.clear()
        UserInput.value = event.value

        listeners: List[Callable[[], bool]] = [self._input_change_root]

        if not any(listener() for listener in listeners):
            self._send_message(UserInput.value, noti_type="Unknown command")

    def _update_input_with_path(self, event) -> None:
        input_field = self.query_one(Input)
        input_field.value = str(event.path)

    @on(DirectoryTree.DirectorySelected)
    def on_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        self._update_input_with_path(event)

    @on(DirectoryTree.FileSelected)
    def on_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        self._update_input_with_path(event)


if __name__ == "__main__":
    MainApp().run()
