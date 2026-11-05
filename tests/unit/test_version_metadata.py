"""The package metadata is the sole source for runtime version strings."""

import tomllib
from importlib.metadata import version

from zcoder import __version__, main


def test_runtime_versions_follow_project_metadata():
    with open("pyproject.toml", "rb") as project_file:
        project_version = tomllib.load(project_file)["project"]["version"]

    assert version("zcoder") == project_version
    assert __version__ == project_version
    assert main.VERSION == project_version
