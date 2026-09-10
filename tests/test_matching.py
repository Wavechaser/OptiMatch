from dataclasses import replace
from decimal import Decimal

import pytest

from optimatch.inputs import (
    InputError,
    load_catalog_csv,
    load_sectioned_csv,
    prescription_from_dict,
)
from optimatch.matching import (
    PROFILES,
    match_prescription,
    pgf_to_dpgf,
)
from optimatch.models import (
    Asphere,
    CatalogGlass,
    Prescription,
    Surface,
)


def prescription(surface):
    return Prescription(1, "test", "mm", (surface,))


def glass(name, nd, vd, maker="Ohara", pgf=None, dpgf=None, molding=None):
    return CatalogGlass(maker, name, nd, vd, pgf, dpgf, precision_molding=molding)


@pytest.mark.parametrize(
    ("nd", "vd", "expected"),
    [
        ("1.500199", "50.099", "close"),
        ("1.5002", "50", "offset"),
        ("1.5", "50.1", "offset"),
        ("1.51999", "51.999", "offset"),
        ("1.52", "50", "model"),
        ("1.5", "52", "model"),
        ("1.520001", "50", "model"),
        ("1.5", "52.001", "model"),
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
    assert excluded_only.matches[0].status == "model"


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
    assert missing["residuals"]["dpgf"]["catalogue"] is None


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


def test_supplied_name_uses_exact_match_before_ohara_whitespace_lookup():
    supplied = Surface("1", "10", "2", material="S FPL 51")
    catalogue = [
        glass("S FPL 51", "1.5", "60", "Hoya"),
        glass("S-FPL51", "1.6", "50", "Ohara"),
    ]
    result = match_prescription(prescription(supplied), catalogue)
    assert result.matches[0].selected_manufacturer == "Hoya"
    assert result.prescription.surfaces[0].material == "S FPL 51"


def test_supplied_name_normalizes_whitespace_only_for_ohara():
    supplied = Surface("1", "10", "2", material="S - FPL 51")
    ohara = match_prescription(
        prescription(supplied), [glass("S-FPL51", "1.5", "60", "Ohara")]
    )
    assert ohara.matches[0].original_material == "S - FPL 51"
    assert ohara.matches[0].selected_typecode == "S-FPL51"
    assert ohara.prescription.surfaces[0].material == "S-FPL51"
    non_ohara = match_prescription(
        prescription(supplied), [glass("S-FPL51", "1.5", "60", "Hoya")]
    )
    assert non_ohara.matches[0].selected_manufacturer is None
    assert non_ohara.prescription.surfaces[0].material == "S - FPL 51"


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


def test_air_and_model_are_distinct_and_source_is_preserved():
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
    assert [item.status for item in result.matches] == ["air", "model"]
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
        "model",
        "unmatched",
    }


@pytest.mark.parametrize(
    ("profile", "order", "excluded"),
    [
        ("default", ("Ohara", "Hoya", "Hikari", "Other"), ()),
        ("canon", ("Ohara", "Hoya", "Other"), ("Hikari", "CDGM", "Schott", "Sumita")),
        ("nikon", ("Hikari", "Hoya", "Ohara", "Other"), ("CDGM", "Schott", "Sumita")),
        ("sony", ("Hoya", "Ohara", "Hikari", "Other"), ("CDGM", "Schott", "Sumita")),
        ("sigma", ("Hoya", "Ohara", "Other"), ("Hikari", "CDGM", "Schott", "Sumita")),
        (
            "fujifilm",
            ("Ohara", "Hoya", "CDGM", "Hikari", "Other"),
            ("Schott", "Sumita"),
        ),
    ],
)
def test_all_profile_orders_and_exclusions(profile, order, excluded):
    source = prescription(Surface("1", "10", "2", nd="1.5", vd="50"))
    for index, expected in enumerate(order):
        catalogue = [
            glass(maker, "1.5", "50", maker) for maker in reversed(order[index:])
        ]
        assert (
            match_prescription(source, catalogue, profile)
            .matches[0]
            .selected_manufacturer
            == expected
        )
    for maker in excluded:
        result = match_prescription(source, [glass(maker, "1.5", "50", maker)], profile)
        assert result.matches[0].status == "model"
        aspheric = replace(source, aspheres=(_asphere("1"),))
        molding = match_prescription(
            aspheric, [glass(maker, "1.5", "50", maker, molding=True)], profile
        )
        assert molding.matches[0].status == "model"
    assert tuple(PROFILES) == ("default", "canon", "nikon", "sony", "sigma", "fujifilm")


def test_pgf_to_dpgf_endpoints_midpoint_and_caller_context():
    from decimal import localcontext

    assert Decimal(pgf_to_dpgf(".582848", "36.26")) == 0
    assert Decimal(pgf_to_dpgf(".543528", "60.49")) == 0
    midpoint_vd = str((Decimal("36.26") + Decimal("60.49")) / 2)
    assert Decimal(pgf_to_dpgf(".57", midpoint_vd)) > 0
    with localcontext() as context:
        context.prec = 5
        assert pgf_to_dpgf(".582848", "36.26") == "0.000000"


def test_effective_dispersion_resolution_ignores_caller_decimal_context():
    from decimal import localcontext

    source = Surface("1", "10", "2", nd="1.5", vd="50.0", pgf=".55")
    with localcontext() as context:
        context.prec = 5
        match = match_prescription(
            prescription(source), [glass("G", "1.5", "50", pgf=".55")]
        ).matches[0]
    assert (
        match.source_effective_dispersion["dpgf"]["step"]
        == "0.01016227816756087494841106067"
    )


def test_effective_dispersion_derivation_precedence_resolution_and_immutability():
    surface = Surface("1", "10", "2", nd="1.5", vd="50.0", pgf=".55")
    result = match_prescription(
        prescription(surface),
        [glass("G", "1.5", "50", pgf=".55", dpgf=".123")],
    )
    selected = result.matches[0].selected
    effective = selected["source_effective_dispersion"]
    assert set(effective) == {"pgf", "dpgf"}
    assert effective["dpgf"]["provenance"] == "derived_from_pgf_vd"
    expected_step = Decimal(".01") + abs(
        (Decimal(".543528") - Decimal(".582848")) / Decimal("24.23")
    ) * Decimal(".1")
    assert Decimal(effective["dpgf"]["step"]) == expected_step
    assert selected["catalogue_effective_dispersion"]["dpgf"] == {
        "value": ".123",
        "provenance": "supplied",
        "step": "0.001",
    }
    assert result.prescription.surfaces[0].pgf == ".55"
    assert result.prescription.surfaces[0].dpgf is None
    assert set(selected["dispersion"]["residuals"]) == {"dpgf"}


def test_explicit_dual_source_compares_pgf_to_pgf_only_catalogue():
    source = Surface("1", "10", "2", nd="1.5", vd="50", pgf=".55", dpgf=".01")
    result = match_prescription(
        prescription(source), [glass("G", "1.5", "50", pgf=".551")]
    )
    residuals = result.matches[0].selected["dispersion"]["residuals"]
    assert residuals["pgf"]["catalogue"] == ".551"
    assert residuals["dpgf"]["catalogue_provenance"] == "derived_from_pgf_vd"


def test_model_pgf_source_retains_effective_dispersion_in_report():
    source = Surface("1", "10", "2", nd="1.9", vd="20.0", pgf=".70")
    match = match_prescription(prescription(source), []).matches[0]
    assert match.status == "model"
    assert (
        match.source_effective_dispersion["dpgf"]["provenance"] == "derived_from_pgf_vd"
    )


def test_model_has_no_catalogue_identity_or_offsets_and_legacy_summary_key():
    source = Surface("1", "10", "2", nd="1.9", vd="20")
    result = match_prescription(prescription(source), [])
    match = result.matches[0]
    assert match.status == "model"
    assert match.selected_manufacturer is None
    assert match.selected_typecode is None
    assert match.selected is None
    assert result.prescription.surfaces[0] == source
    assert result.report()["summary"]["model"] == 1
    assert result.report()["summary"]["unmatched"] == 0


@pytest.mark.parametrize(
    ("nd", "vd"), [("NaN", "50"), ("1.5", "Infinity"), ("0", "50"), ("1.5", "-1")]
)
def test_public_matcher_rejects_invalid_numeric_model_data(nd, vd):
    with pytest.raises(ValueError, match="finite positive|finite decimal string"):
        match_prescription(prescription(Surface("1", "10", "2", nd=nd, vd=vd)), [])


def test_derived_catalogue_dispersion_beats_missing_candidate():
    surface = Surface("1", "10", "2", nd="1.5", vd="50", pgf=".55")
    result = match_prescription(
        prescription(surface),
        [glass("MISSING", "1.5", "50"), glass("DERIVED", "1.5", "50", pgf=".55")],
    )
    assert result.matches[0].selected_typecode == "DERIVED"
    assert (
        result.matches[0].alternatives[0]["dispersion"]["missing_supplied_fields"] == 1
    )


def _asphere(surface_id):
    return Asphere(surface_id, "even", "0", {})


@pytest.mark.parametrize("trigger_id", ["1", "2"])
def test_front_or_back_asphere_promotes_molding_candidate(trigger_id):
    source = Prescription(
        1,
        "test",
        "mm",
        (Surface("1", "10", "2", nd="1.5", vd="50"), Surface("2", "20", "0")),
        (_asphere(trigger_id),),
    )
    result = match_prescription(
        source,
        [glass("ORDINARY", "1.5", "50"), glass("MOLD", "1.504", "50.4", molding=True)],
    )
    assert result.matches[0].status == "offset"
    assert result.matches[0].selected_typecode == "MOLD"
    assert result.matches[0].selected["catalogue_precision_molding"] is True
    assert trigger_id in result.matches[0].reason


@pytest.mark.parametrize(("nd", "vd"), [("1.505", "50.4"), ("1.504", "50.5")])
def test_molding_pool_is_strict_bounded_and_does_not_propagate_cemented_group(nd, vd):
    surfaces = (
        Surface("1", "10", "2", nd="1.5", vd="50"),
        Surface("2", "20", "2", nd="1.5", vd="50"),
        Surface("3", "30", "0"),
    )
    source = Prescription(1, "test", "mm", surfaces, (_asphere("1"),))
    catalogue = [
        glass("ORDINARY", "1.5", "50"),
        glass("BOUNDARY", nd, vd, molding=True),
    ]
    result = match_prescription(source, catalogue)
    assert [match.selected_typecode for match in result.matches[:2]] == [
        "ORDINARY",
        "ORDINARY",
    ]
    inside = [
        glass("ORDINARY", "1.5", "50"),
        glass("INSIDE", "1.504999", "50.499", molding=True),
    ]
    promoted = match_prescription(source, inside)
    assert promoted.matches[0].selected_typecode == "INSIDE"
    assert promoted.matches[1].selected_typecode == "ORDINARY"


def test_no_asphere_or_empty_molding_pool_keeps_ordinary_stable_ranking():
    source = prescription(Surface("1", "10", "2", nd="1.5", vd="50"))
    catalogue = [glass("B", "1.5", "50", molding=True), glass("A", "1.5", "50")]
    assert match_prescription(source, catalogue).matches[0].selected_typecode == "A"
    aspheric = replace(source, aspheres=(_asphere("1"),))
    assert (
        match_prescription(aspheric, reversed(catalogue)).matches[0].selected_typecode
        == "B"
    )


def test_supplied_name_is_authoritative_despite_asphere_profile_and_molding():
    supplied = Surface("1", "10", "2", material="KEEP", nd="1.5", vd="50")
    source = Prescription(1, "test", "mm", (supplied,), (_asphere("1"),))
    catalogue = [
        glass("KEEP", "1.5", "50", "Schott", molding=False),
        glass("MOLD", "1.5", "50", "Ohara", molding=True),
    ]
    result = match_prescription(source, catalogue, "canon")
    assert result.prescription.surfaces[0] == supplied
    assert result.matches[0].selected_typecode == "KEEP"
