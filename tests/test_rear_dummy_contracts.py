from dataclasses import replace
from decimal import Decimal

import pytest

from optimatch.export import render_zmx
from optimatch.matching import Match, MatchingResult, match_prescription
from optimatch.models import (
    Asphere,
    Configuration,
    Prescription,
    Solve,
    Surface,
    SystemSettings,
    Wavelength,
)


def _result(surfaces, configurations, *, solves=(), aspheres=(), units="mm"):
    prescription = Prescription(
        1,
        "rear contract",
        units,
        tuple(surfaces),
        tuple(aspheres),
        tuple(configurations),
        tuple(solves),
        SystemSettings(
            stop_surface="front_1",
            aperture_type="f_number",
            aperture_value="4",
            field_type="angle",
            fields=("0", "20"),
            wavelengths=(Wavelength("0.55", "1", True),),
        ),
        declared_symbols=tuple("abcd"),
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
    return MatchingResult(prescription, matches)


def _two_groups(configurations, *, solves=(), units="mm"):
    return _result(
        (
            Surface("OBJ", "0", "infinity"),
            Surface("front_1", "50", "2", material="S-BSL7", stop=True),
            Surface("rear_1", "-50", "a"),
            Surface("front_2", "40", "2", material="S-BSL7"),
            Surface("rear_2", "-40", "b"),
            Surface("IMG", "0", ""),
        ),
        configurations,
        solves=solves,
        units=units,
    )


def _zmx_state(text, configuration):
    base = {}
    overrides = {}
    solves = {}
    current = None
    for line in text.splitlines():
        parts = line.strip().split()
        if not parts:
            continue
        if parts[0] == "SURF":
            current = int(parts[1])
        elif parts[0] == "DISZ" and current is not None:
            base[current] = Decimal(parts[1])
        elif parts[0] == "THIC" and int(parts[2]) == configuration:
            overrides[int(parts[1])] = Decimal(parts[3])
        elif parts[0] in {"TCOM", "TOLE"} and current is not None:
            solves[current] = (parts[0], int(parts[1]), Decimal(parts[2]))
    thicknesses = base | overrides
    for dependent, (kind, reference, total) in solves.items():
        if kind == "TCOM":
            thicknesses[dependent] = total - thicknesses[reference]
        else:
            thicknesses[dependent] = total - sum(
                (thicknesses[index] for index in range(reference, dependent)),
                Decimal(),
            )
    position = Decimal()
    positions = {1: position}
    for surface in range(1, max(base)):
        position += thicknesses[surface]
        positions[surface + 1] = position
    return thicknesses, positions, solves


def test_rounded_inferred_rear_split_uses_evaluated_gap_not_source_spelling():
    source = _two_groups(
        (
            Configuration("one", {"a": "2.00", "b": "8.58"}),
            Configuration("two", {"a": "3.00", "b": "7.57"}),
        )
    )
    source = replace(
        source, prescription=replace(source.prescription, source_precision_trusted=True)
    )
    content, report = render_zmx(source)
    text = content.decode("utf-16")
    rear = report["zmx"]["rear_dummy"]
    assert [item["evaluated_original_gap"] for item in rear["configurations"]] == [
        "8.58",
        "7.58",
    ]
    assert rear["fixed_remainder"] == "6.58"
    for configuration, expected_gap in ((1, Decimal("2")), (2, Decimal("1"))):
        thicknesses, _, solves = _zmx_state(text, configuration)
        assert thicknesses[4] == expected_gap
        assert thicknesses[5] == Decimal("6.58")
        assert solves[4] == ("TCOM", 2, Decimal("4.00"))
        assert thicknesses[4] + thicknesses[5] == Decimal(
            rear["configurations"][configuration - 1]["evaluated_original_gap"]
        )


def test_model_glass_remains_model_after_dummy_insertion():
    base = _two_groups(
        (
            Configuration("one", {"a": "2", "b": "8"}),
            Configuration("two", {"a": "4", "b": "6"}),
        ),
        solves=(Solve("complementary_gap", "rear_2", "rear_1", "10"),),
    )
    surfaces = list(base.prescription.surfaces)
    surfaces[3] = replace(surfaces[3], material=None, nd="1.6934996", vd="53.1858")
    matched = match_prescription(
        replace(base.prescription, surfaces=tuple(surfaces)), []
    )
    text = render_zmx(matched)[0].decode("utf-16")
    assert "GLAS ___BLANK 1 0 1.6934996 53.1858" in text
    assert "SURF 5" in text


def test_direct_rear_tole_is_split_and_remains_tole():
    result = _two_groups(
        (
            Configuration("one", {"a": "2", "b": "8"}),
            Configuration("two", {"a": "4", "b": "6"}),
        ),
        solves=(Solve("constant_span", "rear_2", "rear_1", "12"),),
    )
    text, report = render_zmx(result)
    assert report["zmx"]["rear_dummy"]["transformed_solve"]["total"] == "7"
    assert "TOLE 2 7" in text.decode("utf-16")


def test_varying_excluded_downstream_tole_is_not_relocated():
    base = _two_groups(
        (
            Configuration("one", {"a": "2", "b": "8"}),
            Configuration("two", {"a": "4", "b": "6"}),
        )
    )
    surfaces = (
        *base.prescription.surfaces[:-1],
        Surface("tail", "0", "c"),
        base.prescription.surfaces[-1],
    )
    configurations = (
        Configuration("one", {"a": "2", "b": "8", "c": "2"}),
        Configuration("two", {"a": "4", "b": "5", "c": "3"}),
    )
    prescription = replace(
        base.prescription,
        surfaces=surfaces,
        configurations=configurations,
        solves=(Solve("constant_span", "tail", "rear_1", "14"),),
    )
    _, report = render_zmx(replace(base, prescription=prescription))
    rear = report["zmx"]["rear_dummy"]
    assert rear["status"] == "not_inserted"
    assert rear["reason"] == "downstream TOLE span varies"
    assert report["zmx"]["surface_map"] == {
        surface.source_id: index for index, surface in enumerate(surfaces)
    }


def test_coupled_constraint_prevents_rear_rewrite():
    configurations = (
        Configuration("one", {"a": "2", "b": "8", "c": "8"}),
        Configuration("two", {"a": "4", "b": "6", "c": "6"}),
    )
    base = _two_groups(configurations)
    surfaces = (
        *base.prescription.surfaces[:-1],
        Surface("tail", "0", "c"),
        base.prescription.surfaces[-1],
    )
    prescription = replace(
        base.prescription,
        surfaces=surfaces,
        configurations=configurations,
        solves=(
            Solve("complementary_gap", "rear_2", "rear_1", "10"),
            Solve("complementary_gap", "tail", "rear_1", "10"),
        ),
    )
    _, report = render_zmx(replace(base, prescription=prescription))
    assert report["zmx"]["rear_dummy"]["reason"] == "coupled solve interaction"
    assert "__OPTIMATCH_DUMMY" not in report["zmx"]["surface_map"]


def test_dummy_id_collision_preserves_stop_asphere_and_mapping():
    base = _two_groups(
        (
            Configuration("one", {"a": "2", "b": "8"}),
            Configuration("two", {"a": "4", "b": "6"}),
        ),
        solves=(Solve("complementary_gap", "rear_2", "rear_1", "10"),),
    )
    surfaces = list(base.prescription.surfaces)
    surfaces[1] = replace(surfaces[1], stop=False)
    surfaces.insert(-1, Surface("__OPTIMATCH_DUMMY_1", "0", "1", stop=True))
    system = replace(base.prescription.system, stop_surface="__OPTIMATCH_DUMMY_1")
    asphere = Asphere("__OPTIMATCH_DUMMY_1", "even", "0", {4: "1e-5"})
    prescription = replace(
        base.prescription, surfaces=tuple(surfaces), system=system, aspheres=(asphere,)
    )
    rematched = _result(
        tuple(surfaces),
        base.prescription.configurations,
        solves=base.prescription.solves,
        aspheres=(asphere,),
    )
    rematched = replace(rematched, prescription=prescription)
    text, report = render_zmx(rematched)
    decoded = text.decode("utf-16")
    assert report["zmx"]["rear_dummy"]["dummy_surface_id"] == "__OPTIMATCH_DUMMY_2"
    assert report["zmx"]["surface_map"]["__OPTIMATCH_DUMMY_1"] == 6
    assert report["zmx"]["surface_map"]["IMG"] == 7
    assert "GLRS 6 0" in decoded
    assert (
        decoded.index("SURF 6")
        < decoded.index("TYPE EVENASPH")
        < decoded.index("SURF 7")
    )


@pytest.mark.parametrize(
    ("units", "minimum", "remainder"),
    [
        ("mm", "6", "5"),
        ("cm", ".6", ".5"),
        ("m", ".006", ".005"),
        ("in", ".6", str(Decimal(".6") - Decimal(1) / Decimal("25.4"))),
    ],
)
def test_split_uses_one_millimetre_in_source_units(units, minimum, remainder):
    result = _two_groups(
        (
            Configuration("one", {"a": "2", "b": str(Decimal(minimum) + Decimal("2"))}),
            Configuration("two", {"a": "4", "b": minimum}),
        ),
        solves=(
            Solve(
                "complementary_gap",
                "rear_2",
                "rear_1",
                str(Decimal("4") + Decimal(minimum)),
            ),
        ),
        units=units,
    )
    content, report = render_zmx(result)
    assert Decimal(report["zmx"]["rear_dummy"]["fixed_remainder"]) == Decimal(remainder)
    text = content.decode("utf-16")
    for configuration, original_gap in (
        (1, Decimal(minimum) + Decimal("2")),
        (2, Decimal(minimum)),
    ):
        thicknesses, _, _ = _zmx_state(text, configuration)
        residual = thicknesses[4] + thicknesses[5] - original_gap
        if units == "in":
            assert abs(residual) < Decimal("1e-25")
        else:
            assert residual == 0
