"""Command-line entry point for matching and C2 CSV/report output."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from .export import (
    FIELD_PRESETS,
    merge_export_report,
    render_prescription_csv,
    render_zmx,
)
from .inputs import (
    InputError,
    load_catalog_csv,
    load_prescription_json,
    load_sectioned_csv,
)
from .matching import match_prescription


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Match an optical prescription to a glass catalogue."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument(
        "--profile", choices=("default", "canon", "nikon"), default="default"
    )
    parser.add_argument("--output", required=True, type=Path, help="output prefix")
    parser.add_argument(
        "--metadata", type=Path, help="JSON metadata overlay for CSV input"
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--format", choices=("csv", "zmx", "both"), default="both")
    parser.add_argument(
        "--field-preset",
        choices=tuple(FIELD_PRESETS),
        help="sensor-format y fields for ZMX (explicit fields take precedence)",
    )
    return parser


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve(strict=False))) == os.path.normcase(
        str(right.resolve(strict=False))
    )


def _write_outputs(outputs: dict[Path, str | bytes], overwrite: bool) -> None:
    for path in outputs:
        if path.exists() and not overwrite:
            raise ValueError(f"output exists: {path}; pass --overwrite to replace it")
    created: list[Path] = []
    temporary: list[Path] = []
    try:
        for path, content in outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            binary = isinstance(content, bytes)
            handle, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
            temp = Path(name)
            temporary.append(temp)
            if binary:
                with os.fdopen(handle, "wb") as stream:
                    stream.write(content)
            else:
                with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
                    stream.write(content)
        for temp, path in zip(temporary, outputs, strict=True):
            existed = path.exists()
            if overwrite:
                os.replace(temp, path)
            else:
                os.link(temp, path)
                temp.unlink()
            if not existed:
                created.append(path)
        temporary.clear()
    except OSError:
        for path in created:
            try:
                path.unlink()
            except OSError:
                pass
        raise
    finally:
        for path in temporary:
            try:
                path.unlink()
            except OSError:
                pass


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    csv_path = Path(f"{args.output}.csv")
    zmx_path = Path(f"{args.output}.zmx")
    report_path = Path(f"{args.output}.report.json")
    sources = [args.input, args.catalog, *([args.metadata] if args.metadata else [])]
    if any(
        _same_path(target, source)
        for target in (csv_path, zmx_path, report_path)
        for source in sources
    ):
        print(
            "error: an output path collides with an input, catalogue, or metadata path",
            file=sys.stderr,
        )
        return 2
    if args.metadata and args.input.suffix.casefold() != ".csv":
        print("error: --metadata is only valid with a CSV input", file=sys.stderr)
        return 2
    try:
        prescription = (
            load_sectioned_csv(args.input, args.metadata)
            if args.input.suffix.casefold() == ".csv"
            else load_prescription_json(args.input)
        )
        result = match_prescription(
            prescription, load_catalog_csv(args.catalog), args.profile
        )
        outputs: dict[Path, str | bytes] = {}
        if args.format in {"csv", "both"}:
            outputs[csv_path] = render_prescription_csv(result.prescription)
        zmx_report = None
        if args.format in {"zmx", "both"}:
            zmx_bytes, zmx_report = render_zmx(result, field_preset=args.field_preset)
            outputs[zmx_path] = zmx_bytes
        outputs[report_path] = merge_export_report(result, zmx_report)
        _write_outputs(outputs, args.overwrite)
    except (InputError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if zmx_report:
        for warning in zmx_report["zmx"]["setup"]["warnings"]:
            print(f"warning: {warning}", file=sys.stderr)
    summary = result.report()["summary"]
    written = ", ".join(str(path) for path in outputs)
    print(
        f"wrote {written}; matched="
        f"{summary['close'] + summary['offset'] + summary['supplied']}, "
        f"unmatched={summary['unmatched']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
