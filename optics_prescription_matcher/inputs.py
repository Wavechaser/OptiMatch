"""Strict loaders for canonical JSON and the supported CSV inputs."""

import csv
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .models import (
    Asphere,
    CatalogGlass,
    Configuration,
    Prescription,
    Solve,
    Surface,
    SystemSettings,
    Wavelength,
)

_DECIMAL = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?$")
_SYMBOL = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_UNITS = {"mm", "cm", "m", "in"}
_PLANE = {"flat", "infinity", "∞"}


class InputError(ValueError):
    """An input diagnostic with a precise logical location."""


def _error(context: str, message: str) -> InputError:
    return InputError(f"{context}: {message}")


def _identifier(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(context, "must be a nonempty string")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise _error(context, "must not contain control characters")
    return value.strip()


def decimal_value(text: str, context: str) -> Decimal:
    if not isinstance(text, str) or not _DECIMAL.fullmatch(text):
        raise _error(context, "expected a finite decimal string")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:  # defensive: the grammar is deliberately narrow
        raise _error(context, "expected a finite decimal string") from exc
    if not value.is_finite():
        raise _error(context, "expected a finite decimal string")
    return value


def _quantity(value: Any, context: str, *, plane: bool = False) -> str:
    if not isinstance(value, str):
        raise _error(context, "must be a string so source precision is preserved")
    text = value.strip()
    if plane and text.lower() in _PLANE:
        return "0"
    decimal_value(text, context)
    return text


def _thickness(
    value: Any,
    context: str,
    symbols: set[str],
    *,
    object_distance: bool,
    image_surface: bool,
) -> str:
    if not isinstance(value, str):
        raise _error(context, "must be a decimal or declared symbol string")
    text = value.strip()
    if image_surface and not text:
        return text
    if object_distance and text.lower() in {"infinity", "∞"}:
        return text
    if _DECIMAL.fullmatch(text):
        decimal_value(text, context)
        return text
    if _SYMBOL.fullmatch(text) and text in symbols:
        return text
    raise _error(context, "must be a finite decimal or declared symbol")


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"JSON field {key!r}: duplicate key")
        result[key] = value
    return result


def _keys(data: dict[str, Any], allowed: set[str], context: str) -> None:
    unknown = set(data) - allowed
    if unknown:
        raise _error(context, f"unknown field {sorted(unknown)[0]!r}")


def _optional_quantity(data: dict[str, Any], key: str, context: str) -> str | None:
    value = data.get(key)
    return None if value is None else _quantity(value, f"{context}.{key}")


def _surface(data: Any, index: int, symbols: set[str]) -> Surface:
    context = f"surfaces[{index}]"
    if not isinstance(data, dict):
        raise _error(context, "must be an object")
    allowed = {
        "id",
        "radius",
        "thickness",
        "material",
        "nd",
        "vd",
        "pgf",
        "dpgf",
        "nd_offset",
        "vd_offset",
        "stop",
    }
    _keys(data, allowed, context)
    for key in ("id", "radius", "thickness"):
        if key not in data:
            raise _error(context, f"missing field {key!r}")
    source_id = _identifier(data["id"], f"{context}.id")
    material = data.get("material")
    if material is not None and (not isinstance(material, str) or not material.strip()):
        raise _error(f"{context}.material", "must be a nonempty string or null")
    nd = _optional_quantity(data, "nd", context)
    vd = _optional_quantity(data, "vd", context)
    pgf = _optional_quantity(data, "pgf", context)
    dpgf = _optional_quantity(data, "dpgf", context)
    nd_offset = _optional_quantity(data, "nd_offset", context)
    vd_offset = _optional_quantity(data, "vd_offset", context)
    if (nd is None) != (vd is None):
        raise _error(context, "nd and vd must be supplied together")
    if (nd_offset is None) != (vd_offset is None):
        raise _error(context, "nd_offset and vd_offset must be supplied together")
    if material is None and nd is None and (pgf is not None or dpgf is not None):
        raise _error(context, "partial dispersion requires nd and vd")
    if nd is not None:
        if (
            decimal_value(nd, f"{context}.nd") <= 0
            or decimal_value(vd, f"{context}.vd") <= 0
        ):
            raise _error(context, "nd and vd must be positive")
    stop = data.get("stop", False)
    if not isinstance(stop, bool):
        raise _error(f"{context}.stop", "must be a boolean")
    return Surface(
        source_id,
        _quantity(data["radius"], f"{context}.radius", plane=True),
        _thickness(
            data["thickness"],
            f"{context}.thickness",
            symbols,
            object_distance=source_id.casefold() == "obj",
            image_surface=source_id.casefold() == "img",
        ),
        material.strip() if material else None,
        nd,
        vd,
        pgf,
        dpgf,
        nd_offset,
        vd_offset,
        stop,
    )


def _asphere(data: Any, index: int) -> Asphere:
    context = f"aspheres[{index}]"
    if not isinstance(data, dict):
        raise _error(context, "must be an object")
    _keys(
        data,
        {
            "surface_id",
            "family",
            "conic",
            "coefficients",
            "normalization",
            "normalization_radius",
        },
        context,
    )
    for key in ("surface_id", "family", "conic", "coefficients"):
        if key not in data:
            raise _error(context, f"missing field {key!r}")
    family = data["family"]
    if not isinstance(family, str) or family not in {"even", "odd"}:
        raise _error(f"{context}.family", "must be 'even' or 'odd'")
    coefficients = data["coefficients"]
    if not isinstance(coefficients, dict):
        raise _error(f"{context}.coefficients", "must be an object keyed by power")
    parsed: dict[int, str] = {}
    for power_text, value in coefficients.items():
        if not isinstance(power_text, str) or not power_text.isdigit():
            raise _error(f"{context}.coefficients", f"invalid power {power_text!r}")
        power = int(power_text)
        if power < 1 or (family == "even" and power % 2):
            raise _error(
                f"{context}.coefficients.{power_text}", "power is invalid for family"
            )
        if power in parsed:
            raise _error(
                f"{context}.coefficients.{power_text}", "duplicate numeric power"
            )
        parsed[power] = _quantity(value, f"{context}.coefficients.{power_text}")
    normalization = data.get("normalization", "sag")
    if not isinstance(normalization, str) or normalization not in {
        "sag",
        "normalized",
    }:
        raise _error(f"{context}.normalization", "unsupported normalization")
    radius = _optional_quantity(data, "normalization_radius", context)
    if normalization == "normalized" and radius is None:
        raise _error(context, "normalized coefficients require normalization_radius")
    if radius is not None and Decimal(radius) <= 0:
        raise _error(f"{context}.normalization_radius", "must be positive")
    return Asphere(
        _identifier(data["surface_id"], f"{context}.surface_id"),
        family,
        _quantity(data["conic"], f"{context}.conic"),
        parsed,
        normalization,
        radius,
    )


def _configuration(
    data: Any, index: int, symbols: set[str], object_distance_keys: set[str]
) -> Configuration:
    context = f"configurations[{index}]"
    if not isinstance(data, dict):
        raise _error(context, "must be an object")
    _keys(data, {"name", "thicknesses", "aperture"}, context)
    if not isinstance(data.get("name"), str) or not data["name"]:
        raise _error(f"{context}.name", "must be a nonempty string")
    values = data.get("thicknesses")
    if not isinstance(values, dict):
        raise _error(f"{context}.thicknesses", "must be an object")
    thicknesses = {
        str(key): (
            str(value).strip()
            if str(key) in object_distance_keys
            and isinstance(value, str)
            and value.strip().lower() in {"infinity", "∞"}
            else _quantity(value, f"{context}.thicknesses.{key}")
        )
        for key, value in values.items()
    }
    aperture = _optional_quantity(data, "aperture", context)
    return Configuration(data["name"], thicknesses, aperture)


def _system(data: Any) -> SystemSettings:
    context = "system"
    if not isinstance(data, dict):
        raise _error(context, "must be an object")
    allowed = {
        "stop_surface",
        "aperture_type",
        "aperture_value",
        "field_type",
        "fields",
        "wavelengths",
    }
    _keys(data, allowed, context)

    def strings(key: str) -> tuple[str, ...]:
        values = data.get(key, [])
        if not isinstance(values, list):
            raise _error(f"{context}.{key}", "must be an array")
        return tuple(
            _quantity(value, f"{context}.{key}[{i}]") for i, value in enumerate(values)
        )

    aperture_value = _optional_quantity(data, "aperture_value", context)
    raw_wavelengths = data.get("wavelengths", [])
    if not isinstance(raw_wavelengths, list):
        raise _error("system.wavelengths", "must be an array")
    wavelengths: list[Wavelength] = []
    primary_count = 0
    for index, item in enumerate(raw_wavelengths):
        item_context = f"system.wavelengths[{index}]"
        if not isinstance(item, dict):
            raise _error(item_context, "must be an object")
        _keys(item, {"value", "weight", "primary"}, item_context)
        value = _quantity(item.get("value"), f"{item_context}.value")
        weight = _quantity(item.get("weight", "1"), f"{item_context}.weight")
        primary = item.get("primary", False)
        if not isinstance(primary, bool):
            raise _error(f"{item_context}.primary", "must be a boolean")
        primary_count += primary
        wavelengths.append(Wavelength(value, weight, primary))
    if primary_count > 1:
        raise _error("system.wavelengths", "at most one wavelength may be primary")
    for key in ("stop_surface", "aperture_type", "field_type"):
        if key in data and data[key] is not None and not isinstance(data[key], str):
            raise _error(f"{context}.{key}", "must be a string or null")
    if data.get("aperture_type") not in {None, "f_number"}:
        raise _error("system.aperture_type", "unsupported aperture type")
    if data.get("field_type") not in {None, "angle", "real_image_height"}:
        raise _error("system.field_type", "unsupported field type")
    return SystemSettings(
        data.get("stop_surface"),
        data.get("aperture_type"),
        aperture_value,
        data.get("field_type"),
        strings("fields"),
        tuple(wavelengths),
    )


def _solve(data: Any, index: int, surface_ids: set[str]) -> Solve:
    context = f"solves[{index}]"
    if not isinstance(data, dict):
        raise _error(context, "must be an object")
    _keys(data, {"kind", "surface_id", "reference_surface_id", "total"}, context)
    kind = data.get("kind")
    if not isinstance(kind, str) or kind not in {
        "complementary_gap",
        "constant_span",
    }:
        raise _error(f"{context}.kind", "unsupported solve kind")
    surface_id = _identifier(data.get("surface_id"), f"{context}.surface_id")
    reference = _identifier(
        data.get("reference_surface_id"), f"{context}.reference_surface_id"
    )
    if surface_id not in surface_ids or reference not in surface_ids:
        raise _error(context, "solve references an unknown surface")
    return Solve(
        kind, surface_id, reference, _quantity(data.get("total"), f"{context}.total")
    )


def prescription_from_dict(data: Any) -> Prescription:
    if not isinstance(data, dict):
        raise InputError("prescription: must be an object")
    allowed = {
        "schema_version",
        "title",
        "units",
        "surfaces",
        "aspheres",
        "configurations",
        "solves",
        "system",
        "source_precision_trusted",
        "rounding_steps",
        "declared_symbols",
    }
    _keys(data, allowed, "prescription")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise InputError("schema_version: only integer version 1 is supported")
    title = _identifier(data.get("title"), "title")
    units = data.get("units")
    if not isinstance(units, str) or units not in _UNITS:
        raise InputError(f"units: must be one of {sorted(_UNITS)}")
    declared = data.get("declared_symbols", [])
    if not isinstance(declared, list) or any(
        not isinstance(item, str) or not _SYMBOL.fullmatch(item) for item in declared
    ):
        raise InputError("declared_symbols: must be an array of symbol strings")
    if len(declared) != len(set(declared)):
        raise InputError("declared_symbols: duplicate symbol")
    raw_surfaces = data.get("surfaces")
    if not isinstance(raw_surfaces, list) or not raw_surfaces:
        raise InputError("surfaces: must be a nonempty array")
    symbols = set(declared)
    surfaces = tuple(_surface(item, i, symbols) for i, item in enumerate(raw_surfaces))
    ids = [item.source_id for item in surfaces]
    if len(ids) != len(set(ids)):
        raise InputError("surfaces: duplicate surface id")
    raw_aspheres = data.get("aspheres", [])
    if not isinstance(raw_aspheres, list):
        raise InputError("aspheres: must be an array")
    aspheres = tuple(_asphere(item, i) for i, item in enumerate(raw_aspheres))
    if len({item.surface_id for item in aspheres}) != len(aspheres):
        raise InputError("aspheres: duplicate surface id")
    if any(item.surface_id not in set(ids) for item in aspheres):
        raise InputError("aspheres: unknown surface id")
    object_surface_ids = {
        surface.source_id
        for surface in surfaces
        if surface.source_id.casefold() == "obj"
    }
    object_symbols = {
        surface.thickness
        for surface in surfaces
        if surface.source_id in object_surface_ids and surface.thickness in symbols
    }
    finite_symbols = {
        surface.thickness
        for surface in surfaces
        if surface.source_id not in object_surface_ids and surface.thickness in symbols
    }
    object_distance_keys = object_surface_ids | (object_symbols - finite_symbols)
    raw_configurations = data.get("configurations", [])
    if not isinstance(raw_configurations, list):
        raise InputError("configurations: must be an array")
    configurations = tuple(
        _configuration(item, i, symbols, object_distance_keys)
        for i, item in enumerate(raw_configurations)
    )
    names = [item.name for item in configurations]
    if len(names) != len(set(names)):
        raise InputError("configurations: duplicate name")
    allowed_thickness_keys = set(ids) | symbols
    for index, configuration in enumerate(configurations):
        unknown_keys = set(configuration.thicknesses) - allowed_thickness_keys
        if unknown_keys:
            raise _error(
                f"configurations[{index}].thicknesses",
                f"unknown surface or symbol {sorted(unknown_keys)[0]!r}",
            )
    raw_solves = data.get("solves", [])
    if not isinstance(raw_solves, list):
        raise InputError("solves: must be an array")
    solves = tuple(_solve(item, i, set(ids)) for i, item in enumerate(raw_solves))
    trusted = data.get("source_precision_trusted", False)
    if not isinstance(trusted, bool):
        raise InputError("source_precision_trusted: must be a boolean")
    raw_steps = data.get("rounding_steps", {})
    if not isinstance(raw_steps, dict):
        raise InputError("rounding_steps: must be an object")
    steps = {
        key: None if value is None else _quantity(value, f"rounding_steps.{key}")
        for key, value in raw_steps.items()
    }
    if any(not isinstance(key, str) or not key.startswith("/") for key in steps):
        raise InputError("rounding_steps: keys must be JSON pointer strings")
    return Prescription(
        1,
        title,
        data["units"],
        surfaces,
        aspheres,
        configurations,
        solves,
        _system(data["system"]) if data.get("system") is not None else None,
        trusted,
        steps,
        tuple(declared),
    )


def load_prescription_json(path: str | Path) -> Prescription:
    try:
        with Path(path).open(encoding="utf-8-sig") as stream:
            data = json.load(stream, object_pairs_hook=_object_pairs)
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"JSON: {exc}") from exc
    return prescription_from_dict(data)


_CATALOG_HEADERS = {"Manufacturer", "Typecode", "nd", "vd", "P_g,F", "d_Pg,F"}


def load_catalog_csv(path: str | Path) -> tuple[CatalogGlass, ...]:
    try:
        stream = Path(path).open(encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise InputError(f"catalogue: {exc}") from exc
    with stream:
        reader = csv.DictReader(stream)
        if (
            reader.fieldnames is None
            or len(reader.fieldnames) != len(set(reader.fieldnames))
            or set(reader.fieldnames) != _CATALOG_HEADERS
        ):
            raise InputError(f"catalogue header: expected {sorted(_CATALOG_HEADERS)}")
        records: list[CatalogGlass] = []
        identities: set[tuple[str, str]] = set()
        for row_number, row in enumerate(reader, 2):
            context = f"catalogue row {row_number}"
            if None in row or any(row.get(name) is None for name in _CATALOG_HEADERS):
                raise _error(context, "row has the wrong number of columns")
            manufacturer = _identifier(
                row["Manufacturer"], f"{context} field Manufacturer"
            )
            typecode = _identifier(row["Typecode"], f"{context} field Typecode")
            if any(char.isspace() for char in typecode):
                raise _error(f"{context} field Typecode", "must be a single token")
            if not manufacturer or not typecode:
                raise _error(context, "Manufacturer and Typecode are required")
            identity = (manufacturer.casefold(), typecode.casefold())
            if identity in identities:
                raise _error(context, "duplicate catalogue identity")
            identities.add(identity)
            nd = _quantity(row["nd"], f"{context} field nd")
            vd = _quantity(row["vd"], f"{context} field vd")
            if Decimal(nd) <= 0 or Decimal(vd) <= 0:
                raise _error(context, "nd and vd must be positive")
            pgf = row["P_g,F"].strip() or None
            dpgf = row["d_Pg,F"].strip() or None
            if pgf is not None:
                pgf = _quantity(pgf, f"{context} field P_g,F")
            if dpgf is not None:
                dpgf = _quantity(dpgf, f"{context} field d_Pg,F")
            records.append(CatalogGlass(manufacturer, typecode, nd, vd, pgf, dpgf))
    return tuple(records)


def load_sectioned_csv(
    path: str | Path, metadata_path: str | Path | None = None
) -> Prescription:
    try:
        with Path(path).open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.reader(stream))
    except OSError as exc:
        raise InputError(f"CSV: {exc}") from exc
    sections: dict[str, list[tuple[int, list[str]]]] = {}
    current: str | None = None
    titles = {
        "lens data": "lens",
        "asphere data": "even",
        "even aspheres": "even",
        "odd aspheres": "odd",
        "multiconfiguration data": "config",
    }
    title = Path(path).stem
    for number, row in enumerate(rows, 1):
        cells = [cell.strip() for cell in row]
        if not any(cells):
            continue
        heading = cells[0].casefold()
        if heading in titles and not any(cells[1:]):
            current = titles[heading]
            sections.setdefault(current, [])
            if heading == "lens data":
                title = cells[0]
            continue
        if current is None:
            raise _error(f"CSV row {number}", f"unknown section {cells[0]!r}")
        sections[current].append((number, cells))
    if "lens" not in sections or not sections["lens"]:
        raise InputError("CSV lens section: missing")
    header_number, header = sections["lens"][0]
    aliases = {
        "surface": "id",
        "#": "id",
        "radius": "radius",
        "thickness": "thickness",
        "material": "material",
        "nd": "nd",
        "vd": "vd",
        "?nd": "nd_offset",
        "δnd": "nd_offset",
        "Δnd": "nd_offset",
        "nd offset": "nd_offset",
        "?vd": "vd_offset",
        "δvd": "vd_offset",
        "Δvd": "vd_offset",
        "vd offset": "vd_offset",
        "pgf": "pgf",
        "p_g,f": "pgf",
        "dpgf": "dpgf",
        "d_pg,f": "dpgf",
        "stop": "stop",
    }
    while header and not header[-1]:
        header.pop()
    if any(not cell for cell in header):
        raise _error(
            f"CSV lens header row {header_number}",
            "blank columns are only allowed at the end",
        )
    mapped = [aliases.get(cell.casefold(), aliases.get(cell)) for cell in header]
    if (
        None in mapped
        or len(mapped) != len(set(mapped))
        or not {"id", "radius", "thickness", "material", "nd", "vd"}.issubset(mapped)
    ):
        raise _error(
            f"CSV lens header row {header_number}",
            "unknown, duplicate, or missing column",
        )
    columns = {name: i for i, name in enumerate(mapped)}
    symbols: set[str] = set()
    for row_number, row in sections["lens"][1:]:
        if any(row[len(header) :]):
            raise _error(f"CSV lens row {row_number}", "unexpected extra value")
        value = row[columns["thickness"]] if columns["thickness"] < len(row) else ""
        if _SYMBOL.fullmatch(value) and not _DECIMAL.fullmatch(value):
            symbols.add(value)
    surface_dicts = []
    for number, row in sections["lens"][1:]:

        def cell(name: str) -> str:
            index = columns[name]
            return row[index] if index < len(row) else ""

        item: dict[str, Any] = {
            "id": cell("id"),
            "radius": cell("radius"),
            "thickness": cell("thickness"),
        }
        for name in ("material", "nd", "vd", "pgf", "dpgf", "nd_offset", "vd_offset"):
            if name in columns and cell(name) != "":
                item[name] = cell(name)
        if "stop" in columns and cell("stop") != "":
            stop_text = cell("stop").casefold()
            if stop_text not in {"true", "false"}:
                raise _error(
                    f"CSV lens row {number} field stop",
                    "must be true, false, or empty",
                )
            item["stop"] = stop_text == "true"
        try:
            surface_dicts.append(_surface(item, number, symbols))
        except InputError as exc:
            raise _error(f"CSV lens row {number}", str(exc)) from exc
    aspheres: list[Asphere] = []
    for family in ("even", "odd"):
        section = sections.get(family)
        if not section:
            continue
        number, header = section[0]
        coefficient_columns: list[tuple[int, int]] = []
        if len(header) < 2 or header[0].casefold() not in {"surface", "#"}:
            raise _error(
                f"CSV {family} header row {number}",
                "expected Surface and coefficient columns",
            )
        conic_index = None
        normalization_index = None
        normalization_radius_index = None
        for index, name in enumerate(header[1:], 1):
            if not name:
                continue
            if name.casefold() in {"k", "conic"}:
                if conic_index is not None:
                    raise _error(
                        f"CSV {family} header row {number}",
                        "duplicate conic column",
                    )
                conic_index = index
            elif name.casefold() == "normalization":
                if normalization_index is not None:
                    raise _error(
                        f"CSV {family} header row {number}",
                        "duplicate normalization column",
                    )
                normalization_index = index
            elif name.casefold() == "normalization radius":
                if normalization_radius_index is not None:
                    raise _error(
                        f"CSV {family} header row {number}",
                        "duplicate normalization radius column",
                    )
                normalization_radius_index = index
            elif re.fullmatch(r"A\d+", name, re.IGNORECASE):
                power = int(name[1:])
                if any(existing == power for _, existing in coefficient_columns):
                    raise _error(
                        f"CSV {family} header row {number}",
                        f"duplicate coefficient power A{power}",
                    )
                coefficient_columns.append((index, power))
            else:
                raise _error(
                    f"CSV {family} header row {number}", f"unknown field {name!r}"
                )
        for row_number, row in section[1:]:
            if any(row[len(header) :]):
                raise _error(f"CSV {family} row {row_number}", "unexpected extra value")
            coefficients = {
                power: row[index]
                for index, power in coefficient_columns
                if index < len(row) and row[index] != ""
            }
            conic = (
                row[conic_index]
                if conic_index is not None
                and conic_index < len(row)
                and row[conic_index]
                else "0"
            )
            try:
                normalization = (
                    row[normalization_index]
                    if normalization_index is not None
                    and normalization_index < len(row)
                    and row[normalization_index]
                    else "sag"
                )
                normalization_radius = (
                    row[normalization_radius_index]
                    if normalization_radius_index is not None
                    and normalization_radius_index < len(row)
                    and row[normalization_radius_index]
                    else None
                )
                aspheres.append(
                    Asphere(
                        row[0],
                        family,
                        _quantity(conic, f"CSV {family} row {row_number} field conic"),
                        {
                            power: _quantity(
                                value, f"CSV {family} row {row_number} field A{power}"
                            )
                            for power, value in coefficients.items()
                        },
                        normalization,
                        normalization_radius,
                    )
                )
            except (IndexError, InputError) as exc:
                raise _error(f"CSV {family} row {row_number}", str(exc)) from exc
    configurations: list[Configuration] = []
    if sections.get("config"):
        number, header = sections["config"][0]
        while header and not header[-1]:
            header.pop()
        if len(header) < 2 or any(not name for name in header[1:]):
            raise _error(
                f"CSV configuration header row {number}",
                "blank configuration names are only allowed at the end",
            )
        names = header[1:]
        if not names or len(names) != len(set(names)):
            raise _error(
                f"CSV configuration header row {number}",
                "configuration names must be unique",
            )
        values = {name: {} for name in names}
        apertures: dict[str, str] = {}
        for row_number, row in sections["config"][1:]:
            if any(row[len(header) :]):
                raise _error(
                    f"CSV configuration row {row_number}", "unexpected extra value"
                )
            key = row[0]
            if not key:
                raise _error(
                    f"CSV configuration row {row_number}", "missing quantity name"
                )
            for index, name in enumerate(names, 1):
                if index >= len(row) or row[index] == "":
                    raise _error(
                        f"CSV configuration row {row_number} field {name}",
                        "missing value",
                    )
                if row[index].strip().lower() in {"infinity", "∞"}:
                    object_keys = {
                        surface.thickness
                        for surface in surface_dicts
                        if surface.source_id.casefold() == "obj"
                    }
                    object_keys.update(
                        surface.source_id
                        for surface in surface_dicts
                        if surface.source_id.casefold() == "obj"
                    )
                    if key not in object_keys:
                        raise _error(
                            f"CSV configuration row {row_number} field {name}",
                            "infinity is only valid for the object distance",
                        )
                    value = row[index].strip()
                else:
                    value = _quantity(
                        row[index],
                        f"CSV configuration row {row_number} field {name}",
                    )
                if key.casefold() == "aperture":
                    apertures[name] = value
                else:
                    values[name][key] = value
        configurations = [
            Configuration(name, values[name], apertures.get(name)) for name in names
        ]
    data: dict[str, Any] = {
        "schema_version": 1,
        "title": title,
        "units": "mm",
        "declared_symbols": sorted(symbols),
        "surfaces": [
            surface.__dict__ | {"id": surface.source_id} for surface in surface_dicts
        ],
        "aspheres": [
            {
                "surface_id": item.surface_id,
                "family": item.family,
                "conic": item.conic,
                "coefficients": {
                    str(power): value for power, value in item.coefficients.items()
                },
                "normalization": item.normalization,
                **(
                    {"normalization_radius": item.normalization_radius}
                    if item.normalization_radius is not None
                    else {}
                ),
            }
            for item in aspheres
        ],
        "configurations": [
            {
                "name": item.name,
                "thicknesses": dict(item.thicknesses),
                **({"aperture": item.aperture} if item.aperture is not None else {}),
            }
            for item in configurations
        ],
    }
    for item in data["surfaces"]:
        item.pop("source_id", None)
        for key in list(item):
            if item[key] is None:
                item.pop(key)
    if metadata_path is not None:
        try:
            with Path(metadata_path).open(encoding="utf-8-sig") as stream:
                overlay = json.load(stream, object_pairs_hook=_object_pairs)
        except (OSError, json.JSONDecodeError) as exc:
            raise InputError(f"metadata JSON: {exc}") from exc
        if not isinstance(overlay, dict):
            raise InputError("metadata JSON: must be an object")
        forbidden = set(overlay) & {"surfaces", "aspheres", "configurations"}
        if forbidden:
            raise InputError(
                f"metadata JSON: cannot replace CSV field {sorted(forbidden)[0]!r}"
            )
        data.update(overlay)
    return prescription_from_dict(data)
