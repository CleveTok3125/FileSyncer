import os
from typing import List

from textual.app import App, ComposeResult
from textual.widgets import Tree, Header, Footer
from textual.containers import Container
from textual.widgets.tree import TreeNode

from file_tracker_core import ConfigFileHandler


class PathBeautify:
    @staticmethod
    def simplify(paths: List[str], *, connector: str = " > ") -> List[str]:
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


class CoreAPI:
    config_file_handler: ConfigFileHandler = ConfigFileHandler()
    files_tracked: List[str] = config_file_handler.get_files_tracked()
    files_tracked = PathBeautify.simplify(files_tracked)


class MainApp(App):
    CSS_PATH = None
    BINDINGS = [("d", "toggle_dark", "Toggle dark mode")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

        paths = CoreAPI.files_tracked
        tree = Forests.plant_tree(paths)
        yield Container(tree)

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.theme = (
            "textual-dark" if self.theme == "textual-light" else "textual-light"
        )


if __name__ == "__main__":
    MainApp().run()
