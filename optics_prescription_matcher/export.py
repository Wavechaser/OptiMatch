"""CSV serialization for validated prescriptions."""

import csv
import io
from pathlib import Path
from typing import TextIO

from .models import Prescription


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
