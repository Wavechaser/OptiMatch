"""Check that the installed package is discoverable without a path override."""

import subprocess
import sys
from importlib import import_module
from importlib.metadata import distribution


def test_installed_package():
    package = import_module("optimatch")
    metadata = distribution("optics-prescription-matcher").metadata
    assert package.__name__ == "optimatch"
    assert metadata["Name"] == "optics-prescription-matcher"


def test_installed_cli_outside_checkout(tmp_path):
    completed = subprocess.run(
        [sys.executable, "-m", "optimatch", "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert completed.stdout.startswith("usage: python -m optimatch ")
    assert "--catalog" in completed.stdout
    assert "--profile" in completed.stdout
    assert completed.stderr == ""


def test_old_package_is_not_installed(tmp_path):
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import importlib.util; "
            "assert importlib.util.find_spec('optics_prescription_matcher') is None",
        ],
        cwd=tmp_path,
        check=True,
    )
