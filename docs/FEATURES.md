# Desired features

Status: validated JSON/CSV inputs, deterministic glass matching, CSV/ZMX output,
the revised catalogue, all manufacturer profiles, molding-aware selection,
partial-dispersion derivation, and model-glass fallback are implemented. OCR
remains planned.
Historical engineering decisions and completed delivery checkpoints are archived in
[IMPLEMENTATION_PLAN.md](obsolete/IMPLEMENTATION_PLAN.md); known ZMX records and their
evidence belong in [ZMX_SYNTAX.md](ZMX_SYNTAX.md).

## Purpose

Produce a credible, close-enough optical prescription for study from patent
data. Choose practical glass substitutes using available optical properties and
best-effort knowledge of manufacturer behavior. A result is not a claim about
the materials or tolerances of production lenses.

## Prescription inputs

- Accept supplied structured prescriptions, whether transcribed manually or
  obtained through OCR. Preserve surface order, source decimal strings,
  significant figures, scientific notation, and variable-distance placeholders.
- Retain supplied partial dispersion, including its alternative notation, to
  support matching even when it is omitted from the final prescription table.
- Distinguish confirmed airspaces from unknown material data. Missing or unreadable
  information must not silently become air, zero, or a fabricated coefficient.
- Use a CSV export of the user's maintained Excel glass lookup table.
- Accept the canonical catalogue columns `Manufacturer`, `Typecode`, `nd`, `vd`,
  `PgF`, and `dPgF`, plus optional `ne`, `ve`, and `PrecisionMolding`; retain
  historical partial-dispersion header aliases for existing six-column exports.
- Make missing information and study assumptions visible. Request necessary
  information when a usable model cannot otherwise be produced.

## Glass selection

- Preserve explicitly supplied material typecodes; report any that cannot be
  resolved for export.
- Normalize whitespace in Ohara typecodes for catalogue identity and supplied-name
  lookup, while preserving non-Ohara internal spaces. Exact supplied-name matches
  take precedence, and whitespace fallback never assigns an arbitrary name to
  Ohara.
- Consider close candidates with absolute differences strictly below `0.0002`
  in nd and `0.1` in Vd. Do not apply offsets to close substitutes.
- Default to Ohara, then Hoya, then Hikari, then other catalogues. A selected
  manufacturer profile may change priorities or explicitly exclude catalogues;
  a preference alone does not exclude alternatives.
- Offer explicit Canon, Nikon, Sony, Sigma, and Fujifilm study profiles. Apply
  each profile's exclusions before ranking, but never infer a profile from a
  filename or override an explicitly supplied material.
- Within the close range, allow profile preferences to outweigh insignificant
  numerical differences. Use supplied partial dispersion to distinguish
  plausible candidates. Prefer shorter typecodes for otherwise equivalent
  variants, without discarding meaningful differences in optical properties.
- When no close candidate exists, consider offset candidates with absolute
  differences strictly below `0.02` in nd and `2` in Vd. Favor dispersion
  proximity when selecting a suitable base glass.
- If either boundary of an element is aspheric, first prefer precision-molding
  candidates within the bounded window `|Δnd| < 0.005` and `|ΔVd| < 0.5`.
  Fall back to ordinary matching when that pool is empty; molding suitability
  is a preference, not a material-class exclusion.
- When PgF is supplied without dPgF, derive dPgF from the documented F2–K7
  normal line so partial dispersion remains useful for selection and export.
  Preserve the source strings and report supplied versus derived provenance;
  never substitute zero for missing matching data.
- Calculate offsets as prescription minus catalogue. Display precision should
  reflect the supplied data rather than imply extra measurement accuracy.
- If no suitable catalogue candidate exists, retain the original nd/Vd as an
  explicit model glass rather than inventing a typecode, offset, zero, or air.
  Report the fallback distinctly from a named catalogue match.
- Record the chosen profile, selection reason, and any material ambiguity so the
  user can assess the substitute. Prescription material cells contain typecodes
  only, without manufacturer names.

## Study outputs

- Provide the user's five-wavelength study setup in the sample order, with the
  e line primary, plus selectable 1-type, M43, APS-C, full-frame, 44x33, and
  fisheye field presets. Fisheye uses angle fields; preserve explicit settings
  rather than silently overriding them.
- Default to radial real-image-height y fields, unit field weights, paraxial ray
  aiming and the stop as global coordinate reference. Use paraxial working
  f-number, leaving a warned zero placeholder when the aperture is unspecified.

- Produce a CSV containing surface numbers, radii, thicknesses, materials, nd,
  and Vd. Represent planes with radius `0`; leave confirmed air material cells
  blank. Include offset columns only when offset matches are present.
- Include asphere and configuration tables below the base prescription. Preserve
  conic constants, distinguish even and odd terms, and list coefficients across
  columns using their actual polynomial orders.
- Produce a ZMX study model with matched materials and applicable offsets,
  surface geometry, stop, and the units, fields, wavelengths, and aperture
  definition needed to study it.
- Export a numerically valid no-match as fixed model glass using its source
  nd/Vd and supplied, PgF-derived, or default-zero dPgF. Keep its CSV material
  cell blank and report it separately from named matches; invalid optical data
  remains an error.
- Support ordinary and extended even/odd aspheres. Select extended forms only
  for nonzero overflow terms; ignore zero padding and export rows with only even
  nonzero powers as even, retaining original input tables.
- Retain supplied configurations and calculate configuration distances when the
  patent provides enough information to determine them.
- Keep ZMX multi-configuration tables compact: title, varying independent
  thicknesses, optional apertures, and paired off-axis vignetting operands;
  fixed and solve-controlled thicknesses stay in the base prescription.
- Insert an export-only rear dummy when an eligible accepted rear solve needs
  back-focus decoupling, retaining source geometry/solve data and reporting the
  transformed export geometry, solve, and warnings.
- Create eligible thickness compensator or position solves for stated or clearly
  supported constant-distance relationships. Accommodate source rounding where
  justified, disclose adjusted distances, and preserve explicit configuration
  data when a relationship is uncertain.
- Retain multiple independent thickness relationships without treating longer
  spans that merely combine them as competing explanations.
- Allow explicit export controls for compensators and position spans, including
  configuration-varying totals. Offer normal or reversed position placement
  without searching again in reverse, retaining the same covered thicknesses.
- Allow zero-initialized, paired OIS translation controls with same-configuration
  cancelling pickups to their actual control rows. Report overrides, conflicts,
  direction fallbacks, and source/export mappings rather than guessing placement.
- Initialize y-field vignetting quantities and offsets to zero. Leave per-surface
  clear and mechanical apertures unset rather than copy them from reference
  lenses.

## Deferred inputs

OCR remains required for PDFs and images, including Japanese-only filings and
historical scanned patents. Available machine-readable patent text may reduce
OCR work, but must not become a prerequisite. Uncertain numerical transcription
must be identifiable for review. OCR implementation is deferred until the
supplied-prescription matching and export workflow is usable.

Direct XLSX reading, AGF catalogue parsing, and SQLite/database storage are
outside the current scope. The catalogue enters the tool as CSV.

Matching on the e-line `ne`/`ve` pair is deferred. The revised catalogue may
retain those columns for later use, but this delivery neither ranks by them nor
converts between d-line and e-line properties.
