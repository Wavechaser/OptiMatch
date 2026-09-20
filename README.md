# OptiMatch

OptiMatch matches prescription glasses against a CSV catalogue and exports
CSV/ZMX study models with a JSON decision report. Manufacturer profiles guide
best-effort selection. Results are study substitutes, not claims about production
lenses or optical performance.

## Installation

OptiMatch requires **Python 3.13 or newer** and has no third-party runtime
dependencies. It is distributed as a Python package, not a Windows executable.
The distribution name is `optimatch`; run it as
`python -m optimatch`.

For the prepared 0.1.0 release, install the wheel supplied with the release
artifacts. These PowerShell commands use a new working directory; replace the
wheel path with your downloaded file's absolute path:

```powershell
New-Item -ItemType Directory optimatch-study
Set-Location optimatch-study
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install "C:\Downloads\optimatch-0.1.0-py3-none-any.whl"
.\.venv\Scripts\python.exe -m optimatch --help
```

Use an installed newer Python version in place of `-3.13` if needed. Environment
activation is unnecessary. This release preparation does not imply a PyPI
publication. You can also install the source archive with
`python -m pip install PATH\optimatch-0.1.0.tar.gz` using your
environment's Python; pip must obtain the build requirements.

For development from a repository checkout, see the
[development commands](docs/COMMANDLINE.md#development-windows--powershell).

## Try the packaged example

The package includes one synthetic lens and a two-row example catalogue. In the
new working directory from installation, copy them from the installed package:

```powershell
@'
from importlib.resources import files
from pathlib import Path

examples = files("optimatch").joinpath("examples")
for name in ("study.csv", "catalog.csv"):
    Path(name).write_bytes(examples.joinpath(name).read_bytes())
'@ | .\.venv\Scripts\python.exe -

.\.venv\Scripts\python.exe -m optimatch study.csv `
  --catalog catalog.csv --field-preset aps-c --output output/study
```

Copy into an empty working directory: the copy step replaces files with these
names. The example demonstrates a supplied glass with offsets, an even asphere,
and two configurations. Its values are synthetic, and `TEST-PM` is fictitious;
this is neither a reference catalogue nor a recommended optical design.

The command creates:

- `output/study.csv`: sectioned prescription CSV preserving source quantities.
- `output/study.zmx`: UTF-16 study model for OpticStudio.
- `output/study.report.json`: glass decisions, offsets, warnings and export adjustments.

Review the report before using a result. Existing outputs are protected; choose a
new prefix or pass `--overwrite` to replace them. Use `--format csv` when your
transcription does not yet contain the setup required for ZMX output.

## Prepare your prescription CSV

Prescription CSV is **sectioned**, not a single flat table. Save it as UTF-8 CSV
(a BOM is accepted), using decimal points. Start with a `Lens Data` line and the
required columns `Surface,Radius,Thickness,Material,nd,vd`. For example:

```csv
Lens Data
Surface,Radius,Thickness,Material,nd,vd,Stop
OBJ,0,infinity,,,,
1,40.000,2.50,,1.51680,64.1700,true
2,-30.000,15.00,,,,
IMG,0,,,,,
```

Each row describes a surface and the medium/thickness after it. Leave `Material`
blank and supply both `nd` and `vd` to request matching. A supplied material
typecode remains authoritative. Empty material and optical-value cells describe
air; do not leave unknown glass data blank. Optional columns include `PgF`,
`dPgF`, `nd offset`, `vd offset`, and `Stop` (`true`, `false`, or blank). Keep
source decimals and significant figures intact; offsets mean prescription minus
catalogue. CSV distances default to millimetres.

Optional `Even Aspheres` / `Odd Aspheres` sections hold coefficients. A
`Multiconfiguration Data` section holds configuration columns and values for
symbolic thicknesses such as `d0`. Use the packaged `study.csv` as a complete
example. ZMX requires `OBJ` and `IMG`, one internal stop, and explicit fields or
a `--field-preset`; set a usable aperture through configuration data or metadata.
The [input reference](docs/COMMANDLINE.md#prescription-inputs) describes all
sections, canonical JSON input and optional `--metadata` overlays.

## Supply your glass catalogue

Pass the catalogue path explicitly on every invocation with `--catalog`.
OptiMatch reads that one CSV file; it does not search folders, load installed
OpticStudio catalogues, merge files or download glass data. Relative paths are
resolved from your working directory. The bundled catalogue is only an example.

Export your maintained workbook as UTF-8 CSV, using these case-sensitive headers:

```csv
Manufacturer,Typecode,nd,vd,PgF,dPgF,ne,ve,PrecisionMolding
Ohara,S-BSL7,1.51680,64.1700,,0.0000,1.51872,63.9600,
```

`Manufacturer`, `Typecode`, `nd`, `vd`, `PgF`, and `dPgF` are required headers;
partial-dispersion cells may be blank. `ne`, `ve`, and `PrecisionMolding` are
optional headers. Populate both e-line values or neither; they are retained but
not used for matching. `PrecisionMolding` accepts `1`, `0`, or blank. Unknown or
duplicate headers are rejected. The [catalogue reference](docs/COMMANDLINE.md#prescription-inputs)
also lists accepted historical aliases and typecode restrictions.

```powershell
.\.venv\Scripts\python.exe -m optimatch "my lens.csv" `
  --catalog "C:\My Optical Data\glass.csv" --profile default `
  --field-preset aps-c --output output/my-lens
```

The default preference is Ohara, then Hoya, then Hikari, then others. Other
profiles have their own preferences and exclusions; see the
[CLI reference](docs/COMMANDLINE.md#match-a-prescription). A numeric glass without
an acceptable catalogue candidate becomes model glass, with the reason recorded
in the report. In a checkout, keep private prescriptions in ignored `samples/`
and maintained catalogues in ignored `catalogs/`; neither is shipped.

## Limits and documentation

OCR and PDF/image transcription are not implemented. OptiMatch does not read
XLSX, AGF or ZMX inputs, or use a database. Exporting a ZMX file does not prove
that a particular OpticStudio host loaded it or that its glass names resolve.

- [Release notes](docs/RELEASE_NOTES.md): release scope and limitations.
- [Changelog](CHANGELOG.md): retrospective implementation history and unreleased work.
- [Command-line reference](docs/COMMANDLINE.md): all options, presets, inputs and development commands.
- [Features](docs/FEATURES.md): supported and desired behavior.
- [Historical implementation record](docs/obsolete/IMPLEMENTATION_PLAN.md): completed checkpoints and delivery evidence.
- [ZMX syntax](docs/ZMX_SYNTAX.md): verified records and unresolved details.
- [Project rules](AGENTS.md): structure, optical-data handling and Git conventions.
