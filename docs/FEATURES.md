# Desired features

Status: the project currently provides a Python scaffold only. The matching,
prescription output, and OCR capabilities below are planned, not implemented.
Engineering decisions and delivery checkpoints belong in
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md); known ZMX records and their
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
- Make missing information and study assumptions visible. Request necessary
  information when a usable model cannot otherwise be produced.

## Glass selection

- Preserve explicitly supplied material typecodes; report any that cannot be
  resolved for export.
- Consider close candidates with absolute differences strictly below `0.0002`
  in nd and `0.1` in Vd. Do not apply offsets to close substitutes.
- Default to Ohara, then Hoya, then Hikari, then other catalogues. A selected
  manufacturer profile may change priorities or explicitly exclude catalogues;
  a preference alone does not exclude alternatives.
- Within the close range, allow profile preferences to outweigh insignificant
  numerical differences. Use supplied partial dispersion to distinguish
  plausible candidates. Prefer shorter typecodes for otherwise equivalent
  variants, without discarding meaningful differences in optical properties.
- When no close candidate exists, consider offset candidates with absolute
  differences strictly below `0.02` in nd and `2` in Vd. Favor dispersion
  proximity when selecting a suitable base glass.
- Calculate offsets as prescription minus catalogue. Display precision should
  reflect the supplied data rather than imply extra measurement accuracy.
- If no suitable candidate exists, retain the original nd/Vd with no invented
  typecode or offsets. Make unresolved materials visible before ZMX export.
- Record the chosen profile, selection reason, and any material ambiguity so the
  user can assess the substitute. Prescription material cells contain typecodes
  only, without manufacturer names.

## Study outputs

- Produce a CSV containing surface numbers, radii, thicknesses, materials, nd,
  and Vd. Represent planes with radius `0`; leave confirmed air material cells
  blank. Include offset columns only when offset matches are present.
- Include asphere and configuration tables below the base prescription. Preserve
  conic constants, distinguish even and odd terms, and list coefficients across
  columns using their actual polynomial orders.
- Produce a ZMX study model with matched materials and applicable offsets,
  surface geometry, stop, and the units, fields, wavelengths, and aperture
  definition needed to study it.
- Support ordinary even, extended even, and extended odd aspheres, including
  prescriptions exceeding the ordinary even coefficient capacity.
- Retain supplied configurations and calculate configuration distances when the
  patent provides enough information to determine them.
- Create eligible thickness compensator or position solves for stated or clearly
  supported constant-distance relationships. Accommodate source rounding where
  justified, disclose adjusted distances, and preserve explicit configuration
  data when a relationship is uncertain.
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
