# Known ZMX syntax

This is a working reference for the planned sequential study-model exporter,
not a complete ZMX specification. No exporter or OpticStudio verification is
implemented yet. Record shapes below come from the supplied samples; optical
meanings come from the cited help pages or the user's experiments. Unknown
fields must remain unknown until a controlled edit/save comparison resolves them.

## Evidence

- [Canon EF-M sample](../samples/EF-M%2022mm%20F2%20STM.ZMX): standard surfaces,
  even aspheres, a glass offset, three focus configurations, and the user's
  all-zero ordinary catalogue-glass test on surface 12.
- [Sigma sample](../samples/14-24mm%20F2.8%20DG%20DN%20Art.ZMX): extended even
  and odd aspheres, two glass offsets, three configurations, and a compensator
  thickness solve on surface 14.
- User experiments: accepted catalogue typecodes still resolve when their
  ordinary numeric payload is zero; omitting `GCAT` permits catalogue discovery
  on their installation; ordinary shorter decimal strings load successfully.
  These are observations on that installation, not cross-version guarantees.
- A 2020 response on the [Zemax community forum](https://community.zemax.com/zpl-13/zmx-file-specification-106)
  says the file-format documentation left the Help System around 2005. Current
  feature documentation does not establish a complete serialization contract.

## File and system records

Samples are UTF-16 LE text with a BOM. Preserve reference bytes; write new files
with that encoding and ordinary decimal/scientific notation using a decimal
point. Long floating-point tails in saved files are not required input precision.
Do not confuse character encoding with the precision of numerical values.

| Record | Observed role / limits |
| --- | --- |
| `VERS ...` | File version metadata; minimum required/version-compatible header remains to be tested. |
| `MODE SEQ` | Sequential optical system. |
| `NAME ...` | Model title. |
| `UNIT MM X W X CM MR CPMM` | Sample units record; `MM` supplies lens units. Remaining tokens are not decoded here. |
| `FNUM 2 1` | EF-M aperture setting. Flag meanings and alternative aperture encodings need a controlled test. |
| `GCAT OHARA_2021-04` | Named catalogue list; optional under the user's tested automatic discovery behavior. |
| `FTYP ...`, `XFLN ...`, `YFLN ...`, `FWGN ...` | Field definition, coordinates, and weights; do not copy field-type flags without confirming their meaning. |
| `WAVM index wavelength weight` | Wavelength records; sample values such as `0.587562` are in micrometres. Active count/primary-wavelength selection must also be verified. |
| `VDXN`, `VDYN`, `VCXN`, `VCYN` | System-level vignetting arrays. Initialize to zero when emitting unvignetted study models. |

Never inherit sample-specific ray aiming, pupil settings, apertures, fields, or
wavelength weights merely because they appear in a template. A minimal usable
system header must be established by loading and saving a controlled model.

## Surface blocks

`SURF n` begins a surface block. Surface 0 is the object; the last surface is the
image. The following indented records belong to that surface until the next
block. A material describes the medium after the surface.

| Record | Meaning / exporter intent |
| --- | --- |
| `TYPE STANDARD` | Standard surface. |
| `CURV c ...` | Curvature `c = 1/R`, preserving sign; zero denotes a plane. Additional fields are not decoded here. |
| `DISZ t` | Thickness to the next surface in lens units. |
| `STOP` | Aperture-stop surface marker. |
| `CONI k` | Conic constant, separate from polynomial asphere coefficients. |
| `GLAS ...` | Material record; see below. Omit for explicitly identified air, never for an unresolved material. |
| `DIAM ...` | Clear semi-diameter / semi-diameter record; omit fixed values in initial export. |
| `MEMA ...` | Mechanical semi-diameter record; omit fixed values in initial export. |

The aperture quantities are radial **semi-diameters**, not full diameters.
OpticStudio documents automatic clear and mechanical semi-diameter calculation;
the exact serialized omission behavior still needs a load test.
[Clear semi-diameter](https://ansyshelp.ansys.com/public/Views/Secured/Zemax/v251/en/OpticStudio_User_Guide/OpticStudio_Help/topics/Clear_Semi_Diameter_or_Semi_Diameter.html),
[mechanical semi-diameter](https://ansyshelp.ansys.com/public/Views/Secured/Zemax/v242/en/OpticStudio_User_Guide/OpticStudio_Help/topics/Mechanical_Semi_Diameter.html).
Do not copy fixed aperture records such as `FLAP` from the samples either.

## Glass records

Observed shape, using symbolic names only where supported:

```text
GLAS typecode mode u1 nd vd dPgF u2 u3 u4 delta_nd delta_vd
```

Ordinary catalogue records use mode `0`; offset examples use mode `4`.
`u1` through `u4` are not decoded. Do not assume the `nd`, `vd`, and `dPgF`
slots override catalogue dispersion when the typecode resolves. The user's
test with `GLAS S-LAH58 0 0 0 0 0 0 0 0 0 0` produced unchanged results.
Populate known sensible catalogue numbers where available, but do not invent
unknown flags or use those numbers as a substitute for successful catalogue lookup.

Observed offset tails, shortened for readability:

| Sample / surface | Typecode | Mode | Penultimate | Last |
| --- | --- | --- | --- | --- |
| EF-M / 8 | S-TIH11 | 4 | 0 | 0.1 |
| Sigma / 5 | M-PCD51 | 4 | 0.0007 | -0.05 |
| Sigma / 32 | M-FCD500 | 4 | 0.0002 | 0.04 |

The working interpretation is **delta_nd then delta_vd**, both prescription minus
catalogue. This agrees with the user's identification of the EF-M's `0.1` as a
Vd offset and the scales of both Sigma examples. The user's initial verbal
description reversed those positions; resolve that discrepancy with independent
nd-only and vd-only edit/save tests before claiming exporter correctness.
Also verify mode `4` explicitly rather than assuming the tail alone enables it.

## Aspheres

Preserve coefficient powers explicitly in the input. Missing lower-order terms
must not shift higher-order terms into earlier slots.

| Surface type | Serialized coefficients | Sample evidence |
| --- | --- | --- |
| `EVENASPH` | `PARM i A_(2i)`, `i=1..8`: A2 through A16 | EF-M surfaces 14 and 15; `PARM 1 0` precedes nonzero A4. |
| `XASPHERE` | `XDAT 1 N`, `XDAT 2 r0`, then `XDAT (i+2) alpha_(2i)` | Sigma surface 1 has N=10, r0=1, then A2 through A20. |
| `XOSPHERE` | `XDAT 1 N`, `XDAT 2 r0`, then `XDAT (p+2) alpha_p` | Sigma surfaces 5 and 6 have N=20, r0=1, then A1 through A20. |

The literal extended odd identifier is `XOSPHERE`, not `XOASPHERE`. Extended odd
includes consecutive powers, both odd and even. For extended even, N counts
even terms (maximum power 2N); for extended odd, N is also the maximum power.
The sample extended data records include an opaque solve/metadata tail:

```text
XDAT index value 0 0 1 0 0 ""
```

This is the observed numeric tail written with shorter decimals; its flags and
whether they can be omitted have not been established. Ansys's current help
labels the corresponding extra-data parameters starting at 13, whereas these
files serialize them starting at `XDAT 1`.

Extended polynomials use `rho = r/r0`. For an input term `A_p * r^p`, emit
`alpha_p = A_p * r0^p`; choosing r0=1 preserves numerical coefficient values
when lens units agree. Unit conversion must happen before this mapping.
The base conic remains controlled by curvature and `CONI`.
[Extended Asphere](https://ansyshelp.ansys.com/public/Views/Secured/Zemax/v261/en/OpticStudio_User_Guide/OpticStudio_Help/topics/Extended_Asphere.html),
[Extended Odd Asphere](https://ansyshelp.ansys.com/public/Views/Secured/Zemax/v251/en/OpticStudio_User_Guide/OpticStudio_Help/topics/Extended_Odd_Asphere.html).

## Thickness solves

For the supported case of a solve placed on surface j, with reference surface
i preceding j in the same axial coordinate system:

| Record | Constraint | Evidence |
| --- | --- | --- |
| `TCOM i total` | `t_i + t_j = total` | Sigma surface 14 contains `TCOM 11 10.58`; user explanation. |
| `TOLE i total` | `t_i + t_(i+1) + ... + t_j = total` | User-supplied syntax; no sample record yet. |

The [official thickness-solve help](https://ansyshelp.ansys.com/public/Views/Secured/Zemax/v251/en/OpticStudio_User_Guide/OpticStudio_Help/topics/Thickness_Solves.html)
supports the compensator/position distinction, but is not a keyword syntax
specification. On surface 14, `TOLE 11 10.58` would therefore include thicknesses
11, 12, 13, and 14, unlike the two-term `TCOM` constraint.

Inference eligibility and handling of rounded sums belong in
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). Never put an independently
driven `THIC` value and a thickness solve on the same dependent surface.

## Multiple configurations

Both samples have `MNUM 3 1`, consistent with three configurations and active
configuration 1. Verify the second field by changing the active configuration
and saving. Configuration records share this observed shape:

```text
THIC surface configuration value 0 0 0 1 1 1 0 0 "" 0
APER 0       configuration value 0 0 0 1 1 1 0 0 "" 0
FVCY field   configuration value 0 0 0 1 1 1 0 0 "" 0
FVDY field   configuration value 0 0 0 1 1 1 0 0 "" 0
```

Configuration numbers are 1-based in the samples. `THIC` supplies thicknesses;
`APER` supplies configuration aperture values under the system's aperture
definition, so its value must not universally be interpreted as a diameter or
f-number. `FVCY` and `FVDY` supply y-field vignetting compression and decenter.
Their long trailing payloads are observed metadata, not decoded flags.

Create `FVCY`/`FVDY` entries with numeric zero for applicable field/configuration
slots: this is the proposed representation of the user's requested empty fields,
pending a load test. Do not inherit sample vignetting values. `THIC` can come
from supplied distances or documented calculations; do not derive a focus
distance from insufficient patent information. The samples use `1e10` for an
effectively infinite object distance; treatment of true infinity needs testing.

## Targeted verification before exporter acceptance

1. Establish a minimal system header, object/image blocks, field conventions,
   wavelength selection, aperture settings, and omitted automatic diameters in
   the target OpticStudio version.
2. Load ordinary catalogue glasses with and without `GCAT`; confirm unresolved
   typecodes are reported. Independently test nd and vd offsets and mode `4`.
3. Verify coefficient order, conic, and sag at several radii for all three
   asphere types, including an extended normalization radius other than 1.
4. Load/save `TCOM` and `TOLE`, then inspect solved thicknesses in every
   configuration; confirm zero vignetting and aperture interpretation.
5. Compare the loaded prescription and basic ray trace with a controlled
   reference. A text round trip establishes only serialization consistency.

Record target version and results here when performed. Keep opaque fields and
untested omission behavior explicitly unresolved until evidence closes them.
