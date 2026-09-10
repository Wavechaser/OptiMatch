"""Check that the installed package is discoverable without a path override."""

from importlib import import_module
from importlib.metadata import distribution


def test_installed_package():
    package = import_module("optics_prescription_matcher")
    metadata = distribution("optics-prescription-matcher").metadata
    assert package.__name__ == "optics_prescription_matcher"
    assert metadata["Name"] == "optics-prescription-matcher"
