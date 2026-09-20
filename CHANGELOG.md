# Changelog

This is the detailed task history, newest first. Following the neighboring
NamiSync convention, `##` identifies a milestone or version, `###` a phase, and
`#### task (YYYY-MM-DD)` a dated delivery. Related work stays under one task;
extend its date range when it continues. Dates below describe development, not
publication. Retrospective entries summarize the Git history and
[archived implementation plan](docs/obsolete/IMPLEMENTATION_PLAN.md); commit IDs identify the
historical deliveries. User-facing release summaries live in
[RELEASE_NOTES.md](docs/RELEASE_NOTES.md).

## v0.1.0 (unreleased)

The first Python package release provides prescription input, deterministic
study-glass matching, and CSV/ZMX export. The distribution is
`optimatch`, matching its import and module command.

### Release preparation

#### Prepare Python package documentation and examples (2026-09-20)

- Rename the release distribution to `optimatch`, aligning wheel/source archive
  names and installation metadata with the existing import package and CLI.
- Document installation, expected prescription CSV sections, explicit catalogue
  selection, and the installed-user quickstart.
- Add this retrospective changelog and pending-release notes. Package a synthetic
  study lens and small catalogue; private examples and maintained catalogues
  remain ignored and are not release inputs.
- Archive the completed implementation plan under `docs/obsolete/`, retaining
  its engineering decisions and verification history for reference.
- Verify wheel/source-archive contents and metadata, excluding private inputs;
  preserve private-input hashes. Fresh wheel and source-archive installations
  run the packaged example and reject accidental output replacement. All 240
  tests pass against the installed wheel and in the checkout; lint, formatting
  and dependency checks pass. No release has been published.

### Export controls and source-data isolation

#### Add forced solves, OIS controls and asphere refinement (2026-09-14)

- Add repeatable forced compensator pairs and inclusive position spans, including
  configuration-varying totals, normal/reversed placement, dependency ordering,
  override diagnostics, and conflict/cycle rejection. Keep inference forward-only
  and preserve source-rounding corrections when reorienting an inferred solve.
- Add disjoint OIS boundary pairs with zero-initialized translations and cancelling
  same-configuration pickups that reference actual operand rows.
- Select ordinary/extended and even/odd asphere output from nonzero powers;
  handle normalized ordinary terms and ignore zero padding without rewriting
  the source tables.
- Make `samples/` and `catalogs/` local-only and ignored, replacing test and
  quickstart dependencies with synthetic fixtures. Previously committed private
  files remain in historical commits; this change did not rewrite Git history.
- Record 240 passing tests and twelve isolated OpticStudio 2023 R1.00 controls,
  including load/save/reload, solve perturbations and OIS cancellation.
  Delivery: `367a5c6`.

### Export refinements (F1–F4)

#### Separate rear movement from back focus (2026-09-11)

- Insert an export-only dummy surface for eligible rear solves, preserving original
  surface positions while separating the solved movement from a fixed rear gap.
  Report mappings, transformed solves and negative remainders; leave unsupported
  coupled or relocation cases unsplit with diagnostics.
- Record 199 passing tests and isolated TCOM, TOLE and combined host controls,
  including independent post-dummy adjustment. Delivery: `52ce37f` (F4).

#### Retain independent compensator relationships (2026-09-11)

- Collapse redundant constant spans before deciding solve ambiguity, preserving
  independent relationships while rejecting genuine conflicting dependencies.
  Recompute after rejected provisional equations so they cannot affect survivors.
- Record 180 passing tests and focused independent-pair, rounding and conflict
  regressions. Delivery: `acb5d86` (F3).

#### Organize multi-configuration operands (2026-09-11)

- Emit compact ordered sections for titles, varying independent thicknesses,
  apertures and off-axis vignetting pairs. Omit fixed and solved THIC rows and
  on-axis vignetting operands; separate nonempty sections with MOFF.
- Verify operand order and field indexing in OpticStudio 2023 R1.00; document
  the Windows host-validation workflow. Delivery: `770aeb1` (F2).

#### Add the fisheye field preset (2026-09-11)

- Add angle fields at 0, 18, 36, 54, 72 and 89 degrees, preserving compatible
  explicit fields and rejecting incompatible field types. Keep angle values
  independent of length-unit scaling. Delivery: `1dac687` (F1).

### Catalogue and matching policy (R0–R3)

#### Rename the Python interface to OptiMatch (2026-09-11)

- Rename the import package and module CLI to `optimatch`, retaining the
  `optics-prescription-matcher` distribution name. Update installation checks
  and command examples. Delivery: `d328957`.

#### Export unmatched numerical materials as model glass (2026-09-11)

- Use explicit fixed model glass when valid source nd/Vd falls outside catalogue
  matching gates. Retain supplied, derived or default-zero dPgF in that order;
  preserve transcription values and report model fallbacks separately.
- Confirm model-glass flags and supplied/derived/default dispersion using three
  OpticStudio load/save/reload and finite-ray controls; record 160 passing tests.
  Delivery: `7bc6f56` (R3).

#### Add molding preferences and manufacturer profiles (2026-09-11)

- Add Sony, Sigma and Fujifilm profiles alongside default, Canon and Nikon.
  Apply profile exclusions before ranking and retain supplied-name precedence.
- Prefer molding-suitable candidates within a bounded window for elements with
  an aspheric boundary, falling back to ordinary matching when none qualify.
- Derive missing dPgF from supplied PgF using the documented F2–K7 normal line;
  retain provenance and source strings without double-counting derived evidence.
- Record 141 passing tests. Delivery: `9394723` (R2).

#### Accept the revised reference-catalogue schema (2026-09-11)

- Accept canonical `Manufacturer,Typecode,nd,vd,PgF,dPgF` headers and optional
  `ne,ve,PrecisionMolding`, keeping legacy partial-dispersion aliases.
- Validate populated e-line values as a pair without using them for matching;
  normalize Ohara typecode whitespace and reject identity collisions while
  preserving exact-name lookup precedence. Record 122 passing tests.
  Delivery: `cdea729` (R1).

#### Organize reference data and record the delivery plan (2026-09-11)

- Establish the catalogue directory and the R0–R3 delivery contract; migrate the
  maintained reference data with byte/row checks and bounded Ohara whitespace
  normalization. These reference files were later made local-only on September 14.
- Record 106 passing tests after migration. Delivery: `70d45ac` (R0).

### Core prescription workflow (C1–C3)

#### Add study setup presets and the CLI reference (2026-09-10)

- Add the five-wavelength study setup and sensor field presets, explicit-setting
  precedence, paraxial ray aiming and working f-number setup. Report assumptions
  and an unspecified-aperture placeholder rather than hiding them.
- Establish `docs/COMMANDLINE.md` as the complete command and input reference.
  Delivery: `8f8dcff`.

#### Export ZMX study models and thickness solves (2026-09-10)

- Add Unicode ZMX export for supported even/odd asphere families, configurations,
  named/offset glass and explicit or eligible inferred TCOM/TOLE relationships.
  Preserve source geometry and report rounding-based dependent adjustments.
- Protect input/output paths and reject missing export essentials before writing.
  Record 96 passing tests and five OpticStudio 2023 R1.00 control files covering
  twelve configurations, ray traces and independent asphere sag comparisons.
  Delivery: `0957e61` (C3).

#### Match study glass using preference profiles (2026-09-10)

- Add deterministic close/offset candidate gates, default/Canon/Nikon priorities,
  supplied-typecode handling, partial-dispersion comparisons and traceable reports.
  Keep offsets signed as prescription minus catalogue and preserve source values.
- Add CSV/report CLI output and validation for unnamed source offsets; record
  71 passing tests. Delivery: `12ef54c` (C2).

#### Load structured optical prescriptions (2026-09-10)

- Add validated JSON and sectioned CSV prescriptions, catalogue loading and faithful
  CSV output. Preserve numeric strings, aspheres, configurations and meaningful
  distinctions between air and missing material data.
- Add section/row/field diagnostics and numeric/reference validation; record
  40 passing tests. Delivery: `47d79bd` (C1).

### Project foundations

#### Establish the Python project and development rules (2026-09-10)

- Initialize the repository and license (`c2ccc13`), then add the flat Python
  package, setuptools configuration, installation smoke test, pytest/Ruff checks,
  CI and line-ending rules (`ed91cf6`).
- Record product scope, checkpoint plans and ZMX syntax evidence. Keep OCR deferred
  and XLSX, AGF and database parsing outside the implemented input workflow.
