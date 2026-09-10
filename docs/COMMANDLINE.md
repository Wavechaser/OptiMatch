# Command-line reference

Run all commands from the repository root using native PowerShell. Quote paths
containing spaces. Results are study substitutes, not representations of
production samples.

The repository contains validated JSON/CSV input records, deterministic glass
matching, a machine-readable decision report, and sectioned CSV/ZMX output. OCR
is not implemented. Catalogue input is CSV exported from the
user's maintained Excel workbook. XLSX parsing, AGF parsing, and SQLite/database
storage are out of scope. OCR can be added independently later.

## Current delivery note

At the R3 matching-policy checkpoint, the executable accepts both the historical
six-column catalogue and the revised nine-column catalogue described below. All
six profiles, molding-aware selection, and partial-dispersion derivation are
implemented. A valid numeric no-match is exported as model glass. An explicitly
unresolved legacy result still blocks ZMX output; all ordinary setup, identifier,
and optical-data validation also remains in force.

The active delivery policy uses these strict numerical boundaries:

| Outcome | Required absolute difference | Export behavior |
| --- | --- | --- |
| Close (including exact) | `abs(Δnd) < 0.0002` and `abs(ΔVd) < 0.1` | Named typecode, no offsets |
| Near/offset | `abs(Δnd) < 0.02` and `abs(ΔVd) < 2` | Named typecode plus prescription-minus-catalogue offsets |
| Model glass | No allowed candidate passes either gate | Source nd/Vd, no invented typecode or catalogue offsets |

Equality at a boundary fails that gate. An element bounded by an aspheric front
or rear surface first considers `PrecisionMolding=1` candidates inside the
strict promotion window `|Δnd| < 0.005`, `|ΔVd| < 0.5`; an empty promotion pool
falls back to ordinary matching. This is a bounded preference, not an exclusion
of polymers, crystals, or ordinary glass.

The CLI accepts `default`, `canon`, `nikon`, `sony`, `sigma`, and
`fujifilm`. Their precise preference orders and exclusions are recorded in
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). Profiles are selected only by
`--profile`, never inferred from a filename. e-line ne/ve matching is deferred.

## Match a prescription

Complete invocation (there are no subcommands):

```text
python -m optimatch INPUT --catalog CSV --output PREFIX
    [--profile {default,canon,nikon,sony,sigma,fujifilm}]
    [--format {csv,zmx,both}]
    [--metadata JSON] [--overwrite]
    [--field-preset {1-type,m43,aps-c,full-frame,44x33}]
```

| Argument | Meaning / default |
| --- | --- |
| `INPUT` | Required prescription path. A `.csv` suffix (case-insensitive) selects the sectioned CSV adapter; otherwise the file is read as canonical JSON. Not a PDF, image, ZMX, or workbook reader. |
| `--catalog CSV` | Required glass catalogue CSV export. |
| `--output PREFIX` | Required output prefix; `.csv`, `.zmx`, and `.report.json` suffixes are appended, not substituted. Parent directories are created. |
| `--profile default\|canon\|nikon\|sony\|sigma\|fujifilm` | Glass preference profile; default `default`. |
| `--format csv\|zmx\|both` | Requested prescription outputs; default `both`. Every successful invocation also writes the JSON report. |
| `--metadata JSON` | Optional metadata overlay for a CSV prescription only. Cannot replace CSV tables. |
| `--field-preset 1-type\|m43\|aps-c\|full-frame\|44x33` | ZMX real-image-height y-field preset. Overrides `system.field_preset`, not explicit real-image-height fields. An explicit angle field type conflicts with a preset. Ignored for CSV-only output. No implicit format. |
| `--overwrite` | Replace existing requested output files. Without it, existing outputs cause an error. Inputs remain protected. |
| `-h`, `--help` | Display usage and exit without reading inputs. |

Exit status is `0` on success/help and `2` for command syntax, input, export or
filesystem errors handled by the CLI. Errors go to stderr, successful output
paths and matching counts to stdout. A zero-aperture warning also goes to stderr
but is not an export failure. Numerically valid model glass can succeed in every
format. Inspect the report instead of treating status 0 as optical
validation. There is no automatic retry, interactive prompt or host launch.

Run the study-model workflow with a canonical JSON or sectioned CSV input:

```powershell
.\.venv\Scripts\python.exe -m optimatch prescription.json `
  --catalog samples/combined_glass_catalog.csv --profile default `
  --output output/study --format both
```

Profile policies are:

| Profile | Preference order | Exclusions |
| --- | --- | --- |
| `default` | Ohara, Hoya, Hikari, others | None |
| `canon` | Ohara, Hoya, others | Hikari, CDGM, Schott, Sumita |
| `nikon` | Hikari, Hoya, Ohara, others | CDGM, Schott, Sumita |
| `sony` | Hoya, Ohara, Hikari, others | CDGM, Schott, Sumita |
| `sigma` | Hoya, Ohara, others | Hikari, CDGM, Schott, Sumita |
| `fujifilm` | Ohara, Hoya, CDGM, Hikari, others | Schott, Sumita |

Exclusions apply only to inferred matching. Explicit typecodes remain
authoritative. The
`--format` option defaults to `both`; use `csv` for an incomplete transcription that
lacks the system metadata required by ZMX, or `zmx` for model-only output. A JSON
report is always written on success. Existing outputs require
`--overwrite`; outputs can never overwrite the input, catalogue, or CSV metadata
overlay. Pass `--metadata PATH` only with a sectioned CSV input. Requested outputs
are validated before writing; replacing several files is not a single transaction.

ZMX output requires explicit OBJ and IMG endpoints and one internal stop.
Specify fields explicitly or select a sensor-format preset; setup defaults are
described below. Explicit wavelengths/weights must be positive.
It writes UTF-16 LE with a BOM and preserves source coefficients. Source distances
remain in CSV/report; ZMX applies disclosed solve adjustments and derivations.
It supports ordinary/extended even and extended odd aspheres, omits fixed aperture
records and GCAT, and emits neutral vignetting configuration operands. Configured
infinite object distance uses the tested numeric `1e10` representation and is
disclosed in the report. Unknown supplied typecodes remain visibly
host-lookup-unverified; the report does not claim that a particular output was
loaded by OpticStudio.

### Setup defaults and field presets

Add `--field-preset aps-c` to use a format preset, or set
`"system": {"field_preset": "aps-c"}` in JSON/CSV metadata. Format is never guessed.
Explicit real-image-height field arrays take precedence over a preset. Supplying
a preset with an explicit `angle` field type is an error even when fields are
present; omit the preset to use angle fields. Heights below are millimetres,
converted for other lens units.

| Preset | Y image heights (mm) |
| --- | --- |
| `1-type` | 0, 1.6, 3.2, 4.8, 6.4, 8 |
| `m43` | 0, 2, 4, 6, 8.5, 11 |
| `aps-c` | 0, 3, 6, 9, 12, 15 |
| `full-frame` | 0, 4, 8, 12, 17, 22 |
| `44x33` | 0, 5, 10, 15, 21, 27 |

Absent wavelength data uses the five sample wavelengths in their original order:
0.486133, 0.546073, 0.656273, 0.587562, 0.435833 micrometres; weights are
0.9393, 1.000, 0.7349, 0.9507, 0.7868. Primary is #2 (e line). Explicit
wavelength arrays keep their values and order; an explicit primary takes
precedence, otherwise #2 is used (#1 for a single wavelength).

Fields default to real image height, radial normalization, y only, with unit
weights and zero vignetting. Paraxial ray aiming is enabled and the global
coordinate reference is the stop. Aperture type defaults to paraxial working
f-number; its value comes from the system, otherwise the first configuration,
otherwise zero. Zero is a warned incomplete-setup placeholder, not a usable
analysis aperture. Applied settings and warnings appear in the JSON report.
Other sample-specific header settings are not copied.

The JSON report distinguishes air, supplied typecodes, close matches, offset
matches, model glass, and the retained legacy unmatched category. CLI `matched`
counts only named supplied/close/offset results; `model` is separate. The report
includes signed prescription-minus-
catalogue differences, source precision steps, partial-dispersion residuals,
effective supplied/derived dispersion values and their provenance, molding
suitability, asphere trigger IDs, alternatives, ambiguities, and the ranking
criterion that selected a candidate.
An unknown supplied typecode is preserved and marked host-lookup-unverified.
Reported decimal steps describe source formatting, not independently established
measurement accuracy; Excel padding can make them misleading. Supplied offsets
require a named base glass and are preserved, never reinterpreted as air.

When dPgF is absent but PgF and Vd are present, matching derives dPgF from the
documented F2--K7 normal line. A supplied dPgF always wins. A PgF-only source
contributes only that derived dPgF comparison channel; explicitly supplied PgF
and dPgF retain both channels and use the maximum normalized residual. Derived
format resolution is the PgF last-place step plus the absolute normal-line slope
times the Vd last-place step. Source and catalogue strings are not rewritten,
and missing catalogue dispersion remains missing rather than becoming zero for
matching. For export, named glasses use effective catalogue dPgF when available.
A model glass uses source dPgF, otherwise derives it from PgF/Vd, otherwise uses
fixed zero; that last export fallback is reported as `default_zero` and is not a
warning.

## Prescription inputs

Catalogue input is UTF-8 CSV, optionally with a BOM. Required headers are
`Manufacturer`, `Typecode`, `nd`, `vd`, `PgF`, and `dPgF`; the historical
`P_g,F` and `d_Pg,F` spellings remain accepted aliases. Optional headers are
`ne`, `ve`, and `PrecisionMolding`. Partial-dispersion cells may be blank. When
either e-line value is populated, both `ne` and `ve` must be populated; these
strings are retained but not used for matching. `PrecisionMolding` accepts `1`,
`0`, or blank. Unknown, duplicate, and alias-colliding headers are rejected.
Optical values must be finite, with nd/vd and populated ne/ve positive.

Ohara typecodes have all whitespace removed before validation and duplicate
detection. Other manufacturers lose only surrounding whitespace; internal spaces
are retained, while control characters remain invalid. A selected typecode with
internal spaces cannot be emitted as a ZMX token: supply its verified single-token
Zemax name, or use CSV-only output. Do not remove non-Ohara spaces by guesswork.
Example:

```csv
Manufacturer,Typecode,nd,vd,ne,ve,PgF,dPgF,PrecisionMolding
Ohara,S-BSL7,1.51633,64.1428,1.51825,63.9307,0.535322,-0.0024,
```

Example using the supplied transcription without requiring complete ZMX setup:

```powershell
.\.venv\Scripts\python.exe -m optimatch samples/sample_lens_data.csv `
  --catalog samples/combined_glass_catalog.csv --format csv --output output/matched
```

For ZMX from a CSV transcription, supply absent stop/system information through
an overlay and choose a field preset:

```powershell
.\.venv\Scripts\python.exe -m optimatch prescription.csv `
  --catalog "my catalogue.csv" --metadata setup.json --field-preset aps-c `
  --profile canon --output output/study
```

Load canonical JSON or adapt the historical sectioned CSV:

```python
from optimatch.inputs import (
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

The import package and module CLI are now `optimatch`; the project/distribution
name remains `optics-prescription-matcher`. Existing checkouts should rerun the
editable install below after updating. The former package name is not an alias.

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

- `optimatch/`: Python package (flat layout).
- `optics_prescription_matcher.egg-info/`: ignored installation metadata.
- `tests/`: input, CSV, matching, ZMX, solve, CLI, and installation tests.
- `catalogs/REFERENCE_CATALOG.csv`: maintained, executable reference-catalogue
  CSV export using the revised schema.
- `samples/combined_glass_catalog.csv`: supplied catalogue snapshot.
- `samples/sample_lens_data.csv`: worked, multi-section prescription CSV.
- `samples/EF-M 22mm F2 STM.ZMX` and `samples/14-24mm F2.8 DG DN Art.ZMX`: original
  UTF-16 reference designs.
- `samples/SAMPLE_INSTRUCTIONS.md`: historical agent instructions, qualified by the
  current scope and data rules in `AGENTS.md`.
- `output/`: ignored generated files, created only when needed.

## Documentation

- [Features](FEATURES.md): desired capabilities, independent of implementation.
- [Implementation proposal](IMPLEMENTATION_PLAN.md): data contracts, matching
  policy, exporter design, and completed implementation checkpoints.
- [ZMX syntax](ZMX_SYNTAX.md): observed records, sources, and unresolved details.

See [AGENTS.md](../AGENTS.md) for development and optical-data conventions. Git attributes
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
