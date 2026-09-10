# Project rules

## Scope

Build a small Python tool that produces credible optical study prescriptions,
guided by best-effort manufacturer preferences. Outputs are study substitutes,
not claims about production lenses. Matching, transcription/OCR, and ZMX export
are separate steps; OCR can be added later. The catalogue input is a CSV export
from the user's maintained Excel workbook. XLSX parsing, AGF parsing, and
SQLite/database storage are out of scope.

## Structure

- `optics_prescription_matcher/`: importable Python code; snake_case modules.
- `optics_prescription_matcher.egg-info/`: generated editable-install metadata
  at the project root, ignored by Git.
- `tests/`: pytest tests named `test_*.py`, organized by behavior as code grows.
- `samples/`: original CSV/ZMX files and `SAMPLE_INSTRUCTIONS.md`;
  preserve their names, encoding, and contents. The sample instructions are a
  historical workflow reference, not a complete executable specification.
- `docs/`: project documentation, named in uppercase snake case. `FEATURES.md`
  describes desired behavior; `IMPLEMENTATION_PLAN.md` defines engineering
  decisions and checkpoint status; `ZMX_SYNTAX.md` records known serialization
  details with evidence and uncertainty. Keep these roles distinct and update
  each with the behavior it governs. README is the entry point.
- `.github/workflows/`: lightweight automated checks only.
- `output/`: ignored generated prescriptions and diagnostic artifacts. Remove
  only your own temporary artifacts; never clean user inputs automatically.
- `.venv/`: local environment, never committed.
- Keep project configuration at the root. Document new directory conventions
  here before adding directories; avoid empty scaffolding and duplicate rules.

## Development

Use native PowerShell and `.venv/Scripts/python.exe` on Windows. Dependencies
and tool settings live in `pyproject.toml`; do not add a second requirements list.
Keep runtime dependencies minimal and add optional OCR/Office dependencies only
when their features are implemented. Use pytest and Ruff; see README for commands.

Read the relevant code and samples before editing. Make surgical changes and
preserve unrelated user work. Verify behavior with focused tests, then run the
project checks. Before completion, review for requirement drift, numerical or
encoding mistakes, and unnecessary complexity. Delegate only bounded independent
work when requested; no persistent agent infrastructure is required.

## Optical data

Preserve source numeric strings and significant figures separately from computed
values. Close-match selection may prioritize a chosen manufacturer profile over
tiny numerical differences; default catalogue preference is Ohara, then Hoya,
then Hikari. Distinguish preferences from exclusions. Retain partial dispersion
when supplied and record selection reasons. Offsets mean prescription minus
catalogue; missing data must not silently become zero or air.

Consult `docs/ZMX_SYNTAX.md` for serialization details and their evidence.
Do not guess undocumented fields or promote observations into verified contracts.

## Git

Use repository `.gitattributes` for line endings. Preserve UTF-16 ZMX bytes;
never run generic text normalization over reference files. Keep credentials,
environments, caches, and generated outputs untracked. Do not change global Git
configuration, install hooks, commit, or push unless requested.

Commit titles use `<category>(<optional-scope>): <imperative summary>`; omit the
parenthesized scope when unnecessary. Categories: `feat`, `fix`, `refactor`,
`docs`, `test`, `build`, `ci`, `chore`. Use a short imperative summary, such as
`docs(zmx): document extended asphere records`. Keep each commit coherent and
run the relevant checks before committing. A commit request does not authorize
a push.
