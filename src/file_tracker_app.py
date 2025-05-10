import os
from typing import List

from textual.app import App, ComposeResult
from textual.widgets import Tree, Header, Footer, Static, Button
from textual.containers import Container, Vertical, HorizontalGroup
from textual.widgets.tree import TreeNode

from file_tracker_core import ConfigFileHandler


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

class UserConfig:
    config_path = 'user_config.json'

class CoreAPI:
    @staticmethod
    def get_files_tracked() -> List[str]:
        config_file_handler: ConfigFileHandler = ConfigFileHandler(UserConfig.config_path)
        files_tracked: List[str] = config_file_handler.get_files_tracked()
        files_tracked = PathBeautify.simplify(files_tracked)
        return files_tracked


class TreeContainer(Container):
    def compose(self) -> ComposeResult:
        paths = CoreAPI.get_files_tracked()

        if not paths:
            yield Static("No files are tracked", id="no-files-messages")
        else:
            tree = Forests.plant_tree(paths)
            yield tree


class ActionButton(HorizontalGroup):
    def compose(self) -> ComposeResult:
        yield Button("Add File", id="add_file", classes="action-button")
        yield Button("Add Directory", id="add_dir", classes="action-button")
        yield Button("Remove File", id="remove_file", classes="action-button")
        yield Button("Save File", id="save_file", classes="action-button")


class MainApp(App):
    CSS_PATH = "file_tracker_app.tcss"
    BINDINGS = [("d", "toggle_dark", "Toggle dark mode")]

    def compose(self) -> ComposeResult:
        yield Header()

        yield Vertical(TreeContainer(id="tree-container"), ActionButton())

        yield Footer()

    def action_toggle_dark(self) -> None:
        self.theme = (
            "textual-dark" if self.theme == "textual-light" else "textual-light"
        )


if __name__ == "__main__":
    MainApp().run()
