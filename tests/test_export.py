from dataclasses import replace
from decimal import Decimal

import pytest

from optimatch.export import _asphere_lines, render_zmx
from optimatch.inputs import prescription_from_dict
from optimatch.matching import (
    Match,
    MatchingResult,
    match_prescription,
)
from optimatch.models import (
    Asphere,
    CatalogGlass,
    Configuration,
    Prescription,
    Solve,
    Surface,
    SystemSettings,
    Wavelength,
)


def result(*, aspheres=(), configurations=(), material="S-BSL7"):
    surfaces = (
        Surface("OBJ", "0", "infinity"),
        Surface("1", "50", "2", material=material, stop=True),
        Surface("2", "-50", "10"),
        Surface("IMG", "0", ""),
    )
    prescription = Prescription(
        1,
        "study",
        "mm",
        surfaces,
        aspheres,
        configurations,
        system=SystemSettings(
            aperture_type="f_number",
            aperture_value="4",
            field_type="angle",
            fields=("0", "5"),
            wavelengths=(Wavelength("0.55", "1", True),),
        ),
    )
    matches = tuple(
        Match(
            s.source_id,
            "supplied" if s.material else "air",
            "default",
            s.material,
            s.nd,
            s.vd,
            selected_typecode=s.material,
        )
        for s in surfaces
    )
    return MatchingResult(prescription, matches)


def test_render_zmx_is_utf16_bom_and_uses_verified_core_records():
    content, report = render_zmx(result())
    assert content.startswith(b"\xff\xfe")
    text = content.decode("utf-16")
    assert "VERS 221221 730 20120530 20120530" in text
    assert "UNIT MM X W X CM MR CPMM" in text
    assert "FNUM 4 1" in text and "FTYP 0 0 2 1 0 0 0 2" in text
    assert 'LTTL 0 1 "" 0 0 0 1 1 0 0.0 "" 0' in text
    assert "FVCY 1 1 0" not in text and "FVCY 2 1 0" in text
    assert "DIAM" not in text and "MEMA" not in text and "GCAT" not in text
    assert " None " not in text
    assert report["zmx"]["surface_map"] == {"OBJ": 0, "1": 1, "2": 2, "IMG": 3}


@pytest.mark.parametrize(
    ("pgf", "dpgf", "expected", "provenance"),
    [
        (None, "-.0072", "-.0072", "supplied"),
        (".56", None, None, "derived_from_pgf_vd"),
        (None, None, "0", "default_zero"),
    ],
)
def test_model_glass_uses_source_dispersion_precedence(pgf, dpgf, expected, provenance):
    base = result()
    surfaces = (
        base.prescription.surfaces[0],
        replace(
            base.prescription.surfaces[1],
            material=None,
            nd="1.6934996",
            vd="53.1858",
            pgf=pgf,
            dpgf=dpgf,
        ),
        *base.prescription.surfaces[2:],
    )
    matched = match_prescription(replace(base.prescription, surfaces=surfaces), [])
    text, report = render_zmx(matched)
    effective = matched.matches[1].source_effective_dispersion["dpgf"]
    expected = expected or effective["value"]
    assert effective["provenance"] == provenance
    assert f"GLAS ___BLANK 1 0 1.6934996 53.1858 {expected} 0 0 0 0 0" in text.decode(
        "utf-16"
    )
    assert report["zmx"]["setup"]["warnings"] == []


def test_named_and_offset_glass_use_effective_catalogue_dispersion_and_existing_modes():
    base = result()
    surfaces = list(base.prescription.surfaces)
    surfaces[1] = replace(surfaces[1], material=None, nd="1.51", vd="51")
    matched = match_prescription(
        replace(base.prescription, surfaces=tuple(surfaces)),
        [CatalogGlass("Ohara", "G", "1.5", "50", ".56", None)],
    )
    effective = matched.matches[1].selected["catalogue_effective_dispersion"]["dpgf"]
    line = next(
        line.strip()
        for line in render_zmx(matched)[0].decode("utf-16").splitlines()
        if "GLAS G" in line
    )
    assert line == f"GLAS G 4 0 1.5 50 {effective['value']} 0 0 0 0.01 1"

    surfaces[1] = replace(surfaces[1], nd="1.5", vd="50")
    close = match_prescription(
        replace(base.prescription, surfaces=tuple(surfaces)),
        [CatalogGlass("Ohara", "G", "1.5", "50", ".56", None)],
    )
    effective = close.matches[1].selected["catalogue_effective_dispersion"]["dpgf"]
    assert f"GLAS G 0 0 1.5 50 {effective['value']} 0 0 0 0 0" in render_zmx(close)[
        0
    ].decode("utf-16")


def test_named_glass_retains_legacy_raw_catalogue_dpgf_diagnostic():
    base = result()
    matches = list(base.matches)
    matches[1] = replace(
        matches[1],
        selected={
            "catalogue_nd": "1.5",
            "catalogue_vd": "50",
            "catalogue_dpgf": ".004",
        },
    )
    assert "GLAS S-BSL7 0 0 1.5 50 .004 0 0 0 0 0" in render_zmx(
        replace(base, matches=tuple(matches))
    )[0].decode("utf-16")


def test_explicit_unmatched_result_remains_rejected():
    base = result()
    matches = list(base.matches)
    matches[1] = replace(matches[1], status="unmatched")
    with pytest.raises(ValueError, match="blocked by unmatched"):
        render_zmx(replace(base, matches=tuple(matches)))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("nd", "NaN"),
        ("vd", "0"),
        ("pgf", "Infinity"),
        ("dpgf", "NaN"),
        ("dpgf", "0\n1"),
        ("pgf", 1),
    ],
)
def test_direct_model_result_rejects_invalid_optical_values(field, value):
    base = result()
    surfaces = list(base.prescription.surfaces)
    surfaces[1] = replace(
        replace(surfaces[1], material=None, nd="1.6", vd="50"), **{field: value}
    )
    matches = list(base.matches)
    matches[1] = Match("1", "model", "default", None, "1.6", "50")
    direct = MatchingResult(
        replace(base.prescription, surfaces=tuple(surfaces)), tuple(matches)
    )
    with pytest.raises(ValueError, match="model glass"):
        render_zmx(direct)


def test_direct_model_result_rejects_unknown_surface_and_catalogue_identity():
    base = result()
    unknown = replace(
        base,
        matches=base.matches
        + (Match("missing", "model", "default", None, "1.6", "50"),),
    )
    with pytest.raises(ValueError, match="unknown surface"):
        render_zmx(unknown)
    surfaces = list(base.prescription.surfaces)
    surfaces[1] = replace(surfaces[1], material=None, nd="1.6", vd="50")
    matches = list(base.matches)
    matches[1] = Match(
        "1", "model", "default", None, "1.6", "50", selected_typecode="BAD"
    )
    with pytest.raises(ValueError, match="catalogue identity"):
        render_zmx(
            MatchingResult(
                replace(base.prescription, surfaces=tuple(surfaces)), tuple(matches)
            )
        )
    matches[1] = Match("1", "model", "default", "S-BSL7", "1.6", "50")
    with pytest.raises(ValueError, match="catalogue identity"):
        render_zmx(
            MatchingResult(
                replace(base.prescription, surfaces=tuple(surfaces)), tuple(matches)
            )
        )


def _extended_values(lines):
    result = {}
    for line in lines:
        parts = line.split()
        if parts and parts[0] == "XDAT" and int(parts[1]) >= 3:
            result[int(parts[1])] = Decimal(parts[2])
    return result


@pytest.mark.parametrize("radius", [Decimal("0.5"), Decimal("1"), Decimal("2")])
def test_asphere_serialization_preserves_polynomial_sag(radius):
    cases = [
        Asphere("1", "even", "-0.2", {4: "1E-5", 20: "2E-12"}, "sag", "2"),
        Asphere("1", "odd", "-0.2", {3: "2E-6", 20: "2E-12"}, "sag", "2"),
    ]
    for asphere in cases:
        values = _extended_values(_asphere_lines(asphere))
        r0 = Decimal("2")
        powers = range(1, 21) if asphere.family == "odd" else range(2, 21, 2)
        actual = sum(
            values[(power + 2) if asphere.family == "odd" else (power // 2 + 2)]
            * (radius / r0) ** power
            for power in powers
        )
        expected = sum(
            Decimal(value) * radius**power
            for power, value in asphere.coefficients.items()
        )
        assert actual == expected


def test_ordinary_even_preserves_explicit_slots_and_missing_zeros():
    lines = _asphere_lines(Asphere("1", "even", "-1", {4: "1E-5", 16: "2E-20"}))
    assert "  PARM 1 0" in lines
    assert "  PARM 2 1E-5" in lines
    assert "  PARM 8 2E-20" in lines


def test_configuration_records_are_operand_major_and_infinity_is_numeric():
    configurations = (
        Configuration("far", {"OBJ": "infinity", "2": "10"}, "4"),
        Configuration("near", {"OBJ": "100", "2": "12"}, "5"),
    )
    text = render_zmx(result(configurations=configurations))[0].decode("utf-16")
    lines = text.splitlines()
    assert "THIC 1 1 2" not in text
    assert (
        lines.index('THIC 0 1 1e10 0 0 0 1 1 1 0 0 "" 0')
        < lines.index('THIC 0 2 100 0 0 0 1 1 1 0 0 "" 0')
        < lines.index('THIC 2 1 10 0 0 0 1 1 1 0 0 "" 0')
        < lines.index('THIC 2 2 12 0 0 0 1 1 1 0 0 "" 0')
    )
    assert "FVCY 1 1 0" not in text
    assert (
        lines.index('FVCY 2 1 0 0 0 0 1 1 1 0 0 "" 0')
        < lines.index('FVCY 2 2 0 0 0 0 1 1 1 0 0 "" 0')
        < lines.index('FVDY 2 1 0 0 0 0 1 1 1 0 0 "" 0')
        < lines.index('FVDY 2 2 0 0 0 0 1 1 1 0 0 "" 0')
    )
    assert lines[-1] == 'MOFF 0 2 "" 0 0 0 1 1 0 0.0 "" 0'


def test_multi_configuration_sections_and_titles_are_compact():
    configurations = (
        Configuration("far", {"OBJ": "infinity", "2": "10", "3": "20"}, "4"),
        Configuration("near", {"OBJ": "100", "2": "12", "3": "21"}, "5"),
    )
    base = result(configurations=configurations)
    surfaces = (
        *base.prescription.surfaces[:-1],
        Surface("3", "0", "20"),
        base.prescription.surfaces[-1],
    )
    changed = replace(base, prescription=replace(base.prescription, surfaces=surfaces))
    lines = render_zmx(changed)[0].decode("utf-16").splitlines()
    start = lines.index("MNUM 2 1") + 1
    records = lines[start:]
    assert records[:6] == [
        'LTTL 0 1 "far" 0 0 0 1 1 0 0.0 "" 0',
        'LTTL 0 2 "near" 0 0 0 1 1 0 0.0 "" 0',
        'MOFF 0 1 "" 0 0 0 1 1 0 0.0 "" 0',
        'MOFF 0 2 "" 0 0 0 1 1 0 0.0 "" 0',
        'THIC 0 1 1e10 0 0 0 1 1 1 0 0 "" 0',
        'THIC 0 2 100 0 0 0 1 1 1 0 0 "" 0',
    ]
    second_thickness = records.index('THIC 2 2 12 0 0 0 1 1 1 0 0 "" 0')
    assert records[second_thickness + 1] == 'THIC 3 1 20 0 0 0 1 1 1 0 0 "" 0'
    assert records[-2:] == [
        'MOFF 0 1 "" 0 0 0 1 1 0 0.0 "" 0',
        'MOFF 0 2 "" 0 0 0 1 1 0 0.0 "" 0',
    ]


@pytest.mark.parametrize("name", ['bad"quote', "bad\nline", "bad\x7fcontrol"])
def test_multi_configuration_title_rejects_unsupported_zmx_text(name):
    base = result(
        configurations=(
            Configuration(name, {"2": "10"}),
            Configuration("valid", {"2": "12"}),
        )
    )
    with pytest.raises(ValueError, match="configuration title"):
        render_zmx(base)


def test_single_explicit_configuration_keeps_its_title():
    base = result(configurations=(Configuration("near", {"2": "12"}),))
    text = render_zmx(base)[0].decode("utf-16")
    assert 'LTTL 0 1 "near" 0 0 0 1 1 0 0.0 "" 0' in text


def test_partial_configuration_aperture_inherits_explicit_base_value():
    configurations = (
        Configuration("override", {"OBJ": "100", "2": "10"}, "4"),
        Configuration("base", {"OBJ": "50", "2": "12"}),
    )
    text = render_zmx(result(configurations=configurations))[0].decode("utf-16")
    assert "APER 0 1 4 " in text
    assert "APER 0 2 4 " in text


def test_base_only_explicit_dependent_renders_resolved_disz_not_symbol():
    base = result()
    surfaces = (
        Surface("OBJ", "0", "infinity"),
        Surface("1", "50", "2", material="S-BSL7", stop=True),
        Surface("2", "-50", "gap"),
        Surface("IMG", "0", ""),
    )
    prescription = Prescription(
        1,
        "base solve",
        "mm",
        surfaces,
        solves=(Solve("complementary_gap", "2", "1", "12"),),
        system=base.prescription.system,
        declared_symbols=("gap",),
    )
    matches = tuple(
        Match(
            surface.source_id,
            "supplied" if surface.material else "air",
            "default",
            surface.material,
            surface.nd,
            surface.vd,
            selected_typecode=surface.material,
        )
        for surface in surfaces
    )
    text = render_zmx(MatchingResult(prescription, matches))[0].decode("utf-16")
    assert "  DISZ INFINITY" in text
    assert "  DISZ 1" in text
    assert "  DISZ 9" in text
    assert "DISZ gap" not in text


@pytest.mark.parametrize(
    ("units", "reference", "gaps", "total"),
    [
        ("mm", ("2", "4", "4"), ("10", "8", "8"), "12"),
        ("cm", (".2", ".4", ".4"), ("1", ".8", ".8"), "1.2"),
        ("m", (".002", ".004", ".004"), (".010", ".008", ".008"), ".012"),
        (
            "in",
            (".07874015748", ".15748031496", ".15748031496"),
            (".3937007874", ".31496062992", ".31496062992"),
            ".47244094488",
        ),
    ],
)
def test_rear_tcom_dummy_uses_minimum_gap_and_preserves_coordinates(
    units, reference, gaps, total
):
    configurations = tuple(
        Configuration(name, {"1": ref, "2": gap})
        for name, ref, gap in zip(("far", "near", "tie"), reference, gaps, strict=True)
    )
    base = result(configurations=configurations)
    prescription = replace(
        base.prescription,
        units=units,
        solves=(Solve("complementary_gap", "2", "1", total),),
    )
    content, report = render_zmx(replace(base, prescription=prescription))
    lines = content.decode("utf-16").splitlines()
    dummy = report["zmx"]["rear_dummy"]
    assert dummy["status"] == "inserted"
    assert dummy["rear_boundary"] == "2"
    assert dummy["minimum_configurations"] == [2, 3]
    expected_remainder = min(map(Decimal, gaps)) - Decimal("1") / Decimal(
        {"mm": "1", "cm": "10", "m": "1000", "in": "25.4"}[units]
    )
    assert Decimal(dummy["fixed_remainder"]) == expected_remainder
    dummy_id = dummy["dummy_surface_id"]
    assert report["zmx"]["surface_map"][dummy_id] == 3
    assert report["zmx"]["source_surface_map"] == {"OBJ": 0, "1": 1, "2": 2, "IMG": 3}
    transformed_total = Decimal(total) - expected_remainder
    assert f"  TCOM 1 {transformed_total}" in lines
    assert "SURF 3" in lines and any(
        line.startswith("  DISZ ")
        and Decimal(line.removeprefix("  DISZ ")) == expected_remainder
        for line in lines
    )


def test_rear_downstream_tole_relocates_across_invariant_coverglass():
    configurations = (
        Configuration("far", {"1": "2", "2": "8", "3": "1", "4": "1"}),
        Configuration("near", {"1": "4", "2": "6", "3": "1", "4": "1"}),
    )
    base = result(configurations=configurations)
    surfaces = (
        Surface("OBJ", "0", "infinity"),
        Surface("1", "50", "2", material="S-BSL7", stop=True),
        Surface("2", "-50", "8"),
        Surface("3", "0", "1", material="S-BSL7"),
        Surface("4", "0", "1"),
        Surface("IMG", "0", ""),
    )
    prescription = replace(
        base.prescription,
        surfaces=surfaces,
        solves=(Solve("constant_span", "4", "1", "12"),),
    )
    _, report = render_zmx(replace(base, prescription=prescription))
    dummy = report["zmx"]["rear_dummy"]
    assert dummy["status"] == "inserted"
    assert dummy["rear_boundary"] == "2"
    assert dummy["fixed_remainder"] == "5"
    assert dummy["transformed_solve"] == {
        "kind": "constant_span",
        "surface_id": "2",
        "reference_surface_id": "1",
        "total": "5",
        "totals": (),
        "origin": "explicit",
        "reverse": False,
    }


def test_rear_dummy_skips_unsupported_downstream_complementary_solve():
    base = result(
        configurations=(
            Configuration("far", {"1": "2", "2": "8", "3": "2"}),
            Configuration("near", {"1": "4", "2": "6", "3": "0"}),
        )
    )
    surfaces = (
        *base.prescription.surfaces[:-1],
        Surface("3", "0", "2"),
        base.prescription.surfaces[-1],
    )
    prescription = replace(
        base.prescription,
        surfaces=surfaces,
        solves=(Solve("complementary_gap", "3", "1", "4"),),
    )
    _, report = render_zmx(replace(base, prescription=prescription))
    assert report["zmx"]["rear_dummy"]["status"] == "not_inserted"
    assert "downstream complementary" in report["zmx"]["rear_dummy"]["reason"]


def test_no_rear_dummy_keeps_unadjusted_rounded_inferred_thickness():
    base = result()
    surfaces = (
        Surface("OBJ", "0", "infinity"),
        Surface("1", "0", "a", stop=True),
        Surface("2", "0", "b"),
        Surface("IMG", "0", ""),
    )
    prescription = replace(
        base.prescription,
        surfaces=surfaces,
        configurations=(
            Configuration("one", {"a": "4.00", "b": "6.57"}),
            Configuration("two", {"a": "2.00", "b": "8.58"}),
            Configuration("three", {"a": "3.00", "b": "7.58"}),
        ),
        declared_symbols=("a", "b"),
        source_precision_trusted=True,
    )
    text, report = render_zmx(replace(base, prescription=prescription))
    assert report["zmx"]["rear_dummy"]["status"] == "not_inserted"
    assert report["zmx"]["rear_dummy"]["reason"] == "no powered group"
    assert "  DISZ 6.57\n" in text.decode("utf-16")


def test_rear_dummy_handles_cemented_planar_group_asphere_and_coverglass():
    base = result(
        configurations=(
            Configuration("far", {"2": "2", "3": "8"}),
            Configuration("near", {"2": "4", "3": "6"}),
        )
    )
    surfaces = (
        Surface("OBJ", "0", "infinity"),
        Surface("1", "0", "1", material="S-BSL7", stop=True),
        Surface("2", "0", "2", material="S-LAH58"),
        Surface("3", "0", "8"),
        Surface("4", "0", "1", material="S-BSL7"),
        Surface("5", "0", "1"),
        Surface("IMG", "0", ""),
    )
    prescription = replace(
        base.prescription,
        surfaces=surfaces,
        aspheres=(Asphere("3", "even", "0", {4: "1E-5"}),),
        solves=(Solve("complementary_gap", "3", "2", "10"),),
    )
    _, report = render_zmx(replace(base, prescription=prescription))
    dummy = report["zmx"]["rear_dummy"]
    assert dummy["status"] == "inserted"
    assert dummy["rear_boundary"] == "3"
    assert report["zmx"]["surface_map"][dummy["dummy_surface_id"]] == 4
    assert report["zmx"]["surface_map"]["4"] == 5


def test_rear_dummy_reports_no_eligible_solve_and_negative_remainder():
    base = result()
    _, report = render_zmx(base)
    assert report["zmx"]["rear_dummy"] == {
        "status": "not_inserted",
        "source_solves": [],
        "reason": "no eligible rear solve",
        "rear_boundary": "2",
    }

    configured = replace(
        base,
        prescription=replace(
            base.prescription,
            configurations=(Configuration("short", {"1": "1", "2": ".5"}),),
            solves=(Solve("complementary_gap", "2", "1", "1.5"),),
        ),
    )
    _, negative = render_zmx(configured)
    dummy = negative["zmx"]["rear_dummy"]
    assert dummy["fixed_remainder"] == "-0.5"
    assert dummy["configurations"][0]["solved_gap"] == "1.0"
    assert negative["zmx"]["setup"]["warnings"][-1].startswith("rear dummy")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: Prescription(1, "x", "mm", p.surfaces, system=None),
        lambda p: Prescription(1, "x", "mm", p.surfaces[:-1], system=p.system),
        lambda p: Prescription(
            1,
            "x",
            "mm",
            tuple(
                Surface(s.source_id, s.radius, s.thickness, s.material)
                for s in p.surfaces
            ),
            system=p.system,
        ),
    ],
)
def test_zmx_requires_complete_system_sequence_and_stop(mutation):
    base = result()
    changed = mutation(base.prescription)
    with pytest.raises(ValueError):
        render_zmx(MatchingResult(changed, base.matches[: len(changed.surfaces)]))


def test_zmx_rejects_reserved_internal_ids_and_control_character_material():
    base = result()
    internal = tuple(base.prescription.surfaces[:2]) + (
        Surface("img", "0", "1"),
        *base.prescription.surfaces[2:],
    )
    with pytest.raises(ValueError, match="reserved"):
        render_zmx(
            MatchingResult(
                Prescription(1, "x", "mm", internal, system=base.prescription.system),
                base.matches + (base.matches[-1],),
            )
        )
    unsafe = result(material="BAD\x00TOKEN")
    with pytest.raises(ValueError, match="unsafe ZMX token"):
        render_zmx(unsafe)


@pytest.mark.parametrize(
    "preset, expected",
    [
        ("1-type", "0 1.6 3.2 4.8 6.4 8"),
        ("m43", "0 2 4 6 8.5 11"),
        ("aps-c", "0 3 6 9 12 15"),
        ("full-frame", "0 4 8 12 17 22"),
        ("44x33", "0 5 10 15 21 27"),
    ],
)
def test_setup_presets_defaults_and_source_preservation(preset, expected):
    base = result()
    base = replace(base, prescription=replace(base.prescription, system=None))
    content, report = render_zmx(base, field_preset=preset)
    lines = content.decode("utf-16").splitlines()
    assert f"YFLN {expected}" in lines
    assert "FTYP 3 0 6 5 0 0 0 2" in lines
    assert "XFLN 0 0 0 0 0 0" in lines
    assert "FWGN 1 1 1 1 1 1" in lines
    for token in ("VDXN", "VCXN", "VDYN", "VCYN"):
        assert f"{token} 0 0 0 0 0 0" in lines
    assert [line for line in lines if line.startswith("WAVM")] == [
        "WAVM 1 0.486133 0.9393",
        "WAVM 2 0.546073 1.000",
        "WAVM 3 0.656273 0.7349",
        "WAVM 4 0.587562 0.9507",
        "WAVM 5 0.435833 0.7868",
    ]
    assert "PWAV 2" in lines and "FNUM 0 1" in lines
    assert "RAIM 0 1 1 1 0 0 0 0 0 1" in lines
    assert "GLRS 1 0" in lines
    assert base.prescription.system is None
    assert report["zmx"]["setup"]["warnings"]


@pytest.mark.parametrize("units", ["mm", "cm", "m", "in"])
def test_fisheye_preset_uses_unscaled_angle_fields(units):
    base = result()
    base = replace(
        base,
        prescription=replace(base.prescription, units=units, system=None),
    )
    content, report = render_zmx(base, field_preset="fisheye")
    lines = content.decode("utf-16").splitlines()
    assert "FTYP 0 0 6 5 0 0 0 2" in lines
    assert "YFLN 0 18 36 54 72 89" in lines
    assert report["zmx"]["setup"]["field_type"] == "angle"


def test_fisheye_preset_keeps_explicit_compatible_fields():
    base = result()
    system = SystemSettings(field_type="angle", fields=("0", "42"))
    changed = replace(base, prescription=replace(base.prescription, system=system))
    text = render_zmx(changed, field_preset="fisheye")[0].decode("utf-16")
    assert "FTYP 0 0 2 5 0 0 0 2" in text
    assert "YFLN 0 42\n" in text


def test_fisheye_metadata_preset_infers_angle_fields():
    prescription = prescription_from_dict(
        {
            "schema_version": 1,
            "title": "fisheye",
            "units": "cm",
            "surfaces": [
                {"id": "OBJ", "radius": "0", "thickness": "infinity"},
                {"id": "STOP", "radius": "0", "thickness": "1", "stop": True},
                {"id": "IMG", "radius": "0", "thickness": ""},
            ],
            "system": {"field_preset": "fisheye"},
        }
    )
    base = replace(result(), prescription=prescription, matches=())
    text = render_zmx(base)[0].decode("utf-16")
    assert "FTYP 0 0 6 5 0 0 0 2" in text
    assert "YFLN 0 18 36 54 72 89" in text


def test_preset_json_input_units_and_explicit_precedence():
    prescription = prescription_from_dict(
        {
            "schema_version": 1,
            "title": "preset",
            "units": "cm",
            "surfaces": [
                {"id": "OBJ", "radius": "0", "thickness": "infinity"},
                {"id": "STOP", "radius": "0", "thickness": "1", "stop": True},
                {"id": "IMG", "radius": "0", "thickness": ""},
            ],
            "system": {"field_preset": "full-frame"},
        }
    )
    base = replace(result(), prescription=prescription, matches=())
    text = render_zmx(base)[0].decode("utf-16")
    assert "YFLN 0 0.4 0.8 1.2 1.7 2.2" in text
    system = replace(
        prescription.system,
        fields=("0", "0.8"),
        wavelengths=(Wavelength("0.55555555", "0.123456", True),),
    )
    changed = replace(base, prescription=replace(prescription, system=system))
    text = render_zmx(changed, field_preset="aps-c")[0].decode("utf-16")
    assert "YFLN 0 0.8\n" in text
    assert "WAVM 1 0.55555555 0.123456" in text and "PWAV 1" in text


def test_setup_aperture_from_configuration_and_mapped_stop():
    base = result(
        configurations=(Configuration("one", {}, "2.8"), Configuration("two", {}, "4"))
    )
    surfaces = tuple(
        replace(s, stop=(s.source_id == "2")) for s in base.prescription.surfaces
    )
    base = replace(
        base,
        prescription=replace(
            base.prescription,
            surfaces=surfaces,
            system=SystemSettings(field_preset="m43"),
        ),
    )
    text, report = render_zmx(base)
    assert "FNUM 2.8 1" in text.decode("utf-16")
    assert "GLRS 2 0" in text.decode("utf-16")
    assert report["zmx"]["setup"]["aperture_source"] == "first_configuration"


def test_setup_rejects_unknown_preset_wrong_field_type_and_negative_aperture():
    for system, message in [
        (SystemSettings(field_preset="guess"), "unknown field_preset"),
        (SystemSettings(field_type="angle", field_preset="aps-c"), "real_image_height"),
        (
            SystemSettings(field_type="real_image_height", field_preset="fisheye"),
            "angle",
        ),
        (SystemSettings(field_preset="aps-c", aperture_value="-1"), "nonnegative"),
    ]:
        base = result()
        with pytest.raises(ValueError, match=message):
            render_zmx(
                replace(base, prescription=replace(base.prescription, system=system))
            )
