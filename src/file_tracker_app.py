import os
from typing import List

from textual import on
from textual.app import App, ComposeResult
from textual.widgets import Tree, Header, Footer, Static, Button, Input, Label
from textual.containers import Container, Vertical, HorizontalGroup
from textual.widgets.tree import TreeNode

from file_tracker_core import ConfigFileHandler, Tracker


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
    def populate_tree(node: TreeNode, data: dict):
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
        return tree


class MessageBar(Static):
    def on_mount(self):
        self.display = False

    def show_message(self, message: str, duration: float = 3.0):
        self.update(f"Message: {message}")
        self.display = True
        self.set_timer(duration, self.clear_message)

    def clear_message(self):
        self.update("")
        self.display = False


class UserConfig:
    root = "./"
    config_path = "user_config.json"
    auto_save = True
    auto_clean = True


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


class ActionButton(HorizontalGroup):
    def compose(self) -> ComposeResult:
        yield Button("Add File", id="add_file", classes="action-button")
        yield Button("Add Directory", id="add_dir", classes="action-button")
        yield Button("Remove File", id="remove_file", classes="action-button")
        yield Button("Change working dir", id="change_root", classes="action-button")


class MainApp(App):
    CSS_PATH = "file_tracker_app.tcss"
    BINDINGS = [
        ("q", "quit_app", "Quit"),
        ("d", "toggle_dark", "Toggle dark mode"),
        ("r", "refresh_tree", "Refresh tree"),
        ("s", "save_conf", "Save configuration"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Vertical(
            Static(id="top-gap", classes="messages"),
            TreeContainer(id="tree-container"),
            MessageBar(id="message-bar", classes="messages"),
            Input(
                placeholder="Enter a path or regular expression here then select one of the buttons below",
                id="input-bar",
            ),
            ActionButton(),
        )
        yield Footer()

    def action_toggle_dark(self) -> None:
        self.theme = (
            "textual-dark" if self.theme == "textual-light" else "textual-light"
        )

    def _get_input(self) -> UserInput.value:
        input = self.query_one(Input)
        UserInput.value = input.value
        input.value = ""

    def _refresh_tree(self) -> None:
        tree_container = self.query_one(TreeContainer)
        tree_container.refresh_tree()

    def _send_message(self, message: str, timeout: float = 3.0) -> None:
        message_bar = self.query_one("#message-bar", MessageBar)
        message_bar.show_message(message, timeout)

    @on(Button.Pressed, "#add_file")
    def button_add_file(self) -> None:
        self._get_input()
        tracker = CoreInstance.init_tracker()
        tracker.add_file(UserInput.value, UserConfig.root)
        self._refresh_tree()
        self._send_message("File added successfully")

    def action_refresh_tree(self) -> None:
        self._refresh_tree()
        self._send_message("Reloaded directory tree")

    def action_quit_app(self) -> None:
        self.exit()


if __name__ == "__main__":
    MainApp().run()
