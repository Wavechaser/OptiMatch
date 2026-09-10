# Known ZMX syntax

This is a working reference for the implemented sequential study-model exporter,
not a complete ZMX specification. The supported subset was tested in OpticStudio
2023 R1.00; compatibility with other versions is unverified.
Record shapes below come from the supplied samples; optical
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
| `VERS 221221 730 20120530 20120530` | Tested header on 2023 R1.00; not a cross-version compatibility guarantee. |
| `MODE SEQ` | Sequential optical system. |
| `NAME ...` | Model title. |
| `UNIT MM X W X CM MR CPMM` | Lens unit tokens `MM`, `CM`, `IN`, `METER` confirmed by API saves in 2023 R1.00. Remaining tokens are not decoded here. |
| `FNUM value 1` | Confirmed ParaxialWorkingFNum aperture type in 2023 R1.00. Other flags/types remain separate contracts. |
| `ENPD value` | Confirmed EntrancePupilDiameter aperture definition in lens units, 2023 R1.00. |
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
omitting these records was verified in the 2023 R1.00 minimal-header probe below.
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

The confirmed order is **delta_nd then delta_vd**, both prescription minus
catalogue. On 2026-09-10, OpticStudio 2023 R1.00 Premium standalone API read
EF-M surface 8 as MaterialOffset, NdOffset=0, VdOffset=0.1. Independent API
edits saved nd-only=0.001 as mode 4 with tail `0.001 0`, and vd-only=0.2 as
mode 4 with tail `0 0.20000000000000001`. This resolves the initial reversed
verbal description. Temporary evidence: `output/probe_zos.ps1`, `nd_only.zmx`,
and `vd_only.zmx` (ignored local artifacts; summary retained here).

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
| `TOLE i total` | `t_i + t_(i+1) + ... + t_j = total` | Independently saved through OpticStudio Position solve, 2026-09-10. |

The [official thickness-solve help](https://ansyshelp.ansys.com/public/Views/Secured/Zemax/v251/en/OpticStudio_User_Guide/OpticStudio_Help/topics/Thickness_Solves.html)
supports the compensator/position distinction, but is not a keyword syntax
specification. On surface 14, `TOLE 11 10.58` would therefore include thicknesses
11, 12, 13, and 14, unlike the two-term `TCOM` constraint.

OpticStudio 2023 R1.00 verification: Sigma TCOM configurations produced
`2.1617 + 8.4183`, `0.3791 + 10.2009`, and `1 + 9.58`, all totaling 10.58.
Setting Position with FromSurface=11 and Length=10.58 on surface 14 saved
`TOLE 11 10.58` and yielded a contiguous thickness sum of 10.58. The source
files were not saved over; the modified model is local `output/position.zmx`.

Inference eligibility and handling of rounded sums belong in
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). Never put an independently
driven `THIC` value and a thickness solve on the same dependent surface.

## Multiple configurations

Both samples have `MNUM 3 1`: three configurations and active configuration 1.
The controlled API save after selecting configuration 3 produced `MNUM 3 3`,
confirming the second field. Configuration records share this observed shape:

```text
THIC surface configuration value 0 0 0 1 1 1 0 0 "" 0
APER 0       configuration value 0 0 0 1 1 1 0 0 "" 0
FVCY field   configuration value 0 0 0 1 1 1 0 0 "" 0
FVDY field   configuration value 0 0 0 1 1 1 0 0 "" 0
```

Records must be **operand-major**: all configurations for one THIC surface (or
APER/FVCY/FVDY operand) are contiguous before moving to the next operand.
A generated configuration-major file loaded, but configurations 2 and 3 read
back zero thickness/aperture values. Grouping by operand restored all values in
the same 2023 R1.00 host check. Record presence alone does not establish a valid
multiconfiguration model.

Configuration numbers are 1-based in the samples. `THIC` supplies thicknesses;
`APER` supplies configuration aperture values under the system's aperture
definition, so its value must not universally be interpreted as a diameter or
f-number. `FVCY` and `FVDY` supply y-field vignetting compression and decenter.
Their long trailing payloads are observed metadata, not decoded flags.

Create `FVCY`/`FVDY` entries with numeric zero for applicable field/configuration
slots: this representation of the user's requested empty fields was verified
by the 2023 R1.00 minimal-header probe. Do not inherit sample vignetting values. `THIC` can come
from supplied distances or documented calculations; do not derive a focus
distance from insufficient patent information. The samples use `1e10` for an
effectively infinite object distance. Use `1e10` in an object-distance THIC
operand, while a non-configured object DISZ may use `INFINITY`; disclose this
representation in the export report without changing the source string.

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

### Minimal-header host probe (2026-09-10)

`output/minimal.zmx` loaded in OpticStudio 2023 R1.00 through the standalone API:
four standard surfaces, object at INFINITY, S-BSL7 singlet, FNUM 4 1, no GCAT,
no DIAM/MEMA/FLAP, two angular y fields and three wavelengths. The host resolved
S-BSL7 from OHARA_2021-04.AGF, computed semi-diameter 6.14799151045575, retained
two Angle fields and three wavelengths, and retained numeric-zero FVCY/FVDY.
Saved `FTYP 0 0 2 3 0 0 0 2` denotes this tested field/wavelength population;
PWAV 2 selects the primary wavelength. A real ray at normalized on-axis pupil
y=0.7 reached image surface 3 with error=0, vignette=0, intensity=1 and image
y=0.0287049567370472. This validates the prototype record subset and omission
behavior on this installation, not yet the implementation's end-to-end output.

Independent API edits in `output/probe_header.ps1` confirmed the first FTYP
integer: Angle=0, ObjectHeight=1, ParaxialImageHeight=2, RealImageHeight=3.
The saved shape was `FTYP type 0 field_count wavelength_count 0 0 0 2`.
TheodoliteAngle also changes another flag and is outside the initial exporter.
Lens-unit and entrance-pupil records in the table above were saved in the same
controlled session; all writes were ignored output copies.

A second control (`output/asphere_probe.zmx`) confirmed sag at radius 1 for
EVENASPH A4/A16, XASPHERE A4/A20 at normalization radius 2, and XOSPHERE A3 at
normalization radius 2: respectively 0.010010800128025707,
-0.009990800128025605, and 0.00001. These agree with independent conic-plus-power
evaluation. Direct `THIC 0 1 INFINITY ...` loaded but produced zero automatic
semi-diameters and a degenerate zero-height pupil ray in configuration 1.
Changing only that operand to `1e10` restored a 6.114796774069259 semi-diameter
and image-ray y=0.027599647107499, error=0. The API reports the object as Infinity
for that large-number convention. Therefore use the tested numeric configuration
convention; textual INFINITY in THIC is not treated as a supported record value.

### Implementation smoke, 2026-09-10

The generated `output/host_study_render.zmx` passed a source-based standalone
API oracle (`output/check_host_study.py`): seven surfaces, all three asphere
formats, three configurations, an inferred Compensator, and a supplied glass
offset. Sag matched independently evaluated source expressions at radii 0.5,
1, and 2 (largest measured difference 0 in the double-precision comparison).
Gap pairs were 2+8, 3+7, and 4+6; nd/vd offsets read back 0.001/0.2.
Both angular fields, neutral vignetting, f-number 8, all three wavelength values
and primary index 2 survived. Real on-axis pupil-y 0.7 rays at wavelength 1 had
error/vignette codes 0 in all configurations, with image-y values
-0.25909897402885784, -0.21060188546775183, and -0.15933267714301858.
These are structural/sag/trace checks, not optimization or performance claims.
Independent C3 review and the additional controls below completed successfully.

An explicit rounded-span control (`output/host_span_render.zmx`) read back as a
Position solve from surface 2 through 4, total 10.58. The three loaded triples
were [2, 3, 5.58], [3, 4, 3.58], and [4, 2, 4.58]. In the last configuration,
source thickness 4.57 remained in the exported CSV and the report recorded a
+0.01 dependent adjustment. All three host sums were 10.58, with zero ray-error
and vignette codes. This checks actual TOLE endpoint semantics and rounded
export adjustment rather than only its serialized text.

### Final configuration and solve controls, 2026-09-10

Three additional generated files passed inspection and real pupil-y 0.7 ray
traces (zero error and vignette codes in every configuration):

- `output/host_partial_aperture_render.zmx`: a base f-number of 8 with only the
  first configuration overriding it to 4 loaded as [4, 8]. Once APER is used,
  every configuration needs its value; an omitted override uses the base value.
- `output/host_base_derived_render.zmx`: an explicit TCOM with independent gap 2
  and total 10 derived dependent DISZ 8 without any configuration table. The host
  read Compensator and thickness 8; object DISZ INFINITY remained infinite.
- `output/host_chain_render.zmx`: two forward explicit TCOM constraints, supplied
  in reverse order, loaded correctly in all three configurations. For the last,
  source [4, 6.57, 3.43] became [4, 6.58, 3.42], satisfying totals 10.58 and 10.
  The report retained originals and effective adjustments +0.01 and -0.01.

The final five-file suite covers 12 configurations. Original samples were never
overwritten. Host scripts and generated files are ignored local evidence, not
runtime dependencies; the committed tests retain regressions for these seams.
This validates the supported exporter subset, not unknown ZMX flags, arbitrary
installed-catalogue availability, or production optical performance.
