# OpticsPrescriptionMatcher

Python tools for producing credible optical study prescriptions from patent
data, using best-effort manufacturer preferences for glass selection. Results
are study substitutes, not representations of production samples.

The repository contains validated JSON/CSV input records, deterministic glass
matching, a machine-readable decision report, and sectioned CSV/ZMX output. OCR
is not implemented. Catalogue input is CSV exported from the
user's maintained Excel workbook. XLSX parsing, AGF parsing, and SQLite/database
storage are out of scope. OCR can be added independently later.

## Match a prescription

Run the study-model workflow with a canonical JSON or sectioned CSV input:

```powershell
.\.venv\Scripts\python.exe -m optics_prescription_matcher prescription.json `
  --catalog samples/combined_glass_catalog.csv --profile default `
  --output output/study --format both
```

Profiles are `default` (Ohara, Hoya, Hikari), `canon` (Ohara, Hoya; Hikari
excluded for inferred matches), and `nikon` (Hikari, Ohara, Hoya). The
`--format` option defaults to `both`; use `csv` for an incomplete transcription that
lacks the system metadata required by ZMX, or `zmx` for model-only output. A JSON
report is always written on success. Existing outputs require
`--overwrite`; outputs can never overwrite the input, catalogue, or CSV metadata
overlay. Pass `--metadata PATH` only with a sectioned CSV input. Requested outputs
are validated before writing; replacing several files is not a single transaction.

ZMX output requires explicit OBJ and IMG endpoints, one internal stop, a positive
f-number, angle or real-image-height fields, and positive wavelengths/weights.
It writes UTF-16 LE with a BOM and preserves source coefficients. Source distances
remain in CSV/report; ZMX applies disclosed solve adjustments and derivations.
It supports ordinary/extended even and extended odd aspheres, omits fixed aperture
records and GCAT, and emits neutral vignetting configuration operands. Configured
infinite object distance uses the tested numeric `1e10` representation and is
disclosed in the report. Unknown supplied typecodes remain visibly
host-lookup-unverified; the report does not claim that a particular output was
loaded by OpticStudio.

The JSON report distinguishes air, supplied typecodes, close matches, offset
matches, and unmatched properties. It includes signed prescription-minus-
catalogue differences, source precision steps, partial-dispersion residuals,
alternatives, ambiguities, and the ranking criterion that selected a candidate.
An unknown supplied typecode is preserved and marked host-lookup-unverified.
Reported decimal steps describe source formatting, not independently established
measurement accuracy; Excel padding can make them misleading. Supplied offsets
require a named base glass and are preserved, never reinterpreted as air.

## Prescription inputs

Load canonical JSON or adapt the historical sectioned CSV:

```python
from optics_prescription_matcher.inputs import (
    load_catalog_csv,
    load_prescription_json,
    load_sectioned_csv,
)

prescription = load_prescription_json("prescription.json")
catalogue = load_catalog_csv("samples/combined_glass_catalog.csv")
legacy = load_sectioned_csv("samples/sample_lens_data.csv")
```

The minimal transcription schema is explicit. Optical quantities are JSON strings
so their source decimals survive; JSON numbers are rejected. This example is for
CSV output; ZMX also needs the system metadata described below.

```json
{
  "schema_version": 1,
  "title": "Example study lens",
  "units": "mm",
  "declared_symbols": ["d0"],
  "surfaces": [
    {"id": "OBJ", "radius": "infinity", "thickness": "d0"},
    {"id": "1", "radius": "38.185", "thickness": "3.07",
     "nd": "1.834807", "vd": "42.7253", "stop": true},
    {"id": "IMG", "radius": "0", "thickness": ""}
  ],
  "aspheres": [
    {"surface_id": "1", "family": "even", "conic": "0",
     "coefficients": {"4": "-3.4255E-05"}, "normalization": "sag"}
  ],
  "configurations": [
    {"name": "infinity", "aperture": "2.8",
     "thicknesses": {"d0": "infinity"}}
  ]
}
```

Optional top-level fields are `system`, `solves`, `rounding_steps`, and
`source_precision_trusted`. A system may state its stop, aperture and field
types, decimal-string fields, and wavelength objects (`value`, `weight`, and
`primary`). Explicit solves use kind `complementary_gap` or `constant_span`, two
surface IDs, and a decimal-string `total`; this layer preserves but does not
infer solves. ZMX export resolves explicit constraints and conservatively infers
eligible constant-distance relationships across configurations. Original distances
remain in CSV; the report records derived values and rounding adjustments.

For example, a `system` object can supply the remaining ZMX essentials:

```json
{
  "aperture_type": "f_number",
  "aperture_value": "2.8",
  "field_type": "angle",
  "fields": ["0", "5"],
  "wavelengths": [{"value": "0.5875618", "weight": "1", "primary": true}]
}
```

The CSV adapter recognizes Lens Data, Even/Odd Aspheres (legacy Asphere Data is
even), and Multiconfiguration Data sections. Lens headers may use `Surface` or
`#`, and `nd offset`/`vd offset`, `Δnd`/`Δvd`, or legacy `?nd`/`?vd`. Optional
metadata JSON may overlay fields absent from CSV but cannot replace CSV tables.
Unknown fields, sections, duplicate identifiers, incomplete nd/vd pairs,
undeclared symbols, and misplaced nonfinite values are rejected with location.

## Development (Windows / PowerShell)

Python 3.13 or newer is required. From the repository root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Activation is optional; invoking the environment's interpreter directly avoids
PowerShell activation-policy changes. Do not recreate an existing environment
unless you intend to replace it.

Run checks:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest
```

Format Python code with `.\.venv\Scripts\python.exe -m ruff format .`.
There are no runtime dependencies; development tools are declared in
`pyproject.toml`. Dependencies are not locked at this stage.

## Layout and reference data

- `optics_prescription_matcher/`: Python package (flat layout).
- `optics_prescription_matcher.egg-info/`: ignored installation metadata.
- `tests/`: input, CSV, matching, ZMX, solve, CLI, and installation tests.
- `samples/combined_glass_catalog.csv`: supplied catalogue snapshot.
- `samples/sample_lens_data.csv`: worked, multi-section prescription CSV.
- `samples/EF-M 22mm F2 STM.ZMX` and `samples/14-24mm F2.8 DG DN Art.ZMX`: original
  UTF-16 reference designs.
- `samples/SAMPLE_INSTRUCTIONS.md`: historical agent instructions, qualified by the
  current scope and data rules in `AGENTS.md`.
- `output/`: ignored generated files, created only when needed.

## Documentation

- [Features](docs/FEATURES.md): desired capabilities, independent of implementation.
- [Implementation proposal](docs/IMPLEMENTATION_PLAN.md): data contracts, matching
  policy, exporter design, and completed implementation checkpoints.
- [ZMX syntax](docs/ZMX_SYNTAX.md): observed records, sources, and unresolved details.

See `AGENTS.md` for development and optical-data conventions. Git attributes
normalize code to LF while preserving CSV and ZMX reference bytes. GitHub
Actions runs the same checks on Windows with Python 3.13.

This checkout also uses repository-local `core.autocrlf=false`,
`core.safecrlf=warn`, and `fetch.prune=true`. These local Git settings are not
transferred by cloning; the committed attributes still apply in other checkouts.

## Conventions borrowed from NamiSync

Reuse its central Python configuration, local venv, pytest workflow, and explicit
agent rules and commit titles (`category(scope): imperative summary`, with scope
optional). This smaller project uses a flat package layout and adds Ruff. It does not
need NamiSync's layered architecture, departmental testing, checkpoint ledgers,
or agent permission configuration. No hooks or separate agent configuration
directories are needed at present.
