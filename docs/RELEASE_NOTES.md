# Release notes

## v0.1.0 — pending release

OptiMatch turns a supplied optical prescription and a reference-catalogue CSV
into a study prescription, a matching report, and optionally an OpticStudio ZMX
model. Results are study substitutes, not identification of production materials
or validation of a lens's optical performance.

### Installation and first run

The Python distribution is `optics-prescription-matcher`; run it with
`python -m optimatch`. Python 3.13 or newer is required, with no third-party
runtime dependencies. This release targets a wheel and source archive, not a
standalone executable. See the [README](../README.md) for installation and the
quickstart using the bundled synthetic lens and small catalogue.

### Included behavior

- Validated sectioned CSV and structured JSON prescription input, preserving
  source numeric strings, asphere tables and configuration values.
- Explicit catalogue CSV selection, deterministic glass matching, default/Canon/
  Nikon/Sony/Sigma/Fujifilm preference profiles, bounded molding preferences,
  partial-dispersion handling and model-glass fallback for valid numerical data.
- Matched CSV and diagnostic JSON reports, plus ZMX export with study setup
  presets, supported even/odd aspheres, configurations and eligible thickness
  solves. Reports explain material selections, assumptions and solve adjustments.
- Forced compensator/position controls, normal/reversed position placement,
  paired OIS translations and eligible rear-dummy back-focus separation.
- Synthetic examples only. Maintained catalogues and private prescriptions are
  not release inputs; supply your own catalogue through the command line.

The [CLI reference](COMMANDLINE.md) defines accepted CSV headers, catalogue
columns, options and examples. The [changelog](../CHANGELOG.md) records the
retrospective development history.

### Limitations and verification

Matching is a deterministic study heuristic. Manufacturer profiles express
preferences and exclusions, not proof of a manufacturer's actual material choice.
Source CSV output retains transcribed values; export-only solve adjustments and
surface mappings are described in the report.

OCR is not implemented. Direct XLSX input, AGF parsing and database storage are
outside scope. Optional catalogue `ne`/`ve` values are retained but not used for
matching. ZMX export covers the documented surface and solve families, not a
general-purpose ZMX reader or arbitrary OpticStudio system.

The existing implementation was verified with 240 tests and selected controls
in OpticStudio 2023 R1.00, including load/save/reload, geometry, solves and OIS
perturbations. This evidence applies to those controls; arbitrary exports and
other OpticStudio versions are not automatically host-validated. See
[ZMX_SYNTAX.md](ZMX_SYNTAX.md) for the supported records and evidence.

Package checks on Windows with Python 3.13.14 passed on 2026-09-20: wheel and
source-archive contents inspected, metadata checked, and each artifact installed
in a separate fresh environment. Both installations run the bundled example,
produce CSV/UTF-16 ZMX/JSON outputs and protect existing outputs. All 240 tests
pass against the installed wheel and in the checkout; Ruff and dependency checks
pass. Private-input hashes are unchanged. Other Python versions and operating
systems were not tested in this release check.

The default Windows temporary-directory and pip-cache paths encountered access
restrictions; verification used a task-owned pytest directory and disabled pip
caching for the source installation. No application change was needed.

The artifacts are prepared for review; no tag, push or publication has occurred.
