import json
from pathlib import Path

import pytest

from optics_prescription_matcher.inputs import (
    InputError,
    decimal_value,
    load_catalog_csv,
    load_prescription_json,
    load_sectioned_csv,
    prescription_from_dict,
)

ROOT = Path(__file__).parents[1]


def minimal(**changes):
    data = {
        "schema_version": 1,
        "title": "Study lens",
        "units": "mm",
        "declared_symbols": ["d0"],
        "surfaces": [
            {"id": "OBJ", "radius": "infinity", "thickness": "d0"},
            {
                "id": "1",
                "radius": "10.00",
                "thickness": "1.0",
                "nd": "1.50",
                "vd": "60",
            },
        ],
    }
    data.update(changes)
    return data


def test_canonical_json_preserves_strings_and_explicit_metadata(tmp_path):
    data = minimal(
        aspheres=[
            {
                "surface_id": "1",
                "family": "odd",
                "conic": "0",
                "coefficients": {"1": "0", "4": "-1.00E-5"},
            }
        ],
        configurations=[
            {"name": "far", "thicknesses": {"d0": "infinity"}, "aperture": "2.8"}
        ],
        system={
            "stop_surface": "1",
            "aperture_type": "f_number",
            "aperture_value": "2.8",
            "field_type": "angle",
            "fields": ["0", "12.5"],
            "wavelengths": [{"value": "0.5875618", "weight": "1.0", "primary": True}],
        },
        solves=[
            {
                "kind": "constant_span",
                "surface_id": "1",
                "reference_surface_id": "OBJ",
                "total": "12.00",
            }
        ],
        rounding_steps={"/surfaces/1/thickness": "0.1"},
    )
    path = tmp_path / "input.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    result = load_prescription_json(path)
    assert result.surfaces[1].radius == "10.00"
    assert result.aspheres[0].coefficients[4] == "-1.00E-5"
    assert result.system.wavelengths[0].primary is True
    assert result.solves[0].total == "12.00"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"schema_version": 1.0}, "schema_version"),
        ({"units": "yards"}, "units"),
        ({"mystery": "x"}, "unknown field"),
        (
            {"surfaces": [{"id": "1", "radius": "0", "thickness": "1", "nd": "1.5"}]},
            "nd and vd",
        ),
        ({"surfaces": [{"id": "1", "radius": "0", "thickness": "flat"}]}, "thickness"),
        ({"aspheres": None}, "aspheres: must be an array"),
        ({"title": "bad\nname"}, "control characters"),
    ],
)
def test_canonical_rejects_invalid_data_with_context(change, message):
    with pytest.raises(InputError, match=message):
        prescription_from_dict(minimal(**change))


def test_json_rejects_duplicate_keys(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    with pytest.raises(InputError, match="duplicate key"):
        load_prescription_json(path)


def test_catalogue_loads_sample_and_preserves_precision():
    records = load_catalog_csv(ROOT / "samples" / "combined_glass_catalog.csv")
    assert records[0].typecode == "E-FDS3"
    assert records[0].nd == "2.1042"
    assert records[-1].dpgf == "0.055200"


def test_revised_catalogue_loads_all_rows_and_retains_optional_fields():
    records = load_catalog_csv(ROOT / "catalogs" / "REFERENCE_CATALOG.csv")
    assert len(records) == 1186
    assert records[0].typecode == "S-FPL51"
    assert records[0].ne == "1.49845"
    assert records[0].ve == "81.1526"
    assert records[0].precision_molding is None


def test_catalogue_accepts_canonical_and_legacy_dispersion_headers(tmp_path):
    canonical = tmp_path / "canonical.csv"
    canonical.write_text(
        "Manufacturer,Typecode,nd,vd,PgF,dPgF,ne,ve,PrecisionMolding\n"
        "Ohara,S - FPL 51,1.49700,81.5468,0.537497,0.0280,1.49845,81.1526,1\n"
        "Hoya,N B K,1.5,60,,,,,0\n",
        encoding="utf-8",
    )
    records = load_catalog_csv(canonical)
    assert records[0].typecode == "S-FPL51"
    assert records[0].precision_molding is True
    assert records[1].typecode == "N B K"
    assert records[1].precision_molding is False


def test_catalogue_ignores_empty_rows(tmp_path):
    path = tmp_path / "catalog.csv"
    path.write_text(
        "Manufacturer,Typecode,nd,vd,PgF,dPgF\n\nOhara,X,1.5,60,,\n",
        encoding="utf-8",
    )
    assert len(load_catalog_csv(path)) == 1


@pytest.mark.parametrize(
    ("headers", "message"),
    [
        ("Manufacturer,Typecode,nd,vd,PgF,dPgF,Extra", "catalogue header"),
        (
            'Manufacturer,Typecode,nd,vd,PgF,"P_g,F",dPgF',
            "alias-colliding",
        ),
    ],
)
def test_catalogue_rejects_unknown_and_alias_colliding_headers(
    tmp_path, headers, message
):
    path = tmp_path / "catalog.csv"
    path.write_text(headers + "\n", encoding="utf-8")
    with pytest.raises(InputError, match=message):
        load_catalog_csv(path)


@pytest.mark.parametrize(
    ("ne", "ve", "molding", "message"),
    [
        ("1.5", "", "", "ne and ve"),
        ("", "60", "", "ne and ve"),
        ("-1", "60", "", "ne and ve must be positive"),
        ("1.5", "60", "yes", "PrecisionMolding"),
    ],
)
def test_catalogue_validates_optional_e_line_and_molding_values(
    tmp_path, ne, ve, molding, message
):
    path = tmp_path / "catalog.csv"
    path.write_text(
        "Manufacturer,Typecode,nd,vd,PgF,dPgF,ne,ve,PrecisionMolding\n"
        f"Ohara,X,1.5,60,,,{ne},{ve},{molding}\n",
        encoding="utf-8",
    )
    with pytest.raises(InputError, match=message):
        load_catalog_csv(path)


def test_ohara_normalization_participates_in_duplicate_detection(tmp_path):
    path = tmp_path / "catalog.csv"
    path.write_text(
        "Manufacturer,Typecode,nd,vd,PgF,dPgF\n"
        "Ohara,S - FPL 51,1.5,60,,\n"
        "Ohara,S-FPL51,1.6,50,,\n",
        encoding="utf-8",
    )
    with pytest.raises(InputError, match="catalogue row 3.*duplicate"):
        load_catalog_csv(path)


def test_catalogue_optional_fields_default_to_none(tmp_path):
    path = tmp_path / "catalog.csv"
    path.write_text(
        "Manufacturer,Typecode,nd,vd,PgF,dPgF\nHoya,N B K,1.5,60,,\n",
        encoding="utf-8",
    )
    record = load_catalog_csv(path)[0]
    assert (record.ne, record.ve, record.precision_molding) == (None, None, None)


@pytest.mark.parametrize(
    ("manufacturer", "typecode"),
    [("Ho\tya", "X"), ("Hoya", "N\tBK")],
)
def test_catalogue_rejects_controls_outside_ohara_whitespace_normalization(
    tmp_path, manufacturer, typecode
):
    path = tmp_path / "catalog.csv"
    path.write_text(
        f"Manufacturer,Typecode,nd,vd,PgF,dPgF\n{manufacturer},{typecode},1.5,60,,\n",
        encoding="utf-8",
    )
    with pytest.raises(InputError, match="control characters"):
        load_catalog_csv(path)


def test_ohara_removes_control_whitespace_before_identifier_validation(tmp_path):
    path = tmp_path / "catalog.csv"
    path.write_text(
        "Manufacturer,Typecode,nd,vd,PgF,dPgF\nOhara,S\t-FPL 51,1.5,60,,\n",
        encoding="utf-8",
    )
    assert load_catalog_csv(path)[0].typecode == "S-FPL51"


def test_catalogue_rejects_duplicate_identity(tmp_path):
    path = tmp_path / "catalog.csv"
    path.write_text(
        'Manufacturer,Typecode,nd,vd,"P_g,F","d_Pg,F"\n'
        "Ohara,X,1.5,60,,\nOhara,X,1.6,50,,\n",
        encoding="utf-8",
    )
    with pytest.raises(InputError, match="catalogue row 3.*duplicate"):
        load_catalog_csv(path)


def test_sample_adapter_assigns_sections_and_offsets():
    result = load_sectioned_csv(ROOT / "samples" / "sample_lens_data.csv")
    assert len(result.surfaces) == 13
    assert result.surfaces[0].source_id == "OBJ"
    assert result.surfaces[10].nd_offset == "0.005000"
    assert result.aspheres[0].coefficients[4] == "-3.4255E-05"
    assert result.configurations[0].thicknesses["d0"] == "infinity"


@pytest.mark.parametrize("text", ["0", "-1.00E-5", "+.25", "2e3"])
def test_decimal_value_accepts_finite_decimal_grammar(text):
    assert decimal_value(text, "quantity").is_finite()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("radius", True),
        ("radius", 1.2),
        ("radius", "NaN"),
        ("thickness", "Infinity"),
        ("radius", "1E"),
        ("radius", "--2"),
    ],
)
def test_quantities_reject_non_strings_and_nonfinite_or_malformed_values(field, value):
    data = minimal()
    data["surfaces"][1][field] = value
    with pytest.raises(InputError, match=rf"surfaces\[1\].{field}"):
        prescription_from_dict(data)


@pytest.mark.parametrize(
    "change",
    [
        {"units": []},
        {
            "aspheres": [
                {"surface_id": "1", "family": [], "conic": "0", "coefficients": {}}
            ]
        },
        {
            "aspheres": [
                {
                    "surface_id": "1",
                    "family": "even",
                    "conic": "0",
                    "coefficients": {},
                    "normalization": {},
                }
            ]
        },
        {
            "solves": [
                {
                    "kind": [],
                    "surface_id": "1",
                    "reference_surface_id": "OBJ",
                    "total": "1",
                }
            ]
        },
    ],
)
def test_malformed_enum_types_raise_input_error(change):
    with pytest.raises(InputError):
        prescription_from_dict(minimal(**change))


def test_duplicate_surface_and_numeric_coefficient_power_are_rejected():
    duplicate_surfaces = minimal()
    duplicate_surfaces["surfaces"].append(duplicate_surfaces["surfaces"][1].copy())
    with pytest.raises(InputError, match="duplicate surface id"):
        prescription_from_dict(duplicate_surfaces)
    with pytest.raises(InputError, match="duplicate numeric power"):
        prescription_from_dict(
            minimal(
                aspheres=[
                    {
                        "surface_id": "1",
                        "family": "even",
                        "conic": "0",
                        "coefficients": {"4": "1E-5", "04": "2E-5"},
                    }
                ]
            )
        )


def test_configuration_accepts_direct_object_surface_infinity():
    result = prescription_from_dict(
        minimal(configurations=[{"name": "far", "thicknesses": {"OBJ": "infinity"}}])
    )
    assert result.configurations[0].thicknesses["OBJ"] == "infinity"
