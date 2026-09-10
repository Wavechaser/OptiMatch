"""Resolve configuration thicknesses and conservative explicit thickness solves."""

from dataclasses import dataclass
from decimal import Decimal

from .models import Configuration, Prescription, Solve


@dataclass(frozen=True)
class ResolvedSolve:
    kind: str
    surface_id: str
    reference_surface_id: str
    total: str


@dataclass(frozen=True)
class SolveResult:
    values: tuple[dict[str, str], ...]
    solves: tuple[ResolvedSolve, ...]
    diagnostics: tuple[dict[str, object], ...]


def _finite(text: str, context: str) -> Decimal:
    try:
        value = Decimal(text)
    except Exception as exc:
        raise ValueError(
            f"{context}: unresolved nonnumeric thickness {text!r}"
        ) from exc
    if not value.is_finite():
        raise ValueError(f"{context}: nonfinite thickness is unsupported")
    return value


def _configuration_values(
    prescription: Prescription, blocked_dependents: set[str]
) -> tuple[dict[str, str], ...]:
    result: list[dict[str, str]] = []
    configurations = prescription.configurations
    if not configurations:
        configurations = (Configuration("base", {}),)
    solve_counts: dict[str, int] = {}
    for solve in prescription.solves:
        solve_counts[solve.surface_id] = solve_counts.get(solve.surface_id, 0) + 1
    derivable = {
        surface_id
        for surface_id, count in solve_counts.items()
        if count == 1 and surface_id not in blocked_dependents
    }
    for config_index, configuration in enumerate(configurations):
        values: dict[str, str] = {}
        for surface in prescription.surfaces[:-1]:
            by_id = configuration.thicknesses.get(surface.source_id)
            by_symbol = (
                configuration.thicknesses.get(surface.thickness)
                if surface.thickness in prescription.declared_symbols
                else None
            )
            if (
                by_id is not None
                and by_symbol is not None
                and _comparable(by_id) != _comparable(by_symbol)
            ):
                raise ValueError(
                    f"configuration {configuration.name!r} surface {surface.source_id}: "
                    "conflicting source-id and symbol values"
                )
            value = by_id or by_symbol
            if value is None:
                if surface.thickness in prescription.declared_symbols:
                    if surface.source_id in derivable:
                        continue
                    raise ValueError(
                        f"configuration {configuration.name!r} surface "
                        f"{surface.source_id}: unresolved symbol {surface.thickness!r}"
                    )
                value = surface.thickness
            if value.casefold() in {"infinity", "∞"}:
                if surface.source_id.casefold() != "obj":
                    raise ValueError(
                        f"configuration {configuration.name!r} surface "
                        f"{surface.source_id}: infinity is only valid for OBJ"
                    )
                value = "1e10" if prescription.configurations else "infinity"
            else:
                _finite(
                    value,
                    f"configuration {config_index + 1} surface {surface.source_id}",
                )
            values[surface.source_id] = value
        result.append(values)
    return tuple(result)


def _comparable(value: str) -> Decimal | str:
    if value.casefold() in {"infinity", "∞"}:
        return "infinity"
    return Decimal(value)


def _terms(solve: Solve, order: dict[str, int], surface_ids: list[str]) -> list[str]:
    start = order[solve.reference_surface_id]
    end = order[solve.surface_id]
    if start >= end or end == len(surface_ids) - 1:
        raise ValueError(
            f"solve on surface {solve.surface_id}: reference must precede "
            "an internal dependent surface"
        )
    if solve.kind == "complementary_gap":
        return [solve.reference_surface_id, solve.surface_id]
    return surface_ids[start : end + 1]


def _step(
    prescription: Prescription, config_index: int, surface_index: int
) -> Decimal | None:
    surface = prescription.surfaces[surface_index]
    configuration = (
        prescription.configurations[config_index]
        if prescription.configurations
        else None
    )
    key = None
    if configuration is not None:
        if surface.source_id in configuration.thicknesses:
            key = surface.source_id
        elif (
            surface.thickness in prescription.declared_symbols
            and surface.thickness in configuration.thicknesses
        ):
            key = surface.thickness
    escaped = key.replace("~", "~0").replace("/", "~1") if key else None
    pointer = (
        f"/configurations/{config_index}/thicknesses/{escaped}"
        if escaped is not None
        else f"/surfaces/{surface_index}/thickness"
    )
    if pointer in prescription.rounding_steps:
        text = prescription.rounding_steps[pointer]
        if text is None:
            return None
        step = Decimal(text)
        if step <= 0:
            raise ValueError(f"rounding step {pointer}: must be positive")
        return step
    if not prescription.source_precision_trusted:
        return None
    value = (
        configuration.thicknesses.get(key, surface.thickness)
        if configuration is not None and key is not None
        else surface.thickness
    )
    return Decimal(1).scaleb(Decimal(value).as_tuple().exponent)


def _candidate(
    prescription: Prescription,
    values: tuple[dict[str, str], ...],
    indexes: list[int],
    kind: str,
) -> tuple[
    tuple[ResolvedSolve, list[str], tuple[tuple[str, ...], Decimal]] | None,
    str | None,
]:
    surfaces = prescription.surfaces
    columns = [
        [Decimal(configuration[surfaces[index].source_id]) for configuration in values]
        for index in indexes
    ]
    if (
        len(set(columns[-1])) < 2
        or len({sum(items) for items in zip(*columns[:-1], strict=True)}) < 2
    ):
        return None, None
    totals = [sum(items) for items in zip(*columns, strict=True)]
    target: Decimal | None = totals[0] if len(set(totals)) == 1 else None
    if target is None:
        bounds: list[Decimal] = []
        for config_index in range(len(values)):
            steps = [_step(prescription, config_index, index) for index in indexes]
            if any(step is None for step in steps):
                return None, "rounding precision is unknown"
            bounds.append(
                sum((step for step in steps if step is not None), Decimal()) / 2
            )
        lower = max(total - bound for total, bound in zip(totals, bounds, strict=True))
        upper = min(total + bound for total, bound in zip(totals, bounds, strict=True))
        if lower > upper:
            return None, "rounding intervals are disjoint"
        median = sorted(totals)[len(totals) // 2]
        target = min(max(median, lower), upper)
    invariant = [
        index
        for index, column in zip(indexes[:-1], columns[:-1], strict=True)
        if len(set(column)) == 1
    ]
    normalized_total = target - sum(
        (columns[indexes.index(item)][0] for item in invariant), Decimal()
    )
    varying = tuple(
        surfaces[index].source_id for index in indexes[:-1] if index not in invariant
    )
    solve = ResolvedSolve(
        kind,
        surfaces[indexes[-1]].source_id,
        surfaces[indexes[0]].source_id,
        str(target),
    )
    return (
        solve,
        [str(target - total) for total in totals],
        (varying, normalized_total),
    ), None


def _infer_solves(
    prescription: Prescription,
    values: tuple[dict[str, str], ...],
    excluded: set[str],
) -> tuple[list[ResolvedSolve], list[dict[str, object]]]:
    if len(values) < 2:
        return [], []
    candidates: dict[
        str, list[tuple[ResolvedSolve, list[str], tuple[tuple[str, ...], Decimal]]]
    ] = {}
    diagnostics: list[dict[str, object]] = []
    surfaces = prescription.surfaces
    for left in range(1, len(surfaces) - 2):
        for right in range(left + 1, len(surfaces) - 1):
            first, second = surfaces[left], surfaces[right]
            if first.material is not None or second.material is not None:
                continue
            candidate, reason = _candidate(
                prescription, values, [left, right], "complementary_gap"
            )
            if candidate:
                candidates.setdefault(second.source_id, []).append(candidate)
            elif reason:
                diagnostics.append(
                    {
                        "surface_id": second.source_id,
                        "status": "rejected",
                        "kind": "complementary_gap",
                        "reason": reason,
                    }
                )
    for left in range(1, len(surfaces) - 3):
        for right in range(left + 2, len(surfaces) - 1):
            if surfaces[right].material is not None:
                continue
            candidate, reason = _candidate(
                prescription, values, list(range(left, right + 1)), "constant_span"
            )
            if candidate:
                candidates.setdefault(surfaces[right].source_id, []).append(candidate)
            elif reason:
                diagnostics.append(
                    {
                        "surface_id": surfaces[right].source_id,
                        "status": "rejected",
                        "kind": "constant_span",
                        "reason": reason,
                    }
                )
    accepted: list[ResolvedSolve] = []
    config_names = [item.name for item in prescription.configurations]
    for dependent, choices in candidates.items():
        if dependent in excluded:
            continue
        unique: dict[
            tuple[tuple[str, ...], Decimal], tuple[ResolvedSolve, list[str]]
        ] = {}
        for solve, adjustments, equation in choices:
            previous = unique.get(equation)
            if previous is None or solve.kind == "complementary_gap":
                unique[equation] = (solve, adjustments)
        if len(unique) != 1:
            diagnostics.append(
                {
                    "surface_id": dependent,
                    "status": "ambiguous",
                    "reason": "multiple inferred relationships",
                }
            )
            continue
        solve, adjustments = next(iter(unique.values()))
        accepted.append(solve)
        diagnostics.append(
            {
                "surface_id": dependent,
                "status": "inferred",
                "adjustments": [
                    {
                        "configuration": config_names[index],
                        "original": values[index][dependent],
                        "solved": str(
                            Decimal(values[index][dependent]) + Decimal(delta)
                        ),
                        "delta": delta,
                    }
                    for index, delta in enumerate(adjustments)
                ],
            }
        )
    order = {surface.source_id: index for index, surface in enumerate(surfaces)}
    terms_by_dependent: dict[str, set[str]] = {}
    for solve in accepted:
        if solve.kind == "complementary_gap":
            terms_by_dependent[solve.surface_id] = {
                solve.reference_surface_id,
                solve.surface_id,
            }
        else:
            terms_by_dependent[solve.surface_id] = {
                item.source_id
                for item in surfaces[
                    order[solve.reference_surface_id] : order[solve.surface_id] + 1
                ]
            }
    overlapping = {
        dependent
        for dependent, terms in terms_by_dependent.items()
        if any(
            other != dependent and terms & other_terms
            for other, other_terms in terms_by_dependent.items()
        )
    }
    if overlapping:
        accepted = [item for item in accepted if item.surface_id not in overlapping]
        diagnostics = [
            item
            for item in diagnostics
            if not (
                item.get("surface_id") in overlapping
                and item.get("status") == "inferred"
            )
        ]
        diagnostics.extend(
            {
                "surface_id": dependent,
                "status": "ambiguous",
                "reason": "inferred relationship overlaps another dependency",
            }
            for dependent in sorted(overlapping)
        )
    return accepted, diagnostics


def resolve_solves(prescription: Prescription) -> SolveResult:
    """Resolve configuration values and validate explicit TCOM/TOLE relationships."""
    ids = [surface.source_id for surface in prescription.surfaces]
    order = {surface_id: index for index, surface_id in enumerate(ids)}
    values = _configuration_values(prescription, set())
    source_values = tuple(dict(item) for item in values)
    accepted: list[ResolvedSolve] = []
    diagnostics: list[dict[str, object]] = []
    counts: dict[str, int] = {}
    for solve in prescription.solves:
        counts[solve.surface_id] = counts.get(solve.surface_id, 0) + 1
    derived: set[tuple[int, str]] = set()
    ordered_solves = sorted(
        prescription.solves, key=lambda item: order[item.surface_id]
    )
    for solve in ordered_solves:
        if counts[solve.surface_id] > 1:
            diagnostics.append(
                {
                    "surface_id": solve.surface_id,
                    "status": "ambiguous",
                    "reason": "multiple explicit solves",
                }
            )
            continue
        terms = _terms(solve, order, ids)
        expected = Decimal(solve.total)
        for config_index, config in enumerate(values):
            if solve.surface_id in config:
                continue
            independent = [item for item in terms if item != solve.surface_id]
            missing = [item for item in independent if item not in config]
            if missing:
                raise ValueError(
                    f"solve on surface {solve.surface_id}: unresolved independent "
                    f"thickness {missing[0]!r}"
                )
            config[solve.surface_id] = str(
                expected
                - sum((Decimal(config[item]) for item in independent), Decimal())
            )
            derived.add((config_index, solve.surface_id))
        totals = [
            sum(
                (_finite(config[item], f"solve {solve.surface_id}") for item in terms),
                Decimal(),
            )
            for config in values
        ]
        adjustments = [expected - total for total in totals]
        consistent = True
        for config_index, adjustment in enumerate(adjustments):
            if adjustment == 0:
                continue
            bounds = [_step(prescription, config_index, order[item]) for item in terms]
            if (
                any(bound is None for bound in bounds)
                or abs(adjustment)
                > sum((bound for bound in bounds if bound is not None), Decimal()) / 2
            ):
                consistent = False
                break
        if not consistent:
            diagnostics.append(
                {
                    "surface_id": solve.surface_id,
                    "status": "conflict",
                    "reason": "explicit total conflicts with configuration values",
                }
            )
            continue
        accepted.append(
            ResolvedSolve(
                solve.kind,
                solve.surface_id,
                solve.reference_surface_id,
                solve.total,
            )
        )
        solved_values = [
            Decimal(config[solve.surface_id]) + adjustment
            for config, adjustment in zip(values, adjustments, strict=True)
        ]
        diagnostics.append(
            {
                "surface_id": solve.surface_id,
                "status": "explicit",
                "adjustments": [
                    {
                        "configuration": (
                            prescription.configurations[index].name
                            if prescription.configurations
                            else "base"
                        ),
                        "original": (
                            None
                            if (index, solve.surface_id) in derived
                            else source_values[index][solve.surface_id]
                        ),
                        "solved": str(solved_values[index]),
                        "delta": (
                            None
                            if (index, solve.surface_id) in derived
                            else str(
                                solved_values[index]
                                - Decimal(source_values[index][solve.surface_id])
                            )
                        ),
                        "derived": (index, solve.surface_id) in derived,
                    }
                    for index, adjustment in enumerate(adjustments)
                ],
            }
        )
        for config, solved in zip(values, solved_values, strict=True):
            config[solve.surface_id] = str(solved)
    inferred, inferred_diagnostics = _infer_solves(
        prescription, values, {item.surface_id for item in prescription.solves}
    )
    explicit_terms = {
        item
        for solve in accepted
        for item in _terms(
            Solve(
                solve.kind, solve.surface_id, solve.reference_surface_id, solve.total
            ),
            order,
            ids,
        )
    }
    safe_inferred: list[ResolvedSolve] = []
    for solve in inferred:
        terms = set(
            _terms(
                Solve(
                    solve.kind,
                    solve.surface_id,
                    solve.reference_surface_id,
                    solve.total,
                ),
                order,
                ids,
            )
        )
        if terms & explicit_terms:
            inferred_diagnostics = [
                item
                for item in inferred_diagnostics
                if not (
                    item.get("surface_id") == solve.surface_id
                    and item.get("status") == "inferred"
                )
            ]
            inferred_diagnostics.append(
                {
                    "surface_id": solve.surface_id,
                    "status": "ambiguous",
                    "reason": "inferred relationship overlaps an explicit constraint",
                }
            )
        else:
            safe_inferred.append(solve)
    accepted.extend(safe_inferred)
    diagnostics.extend(inferred_diagnostics)
    return SolveResult(values, tuple(accepted), tuple(diagnostics))
