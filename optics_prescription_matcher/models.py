"""Validated records shared by prescription input, matching, and export."""

from dataclasses import dataclass, field
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class Surface:
    source_id: str
    radius: str
    thickness: str
    material: str | None = None
    nd: str | None = None
    vd: str | None = None
    pgf: str | None = None
    dpgf: str | None = None
    nd_offset: str | None = None
    vd_offset: str | None = None
    stop: bool = False


@dataclass(frozen=True)
class Asphere:
    surface_id: str
    family: str
    conic: str
    coefficients: Mapping[int, str]
    normalization: str = "sag"
    normalization_radius: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "coefficients", MappingProxyType(dict(self.coefficients))
        )


@dataclass(frozen=True)
class Configuration:
    name: str
    thicknesses: Mapping[str, str]
    aperture: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "thicknesses", MappingProxyType(dict(self.thicknesses))
        )


@dataclass(frozen=True)
class Wavelength:
    value: str
    weight: str = "1"
    primary: bool = False


@dataclass(frozen=True)
class Solve:
    kind: str
    surface_id: str
    reference_surface_id: str
    total: str


@dataclass(frozen=True)
class SystemSettings:
    stop_surface: str | None = None
    aperture_type: str | None = None
    aperture_value: str | None = None
    field_type: str | None = None
    fields: tuple[str, ...] = ()
    wavelengths: tuple[Wavelength, ...] = ()


@dataclass(frozen=True)
class Prescription:
    schema_version: int
    title: str
    units: str
    surfaces: tuple[Surface, ...]
    aspheres: tuple[Asphere, ...] = ()
    configurations: tuple[Configuration, ...] = ()
    solves: tuple[Solve, ...] = ()
    system: SystemSettings | None = None
    source_precision_trusted: bool = False
    rounding_steps: Mapping[str, str | None] = field(default_factory=dict)
    declared_symbols: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "rounding_steps", MappingProxyType(dict(self.rounding_steps))
        )


@dataclass(frozen=True)
class CatalogGlass:
    manufacturer: str
    typecode: str
    nd: str
    vd: str
    pgf: str | None = None
    dpgf: str | None = None

    @property
    def nd_value(self) -> Decimal:
        return Decimal(self.nd)

    @property
    def vd_value(self) -> Decimal:
        return Decimal(self.vd)
