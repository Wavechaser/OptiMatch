from decimal import Decimal

import pytest

from optics_prescription_matcher.export import _asphere_lines, render_zmx
from optics_prescription_matcher.matching import Match, MatchingResult
from optics_prescription_matcher.models import (
    Asphere,
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
