"""Explicit export controls; source prescriptions remain unchanged."""

from dataclasses import dataclass, replace
from decimal import Decimal

from .models import Prescription, Surface
from .solves import ResolvedSolve, SolveResult, _terms, dependency_order, resolve_solves


@dataclass(frozen=True)
class ExportSetup:
    force_compensators: tuple[tuple[str, str], ...] = ()
    force_positions: tuple[tuple[str, str], ...] = ()
    position_direction: str = "normal"
    ois: tuple[tuple[str, str], ...] = ()


def solve_terms(solve: ResolvedSolve, surfaces: tuple[Surface, ...]) -> tuple[str, ...]:
    ids = [item.source_id for item in surfaces]
    return tuple(_terms(solve, {item: index for index, item in enumerate(ids)}, ids))


def prepare_solves(prescription: Prescription, setup: ExportSetup) -> SolveResult:
    if setup.position_direction not in {"normal", "reversed"}:
        raise ValueError("position_direction must be normal or reversed")
    ids = [item.source_id for item in prescription.surfaces]
    order = {item: index for index, item in enumerate(ids)}

    def pair(pair, context, *, single=False):
        if len(pair) != 2 or any(item not in order for item in pair):
            raise ValueError(f"{context}: supply two known source surface IDs")
        first, last = (order[item] for item in pair)
        if (
            first == 0
            or last == len(ids) - 1
            or first > last
            or (first == last and not single)
        ):
            raise ValueError(
                f"{context}: surfaces must be internal and in forward order"
            )
        return first, last

    intervals = [pair(item, "OIS") for item in setup.ois]
    for index, (start, end) in enumerate(intervals):
        if any(
            start <= other_end and other_start <= end
            for other_start, other_end in intervals[:index]
        ):
            raise ValueError(
                "OIS intervals must be disjoint (including their boundaries)"
            )
    forced = []
    for kind, pairs in (
        ("complementary_gap", setup.force_compensators),
        ("constant_span", setup.force_positions),
    ):
        for endpoints in pairs:
            first, last = pair(
                endpoints, f"forced {kind}", single=kind == "constant_span"
            )
            reverse = kind == "constant_span" and setup.position_direction == "reversed"
            forced.append(
                ResolvedSolve(
                    kind,
                    ids[first] if reverse else ids[last],
                    ids[last + 1] if reverse else ids[first],
                    "0",
                    origin="forced",
                    reverse=reverse,
                )
            )
    dependency_order(forced, ids)
    dependents = {item.surface_id for item in forced}
    footprints = {
        frozenset(solve_terms(item, prescription.surfaces)) for item in forced
    }
    overridden = [
        item
        for item in prescription.solves
        if (
            item.surface_id in dependents
            or frozenset(_terms(item, order, ids)) in footprints
        )
    ]
    source = replace(
        prescription,
        solves=tuple(item for item in prescription.solves if item not in overridden),
    )
    diagnostics = [
        dict(
            status="overridden",
            surface_id=item.surface_id,
            reference_surface_id=item.reference_surface_id,
            kind=item.kind,
            total=item.total,
            reason="CLI-forced solve replaces explicit input solve",
        )
        for item in overridden
    ]
    if forced:
        # Resolve remaining explicit equations first, including missing derived values.
        initial = resolve_solves(source, infer=False)
        calculated = []
        for item in forced:
            terms = solve_terms(item, source.surfaces)
            totals = tuple(
                str(sum((Decimal(config[term]) for term in terms), Decimal()))
                for config in initial.values
            )
            calculated.append(replace(item, total=totals[0], totals=totals))
        forced = calculated
    resolved = resolve_solves(source, forced=tuple(forced))
    return replace(resolved, diagnostics=tuple(diagnostics) + resolved.diagnostics)


def canonical_solves(
    solves: tuple[ResolvedSolve, ...], surfaces: tuple[Surface, ...]
) -> tuple[ResolvedSolve, ...]:
    """Forward inclusive spans for structural transformation, not a second search."""
    ids = [item.source_id for item in surfaces]
    result = []
    for item in solves:
        if item.kind == "constant_span" and ids.index(item.surface_id) < ids.index(
            item.reference_surface_id
        ):
            terms = solve_terms(item, surfaces)
            item = replace(
                item, surface_id=terms[-1], reference_surface_id=terms[0], reverse=True
            )
        result.append(item)
    return tuple(result)


def orient_solves(
    solves: tuple[ResolvedSolve, ...], surfaces: tuple[Surface, ...], direction: str
) -> tuple[tuple[ResolvedSolve, ...], list[dict[str, object]]]:
    ids = [item.source_id for item in surfaces]

    def reversed_solve(item):
        return replace(
            item,
            surface_id=item.reference_surface_id,
            reference_surface_id=ids[ids.index(item.surface_id) + 1],
            reverse=True,
        )

    # Mandatory explicit/forced placement is installed before inferred preferences.
    result = [reversed_solve(item) if item.reverse else item for item in solves]
    dependency_order(result, ids)
    diagnostics = []
    for index, item in enumerate(solves):
        if item.kind != "constant_span":
            continue
        reason = None
        if item.origin == "inferred" and direction == "reversed" and not item.reverse:
            proposed = result.copy()
            proposed[index] = reversed_solve(item)
            try:
                dependency_order(proposed, ids)
            except ValueError as exc:
                reason = str(exc)
            else:
                result = proposed
        diagnostics.append(
            dict(
                status="direction",
                origin=item.origin,
                covered_surface_ids=list(solve_terms(item, surfaces)),
                requested_direction=direction
                if item.origin != "explicit"
                else "preserve input",
                applied_direction="reversed" if result[index].reverse else "normal",
                surface_id=result[index].surface_id,
                reference_surface_id=result[index].reference_surface_id,
                totals=list(item.totals) or [item.total],
                fallback_reason=reason,
            )
        )
    dependency_order(result, ids)
    return tuple(result), diagnostics
