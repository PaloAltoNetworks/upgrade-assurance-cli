# my_package/__init__.py
from importlib.metadata import version as get_version
from importlib.metadata import PackageNotFoundError

try:
    __version__ = get_version("upgrade-assurance-cli")
except PackageNotFoundError:
    __version__ = "dev-or-unknown"
