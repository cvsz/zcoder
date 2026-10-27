"""zcoder package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("zcoder")
except PackageNotFoundError:
    __version__ = "0+unknown"
