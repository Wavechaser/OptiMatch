"""Deterministic, preference-aware catalogue glass matching."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from decimal import Decimal
from typing import Any, Iterable

from .models import CatalogGlass, Prescription, Surface


@dataclass(frozen=True)
class MatchProfile:
    name: str
    manufacturers: tuple[str, ...]
    excluded: frozenset[str] = frozenset()


PROFILES = {
    "default": MatchProfile("default", ("Ohara", "Hoya", "Hikari")),
    "canon": MatchProfile("canon", ("Ohara", "Hoya"), frozenset({"hikari"})),
    "nikon": MatchProfile("nikon", ("Hikari", "Ohara", "Hoya")),
}


@dataclass(frozen=True)
class Match:
    surface_id: str
    status: str
    profile: str
    original_material: str | None
    original_nd: str | None
    original_vd: str | None
    selected_manufacturer: str | None = None
    selected_typecode: str | None = None
    nd_delta: str | None = None
    vd_delta: str | None = None
    reason: str = ""
    ambiguity: bool = False
    selected: dict[str, Any] | None = None
    alternatives: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class MatchingResult:
    prescription: Prescription
    matches: tuple[Match, ...]
    profile: str = "default"

    def report(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "summary": {
                status: sum(match.status == status for match in self.matches)
                for status in ("air", "supplied", "close", "offset", "unmatched")
            },
            "surfaces": [asdict(match) for match in self.matches],
        }


def _manufacturer_rank(glass: CatalogGlass, profile: MatchProfile) -> int:
    names = [name.casefold() for name in profile.manufacturers]
    folded = glass.manufacturer.casefold()
    return names.index(folded) if folded in names else len(names)


def _identity(glass: CatalogGlass) -> tuple[str, str, str, str, str, str]:
    return (
        glass.manufacturer.casefold(),
        glass.typecode.casefold(),
        glass.nd,
        glass.vd,
        glass.pgf or "",
        glass.dpgf or "",
    )


def _dispersion(
    surface: Surface, glass: CatalogGlass
) -> tuple[int, Decimal, dict[str, Any]]:
    residuals: dict[str, Any] = {}
    missing = 0
    scaled: list[Decimal] = []
    for label, source, candidate in (
        ("pgf", surface.pgf, glass.pgf),
        ("dpgf", surface.dpgf, glass.dpgf),
    ):
        if source is None:
            continue
        if candidate is None:
            missing += 1
            residuals[label] = {"source": source, "catalogue": None, "residual": None}
            continue
        difference = Decimal(source) - Decimal(candidate)
        step = Decimal(1).scaleb(Decimal(source).as_tuple().exponent)
        scaled.append(abs(difference) / step)
        residuals[label] = {
            "source": source,
            "catalogue": candidate,
            "residual": str(difference),
            "normalized_residual": str(abs(difference) / step),
        }
    return missing, max(scaled, default=Decimal(0)), residuals


def _diagnostic(surface: Surface, glass: CatalogGlass) -> dict[str, Any]:
    nd_delta = Decimal(surface.nd) - glass.nd_value  # type: ignore[arg-type]
    vd_delta = Decimal(surface.vd) - glass.vd_value  # type: ignore[arg-type]
    missing, maximum, residuals = _dispersion(surface, glass)
    return {
        "manufacturer": glass.manufacturer,
        "typecode": glass.typecode,
        "source_nd": surface.nd,
        "source_vd": surface.vd,
        "source_nd_step": str(
            Decimal(1).scaleb(Decimal(surface.nd).as_tuple().exponent)
        ),
        "source_vd_step": str(
            Decimal(1).scaleb(Decimal(surface.vd).as_tuple().exponent)
        ),
        "source_nd_offset": surface.nd_offset,
        "source_vd_offset": surface.vd_offset,
        "catalogue_nd": glass.nd,
        "catalogue_vd": glass.vd,
        "catalogue_dpgf": glass.dpgf,
        "nd_delta": str(nd_delta),
        "vd_delta": str(vd_delta),
        "dispersion": {
            "missing_supplied_fields": missing,
            "maximum_normalized_residual": str(maximum),
            "residuals": residuals,
        },
    }


def _decision(
    selected: tuple[Any, ...],
    runner_up: tuple[Any, ...] | None,
    labels: tuple[str, ...],
) -> str:
    if runner_up is None:
        return "only eligible candidate"
    return next(
        (
            f"selected by {label}"
            for value, other, label in zip(selected, runner_up, labels, strict=True)
            if value != other
        ),
        "selected by deterministic identity",
    )


def _match_numeric(
    surface: Surface, catalogue: tuple[CatalogGlass, ...], profile: MatchProfile
) -> tuple[Surface, Match]:
    nd = Decimal(surface.nd)  # type: ignore[arg-type]
    vd = Decimal(surface.vd)  # type: ignore[arg-type]
    permitted = [
        glass
        for glass in catalogue
        if glass.manufacturer.casefold() not in profile.excluded
    ]
    close = [
        glass
        for glass in permitted
        if abs(nd - glass.nd_value) < Decimal("0.0002")
        and abs(vd - glass.vd_value) < Decimal("0.1")
    ]

    def close_key(glass: CatalogGlass) -> tuple[Any, ...]:
        dn, dv = abs(nd - glass.nd_value), abs(vd - glass.vd_value)
        dispersion = _dispersion(surface, glass)[:2]
        distance = (dn / Decimal("0.0002")) ** 2 + (dv / Decimal("0.1")) ** 2
        return (
            _manufacturer_rank(glass, profile),
            dispersion,
            distance,
            len(glass.typecode),
            _identity(glass),
        )

    def offset_key(glass: CatalogGlass) -> tuple[Any, ...]:
        return (
            _dispersion(surface, glass)[:2],
            abs(vd - glass.vd_value),
            abs(nd - glass.nd_value),
            _manufacturer_rank(glass, profile),
            len(glass.typecode),
            _identity(glass),
        )

    status = "close"
    eligible = close
    key = close_key
    if not eligible:
        status = "offset"
        eligible = [
            glass
            for glass in permitted
            if abs(nd - glass.nd_value) < Decimal("0.02")
            and abs(vd - glass.vd_value) < Decimal("2")
        ]
        key = offset_key
    if not eligible:
        return surface, Match(
            surface.source_id,
            "unmatched",
            profile.name,
            None,
            surface.nd,
            surface.vd,
            reason="no eligible catalogue glass after profile exclusions",
        )
    ranked = sorted(eligible, key=key)
    selected = ranked[0]
    dn, dv = nd - selected.nd_value, vd - selected.vd_value
    updated = replace(
        surface,
        material=selected.typecode,
        nd_offset=str(dn) if status == "offset" else None,
        vd_offset=str(dv) if status == "offset" else None,
    )
    return updated, Match(
        surface.source_id,
        status,
        profile.name,
        None,
        surface.nd,
        surface.vd,
        selected.manufacturer,
        selected.typecode,
        str(dn),
        str(dv),
        reason=_decision(
            key(selected),
            key(ranked[1]) if len(ranked) > 1 else None,
            (
                (
                    "manufacturer preference",
                    "partial dispersion",
                    "normalized nd/vd distance",
                    "typecode length",
                    "lexical identity",
                )
                if status == "close"
                else (
                    "partial dispersion",
                    "absolute vd delta",
                    "absolute nd delta",
                    "manufacturer preference",
                    "typecode length",
                    "lexical identity",
                )
            ),
        ),
        selected=_diagnostic(surface, selected),
        alternatives=tuple(_diagnostic(surface, item) for item in ranked[1:]),
    )


def match_prescription(
    prescription: Prescription,
    catalogue: Iterable[CatalogGlass],
    profile: str = "default",
) -> MatchingResult:
    """Return a matched immutable copy and deterministic per-surface diagnostics."""
    if profile not in PROFILES:
        raise ValueError(
            f"unknown profile {profile!r}; choose default, canon, or nikon"
        )
    policy = PROFILES[profile]
    glasses = tuple(catalogue)
    surfaces: list[Surface] = []
    matches: list[Match] = []
    for surface in prescription.surfaces:
        if surface.material is None and (
            surface.nd_offset is not None or surface.vd_offset is not None
        ):
            raise ValueError(
                f"surface {surface.source_id}: offsets require a supplied material typecode"
            )
        if surface.material is None and surface.nd is None and surface.vd is None:
            surfaces.append(surface)
            matches.append(
                Match(
                    surface.source_id,
                    "air",
                    profile,
                    None,
                    None,
                    None,
                    reason="confirmed blank material fields",
                )
            )
        elif surface.material is not None:
            named = [
                g
                for g in glasses
                if g.typecode.casefold() == surface.material.casefold()
            ]
            ranked = sorted(
                named, key=lambda g: (_manufacturer_rank(g, policy), _identity(g))
            )
            chosen = ranked[0] if ranked else None
            conflicting = len({(g.nd, g.vd, g.pgf, g.dpgf) for g in named}) > 1
            matches.append(
                Match(
                    surface.source_id,
                    "supplied",
                    profile,
                    surface.material,
                    surface.nd,
                    surface.vd,
                    chosen.manufacturer if chosen else None,
                    chosen.typecode if chosen else surface.material,
                    reason=(
                        "supplied typecode resolved by profile"
                        if chosen
                        else "supplied typecode preserved; host lookup unverified"
                    ),
                    ambiguity=conflicting,
                    selected=(
                        _diagnostic(surface, chosen)
                        if chosen is not None and surface.nd is not None
                        else (
                            {
                                "manufacturer": chosen.manufacturer,
                                "typecode": chosen.typecode,
                                "catalogue_nd": chosen.nd,
                                "catalogue_vd": chosen.vd,
                                "catalogue_dpgf": chosen.dpgf,
                                "source_nd_offset": surface.nd_offset,
                                "source_vd_offset": surface.vd_offset,
                            }
                            if chosen is not None
                            else None
                        )
                    ),
                    alternatives=tuple(
                        {
                            "manufacturer": g.manufacturer,
                            "typecode": g.typecode,
                            "catalogue_nd": g.nd,
                            "catalogue_vd": g.vd,
                        }
                        for g in ranked[1:]
                    ),
                )
            )
            surfaces.append(surface)
        else:
            updated, match = _match_numeric(surface, glasses, policy)
            surfaces.append(updated)
            matches.append(match)
    return MatchingResult(
        replace(prescription, surfaces=tuple(surfaces)), tuple(matches), profile
    )
