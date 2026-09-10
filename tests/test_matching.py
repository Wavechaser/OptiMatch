from dataclasses import replace
from decimal import Decimal

import pytest

from optics_prescription_matcher.inputs import (
    InputError,
    load_catalog_csv,
    load_sectioned_csv,
    prescription_from_dict,
)
from optics_prescription_matcher.matching import match_prescription
from optics_prescription_matcher.models import CatalogGlass, Prescription, Surface


def prescription(surface):
    return Prescription(1, "test", "mm", (surface,))


def glass(name, nd, vd, maker="Ohara", pgf=None, dpgf=None):
    return CatalogGlass(maker, name, nd, vd, pgf, dpgf)


@pytest.mark.parametrize(
    ("nd", "vd", "expected"),
    [
        ("1.500199", "50.099", "close"),
        ("1.5002", "50", "offset"),
        ("1.5", "50.1", "offset"),
        ("1.51999", "51.999", "offset"),
        ("1.52", "50", "unmatched"),
        ("1.5", "52", "unmatched"),
        ("1.520001", "50", "unmatched"),
        ("1.5", "52.001", "unmatched"),
    ],
)
def test_strict_close_and_offset_boundaries(nd, vd, expected):
    result = match_prescription(
        prescription(Surface("1", "10", "2", nd=nd, vd=vd)),
        [glass("BASE", "1.5", "50")],
    )
    assert result.matches[0].status == expected


def test_close_manufacturer_preference_outweighs_better_numeric_match():
    surface = Surface("1", "10", "2", nd="1.50010", vd="50.05")
    catalogue = [
        glass("EXACT", "1.50010", "50.05", "Other"),
        glass("PREFERRED", "1.50019", "50.09", "Ohara"),
    ]
    result = match_prescription(prescription(surface), catalogue)
    assert result.prescription.surfaces[0].material == "PREFERRED"
    assert result.prescription.surfaces[0].nd_offset is None


def test_close_pool_always_precedes_offset_pool():
    surface = Surface("1", "10", "2", nd="1.50019", vd="50.09", pgf="0.6000")
    catalogue = [
        glass("CLOSE", "1.5", "50"),
        glass("OFFSET", "1.51", "51", pgf="0.6000"),
    ]
    result = match_prescription(prescription(surface), catalogue)
    assert result.matches[0].status == "close"
    assert result.prescription.surfaces[0].material == "CLOSE"


def test_profiles_and_exclusions_are_explicit_not_filename_inferred():
    source = prescription(Surface("1", "10", "2", nd="1.5", vd="50"))
    catalogue = [
        glass("O", "1.5", "50", "Ohara"),
        glass("K", "1.5", "50", "Hikari"),
    ]
    assert (
        match_prescription(source, catalogue, "default")
        .prescription.surfaces[0]
        .material
        == "O"
    )
    assert (
        match_prescription(source, catalogue, "nikon").prescription.surfaces[0].material
        == "K"
    )
    assert (
        match_prescription(source, catalogue, "canon").prescription.surfaces[0].material
        == "O"
    )
    excluded_only = match_prescription(source, catalogue[1:], "canon")
    assert excluded_only.matches[0].status == "unmatched"


def test_offset_sign_and_source_values_are_preserved():
    surface = Surface("1", "10", "2", nd="1.5100", vd="49.00")
    source = prescription(surface)
    result = match_prescription(source, [glass("BASE", "1.500", "50.0")])
    matched = result.prescription.surfaces[0]
    assert matched.nd == "1.5100" and matched.vd == "49.00"
    assert Decimal(matched.nd_offset) == Decimal("0.0100")
    assert Decimal(matched.vd_offset) == Decimal("-1.00")
    assert source.surfaces[0] == surface


def test_partial_dispersion_missing_metadata_is_not_a_perfect_match():
    surface = Surface("1", "10", "2", nd="1.5", vd="50", pgf="0.6500")
    catalogue = [
        glass("MISSING", "1.5", "50"),
        glass("KNOWN", "1.5", "50", pgf="0.6501"),
    ]
    result = match_prescription(prescription(surface), catalogue)
    assert result.prescription.surfaces[0].material == "KNOWN"
    assert result.matches[0].selected["catalogue_dpgf"] is None
    missing = result.matches[0].alternatives[0]["dispersion"]
    assert missing["missing_supplied_fields"] == 1
    assert missing["residuals"]["pgf"]["catalogue"] is None


def test_offset_ranking_uses_dispersion_before_numeric_proximity():
    surface = Surface("1", "10", "2", nd="1.51", vd="51", pgf="0.6500")
    catalogue = [
        glass("NUMERIC", "1.509", "50.9", pgf="0.6600"),
        glass("DISPERSION", "1.500", "50", pgf="0.6500"),
    ]
    result = match_prescription(prescription(surface), catalogue)
    assert result.matches[0].status == "offset"
    assert result.prescription.surfaces[0].material == "DISPERSION"
    assert result.matches[0].selected["source_nd_step"] == "0.01"


def test_dual_dispersion_uses_maximum_residual_not_double_counting():
    surface = Surface("1", "10", "2", nd="1.5", vd="50", pgf="0.6500", dpgf="0.0100")
    catalogue = [
        glass("ONE-BAD", "1.5", "50", pgf="0.6500", dpgf="0.0110"),
        glass("BALANCED", "1.5", "50", pgf="0.6506", dpgf="0.0106"),
    ]
    result = match_prescription(prescription(surface), catalogue)
    assert result.prescription.surfaces[0].material == "BALANCED"
    assert result.matches[0].selected["catalogue_dpgf"] == "0.0106"
    assert (
        result.matches[0].selected["dispersion"]["maximum_normalized_residual"] == "6"
    )


def test_catalogue_order_does_not_change_result_or_report():
    source = prescription(Surface("1", "10", "2", nd="1.5", vd="50"))
    catalogue = [glass("LONG", "1.5", "50"), glass("A", "1.5", "50")]
    forward = match_prescription(source, catalogue)
    backward = match_prescription(source, reversed(catalogue))
    assert forward == backward
    assert forward.prescription.surfaces[0].material == "A"


def test_unknown_and_conflicting_supplied_typecodes_are_preserved():
    supplied = Surface(
        "1",
        "10",
        "2",
        material="KNOWN",
        nd="1.7",
        vd="30",
        nd_offset="0.01",
        vd_offset="-0.2",
    )
    conflicting = [
        glass("KNOWN", "1.5", "50", "Hikari"),
        glass("KNOWN", "1.6", "40", "Ohara"),
    ]
    result = match_prescription(prescription(supplied), conflicting, "canon")
    assert result.prescription.surfaces[0] == supplied
    assert result.matches[0].ambiguity
    assert result.matches[0].selected_manufacturer == "Ohara"
    unknown = match_prescription(prescription(replace(supplied, material="HOST")), [])
    assert unknown.matches[0].status == "supplied"
    assert "host lookup unverified" in unknown.matches[0].reason
    assert result.matches[0].selected["catalogue_dpgf"] is None


@pytest.mark.parametrize(
    ("nd", "vd", "catalogue"),
    [
        (None, None, []),
        ("1.5", "50", [glass("CLOSE", "1.5", "50")]),
        ("1.51", "51", [glass("OFFSET", "1.5", "50")]),
        ("1.5", "50", []),
    ],
)
def test_public_matcher_rejects_offsets_without_base_typecode(nd, vd, catalogue):
    surface = Surface("1", "10", "2", nd=nd, vd=vd, nd_offset="0.01", vd_offset="-0.2")
    with pytest.raises(ValueError, match="offsets require a supplied material"):
        match_prescription(prescription(surface), catalogue)


@pytest.mark.parametrize(
    ("extra",),
    [
        ({"nd_offset": "0.01", "vd_offset": "-0.2"},),
        (
            {
                "nd": "1.5",
                "vd": "50",
                "nd_offset": "0.01",
                "vd_offset": "-0.2",
            },
        ),
    ],
)
def test_input_rejects_offsets_without_base_typecode(extra):
    data = {
        "schema_version": 1,
        "title": "invalid offsets",
        "units": "mm",
        "surfaces": [{"id": "1", "radius": "10", "thickness": "2", **extra}],
    }
    with pytest.raises(InputError, match="offsets require a supplied material"):
        prescription_from_dict(data)


def test_air_and_unmatched_are_distinct_and_preserved():
    source = Prescription(
        1,
        "test",
        "mm",
        (
            Surface("1", "10", "2"),
            Surface("2", "10", "2", nd="1.5", vd="50"),
        ),
    )
    result = match_prescription(source, [])
    assert [item.status for item in result.matches] == ["air", "unmatched"]
    assert result.prescription == source


def test_real_sample_catalogue_is_a_diagnostic_not_a_ranking_golden():
    from pathlib import Path

    root = Path(__file__).parents[1]
    result = match_prescription(
        load_sectioned_csv(root / "samples" / "sample_lens_data.csv"),
        load_catalog_csv(root / "samples" / "combined_glass_catalog.csv"),
    )
    assert len(result.matches) == len(result.prescription.surfaces)
    assert all(match.reason for match in result.matches)
    assert set(result.report()["summary"]) == {
        "air",
        "supplied",
        "close",
        "offset",
        "unmatched",
    }
