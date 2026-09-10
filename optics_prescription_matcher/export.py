"""CSV serialization for validated prescriptions."""

import csv
import io
import json
from dataclasses import asdict, replace
from decimal import Decimal, localcontext
from pathlib import Path
from typing import TextIO

from .inputs import decimal_value
from .matching import MatchingResult, pgf_to_dpgf
from .models import Asphere, Prescription, SystemSettings, Wavelength
from .solves import resolve_solves


def _write_csv(prescription: Prescription, stream: TextIO) -> None:
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["Lens Data"])
    have_offsets = any(
        surface.nd_offset is not None or surface.vd_offset is not None
        for surface in prescription.surfaces
    )
    have_dispersion = any(
        surface.pgf is not None or surface.dpgf is not None
        for surface in prescription.surfaces
    )
    have_stop = any(surface.stop for surface in prescription.surfaces)
    header = ["Surface", "Radius", "Thickness", "Material", "nd", "vd"]
    if have_dispersion:
        header.extend(["PgF", "dPgF"])
    if have_offsets:
        header.extend(["nd offset", "vd offset"])
    if have_stop:
        header.append("Stop")
    writer.writerow(header)
    for surface in prescription.surfaces:
        row = [
            surface.source_id,
            surface.radius,
            surface.thickness,
            surface.material or "",
            surface.nd or "",
            surface.vd or "",
        ]
        if have_dispersion:
            row.extend([surface.pgf or "", surface.dpgf or ""])
        if have_offsets:
            row.extend([surface.nd_offset or "", surface.vd_offset or ""])
        if have_stop:
            row.append("true" if surface.stop else "")
        writer.writerow(row)
    for family, heading in (("even", "Even Aspheres"), ("odd", "Odd Aspheres")):
        records = [item for item in prescription.aspheres if item.family == family]
        if not records:
            continue
        writer.writerow([])
        writer.writerow([heading])
        powers = sorted({power for item in records for power in item.coefficients})
        have_normalized = any(
            item.normalization != "sag" or item.normalization_radius is not None
            for item in records
        )
        header = ["Surface", "k", *(f"A{power}" for power in powers)]
        if have_normalized:
            header.extend(["Normalization", "Normalization Radius"])
        writer.writerow(header)
        for item in records:
            row = [
                item.surface_id,
                item.conic,
                *(item.coefficients.get(power, "") for power in powers),
            ]
            if have_normalized:
                row.extend([item.normalization, item.normalization_radius or ""])
            writer.writerow(row)
    if prescription.configurations:
        writer.writerow([])
        writer.writerow(["Multiconfiguration Data"])
        names = [item.name for item in prescription.configurations]
        writer.writerow(["", *names])
        if any(item.aperture is not None for item in prescription.configurations):
            writer.writerow(
                [
                    "aperture",
                    *(item.aperture or "" for item in prescription.configurations),
                ]
            )
        keys = list(
            dict.fromkeys(
                key for item in prescription.configurations for key in item.thicknesses
            )
        )
        for key in keys:
            writer.writerow(
                [
                    key,
                    *(
                        item.thicknesses.get(key, "")
                        for item in prescription.configurations
                    ),
                ]
            )


def write_prescription_csv(prescription: Prescription, path: str | Path) -> None:
    """Write the supported sectioned CSV without changing source numeric strings."""
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        _write_csv(prescription, stream)


def render_prescription_csv(prescription: Prescription) -> str:
    """Render CSV in memory so callers can validate all outputs before writing."""
    stream = io.StringIO(newline="")
    _write_csv(prescription, stream)
    return stream.getvalue()


_UNIT_TOKENS = {"mm": "MM", "cm": "CM", "in": "IN", "m": "METER"}
_FIELD_TYPES = {"angle": 0, "real_image_height": 3}
FIELD_PRESETS = {
    "1-type": ("0", "1.6", "3.2", "4.8", "6.4", "8"),
    "m43": ("0", "2", "4", "6", "8.5", "11"),
    "aps-c": ("0", "3", "6", "9", "12", "15"),
    "full-frame": ("0", "4", "8", "12", "17", "22"),
    "44x33": ("0", "5", "10", "15", "21", "27"),
}
_DEFAULT_WAVELENGTHS = tuple(
    Wavelength(value, weight, index == 2)
    for index, (value, weight) in enumerate(
        (
            ("0.486133", "0.9393"),
            ("0.546073", "1.000"),
            ("0.656273", "0.7349"),
            ("0.587562", "0.9507"),
            ("0.435833", "0.7868"),
        ),
        1,
    )
)


def _setup(prescription: Prescription, field_preset: str | None):
    """Resolve export settings without changing the source prescription."""
    source = prescription.system or SystemSettings()
    preset = field_preset or source.field_preset
    if preset is not None and preset not in FIELD_PRESETS:
        raise ValueError(
            f"unknown field_preset {preset!r}; choose {', '.join(FIELD_PRESETS)}"
        )
    field_type = source.field_type or "real_image_height"
    if preset and field_type != "real_image_height":
        raise ValueError("field_preset requires real_image_height fields")
    fields = source.fields
    if not fields and preset:
        millimetres_per_unit = {"mm": "1", "cm": "10", "m": "1000", "in": "25.4"}
        scale = Decimal(millimetres_per_unit[prescription.units])
        fields = tuple(str(Decimal(value) / scale) for value in FIELD_PRESETS[preset])
    if not fields:
        raise ValueError("ZMX requires system.fields or --field-preset (sensor format)")
    aperture = source.aperture_value
    aperture_source = "system"
    if aperture is None:
        aperture = (
            prescription.configurations[0].aperture
            if prescription.configurations
            else None
        )
        aperture_source = "first_configuration" if aperture is not None else "undefined"
    system = replace(
        source,
        aperture_type=source.aperture_type or "f_number",
        aperture_value=aperture if aperture is not None else "0",
        field_type=field_type,
        fields=fields,
        wavelengths=source.wavelengths or _DEFAULT_WAVELENGTHS,
    )
    details = {
        "field_preset": preset,
        "fields_source": "explicit" if source.fields else "preset",
        "field_type": field_type,
        "fields": list(fields),
        "wavelengths_source": "explicit" if source.wavelengths else "sample_default",
        "wavelengths": [asdict(item) for item in system.wavelengths],
        "aperture_source": aperture_source,
        "aperture_value": system.aperture_value,
        "warnings": [],
    }
    return system, details


def _curvature(radius: str) -> str:
    if Decimal(radius) == 0:
        return "0"
    with localcontext() as context:
        context.prec = 28
        exact = Decimal(1) / Decimal(radius)
        rendered = format(exact, ".17g")
        recovered = Decimal(1) / Decimal(rendered)
        tolerance = abs(Decimal(radius)) * Decimal("1e-16")
        if abs(recovered - Decimal(radius)) > tolerance:
            raise ValueError(f"radius {radius}: curvature reciprocal lost precision")
        return rendered


def _safe_token(text: str, context: str) -> str:
    if not text or any(
        char.isspace() or char in {'"', "'"} or ord(char) < 32 or ord(char) == 127
        for char in text
    ):
        raise ValueError(f"{context}: unsafe ZMX token {text!r}")
    return text


def _validate_zmx(result: MatchingResult) -> tuple[dict[str, int], str]:
    prescription = result.prescription
    if len(prescription.surfaces) < 2:
        raise ValueError("ZMX requires OBJ and IMG surfaces")
    if prescription.surfaces[0].source_id.casefold() != "obj":
        raise ValueError("ZMX first surface must be OBJ")
    if prescription.surfaces[-1].source_id.casefold() != "img":
        raise ValueError("ZMX last surface must be IMG")
    for surface in prescription.surfaces[1:-1]:
        if surface.source_id.casefold() in {"obj", "img"}:
            raise ValueError("ZMX OBJ and IMG identifiers are reserved for endpoints")
    system = prescription.system
    if system is None:
        raise ValueError("ZMX requires system settings")
    required = {
        "aperture_type": system.aperture_type,
        "aperture_value": system.aperture_value,
        "field_type": system.field_type,
        "fields": system.fields,
        "wavelengths": system.wavelengths,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise ValueError(f"ZMX system missing {', '.join(missing)}")
    if system.aperture_type != "f_number":
        raise ValueError("ZMX supports only f_number aperture")
    if Decimal(system.aperture_value) < 0:  # type: ignore[arg-type]
        raise ValueError("ZMX aperture_value must be nonnegative")
    if system.field_type not in _FIELD_TYPES:
        raise ValueError("ZMX unsupported field_type")
    for index, wavelength in enumerate(system.wavelengths):
        if Decimal(wavelength.value) <= 0 or Decimal(wavelength.weight) <= 0:
            raise ValueError(
                f"ZMX wavelength {index + 1} value/weight must be positive"
            )
    ids = {
        surface.source_id: index for index, surface in enumerate(prescription.surfaces)
    }
    flags = {surface.source_id for surface in prescription.surfaces if surface.stop}
    if system.stop_surface is not None:
        if system.stop_surface not in ids:
            raise ValueError("ZMX system stop_surface is unknown")
        if flags and flags != {system.stop_surface}:
            raise ValueError("ZMX stop declarations conflict")
        flags.add(system.stop_surface)
    if len(flags) != 1:
        raise ValueError("ZMX requires exactly one internal stop")
    stop = next(iter(flags))
    if ids[stop] in {0, len(ids) - 1}:
        raise ValueError("ZMX stop must be an internal surface")
    unmatched = [
        match.surface_id for match in result.matches if match.status == "unmatched"
    ]
    if unmatched:
        raise ValueError(f"ZMX blocked by unmatched material at surface {unmatched[0]}")
    surfaces = {surface.source_id: surface for surface in prescription.surfaces}
    for match in result.matches:
        if match.status != "model":
            continue
        surface = surfaces.get(match.surface_id)
        if surface is None:
            raise ValueError(
                f"model match references unknown surface {match.surface_id}"
            )
        if (
            surface.material is not None
            or surface.nd_offset is not None
            or surface.vd_offset is not None
            or match.original_material is not None
            or match.selected_manufacturer is not None
            or match.selected_typecode is not None
            or match.selected is not None
        ):
            raise ValueError(
                f"surface {surface.source_id}: model glass cannot have catalogue identity or offsets"
            )
        for label, value in (("nd", surface.nd), ("vd", surface.vd)):
            number = decimal_value(
                value, f"surface {surface.source_id} model glass {label}"
            )
            if number <= 0:
                raise ValueError(
                    f"surface {surface.source_id}: model glass requires finite positive {label}"
                )
        for label, value in (("PgF", surface.pgf), ("dPgF", surface.dpgf)):
            if value is None:
                continue
            decimal_value(value, f"surface {surface.source_id} model glass {label}")
    return ids, stop


def _asphere_lines(asphere: Asphere) -> list[str]:
    maximum = max(asphere.coefficients, default=0)
    if asphere.family == "even" and maximum <= 16 and asphere.normalization == "sag":
        lines = ["  TYPE EVENASPH", f"  CONI {asphere.conic}"]
        lines.extend(
            f"  PARM {index} {asphere.coefficients.get(index * 2, '0')}"
            for index in range(1, 9)
        )
        return lines
    odd = asphere.family == "odd"
    surface_type = "XOSPHERE" if odd else "XASPHERE"
    r0 = Decimal(asphere.normalization_radius or "1")
    count = maximum if odd else (maximum // 2)
    lines = [
        f"  TYPE {surface_type}",
        f"  CONI {asphere.conic}",
        f'  XDAT 1 {count} 0 0 1 0 0 ""',
        f'  XDAT 2 {r0} 0 0 1 0 0 ""',
    ]
    powers = range(1, maximum + 1) if odd else range(2, maximum + 1, 2)
    for power in powers:
        value = Decimal(asphere.coefficients.get(power, "0"))
        if asphere.normalization == "sag":
            value *= r0**power
        index = power + 2 if odd else power // 2 + 2
        lines.append(f'  XDAT {index} {value} 0 0 1 0 0 ""')
    return lines


def render_zmx(
    result: MatchingResult, *, field_preset: str | None = None
) -> tuple[bytes, dict[str, object]]:
    """Validate and render one narrowly supported sequential ZMX study model."""
    system, setup = _setup(result.prescription, field_preset)
    prescription = replace(result.prescription, system=system)
    ids, stop = _validate_zmx(replace(result, prescription=prescription))
    solves = resolve_solves(prescription)
    aspheres = {item.surface_id: item for item in prescription.aspheres}
    matches = {item.surface_id: item for item in result.matches}
    lines = [
        "VERS 221221 730 20120530 20120530",
        "MODE SEQ",
        f"NAME {prescription.title}",
        f"UNIT {_UNIT_TOKENS[prescription.units]} X W X CM MR CPMM",
        f"FNUM {system.aperture_value} 1",
        "RAIM 0 1 1 1 0 0 0 0 0 1",
        f"GLRS {ids[stop]} 0",
        f"FTYP {_FIELD_TYPES[system.field_type]} 0 {len(system.fields)} "
        f"{len(system.wavelengths)} 0 0 0 2",
        "XFLN " + " ".join("0" for _ in system.fields),
        "YFLN " + " ".join(system.fields),
        "FWGN " + " ".join("1" for _ in system.fields),
    ]
    for index, wavelength in enumerate(system.wavelengths, 1):
        lines.append(f"WAVM {index} {wavelength.value} {wavelength.weight}")
    primary = next(
        (index for index, item in enumerate(system.wavelengths, 1) if item.primary),
        2 if len(system.wavelengths) >= 2 else 1,
    )
    lines.append(f"PWAV {primary}")
    for key in ("VDXN", "VDYN", "VCXN", "VCYN"):
        lines.append(f"{key} " + " ".join("0" for _ in system.fields))
    dependent = {item.surface_id: item for item in solves.solves}
    for index, surface in enumerate(prescription.surfaces):
        lines.append(f"SURF {index}")
        lines.extend(
            _asphere_lines(aspheres[surface.source_id])
            if surface.source_id in aspheres
            else ["  TYPE STANDARD"]
        )
        lines.append(f"  CURV {_curvature(surface.radius)}")
        thickness = (
            "0" if index == len(prescription.surfaces) - 1 else surface.thickness
        )
        if solves.values and index < len(prescription.surfaces) - 1:
            thickness = solves.values[0][surface.source_id]
        if thickness.casefold() in {"infinity", "∞"}:
            thickness = "INFINITY"
        lines.append(f"  DISZ {thickness}")
        if surface.source_id in dependent:
            solve = dependent[surface.source_id]
            keyword = "TCOM" if solve.kind == "complementary_gap" else "TOLE"
            lines.append(f"  {keyword} {ids[solve.reference_surface_id]} {solve.total}")
        if surface.source_id == stop:
            lines.append("  STOP")
        match = matches.get(surface.source_id)
        if surface.material or (match is not None and match.status == "model"):
            detail = match.selected or {} if match is not None else {}
            model = match is not None and match.status == "model"
            token = (
                "___BLANK"
                if model
                else _safe_token(
                    surface.material, f"surface {surface.source_id} material"
                )
            )
            nd = detail.get("catalogue_nd") or surface.nd or "0"
            vd = detail.get("catalogue_vd") or surface.vd or "0"
            catalogue_effective = detail.get("catalogue_effective_dispersion", {})
            source_effective = (
                match.source_effective_dispersion or {} if match is not None else {}
            )
            if model:
                dpgf = (
                    surface.dpgf
                    or (
                        pgf_to_dpgf(surface.pgf, surface.vd)
                        if surface.pgf is not None
                        else None
                    )
                    or "0"
                )
            elif detail:
                dpgf = (
                    detail.get("catalogue_dpgf")
                    or catalogue_effective.get("dpgf", {}).get("value")
                    or "0"
                )
            else:
                dpgf = source_effective.get("dpgf", {}).get("value", "0")
            mode = "1" if model else "4" if surface.nd_offset is not None else "0"
            lines.append(
                f"  GLAS {token} {mode} 0 {nd} {vd} {dpgf} 0 0 0 "
                f"{surface.nd_offset or '0'} {surface.vd_offset or '0'}"
            )
    lines.append(f"MNUM {len(prescription.configurations) or 1} 1")
    if prescription.configurations:
        tail = '0 0 0 1 1 1 0 0 "" 0'
        for surface_id in solves.values[0]:
            if surface_id not in dependent:
                for config_index, values in enumerate(solves.values, 1):
                    value = values[surface_id]
                    lines.append(
                        f"THIC {ids[surface_id]} {config_index} {value} {tail}"
                    )
        if any(item.aperture is not None for item in prescription.configurations):
            for config_index, configuration in enumerate(
                prescription.configurations, 1
            ):
                aperture = configuration.aperture or system.aperture_value
                assert aperture is not None
                if Decimal(aperture) < 0:
                    raise ValueError(
                        f"configuration {configuration.name}: aperture must be nonnegative"
                    )
                lines.append(f"APER 0 {config_index} {aperture} {tail}")
        for field_index in range(1, len(system.fields) + 1):
            for config_index in range(1, len(prescription.configurations) + 1):
                lines.append(f"FVCY {field_index} {config_index} 0 {tail}")
        for field_index in range(1, len(system.fields) + 1):
            for config_index in range(1, len(prescription.configurations) + 1):
                lines.append(f"FVDY {field_index} {config_index} 0 {tail}")
    else:
        tail = '0 0 0 1 1 1 0 0 "" 0'
        for field_index in range(1, len(system.fields) + 1):
            lines.append(f"FVCY {field_index} 1 0 {tail}")
            lines.append(f"FVDY {field_index} 1 0 {tail}")
    if Decimal(system.aperture_value) == 0 or any(
        item.aperture is not None and Decimal(item.aperture) == 0
        for item in prescription.configurations
    ):
        setup["warnings"].append(
            "Zero f-number is an incomplete setup placeholder; set an aperture before optical analysis."
        )
    report = {
        "zmx": {
            "status": "rendered",
            "host_validation": "unverified for this output",
            "surface_map": ids,
            "setup": setup,
            "global_coordinate_reference": ids[stop],
            "ray_aiming_record": "0 1 1 1 0 0 0 0 0 1",
            "primary_wavelength": primary,
            "primary_wavelength_defaulted": not any(
                item.primary for item in system.wavelengths
            ),
            "configuration_infinity_representation": "1e10",
            "solves": [asdict(item) for item in solves.solves],
            "solve_diagnostics": list(solves.diagnostics),
        }
    }
    return ("\n".join(lines) + "\n").encode("utf-16"), report


def merge_export_report(
    result: MatchingResult, zmx_report: dict[str, object] | None
) -> str:
    report = result.report()
    if zmx_report:
        report.update(zmx_report)
    return json.dumps(report, indent=2, ensure_ascii=False) + "\n"
