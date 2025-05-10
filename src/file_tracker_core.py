import re
import os
import copy
import functools
from typing import TypedDict, List, Optional

import ujson as json


class InvalidPathError(Exception):
    def __init__(self, message: str = "Invalid file or directory"):
        super().__init__(message)


class OSManager:
    @staticmethod
    def is_absolute(path: str) -> bool:
        return os.path.isabs(path)

    @staticmethod
    def get_abspath(
        path: str, *, return_path: bool = False, force_real_path: bool = True
    ) -> str:
        if isinstance(path, str) and (os.path.isfile(path) or os.path.isdir(path)):
            return os.path.realpath(path) if force_real_path else os.path.abspath(path)
        if return_path:
            return path
        raise InvalidPathError(path)

    @staticmethod
    def format_abspath(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            def normalize(val):
                if isinstance(val, str) and (os.path.isfile(val) or os.path.isdir(val)):
                    return OSManager.get_abspath(val, return_path=True)
                return val

            args = tuple(normalize(arg) for arg in args)
            kwargs = {k: normalize(v) for k, v in kwargs.items()}

            return func(*args, **kwargs)

        return wrapper

    @staticmethod
    def get_rel_path(path: str, root: str) -> str:
        try:
            return os.path.relpath(path, root)
        except ValueError:
            return ""

    @staticmethod
    def get_dir_file(path: str, root: str) -> dict[str, dict]:
        path = OSManager.get_abspath(path)
        return {
            file_info["path"]: file_info
            for filename in os.listdir(path)
            if os.path.isfile(full_path := os.path.join(path, filename))
            and (file_info := FileInfoCollector.get_file_info(full_path, root))
        }

    @staticmethod
    def recursive_get_dir_file(path: str, root: str) -> dict[str, dict]:
        files = {}
        for dirpath, _, filenames in os.walk(path):
            for filename in filenames:
                full_path = os.path.join(dirpath, filename)
                if os.path.isfile(full_path):
                    info = FileInfoCollector.get_file_info(full_path, root)
                    files[info["path"]] = info
        return files


class JsonHandler:
    @staticmethod
    def _json_write(
        content: dict,
        file_path: str,
        *,
        mode: str = "w",
        file_setting: dict = None,
        json_setting: dict = None,
    ):
        file_setting = file_setting or {"encoding": "utf-8"}
        json_setting = json_setting or {"ensure_ascii": False, "indent": 4}

        with open(file_path, mode, **file_setting) as file:
            json.dump(content, file, **json_setting)

    @staticmethod
    def json_write(*args, **kwargs):
        JsonHandler._json_write(*args, **kwargs)

    @staticmethod
    def _json_read(
        file_path: str,
        *,
        mode: str = "r",
        file_setting: dict = None,
    ):
        file_setting = file_setting or {"encoding": "utf-8"}

        with open(file_path, mode, **file_setting) as file:
            content = json.load(file)

        return content

    @staticmethod
    def json_read(*args, **kwargs):
        return JsonHandler._json_read(*args, **kwargs)


class TrackedFileInfo(TypedDict, total=False):
    path: str
    rel_path: str
    size: int
    mtime: float
    outside_root: bool


class ConfigSchema(TypedDict):
    tracked: dict[str, TrackedFileInfo]


class ConfigFileTemplate:
    def get_default_config() -> ConfigSchema:
        return {"tracked": {}}


class ConfigFileHandler:
    def __init__(self, config_path: str = "user_config.json"):
        self.config: dict = copy.deepcopy(ConfigFileTemplate.get_default_config())
        self.config_path: str = config_path

        if not self.config_exists():
            self.create_template_config()

    def config_exists(self) -> bool:
        return os.path.exists(self.config_path)

    def create_template_config(self):
        config_to_save = copy.deepcopy(self.config)
        config_to_save["tracked"] = dict(self.config["tracked"])
        JsonHandler.json_write(config_to_save, self.config_path)

    @staticmethod
    def validate_config_structure(config: dict, template: dict = None) -> dict:
        if not isinstance(config, dict):
            raise ValueError("Config must be a dictionary")

        template = template or ConfigFileTemplate.get_default_config()
        validated = {}

        for key, default_value in template.items():
            if key not in config:
                validated[key] = copy.deepcopy(default_value)
                continue

            value = config[key]

            if isinstance(default_value, dict):
                if not isinstance(value, dict):
                    validated[key] = copy.deepcopy(default_value)
                else:
                    validated[key] = {
                        k: v
                        for k, v in value.items()
                        if isinstance(k, str) and isinstance(v, dict)
                    }
            elif isinstance(value, type(default_value)):
                validated[key] = value
            else:
                validated[key] = copy.deepcopy(default_value)

        return validated

    def read_config(self) -> dict:
        content = JsonHandler.json_read(self.config_path)
        return content

    def safe_read_config(self, *, retries: int = 3):
        for _ in range(retries):
            try:
                content = self.read_config()
                self.config = self.validate_config_structure(content)
                return self.config
            except json.JSONDecodeError:
                self.create_template_config()  # Force overwrite corrupted config file with template file
            except Exception as e:
                raise e
        raise RuntimeError("Failed to read configuration after multiple attempts")

    @staticmethod
    def write_config(config: dict, config_path: str):
        config_to_save = copy.deepcopy(config)
        config_to_save["tracked"] = dict(config["tracked"])
        JsonHandler.json_write(config_to_save, config_path)

    def get_files_tracked(self):
        config = self.safe_read_config()
        files_tracked = config["tracked"]
        return list(files_tracked.keys())


class FileInfoCollector:
    @staticmethod
    def get_size(path: str) -> int:
        return os.path.getsize(path)

    @staticmethod
    def get_mtime(path: str) -> float:
        return os.path.getmtime(path)

    @staticmethod
    def is_outside_root(path: str, root: str) -> bool:
        abs_path = OSManager.get_abspath(path)
        abs_root = OSManager.get_abspath(root)

        try:
            common = os.path.commonpath([abs_path, abs_root])
            return common != abs_root
        except ValueError:
            # Happens on Windows if paths are on different drives
            return True

    @staticmethod
    def get_file_info(path: str, root: str) -> dict:
        abs_path = OSManager.get_abspath(path)
        rel_path = OSManager.get_rel_path(abs_path, root) or ""

        return {
            "path": abs_path,
            "rel_path": rel_path,
            "size": FileInfoCollector.get_size(abs_path),
            "mtime": FileInfoCollector.get_mtime(abs_path),
            "outside_root": FileInfoCollector.is_outside_root(abs_path, root),
        }


class FileFilter:
    def __init__(
        self, pattern: Optional[str] = None, *, only_match_filename: bool = True
    ):
        self.pattern = pattern
        self.only_match_filename = only_match_filename
        self.regex = re.compile(pattern) if pattern else None

    def filter_files(self, files: List[str]) -> List[str]:
        if not self.regex:
            return files

        return [file for file in files if self.regex.match(file)]

    def is_match(self, full_path: str) -> bool:
        if not self.regex:
            return True

        target = os.path.basename(full_path) if self.only_match_filename else full_path

        return self.regex.match(target) is not None


class Tracker:
    def __init__(
        self,
        config: dict,
        config_path: str,
        *,
        auto_save: bool = True,
        auto_clean: bool = True,
        file_filter: Optional[FileFilter] = None,
    ):
        self.config = config
        self.config["tracked"] = dict(config.get("tracked", {}))
        self.config_path = config_path
        self.auto_save = auto_save
        self.auto_clean = auto_clean
        self.file_filter = file_filter or FileFilter()

    def clean_tracked_files(self):
        self.config["tracked"] = {
            path: info
            for path, info in self.config["tracked"].items()
            if os.path.isfile(path)
        }

    def prepare_for_export(self):
        self.clean_tracked_files()

    def export_config(self):
        if self.auto_clean:
            self.prepare_for_export()
        config_to_save = self.config.copy()
        config_to_save["tracked"] = dict(self.config["tracked"])
        ConfigFileHandler.write_config(config_to_save, self.config_path)

    @staticmethod
    def _auto_export_config(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            result = func(self, *args, **kwargs)
            if self.auto_save:
                self.export_config()
            return result

        return wrapper

    @_auto_export_config
    def add_file(self, path: str, root: str = "./"):
        full_path = OSManager.get_abspath(path)

        if os.path.isfile(full_path) and self.file_filter.is_match(full_path):
            file_info = FileInfoCollector.get_file_info(full_path, root)
            self.config["tracked"][file_info["path"]] = file_info

    @_auto_export_config
    def add_dir(self, path: str, root: str, *, recursive: bool = False):
        file_dict = (
            OSManager.recursive_get_dir_file(path, root)
            if recursive
            else OSManager.get_dir_file(path, root)
        )

        file_dict = {
            file_path: file_info
            for file_path, file_info in file_dict.items()
            if self.file_filter.is_match(file_path)
        }
        self.config["tracked"].update(file_dict)

    @_auto_export_config
    @OSManager.format_abspath
    def remove_file(self, path: str):
        self.config["tracked"].pop(path, None)


if __name__ == "__main__":
    config_file_handler = ConfigFileHandler()
    tracker = Tracker(
        config=config_file_handler.safe_read_config(),
        config_path=config_file_handler.config_path,
        auto_save=True,
        auto_clean=True,
    )
    tracker.add_dir("./../", root="./", recursive=True)
    a = config_file_handler.read_config()
    print(a)
