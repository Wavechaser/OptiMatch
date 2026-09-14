from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from optimatch.__main__ import main
from optimatch.export import (
    _asphere_lines,
    _evaluated_solve_values,
    render_prescription_csv,
    render_zmx,
)
from optimatch.export_setup import (
    ExportSetup,
    orient_solves,
    prepare_solves,
    solve_terms,
)
from optimatch.inputs import InputError, load_sectioned_csv, prescription_from_dict
from optimatch.matching import match_prescription
from optimatch.models import (
    Asphere,
    Configuration,
    Prescription,
    Solve,
    Surface,
    SystemSettings,
)
from optimatch.solves import ResolvedSolve, resolve_solves


def study(*, solves=(), powered=False, configurations=None, aspheres=()):
    surfaces = (
        (Surface("OBJ", "0", "infinity"),)
        + tuple(
            Surface(
                str(i),
                "30" if powered and i == 2 else "0",
                str(i + 1),
                material="S-BSL7" if powered and i == 2 else None,
                stop=i == 1,
            )
            for i in range(1, 8)
        )
        + (Surface("IMG", "0", ""),)
    )
    source = Prescription(
        1,
        "synthetic controls",
        "mm",
        surfaces,
        aspheres=aspheres,
        solves=solves,
        configurations=configurations
        if configurations is not None
        else (
            Configuration("far", {"1": "2", "3": "4"}),
            Configuration("near", {"1": "3", "3": "6"}),
        ),
        system=SystemSettings(aperture_value="4", field_preset="aps-c"),
    )
    return match_prescription(source, ())


@pytest.mark.parametrize(
    "direction,dependent,reference", [("normal", "3", "1"), ("reversed", "1", "4")]
)
def test_forced_position_preserves_inclusive_span(direction, dependent, reference):
    source = study()
    content, report = render_zmx(
        source,
        export_setup=ExportSetup(
            force_positions=(("1", "3"),), position_direction=direction
        ),
    )
    solve = report["zmx"]["export_solves"][0]
    assert (solve["surface_id"], solve["reference_surface_id"]) == (
        dependent,
        reference,
    )
    assert tuple(solve["totals"]) == ("9", "12")
    assert f"TSP2 {dependent} 2 12 " in content.decode("utf-16")
    assert f"THIC {dependent} " not in content.decode("utf-16")
    assert source.prescription.solves == ()


def test_forced_compensator_totals_and_constant_total_omission():
    setup = ExportSetup(force_compensators=(("1", "3"),))
    content, report = render_zmx(study(), export_setup=setup)
    assert "TSP2 3 1 6 " in content.decode("utf-16")
    assert "TSP2 3 2 9 " in content.decode("utf-16")
    assert report["zmx"]["export_solves"][0]["origin"] == "forced"
    content, _ = render_zmx(
        study(
            configurations=(
                Configuration("far", {"1": "2", "3": "4"}),
                Configuration("near", {"1": "3", "3": "3"}),
            )
        ),
        export_setup=setup,
    )
    assert "TSP2 " not in content.decode("utf-16")


@pytest.mark.parametrize("direction", ["normal", "reversed"])
def test_direction_preserves_explicit_input(direction):
    source = study(solves=(Solve("constant_span", "1", "4", "9"),), configurations=())
    _, report = render_zmx(
        source, export_setup=ExportSetup(position_direction=direction)
    )
    solve = report["zmx"]["export_solves"][0]
    assert (solve["surface_id"], solve["reference_surface_id"]) == ("1", "4")


def test_forcing_overrides_explicit_dependent_and_reports_it():
    source = study(solves=(Solve("constant_span", "3", "1", "999"),))
    _, report = render_zmx(
        source, export_setup=ExportSetup(force_compensators=(("1", "3"),))
    )
    assert report["zmx"]["export_solves"][0]["kind"] == "complementary_gap"
    assert report["zmx"]["solve_diagnostics"][0]["status"] == "overridden"
    assert source.prescription.solves[0].total == "999"


def test_forcing_reverse_replaces_explicit_same_span():
    source = study(solves=(Solve("constant_span", "3", "1", "999"),))
    _, report = render_zmx(
        source,
        export_setup=ExportSetup(
            force_positions=(("1", "3"),), position_direction="reversed"
        ),
    )
    assert report["zmx"]["export_solves"][0]["surface_id"] == "1"
    assert report["zmx"]["solve_diagnostics"][0]["status"] == "overridden"


def test_direction_changes_inferred_position_without_changing_search_result():
    source = study(
        configurations=(
            Configuration("far", {"1": "2", "3": "4"}),
            Configuration("near", {"1": "3", "3": "3"}),
        )
    )
    source = replace(
        source,
        prescription=replace(
            source.prescription,
            surfaces=tuple(
                replace(s, material="S-BSL7") if s.source_id == "1" else s
                for s in source.prescription.surfaces
            ),
        ),
    )
    _, normal = render_zmx(source)
    _, reversed_report = render_zmx(
        source, export_setup=ExportSetup(position_direction="reversed")
    )
    assert normal["zmx"]["solves"] == reversed_report["zmx"]["solves"]
    assert normal["zmx"]["export_solves"][0]["kind"] == "constant_span"
    assert normal["zmx"]["export_solves"][0]["surface_id"] == "3"
    assert reversed_report["zmx"]["export_solves"][0]["surface_id"] == "1"
    assert reversed_report["zmx"]["export_solves"][0]["reference_surface_id"] == "4"


def test_reversal_keeps_accepted_rounding_adjustment_on_original_thickness():
    source = study(
        configurations=(
            Configuration("far", {"1": "2.00", "3": "4.00"}),
            Configuration("near", {"1": "3.00", "3": "3.01"}),
        )
    )
    source = replace(
        source,
        prescription=replace(
            source.prescription,
            source_precision_trusted=True,
            surfaces=tuple(
                replace(s, material="S-BSL7") if s.source_id == "1" else s
                for s in source.prescription.surfaces
            ),
        ),
    )
    controls = ExportSetup(position_direction="reversed")
    accepted = prepare_solves(source.prescription, controls)
    expected = _evaluated_solve_values(accepted, source.prescription.surfaces)
    content, report = render_zmx(source, export_setup=controls)
    assert report["zmx"]["export_solves"][0]["surface_id"] == "1"
    assert f"THIC 3 1 {expected[0]['3']} " in content.decode("utf-16")
    assert expected[0]["3"] != source.prescription.configurations[0].thicknesses["3"]


@pytest.mark.parametrize("direction", ["normal", "reversed"])
def test_single_thickness_span(direction):
    _, report = render_zmx(
        study(configurations=()),
        export_setup=ExportSetup(
            force_positions=(("1", "1"),), position_direction=direction
        ),
    )
    solve = report["zmx"]["export_solves"][0]
    assert solve["surface_id"] == "1"
    assert solve["reference_surface_id"] == ("1" if direction == "normal" else "2")
    assert solve["total"] == "2"


def test_multiple_independent_forced_solves_survive_inference():
    _, report = render_zmx(
        study(), export_setup=ExportSetup(force_compensators=(("1", "3"), ("5", "7")))
    )
    assert [
        (item["surface_id"], item["origin"]) for item in report["zmx"]["export_solves"]
    ] == [("3", "forced"), ("7", "forced")]


def test_cli_repeated_controls_and_dummy_ois_remapping(tmp_path):
    import json

    fixtures = Path(__file__).parent / "fixtures"
    prefix = tmp_path / "study"
    assert (
        main(
            [
                str(fixtures / "study.csv"),
                "--catalog",
                str(fixtures / "catalog.csv"),
                "--output",
                str(prefix),
                "--field-preset",
                "aps-c",
                "--force-position",
                "1",
                "2",
                "--position-direction",
                "reversed",
                "--ois",
                "1",
                "3",
            ]
        )
        == 0
    )
    report = json.loads(prefix.with_suffix(".report.json").read_text(encoding="utf-8"))[
        "zmx"
    ]
    assert report["rear_dummy"]["status"] == "inserted"
    assert report["ois"][0]["before_export_surface"] == 4
    text = prefix.with_suffix(".zmx").read_text(encoding="utf-16")
    row = report["ois"][0]["cady_operand_row"]
    assert f'CBDY 4 2 0 3 0 0 2 {row} -1 0 0 "" 0' in text


@pytest.mark.parametrize(
    "setup,pattern",
    [
        (ExportSetup(force_positions=(("missing", "3"),)), "known"),
        (ExportSetup(force_compensators=(("3", "1"),)), "forward"),
        (ExportSetup(force_positions=(("1", "IMG"),)), "internal"),
        (ExportSetup(force_compensators=(("1", "3"), ("2", "3"))), "same dependent"),
        (
            ExportSetup(
                force_positions=(("1", "3"), ("2", "4")),
                position_direction="reversed",
                force_compensators=(("1", "2"),),
            ),
            "same dependent",
        ),
        (ExportSetup(ois=(("1", "4"), ("3", "6"))), "disjoint"),
        (ExportSetup(ois=(("4", "1"),)), "forward"),
        (ExportSetup(position_direction="bad"), "normal or reversed"),
    ],
)
def test_invalid_controls_rejected(setup, pattern):
    with pytest.raises(ValueError, match=pattern):
        render_zmx(study(), export_setup=setup)


def test_explicit_cycle_is_rejected():
    source = study(
        solves=(
            Solve("constant_span", "1", "4", "9"),
            Solve("complementary_gap", "3", "1", "6"),
        ),
        configurations=(),
    )
    with pytest.raises(ValueError, match="cycle"):
        render_zmx(source)


def test_explicit_reverse_derivation_uses_dependency_order():
    source = study(configurations=()).prescription
    surfaces = tuple(
        replace(s, thickness="unknown") if s.source_id == "1" else s
        for s in source.surfaces
    )
    source = replace(
        source,
        surfaces=surfaces,
        declared_symbols=("unknown",),
        solves=(Solve("constant_span", "1", "4", "9"),),
    )
    resolved = resolve_solves(source)
    assert Decimal(resolved.values[0]["1"]) == 2


def test_reversed_dependencies_derive_later_surface_before_earlier_surface():
    source = study(configurations=()).prescription
    source = replace(
        source,
        surfaces=tuple(
            replace(s, thickness={"1": "x", "3": "y"}[s.source_id])
            if s.source_id in {"1", "3"}
            else s
            for s in source.surfaces
        ),
        declared_symbols=("x", "y"),
        solves=(
            Solve("constant_span", "1", "4", "9"),
            Solve("constant_span", "3", "4", "4"),
        ),
    )
    resolved = resolve_solves(source)
    assert [item.surface_id for item in resolved.solves] == ["3", "1"]
    assert resolved.values[0]["1"] == "2"
    assert resolved.values[0]["3"] == "4"


def test_preference_is_noop_without_position_and_falls_back_on_conflict():
    source = study(configurations=())
    a = render_zmx(source)[0]
    b = render_zmx(source, export_setup=ExportSetup(position_direction="reversed"))[0]
    assert a == b
    solves = (
        ResolvedSolve("constant_span", "3", "1", "9"),
        ResolvedSolve("complementary_gap", "2", "1", "5", origin="explicit"),
    )
    oriented, diagnostics = orient_solves(
        solves, source.prescription.surfaces, "reversed"
    )
    assert oriented[0].surface_id == "3"
    assert diagnostics[0]["fallback_reason"]


@pytest.mark.parametrize("direction", ["normal", "reversed"])
def test_variable_rear_dummy_preserves_positions_and_totals(direction):
    source = study(powered=True)
    _, report = render_zmx(
        source,
        export_setup=ExportSetup(
            force_positions=(("1", "3"),), position_direction=direction
        ),
    )
    zmx = report["zmx"]
    dummy = zmx["rear_dummy"]
    assert dummy["status"] == "inserted"
    assert dummy["fixed_remainder"] == "3"
    assert [item["solved_gap"] for item in dummy["configurations"]] == ["1", "3"]
    solve = zmx["export_solves"][0]
    assert tuple(solve["totals"]) == ("6", "9")
    if direction == "reversed":
        assert solve["reference_surface_id"] == dummy["dummy_surface_id"]
    assert source.prescription.surfaces[3].thickness == "4"


def test_reverse_image_reference_and_signed_total():
    source = study(configurations=()).prescription
    surfaces = tuple(
        replace(s, thickness="-2") if s.source_id == "6" else s for s in source.surfaces
    )
    source = replace(source, surfaces=surfaces)
    resolved = prepare_solves(
        source,
        ExportSetup(force_positions=(("6", "7"),), position_direction="reversed"),
    )
    solve = resolved.solves[0]
    assert solve.reference_surface_id == "IMG"
    assert solve_terms(solve, surfaces) == ("6", "7")
    assert Decimal(_evaluated_solve_values(resolved, surfaces)[0]["6"]) == -2


def test_multiple_ois_pairs_have_actual_rows_and_same_config_pickups():
    content, report = render_zmx(
        study(),
        export_setup=ExportSetup(
            force_compensators=(("1", "3"),), ois=(("1", "4"), ("5", "7"))
        ),
    )
    text = content.decode("utf-16")
    records = [
        line.split()
        for line in text.splitlines()
        if line.startswith(("LTTL ", "MOFF ", "THIC ", "TSP2 ", "CADY ", "CBDY "))
    ]
    rows = [record for record in records if record[2] == "1"]
    for pair in report["zmx"]["ois"]:
        row = pair["cady_operand_row"]
        assert rows[row - 1][:2] == ["CADY", str(pair["after_export_surface"])]
        for config in (1, 2):
            assert (
                f'CBDY {pair["before_export_surface"]} {config} 0 {config + 1} 0 0 {config} {row} -1 0 0 "" 0'
                in text
            )
    assert text.index("TSP2 ") < text.index("CADY ") < text.index("FVCY ")


@pytest.mark.parametrize(
    "coefficients,expected",
    [
        ({1: "0.001", 8: "1e-8", 20: "0"}, "ODDASPHE"),
        ({1: "0.001", 9: "1e-9"}, "XOSPHERE"),
        ({3: "0", 4: "1e-5", 18: "0"}, "EVENASPH"),
        ({3: "0", 18: "1e-18"}, "XASPHERE"),
        ({1: "0", 99: "-0.000"}, "EVENASPH"),
    ],
)
def test_nonzero_asphere_classification(coefficients, expected):
    assert (
        _asphere_lines(Asphere("2", "odd", "0", coefficients))[0]
        == f"  TYPE {expected}"
    )


@pytest.mark.parametrize("odd", [False, True])
def test_normalized_ordinary_coefficients_preserve_sag(odd):
    coefficients = {3 if odd else 4: "0.032", 8: "0.000256", 22: "0"}
    lines = _asphere_lines(Asphere("2", "odd", "0", coefficients, "normalized", "2"))
    parms = {
        int(parts[1]): Decimal(parts[2])
        for line in lines
        if (parts := line.split())[0] == "PARM"
    }
    for radius in (Decimal("0.5"), Decimal("2"), Decimal("3")):
        actual = sum(
            value * radius ** (index if odd else index * 2)
            for index, value in parms.items()
        )
        expected = sum(
            Decimal(value) * (radius / 2) ** power
            for power, value in coefficients.items()
        )
        assert actual == expected


def test_even_input_allows_zero_odd_padding_but_not_nonzero():
    data = {
        "schema_version": 1,
        "title": "padding",
        "units": "mm",
        "surfaces": [{"id": "1", "radius": "0", "thickness": "1"}],
        "aspheres": [
            {
                "surface_id": "1",
                "family": "even",
                "conic": "0",
                "coefficients": {"3": "0", "4": "1E-5"},
            }
        ],
    }
    assert prescription_from_dict(data).aspheres[0].coefficients[3] == "0"
    data["aspheres"][0]["coefficients"]["3"] = "1"
    with pytest.raises(InputError, match="power is invalid"):
        prescription_from_dict(data)


def test_mixed_csv_table_classifies_per_row_and_preserves_zero_strings(tmp_path):
    path = tmp_path / "mixed.csv"
    path.write_text(
        "Lens Data\nSurface,Radius,Thickness,Material,nd,vd\n1,40,2,,,\n2,-40,10,,,\n\n"
        "Odd Aspheres\nSurface,k,A3,A4,A20\n1,0,0.000,1E-5,0\n2,0,1E-6,1E-5,0\n",
        encoding="utf-8",
    )
    source = load_sectioned_csv(path)
    assert [_asphere_lines(item)[0] for item in source.aspheres] == [
        "  TYPE EVENASPH",
        "  TYPE ODDASPHE",
    ]
    assert all(item.family == "odd" for item in source.aspheres)
    output = tmp_path / "roundtrip.csv"
    output.write_text(render_prescription_csv(source), encoding="utf-8")
    assert load_sectioned_csv(output).aspheres == source.aspheres


@pytest.mark.parametrize(
    "flag",
    [
        ["--position-direction", "normal"],
        ["--force-position", "1", "3"],
        ["--ois", "1", "3"],
    ],
)
def test_cli_requires_zmx_for_controls(tmp_path, capsys, flag):
    assert (
        main(
            [
                "missing.json",
                "--catalog",
                "missing.csv",
                "--output",
                str(tmp_path / "x"),
                "--format",
                "csv",
                *flag,
            ]
        )
        == 2
    )
    assert "require --format zmx or both" in capsys.readouterr().err
    assert not list(tmp_path.iterdir())
