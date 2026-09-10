# OpticsPrescriptionMatcher

A small Python tool for matching patent-prescription glasses against a CSV
catalogue and exporting CSV/ZMX study models with a decision report. Results
are credible study substitutes, not claims about production lenses. OCR is
deferred; XLSX, AGF and database parsing are outside the current scope.

## Setup

Python 3.13+; run from the repository root in PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Skip venv creation if it already exists. Activation is unnecessary.

## Quickstart

Match the supplied transcription to CSV:

```powershell
.\.venv\Scripts\python.exe -m optics_prescription_matcher samples/sample_lens_data.csv `
  --catalog samples/combined_glass_catalog.csv --format csv --output output/study
```

For a complete prescription, omit `--format csv` to export both CSV and ZMX.
Supply fields in the input or add a preset such as `--field-preset aps-c`.

## Documentation

- [Command-line reference](docs/COMMANDLINE.md): all options, presets, inputs and development commands.
- [Features](docs/FEATURES.md): supported and desired behavior.
- [Implementation plan](docs/IMPLEMENTATION_PLAN.md): contracts, policies and delivery evidence.
- [ZMX syntax](docs/ZMX_SYNTAX.md): verified records and unresolved details.
- [Project rules](AGENTS.md): structure, optical-data handling and Git conventions.
