# Glass matcher and ZMX exporter: implementation proposal

Status: C1, C2, and C3 implemented and independently reviewed, 2026-09-10.
The R0–R3 catalogue and matching-policy delivery is in progress.
This plan applies the plan-work structure with small implementation commits.
Product requirements live in [FEATURES.md](FEATURES.md); file-format evidence
lives in [ZMX_SYNTAX.md](ZMX_SYNTAX.md). Proposed policies below are explicit
engineering choices, not claims that the historical examples uniquely imply them.

## Main objectives

Produce a credible prescription for optical study using supplied transcription,
best-effort glass choices, and CSV/ZMX output. Keep the workflow small enough for
a Python command, with deterministic matching and traceable rounding adjustments.
Accept future OCR results through the same structured input contract.

## Current delivery register

| ID | Outcome | Dependency | Acceptance gate | Status |
| --- | --- | --- | --- | --- |
| R0 | Organize the revised catalogue and record active policy | — | Data-only migration audit and baseline checks | Complete |
| R1 | Accept the revised catalogue schema and scoped typecode normalization | R0 | Loader and compatibility tests | Complete |
| R2 | Add profiles, PgF conversion, and asphere-driven molding preference | R1 | Boundary, ownership, and ranking tests | Complete |
| R3 | Emit and validate model-glass fallbacks | R2 | Integrated CLI and OpticStudio checks | Pending |

R0 moves the maintained CSV to `catalogs/REFERENCE_CATALOG.csv`; source XLSX
workbooks remain samples and are not application inputs. The migration removes
whitespace only from Ohara typecodes. Its audit must prove row order and all
other cells unchanged and must reject any identity collision. This checkpoint
also records the intended behavior before production code changes.

R0 migration evidence: 1,186 rows were retained; 38 Ohara typecodes changed;
every other cell was identical; and the normalized manufacturer/typecode keys
remained unique. The baseline suite passed all 106 tests after migration.
Fresh read-only review independently confirmed all 38 raw line changes and the
unchanged Sigma/workbook hashes. Ruff, pip check, and diff checks passed. R0 is
the commit titled `chore(data): organize reference catalog and record delivery plan`.

R1 accepts required headers `Manufacturer,Typecode,nd,vd,PgF,dPgF` and optional
`ne,ve,PrecisionMolding`. Legacy partial-dispersion spellings remain input
aliases, while new output uses the canonical names. `ne` and `ve` must appear as
a complete pair when populated but remain unused. `PrecisionMolding` accepts
`1`, `0`, or blank (suitable, unsuitable, unknown). Ohara typecodes remove all
whitespace before validation and duplicate detection; other manufacturers only
lose surrounding whitespace. Glasses, polymers, and reference crystals are
equally eligible. Status/Class filtering, XLSX, AGF, and database readers remain
out of scope.

R2 keeps strict matching gates: close requires `|Δnd| < 0.0002` and
`|ΔVd| < 0.1` and emits no offsets; near/offset requires `|Δnd| < 0.02` and
`|ΔVd| < 2` and emits prescription-minus-catalogue offsets. Equality does not
pass a gate. For a material following surface *i*, an asphere on surface *i* or
*i+1* activates a bounded molding preference. Molding-suitable candidates first
compete within `|Δnd| < 0.005` and `|ΔVd| < 0.5`; if none exist, ordinary
matching is unchanged. A rear air surface therefore belongs to the preceding
element, while an outer asphere on a cemented component does not promote the
entire cemented group. Explicit material names remain authoritative.

Profiles apply exclusions before either candidate pool and never override a
supplied typecode or arise from a filename:

| Profile | Preference order | Exclusions |
| --- | --- | --- |
| default | Ohara > Hoya > Hikari > others | None |
| canon | Ohara > Hoya > others | Hikari, CDGM, Schott, Sumita |
| nikon | Hikari > Hoya > Ohara > others | CDGM, Schott, Sumita |
| sony | Hoya > Ohara > Hikari > others | CDGM, Schott, Sumita |
| sigma | Hoya > Ohara > others | Hikari, CDGM, Schott, Sumita |
| fujifilm | Ohara > Hoya > CDGM > Hikari > others | Schott, Sumita |

When PgF is supplied without dPgF, calculate with `Decimal` and retain the
original strings:

```text
Pnormal(vd) = 0.582848
            + (vd - 36.26) * (0.543528 - 0.582848) / (60.49 - 36.26)
dPgF = PgF - Pnormal(vd)
```

Supplied dPgF wins. Reports distinguish supplied and derived values; derivation
does not rewrite transcription fields.

R3 turns a numerically valid material outside both catalogue gates into status
`model`, retaining source nd/vd and no catalogue identity or offset. Missing or
invalid optical data still fails. ZMX uses model-glass mode 1 and supplied,
derived, or default-zero dPgF in that order; a missing dPgF default is not a
warning. A bounded host experiment will vary the three suspected model-glass
optimization flags one at a time. If their mapping is confirmed, fixed study
values use `0 0 0`; otherwise populated nd/vd/dPgF retain the observed `1 1 1`
fallback and the uncertainty remains documented. Named and offset modes must
remain unchanged.

Every checkpoint receives focused tests, the full pytest/Ruff/diff checks, and
fresh adversarial review before its atomic commit. Stop on catalogue-normalizing
collisions, unexpected input-byte changes, or host behavior contradicting the
model serialization contract. OCR, e-line matching, optimization, and a general
ZMX reader are non-goals for this delivery.

## Completed C1–C3 baseline record

R2 execution boundary (base `cdea729`): matching policy and dispersion helper,
CLI profile choices, their matching/CLI tests, and policy sections of active docs.
Keep source strings, supplied-name precedence, exact lookup before normalization,
ordinary pool ranking, and exporter behavior intact. PgF-only input contributes
one derived dPgF comparison channel, not both PgF and its derivative. Its format
resolution is `PgF_step + abs(normal_line_slope) * vd_step`, not the computed
decimal expansion's last place; this is not a measurement-uncertainty claim.
Explicit PgF plus dPgF retain the existing maximum-residual comparison. Derive
catalogue dPgF when absent using the same helper, never default missing matching
data to zero. Store effective values/provenance separately for R3 export.
Gate: all profile exclusions and priority orders, strict molding boundaries,
front/back/cemented ownership, conversion endpoints/sign/precedence/resolution,
and catalogue-order stability tested; full suite/Ruff/diff and fresh review pass
before `feat(matching): add molding preferences and manufacturer profiles`.
Model fallback and exporter changes remain R3, not R2.
R2 completed with 141 passing tests, Ruff and diff checks, and fresh adversarial
approval after fixing caller-context leakage in derived resolution. The revised
reference-catalogue CLI smoke matched all six sample materials under Canon.

R1 execution boundary (base `70d45ac`): change only catalogue records/loading,
supplied-name lookup normalization, their input/matching tests, and the catalogue
sections of active docs. Preserve positional constructor compatibility, optical
strings, legacy six-column inputs, exact-name lookup precedence, and exporter
token safety. No new ranking or model-export behavior in R1. Gate: both shipped
catalogues load, aliases and normalization collisions are tested, complete suite
and Ruff pass, and fresh review approves before `feat(catalog): accept revised
reference catalog schema`. Stop on unexpected data changes or scope expansion.
R1 completed with 122 passing tests, Ruff lint/format, pip check, and diff checks.
Fresh review confirmed parser rejection, legacy blank rows, scoped canonicalization,
and source/report preservation. Both shipped catalogues load; no input data changed.

The remaining sections preserve the original implemented proposal and evidence.
Where its earlier matching or unmatched-material policy differs, the current
R0–R3 register above is authoritative for this delivery.

## Scope and decisions

### Setup defaults and presets (2026-09-10 follow-up)

Implement export-time defaults without rewriting transcription: five sample
wavelengths in their original order (six significant digits, four for weights),
primary #2; real-image-height radial y fields with unit weights and zero
vignetting; the requested RAIM string; GLRS at the mapped stop. Preserve explicit
wavelength/field settings. Add `system.field_preset` and CLI `--field-preset`
choices `1-type`, `m43`, `aps-c`, `full-frame`, `44x33`; never infer a format.
Preset heights are millimetres and convert to source lens units. Explicit fields
take precedence; a preset with an explicit non-image-height field type is an error.
Default aperture type is paraxial working f-number; take the base value, otherwise
the first configuration's aperture, otherwise emit zero as an incomplete setup
placeholder with a report warning (not a trace-ready claim). Negative values fail.
Do not copy the rest of a sample header indiscriminately. Scope: models/input,
export/CLI, their tests and documentation. Verify sample values, regression tests,
and loaded host settings, including wavelength count, ray aiming and GLRS.
Preserve pre-existing sample changes and the untracked XLSX file. The subsequent
user request authorizes committing these setup changes together with the complete
CLI reference in COMMANDLINE.md and a minimal README, before upstream research.

Completion: defaults and presets are implemented; 106 tests pass. OpticStudio
2023 R1.00 confirmed five active wavelengths/primary #2, radial image-height
fields, Paraxial aiming, stop global reference and zero-aperture persistence.
A wavelength-count-only control changed the active count to three, proving the
fourth FTYP number's role. A nonzero-aperture generated model traced successfully;
zero-aperture output remains explicitly incomplete. See ZMX_SYNTAX.md for values.

### Implementation boundary

Implement one package with ordinary functions and small dataclasses: `models.py`
for records, `inputs.py` for loading/validation, `matching.py` for selection,
`export.py` for CSV/ZMX, `solves.py` for solve resolution/inference, and
`__main__.py` for argparse.
Split modules further only if an implemented responsibility requires it. No
framework, database, plugin registry, service, GUI, or optimization engine.

First accept a canonical JSON prescription and the supplied catalogue CSV.
Also read the existing sectioned CSV as an adapter, with optional JSON metadata
for information it cannot express. The user exports their maintained Excel
catalogue to CSV; the script only reads that CSV. XLSX readers, openpyxl, AGF
parsing, and SQLite/database storage are out of scope. OCR engines are deferred.
This is not a general ZMX
reader or an attempt to reproduce a manufacturer's production lens.

Proposed command shape:

```powershell
.\.venv\Scripts\python.exe -m optics_prescription_matcher prescription.json --catalog samples/combined_glass_catalog.csv --profile default --output output/study
```

Produce `study.csv`, `study.zmx` when eligible, and `study.report.json`. A CSV-only
request must remain possible when ZMX-required data is absent. Refuse existing
output targets unless an explicit overwrite option is supplied. Fully validate
and render requested outputs before writing them; write through temporary files
beside each destination. Do not claim multi-file transactional guarantees.
Invalid input or failed requested export returns nonzero with an actionable
field/surface diagnostic. Unmatched glass is a reported matching outcome, not
a parser crash; it blocks requested ZMX output until resolved.

### Input and value contracts

- `Prescription`: title, units, ordered surfaces, optional system settings and
  configurations. Version the JSON shape with `schema_version: 1`.
- `Surface`: stable source ID, radius, thickness, material/typecode, nd, vd,
  optional PgF/dPgF, stop flag, optional asphere. Maintain a mapping to sequential
  ZMX surface numbers; object/image and inserted stops must not shift references
  silently. A glass describes the medium following that surface.
- `Asphere`: explicit even/odd family, conic, coefficient map keyed by actual
  power (`"4"`, `"6"`, etc.), and normalization convention. Never infer powers
  from the number of coefficients. Preserve missing versus explicit zero in the
  transcription; insert required serialization placeholders only at export.
- `Configuration`: name, thickness values by source surface ID or declared
  symbol, optional aperture. Symbols such as `d0`, `d11`, and `BFL` are preserved
  but must resolve for every configuration requested for ZMX output.
- Optional `rounding_steps`: map JSON quantity paths to decimal-string rounding
  steps, such as `"/configurations/0/thicknesses/11": "0.01"`. This overrides
  unreliable formatting precision. A null step marks precision unknown and
  disables rounding-based inference for relationships using that quantity.
  Without an override, last-place precision is inferred only for a transcription
  explicitly marked `source_precision_trusted: true`; the default is false.
- `CatalogGlass`: manufacturer, typecode, nd, vd, optional PgF/dPgF. Retain
  manufacturer internally even though the prescription's Material cells omit it.
- `Match`: status (air, supplied, close, offset, unmatched), selected catalogue
  identity, original values, differences, profile, and reason/tie diagnostics.

Store source quantities as strings and parse with `Decimal` for comparison and
arithmetic. Accept signed decimal and scientific notation (e.g. `-1.00E-5`);
reject NaN, malformed exponents, booleans and nonfinite numeric values. Recognize
`flat`, `infinity`, and `∞` only in supported radius/object-distance contexts;
plane radius maps to zero curvature. Thickness symbols must be declared and
resolved, not evaluated as Python expressions. Keep a finite positive nd/vd
requirement for material matching; do not impose arbitrary bounds on radius or
aspheric coefficients. Validate supported units before conversion/export.

CSV reading uses the standard csv module, explicit section/header recognition,
and UTF-8 with optional BOM. The sample has titles, blank separators, and multiple
schemas: never pass its whole body to a single DictReader. Accept `Surface`/`#`
and `nd offset`/`Δnd`/legacy `?nd` headers (and corresponding vd names). Section
names distinguish lens, asphere, and multiconfiguration tables. Reject unknown
nonempty sections or ambiguous headers with location information. A missing
nd or vd partner is incomplete input, not air. All three empty material fields
represent air for supplied transcription; an OCR adapter must separately mark
uncertain/missing recognition instead of treating it as a confirmed blank.

JSON numbers for optical quantities are rejected in favor of strings so source
precision is explicit. Duplicate surface IDs, coefficient powers, or catalogue
identities are errors; equal nd/vd across different glasses is valid. Read JSON
with duplicate-key detection. A named material is preserved. A typecode absent
from the CSV may pass through to ZMX with a visible host-lookup-unverified status,
since OpticStudio may resolve it from installed catalogues. Do not invent
properties or claim host validation; an actual host lookup failure requires
resolution. A typecode appearing
in multiple catalogues requires a profile/catalogue choice if its properties differ.

### Proposed matching policy

Use absolute differences for eligibility and signed prescription-minus-catalogue
differences for reporting. The gates are strict: close requires dn < 0.0002 and
dv < 0.1; offset requires dn < 0.02 and dv < 2. Apply exclusions first and use
the offset pool only when no eligible close candidate remains.

Keep profiles as a small explicit mapping, with manufacturer order and optional
exclusions. Default order is Ohara, Hoya, Hikari, then others. A Canon profile can
encode the user's Ohara/Hoya preference and Hikari exclusion; Nikon can prefer
Hikari, Ohara, Hoya. These are user-informed study heuristics, not independently
verified procurement facts. Do not infer a profile from a filename.

Draft ranking within the close pool: manufacturer preference, supplied partial
dispersion proximity, normalized nd/vd distance, then name length for otherwise
equivalent variants and lexical identity for deterministic final ties. Proposed
distance is `(dn/0.0002)^2 + (dv/0.1)^2`. This deliberately makes close windows
practical equivalence regions. Do not shorten a glass name to beat a better match.

Within the offset pool, prioritize dispersion before manufacturer preference:
supplied partial dispersion proximity, absolute vd difference, absolute nd
difference, then profile and equivalent-variant tie breakers. The initial policy
is lexicographic rather than a tuned weighted fit. The report must show when a
profile or tie breaker determined the selection. A close tie selects a credible
substitute and records alternatives; it does not stall the whole workflow.

For partial dispersion, compare only the fields actually supplied, using the
source's last stated decimal place to scale residuals. If both PgF and dPgF are
given, retain both residuals but do not treat them as independent statistical
evidence: use the maximum normalized residual as one proximity dimension, with
missing-field count preceding it in ranking. Missing catalogue dispersion must
be identified in the report, not
scored as perfect agreement. Do not derive dPgF from PgF without a verified
normal-line convention. Relative priority of dispersion versus profile and this
precision-based scaling are proposed defaults to validate on labelled examples.

Never replace source nd/vd with catalogue values in the transcription output.
Close choices emit no offsets; offset choices include signed differences, with
display precision recorded separately from the full computed difference. The
historical L-BAL42 row illustrates approximate offsets, not an exact arithmetic
golden test. Source strings remain authoritative and untouched.

### Export and solve policy

CSV keeps the existing sectioned presentation, horizontal coefficients, and
separate even/odd sections when needed. Add offset columns only when an offset
match exists. Preserve configuration labels and source numeric formatting.

ZMX export uses the narrowly supported records in ZMX_SYNTAX.md, Unicode encoding,
normal decimals and scientific notation. Curvature requires computation even
when source radius is an exact decimal: use Decimal working precision of 28 and
emit at most 17 significant digits for derived curvature, checking reciprocal
round-trip error. Do not round copied aspheric coefficients or source distances
to that limit. Keep source units and normalization consistent.

The system needs units, a stop location, aperture type/value, field definition,
and wavelengths. Accept explicit metadata; any proposed study defaults must be
visible in the report. Initial exporter should request missing essentials rather
than silently copying a sample lens's settings. Do not require surface diameters:
leave DIAM/MEMA and fixed aperture records unset. Emit zero-valued FVCY/FVDY
configuration placeholders and neutral system vignetting. Optional GCAT can be
omitted, subject to the host catalogue lookup behavior tested by the user.

Use TCOM for an explicit or unambiguous complementary gap pair, and TOLE for a
constant contiguous axial span in a common coordinate system. Test the proposed
relationship across all configurations and require variation in the independent
gaps when inferring it. One configuration alone proves no relationship. Avoid
ambiguous overlapping inferred solves and cycles; retain explicit THIC values
when several explanations are equally plausible. Explicit patent constraints
take precedence over inferred ones.

Rounding rule: derive uncertainty from source precision metadata (not formatting
zeros added by Excel). A value rounded to step q has a half-step bound; a sum's
bound is the sum of its operands' half-step bounds. Infer a constant only when
the intervals for every configuration share a common value. Prefer an explicit
patent constant; otherwise choose the median nominal sum clamped to that common
interval. Thus 10.58, 10.58, 10.57 may support 10.58, but do not guarantee it
without the operands' precision. Keep original configuration values and report
every dependent-thickness adjustment. If precision is unknown or an explicit
constraint conflicts beyond rounding, keep the data and flag the candidate.
Never serialize THIC and an independent thickness solve for the same cell.

### Original baseline and resolved host questions

The starting baseline was an installed flat package, one installation smoke test,
Ruff checks, and intact samples, without matcher behavior tests. C3 verified GLAS
mode and offset order, omitted apertures, neutral vignetting, asphere mappings,
and configuration/solve behavior in OpticStudio 2023 R1.00; evidence is retained
in ZMX_SYNTAX.md. Unknown flags remain tested template values, not decoded fields.
The supplied catalogue CSV headers define the initial catalogue contract.
Optical-policy changes belong to the user; record material changes here before
implementation. Other OpticStudio versions remain unverified.

## Investigation and regression map

| Boundary | Failure | Detection |
|---|---|---|
| Sectioned CSV -> records | Asphere rows mistaken for glass; lost symbols/zeros | C1 sample parser and invalid-input tests |
| Catalogue -> candidates | Air matched; strict bound becomes inclusive; profile ignored | C2 boundary and profile fixtures |
| Raw -> computed values | Loss of source precision, offset sign reversal | C1/C2 string and Decimal checks |
| Coefficients -> ZMX | Wrong power/index, conic or normalization | C3 independent sag comparisons |
| Configurations -> solves | Rounding invents constraint; wrong endpoint; cycles | C3 equation and round-trip checks |
| GLAS -> OpticStudio | Cached values mistaken for active data; offsets swapped | C3 controlled save/reload experiment |
| Output files -> user | Partial file presented as success, overwritten source | C3 failure/overwrite integration tests |
| Flat package -> install | Docs/samples accidentally packaged, stale src path | Baseline packaging smoke check |

## Checkpoint register

Execution boundary: direct work on `main`, base `ed91cf6`, serial checkpoints
with GPT-5.6 builders and fresh read-only reviewers under execute-task. No push.
On 2026-09-10 the agent service reached its thread limit after initial C2 review.
The user explicitly authorized reusing existing independent agents: the read-only
design agent verifies the C2 correction; the C1 builder owns C3 implementation;
the C2 builder reviews C3 without participating in its implementation. All
review/verification gates remain; only the fresh-thread requirement is relaxed.
C1 owns models.py, inputs.py, export.py (CSV only), tests/test_inputs.py,
tests/test_csv.py, and README input examples. C2 owns matching.py, __main__.py,
matching/CLI tests and matching documentation; changes to C1 interfaces require
focused regression checks. C3 owns exporter/solve code, export/solve tests, CLI
integration and ZMX documentation. The orchestrator owns this register and
shared rule updates. Each checkpoint retains the exact gates below; unavailable
OpticStudio validation keeps C3 open rather than converting it to a Python-only
acceptance gate. No OCR/XLSX/AGF/database work enters these populations.

| ID | Accepted outcome | Depends on | Primary verification | Status |
|---|---|---|---|---|
| C1 | Validated prescription/catalogue records and faithful CSV round trip | Baseline | Sample sections, numeric grammar and diagnostics | complete |
| C2 | Deterministic preference-aware glass choices and report | C1 | Gates, profiles, offsets and unresolved outcomes | complete |
| C3 | Usable ZMX export, configurations and eligible solves | C2 | Sag/equation checks and OpticStudio load/trace | complete |

## Detailed checkpoints

### C1: Input contract and CSV

**Objective.** Establish one validated representation before matching/export.

**Scope and approach.** Add models, JSON/catalogue loaders, the sectioned CSV
adapter and CSV writer. Use standard library code with no Excel dependency.
Add fixtures under `tests/fixtures/` only after recording
their ownership and naming conventions in AGENTS.md.

**Acceptance criteria.** Every sample section is assigned its own schema; numeric
strings and symbols survive a CSV round trip; invalid fields identify section,
row and field. Air, supplied glass and incomplete data are distinct.

**Regression watchlist.** Multi-section headers, OBJ/IMG indexing, duplicate IDs,
unknown coefficients and scientific notation must not become silent coercions.

**Tests and evidence.** Characterize the existing sample first. Test UTF-8/BOM,
legacy headers, omitted versus zero coefficients, duplicate keys and unsupported
units. Run `.\.venv\Scripts\python.exe -m pytest` and both Ruff checks below;
accept only correct records/diagnostics with the installation test still passing.

**Documentation and handoff.** Document the canonical JSON example in README,
accepted headers here, and checkpoint evidence/status in this plan.

**Adversarial review.** Inspect malformed inputs and verify no source file is
rewritten and no unknown field is silently discarded. Review sample diffs.

**Commit gate.** All criteria and checks pass; commit
`feat(input): load structured optical prescriptions`.

### C2: Glass matching

**Objective.** Produce reproducible study substitutes with explicit reasons.

**Scope and approach.** Add pure candidate filtering/ranking functions, a small
profile mapping, result reporting, and the matching CLI path. No ZMX or OCR yet.
Finite population: `matching.py`, `__main__.py`, `tests/test_matching.py`,
`tests/test_cli.py`, CSV rendering integration in `export.py`, and matching
usage/status in README and FEATURES. Preserve C1 source strings and public
loaders; use immutable replacement for matched output, never mutate input.
Adversarial seam correction: paired source offsets require a supplied base
typecode. Without one their meaning is undefined; reject at `inputs.py` and
the public matching boundary rather than erase them on a close choice or call
them air. This finite input-validation correction includes its C1/C2 regressions.
Expose the prescribed default/Canon/Nikon profiles explicitly. Render CSV and
report before writing; protect input/catalogue/metadata paths even with
`--overwrite`. C2's CLI produces CSV/report only; C3 adds an explicit format
selection and ZMX eligibility checks. Matching-policy fixtures encode the user's
labelled manufacturer preferences, not unverifiable historical exact matches.

**Acceptance criteria.** Strict gates, supplied typecodes, exclusions and profile
preferences behave as specified. Missing optional dispersion remains visible.
Offsets have correct sign; unmatched entries preserve their source data. The
same input/catalogue/profile yields the same result regardless of catalogue order.

**Regression watchlist.** Do not make rounded catalogue values appear more
authoritative than source precision or mistake the historical sample for proof
of an exact ranking formula.

**Tests and evidence.** Use synthetic glasses immediately inside/on/outside each
gate; identical specs with variant names; competing manufacturers; missing and
conflicting dispersion; unknown supplied glass. Exercise the real catalogue as
a diagnostic fixture, and obtain labelled policy examples before declaring the
ranking settled. Run the full pytest and Ruff checks; inspect a CLI report.

**Documentation and handoff.** Record accepted ranking choices here and supported
profile behavior in FEATURES; update register and evidence.

**Adversarial review.** Shuffle catalogue order, test empty candidate pools and
partial rows, and inspect the reason for every selected representative fixture.

**Commit gate.** Matching criteria, diagnostics, policy decisions and baseline
checks pass; commit `feat(matching): select study glasses using preference profiles`.

### C3: ZMX export and thickness relationships

**Objective.** Create an OpticStudio-readable study model with correct geometry.

**Scope and approach.** Emit only documented/observed supported records; add
configuration resolution and TCOM/TOLE inference with rounding evidence. Keep
unknown ZMX tokens out of the input contract; no general-purpose ZMX parser.
Finite population: `export.py`, a separate `solves.py` if needed to keep the
geometry serializer readable, `__main__.py`, exporter/solve/CLI tests, and
README/FEATURES/ZMX_SYNTAX. Input-contract corrections required by these direct
consumers remain guarded by the full C1 suite. The parent retains shared plan
ownership and runs actual OpticStudio checks on final generated artifacts.
The selected-catalogue diagnostic in `matching.py` additionally exposes known
`catalogue_dpgf` for GLAS serialization; this additive field avoids a duplicate
catalogue lookup and retains all C2 ranking behavior, guarded by its full tests.

Use explicit first OBJ and last IMG surfaces; fail on absent/misplaced endpoints
instead of inventing geometry or shifting references. Source IDs map by sequence,
not numeric spelling. Support the C1 system choices (f_number aperture, angular
or real-image-height y fields) with explicit wavelengths in micrometres. No new
aperture/field families are necessary for this checkpoint. Base object infinity
uses DISZ INFINITY, configured infinity uses the host-tested THIC value `1e10`
with a visible representation note. No unit conversion or focus extrapolation.

For inference, exact constant sums need no precision assumption when no source
thickness changes. Approximate sums require the recorded interval evidence.
Collapse TCOM/TOLE candidates that imply the identical dependency because all
intermediate terms are invariant, preferring TCOM; they are not two independent
physical explanations. Other competing or overlapping inferred dependencies
remain unresolved. Explicit constraints take precedence and are checked against
every configuration before emission. Report rejected/conflicting candidates and
all nonzero dependent adjustments, without altering the transcription.
An explicit total with all independent terms known may determine a missing
dependent thickness; report that value as derived, not transcribed. Resolve
explicit constraints in increasing dependent-surface order so any supported
chain's downstream diagnostics reflect its actual upstream solved values.
Missing independent terms, duplicate/conflicting definitions, and backward
references must never be guessed. This is direct TCOM/TOLE arithmetic, not a
general expression evaluator or inference from missing data.

**Acceptance criteria.** Every requested configuration resolves; even/odd sag
matches its input expression; offsets affect the intended quantity; source and
solved thickness differences are reported; output overwrites are explicit.
Missing materials/system essentials block ZMX without a success claim.

**Regression watchlist.** Highest polynomial power, normalized radius, surface
renumbering, solve endpoints, INFINITY handling and conflicting THIC records.

**Tests and evidence.** Check even A4/A16/A20 and odd A3/A20 mapping, nonzero conic,
nonunit normalization, plane curvature and finite/infinite object distances.
Compare independently calculated sag at several radii. Test exact, rounding-only,
inconsistent and ambiguous thickness relationships across three configurations;
verify all solved equations and unchanged source records. In OpticStudio,
save controlled nd-only/vd-only offset examples, reopen generated files, inspect
surfaces/configurations, and run a basic ray trace. Record application version and
observed quantities. Pure parser tests alone cannot close this checkpoint.

**Documentation and handoff.** Update ZMX_SYNTAX with confirmed record meanings,
README invocation examples, and this plan's completion evidence or blocked gate.

**Adversarial review.** Inspect the complete export against independent source
values; test missing catalogue, existing target, and write failure. Verify no
sample-specific vignetting/apertures or unsupported flags leak into new designs.

**Commit gate.** All acceptance criteria including OpticStudio validation pass;
commit `feat(export): write ZMX study models and thickness solves`.

## Overall final sweep

Run the supplied-transcription -> matching -> CSV/ZMX command on a complete
labelled example. Reopen the ZMX, check all configurations, and retain the match
report, solve residuals, and OpticStudio version/result as evidence. Require all
regression-map risks to have explicit tests or direct validation. Run pytest,
Ruff lint/format, pip check, and git diff --check. Review docs against actual CLI
behavior, invalid input/error messages, output collision behavior, and the full
diff for scope expansion. Do not claim OCR accuracy or ray-trace performance:
neither has been benchmarked. Unverified host behavior keeps C3 open even when
Python tests pass. Checkpoint tests alone do not replace this end-to-end sweep.

## Delivery record

- Integrated directly on `main`: C1 `47d79bd`, C2 `12ef54c`; C3 is the commit
  containing this completion record (`feat(export): write ZMX study models and
  thickness solves`). No task branches or worktrees were created; no push.
- C1 evidence: 40 tests pass, Ruff lint/format and diff checks pass. Fresh
  independent GPT-5.6 review approved corrected reference resolution, CSV column
  validation, malformed-type diagnostics, and normalization/stop round trips.
  Original sample files are unchanged. Canonical JSON retains system/solve
  metadata that sectioned CSV alone cannot encode.
- C2 evidence: 71 tests pass, Ruff lint/format, pip check and diff checks pass.
  Independent review found the unnamed-offset semantic defect; the correction
  was independently approved after the user-authorized reviewer reuse. CLI
  smoke on the synthetic host study with the supplied catalogue matched both
  materials with zero unresolved outcomes. Default/Canon/Nikon tests encode the
  user's labelled preferences; historical sample offsets are not ranking goldens.
- C3 evidence: all 96 tests pass, Ruff lint/format, pip check and diff checks pass.
  Independent read-only review approved the final exporter and solve corrections,
  including ordered explicit chains, aperture inheritance and base-only derived
  distances. No existing tests were retired. Five generated control files passed
  actual OpticStudio 2023 R1.00 inspection and ray traces across 12 configurations;
  independent source-based sag checks covered all three asphere families.
  Detailed quantities are in ZMX_SYNTAX.md; generated probes remain ignored in
  `output/`. Samples are byte-for-byte unchanged from `ed91cf6`.
- Commands: `.\.venv\Scripts\python.exe -m pytest`,
  `.\.venv\Scripts\python.exe -m ruff check .`,
  `.\.venv\Scripts\python.exe -m ruff format --check .`,
  `.\.venv\Scripts\python.exe -m pip check`, `git diff --check`.
- Remaining limitations: ranking is a study heuristic, not a production-material
  identification claim; further labelled examples can refine it. Runtime reports
  do not imply host validation of arbitrary exports. OCR is deferred; XLSX, AGF,
  and database parsing remain excluded. No acceptance blocker remains.
- Preserve samples byte-for-byte and unrelated user work. Do not use sample
  saved numeric tails as source precision metadata.
- Return for review if the required surface family is unsupported, a proposed
  policy materially changes scope, or host testing contradicts serialization
  assumptions. Record findings; do not silently broaden the checkpoint register.
