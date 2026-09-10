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
    assert (
        text.index("THIC 0 1 1e10")
        < text.index("THIC 0 2 100")
        < text.index("THIC 1 1 2")
    )
    assert (
        text.index("APER 0 1 4") < text.index("APER 0 2 5") < text.index("FVCY 1 1 0")
    )


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
    assert "  DISZ 10" in text
    assert "DISZ gap" not in text


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
