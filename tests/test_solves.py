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
