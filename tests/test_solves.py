import pytest

from optimatch.models import (
    Configuration,
    Prescription,
    Solve,
    Surface,
)
from optimatch.solves import resolve_solves


def prescription(configurations, **changes):
    base = Prescription(
        1,
        "solve",
        "mm",
        (
            Surface("OBJ", "0", "100"),
            Surface("1", "10", "a"),
            Surface("2", "10", "b"),
            Surface("IMG", "0", ""),
        ),
        configurations=configurations,
        declared_symbols=("a", "b"),
    )
    return Prescription(**(base.__dict__ | changes))


def test_exact_air_gap_pair_infers_tcom_and_preserves_source_values():
    configs = (
        Configuration("one", {"a": "2.00", "b": "8.00"}),
        Configuration("two", {"a": "3.00", "b": "7.00"}),
        Configuration("three", {"a": "4.00", "b": "6.00"}),
    )
    source = prescription(configs)
    result = resolve_solves(source)
    assert result.solves[0].kind == "complementary_gap"
    assert result.solves[0].total == "10.00"
    assert source.configurations == configs


def test_rounded_inference_requires_precision_metadata():
    configs = (
        Configuration("one", {"a": "2.00", "b": "8.58"}),
        Configuration("two", {"a": "3.00", "b": "7.58"}),
        Configuration("three", {"a": "4.00", "b": "6.57"}),
    )
    assert not resolve_solves(prescription(configs)).solves
    trusted = resolve_solves(prescription(configs, source_precision_trusted=True))
    assert trusted.solves[0].total == "10.58"
    assert [item["delta"] for item in trusted.diagnostics[0]["adjustments"]] == [
        "0.00",
        "0.00",
        "0.01",
    ]


def test_explicit_conflict_keeps_original_thicknesses():
    configs = (
        Configuration("one", {"a": "2", "b": "8"}),
        Configuration("two", {"a": "3", "b": "8"}),
    )
    source = prescription(
        configs,
        solves=(Solve("complementary_gap", "2", "1", "10"),),
    )
    result = resolve_solves(source)
    assert not result.solves
    assert result.diagnostics[0]["status"] == "conflict"


def test_explicit_rounded_span_is_accepted_with_adjustment():
    configs = (
        Configuration("one", {"a": "2.00", "b": "8.58"}),
        Configuration("two", {"a": "3.00", "b": "7.58"}),
        Configuration("three", {"a": "4.00", "b": "6.57"}),
    )
    source = prescription(
        configs,
        solves=(Solve("constant_span", "2", "1", "10.58"),),
        source_precision_trusted=True,
    )
    result = resolve_solves(source)
    assert result.solves[0].kind == "constant_span"
    assert [item["delta"] for item in result.diagnostics[0]["adjustments"]] == [
        "0.00",
        "0.00",
        "0.01",
    ]


def test_inferred_tole_may_include_glass_but_dependent_is_air():
    source = Prescription(
        1,
        "span",
        "mm",
        (
            Surface("OBJ", "0", "100"),
            Surface("gap", "0", "a"),
            Surface("glass", "10", "g", material="G"),
            Surface("dependent", "0", "b"),
            Surface("IMG", "0", ""),
        ),
        configurations=(
            Configuration("one", {"a": "2", "g": "3", "b": "5"}),
            Configuration("two", {"a": "3", "g": "4", "b": "3"}),
        ),
        declared_symbols=("a", "g", "b"),
    )
    result = resolve_solves(source)
    assert [(item.kind, item.surface_id, item.total) for item in result.solves] == [
        ("constant_span", "dependent", "10")
    ]


def test_overlapping_inferred_chain_is_suppressed():
    source = Prescription(
        1,
        "chain",
        "mm",
        (
            Surface("OBJ", "0", "100"),
            Surface("1", "0", "a"),
            Surface("2", "0", "b"),
            Surface("3", "0", "c"),
            Surface("IMG", "0", ""),
        ),
        configurations=(
            Configuration("one", {"a": "2", "b": "8", "c": "2"}),
            Configuration("two", {"a": "3", "b": "7", "c": "3"}),
            Configuration("three", {"a": "4", "b": "6", "c": "4"}),
        ),
        declared_symbols=("a", "b", "c"),
    )
    result = resolve_solves(source)
    assert not result.solves
    assert any(item["status"] == "ambiguous" for item in result.diagnostics)


def test_approximate_rejections_are_visible_and_bad_steps_fail():
    configs = (
        Configuration("one", {"a": "2.00", "b": "8.58"}),
        Configuration("two", {"a": "3.00", "b": "7.40"}),
    )
    unknown = resolve_solves(prescription(configs))
    assert any("unknown" in item["reason"] for item in unknown.diagnostics)
    disjoint = resolve_solves(prescription(configs, source_precision_trusted=True))
    assert any("disjoint" in item["reason"] for item in disjoint.diagnostics)
    bad = prescription(
        configs,
        rounding_steps={"/configurations/0/thicknesses/a": "0"},
    )
    with pytest.raises(ValueError, match="must be positive"):
        resolve_solves(bad)


def test_explicit_solve_derives_only_its_missing_dependent():
    source = prescription(
        (
            Configuration("one", {"a": "2"}),
            Configuration("two", {"a": "3"}),
        ),
        solves=(Solve("complementary_gap", "2", "1", "10"),),
    )
    result = resolve_solves(source)
    assert [item["2"] for item in result.values] == ["8", "7"]
    assert all(item["derived"] for item in result.diagnostics[0]["adjustments"])


def test_explicit_solve_does_not_hide_missing_independent_value():
    source = prescription(
        (Configuration("one", {"b": "8"}),),
        solves=(Solve("complementary_gap", "2", "1", "10"),),
    )
    with pytest.raises(ValueError, match="unresolved symbol 'a'"):
        resolve_solves(source)


@pytest.mark.parametrize("reverse", [False, True])
def test_explicit_chain_uses_forward_solved_values_independent_of_input_order(reverse):
    solves = [
        Solve("complementary_gap", "2", "1", "10.58"),
        Solve("complementary_gap", "3", "2", "10.00"),
    ]
    if reverse:
        solves.reverse()
    source = Prescription(
        1,
        "chain",
        "mm",
        (
            Surface("OBJ", "0", "100"),
            Surface("1", "0", "a"),
            Surface("2", "0", "b"),
            Surface("3", "0", "c"),
            Surface("IMG", "0", ""),
        ),
        configurations=(Configuration("one", {"a": "4.00", "b": "6.57", "c": "3.43"}),),
        solves=tuple(solves),
        source_precision_trusted=True,
        declared_symbols=("a", "b", "c"),
    )
    result = resolve_solves(source)
    assert [item.surface_id for item in result.solves] == ["2", "3"]
    by_surface = {item["surface_id"]: item for item in result.diagnostics}
    assert by_surface["2"]["adjustments"][0]["solved"] == "6.58"
    assert by_surface["2"]["adjustments"][0]["delta"] == "0.01"
    assert by_surface["3"]["adjustments"][0]["solved"] == "3.42"
    assert by_surface["3"]["adjustments"][0]["delta"] == "-0.01"


def independent_pair_prescription(configurations, **changes):
    base = Prescription(
        1,
        "independent pairs",
        "mm",
        (
            Surface("OBJ", "0", "100"),
            Surface("d6", "0", "a"),
            Surface("g7", "10", "1.5000", material="G"),
            Surface("d8", "0", "b"),
            Surface("g9", "10", "2.0000", material="G"),
            Surface("g20", "10", "3.0000", material="G"),
            Surface("d21", "0", "c"),
            Surface("g22", "10", "1.2500", material="G"),
            Surface("g24", "10", "0.7500", material="G"),
            Surface("d25", "0", "d"),
            Surface("IMG", "0", ""),
        ),
        configurations=configurations,
        declared_symbols=("a", "b", "c", "d"),
        source_precision_trusted=True,
    )
    return Prescription(**(base.__dict__ | changes))


@pytest.mark.parametrize("reverse", [False, True])
def test_independent_pairs_survive_redundant_constant_spans(reverse):
    configurations = [
        Configuration(
            "far", {"a": "13.9300", "b": "4.1900", "c": "8.6500", "d": "2.1500"}
        ),
        Configuration(
            "near", {"a": "7.7100", "b": "10.4100", "c": "2.2500", "d": "8.5500"}
        ),
    ]
    if reverse:
        configurations.reverse()
    result = resolve_solves(independent_pair_prescription(tuple(configurations)))
    assert [
        (solve.kind, solve.reference_surface_id, solve.surface_id, solve.total)
        for solve in result.solves
    ] == [
        ("complementary_gap", "d6", "d8", "18.1200"),
        ("complementary_gap", "d21", "d25", "10.8000"),
    ]
    redundant = [item for item in result.diagnostics if item["status"] == "redundant"]
    assert redundant
    assert all(
        {"kind", "reference_surface_id", "surface_id", "total"} <= item.keys()
        for item in redundant
    )


def test_explicit_constraint_takes_precedence_over_inferred_overlap():
    source = independent_pair_prescription(
        (
            Configuration(
                "far", {"a": "13.9300", "b": "4.1900", "c": "8.6500", "d": "2.1500"}
            ),
            Configuration(
                "near", {"a": "7.7100", "b": "10.4100", "c": "2.2500", "d": "8.5500"}
            ),
        ),
        solves=(Solve("complementary_gap", "d8", "d6", "18.1200"),),
    )
    result = resolve_solves(source)
    assert [(item.surface_id, item.kind) for item in result.solves] == [
        ("d8", "complementary_gap"),
        ("d25", "complementary_gap"),
    ]


def test_genuine_shared_dependency_remains_ambiguous_with_candidate_identity():
    source = Prescription(
        1,
        "shared",
        "mm",
        (
            Surface("OBJ", "0", "100"),
            Surface("a", "0", "a"),
            Surface("b", "0", "b"),
            Surface("c", "0", "c"),
            Surface("IMG", "0", ""),
        ),
        configurations=(
            Configuration("one", {"a": "2", "b": "8", "c": "2"}),
            Configuration("two", {"a": "3", "b": "7", "c": "3"}),
            Configuration("three", {"a": "4", "b": "6", "c": "4"}),
        ),
        declared_symbols=("a", "b", "c"),
    )
    result = resolve_solves(source)
    assert not result.solves
    ambiguous = [item for item in result.diagnostics if item["status"] == "ambiguous"]
    assert ambiguous
    assert all(
        {"kind", "reference_surface_id", "surface_id", "total"} <= item.keys()
        for item in ambiguous
    )


def test_removed_provisional_equation_does_not_simplify_downstream_candidates():
    source = Prescription(
        1,
        "provisional",
        "mm",
        (
            Surface("OBJ", "0", "100"),
            Surface("x", "10", "x", material="G"),
            Surface("y", "10", "y", material="G"),
            Surface("b", "0", "b"),
            Surface("c", "0", "c"),
            Surface("d", "0", "d"),
            Surface("e", "0", "e"),
            Surface("IMG", "0", ""),
        ),
        configurations=(
            Configuration(
                "one", {"x": "3", "y": "5", "b": "2", "c": "5", "d": "13", "e": "7"}
            ),
            Configuration(
                "two", {"x": "4", "y": "3", "b": "3", "c": "7", "d": "10", "e": "8"}
            ),
            Configuration(
                "three", {"x": "1", "y": "5", "b": "4", "c": "4", "d": "12", "e": "9"}
            ),
        ),
        declared_symbols=("x", "y", "b", "c", "d", "e"),
    )
    result = resolve_solves(source)
    assert not result.solves
    ambiguous_ids = {
        item["surface_id"]
        for item in result.diagnostics
        if item["status"] == "ambiguous"
    }
    assert {"b", "d", "e"} <= ambiguous_ids


def test_explicit_normalization_compares_numeric_values_not_spelling():
    source = independent_pair_prescription(
        (
            Configuration(
                "far",
                {
                    "a": "13.9300",
                    "g7": "1.5000",
                    "b": "4.1900",
                    "c": "8.6500",
                    "d": "2.1500",
                },
            ),
            Configuration(
                "near",
                {
                    "a": "7.7100",
                    "g7": "1.5",
                    "b": "10.4100",
                    "c": "2.2500",
                    "d": "8.5500",
                },
            ),
        ),
        solves=(Solve("constant_span", "d8", "d6", "19.6200"),),
    )
    result = resolve_solves(source)
    assert [(item.surface_id, item.kind) for item in result.solves] == [
        ("d8", "constant_span"),
        ("d25", "complementary_gap"),
    ]
