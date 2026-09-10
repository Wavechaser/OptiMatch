# OpticsPrescriptionMatcher

Python tools for producing credible optical study prescriptions from patent
data, using best-effort manufacturer preferences for glass selection. Results
are study substitutes, not representations of production samples.

The repository currently contains project scaffolding and reference data.
Matching, OCR, and ZMX export are not implemented yet. The intended workflow is
supplied transcription or OCR, structured prescription, glass matching, then
CSV and ZMX export. Catalogue input is CSV exported from the user's maintained
Excel workbook. XLSX parsing, AGF parsing, and SQLite/database storage are out
of scope. OCR can be added independently later.

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
There are no runtime dependencies yet; development tools are declared in
`pyproject.toml`. Dependencies are not locked at this stage.

## Layout and reference data

- `optics_prescription_matcher/`: Python package (flat layout).
- `optics_prescription_matcher.egg-info/`: ignored installation metadata.
- `tests/`: behavior tests; currently an installation smoke test.
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
  policy, exporter design, and pending implementation checkpoints.
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
