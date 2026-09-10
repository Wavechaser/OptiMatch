from pathlib import Path

import pytest

from optics_prescription_matcher.export import write_prescription_csv
from optics_prescription_matcher.inputs import InputError, load_sectioned_csv

ROOT = Path(__file__).parents[1]


def test_sample_round_trip_preserves_meaningful_source_values(tmp_path):
    source = load_sectioned_csv(ROOT / "samples" / "sample_lens_data.csv")
    output = tmp_path / "roundtrip.csv"
    write_prescription_csv(source, output)
    reread = load_sectioned_csv(output)
    assert reread.surfaces == source.surfaces
    assert reread.aspheres == source.aspheres
    assert reread.configurations == source.configurations
    text = output.read_text(encoding="utf-8")
    assert "nd offset,vd offset" in text
    assert "-3.4255E-05" in text


def test_scrambled_legacy_lens_headers_are_recognized(tmp_path):
    path = tmp_path / "scrambled.csv"
    path.write_text(
        "Lens Data\nvd,Thickness,#,?vd,Material,Radius,?nd,nd\n"
        "60.00,2.0,1,-0.10,GLASS,10.000,+0.0010,1.5000\n",
        encoding="utf-8-sig",
    )
    result = load_sectioned_csv(path)
    surface = result.surfaces[0]
    assert (surface.source_id, surface.radius, surface.nd_offset) == (
        "1",
        "10.000",
        "+0.0010",
    )


def test_writer_omits_optional_columns_when_unused(tmp_path):
    path = tmp_path / "plain.csv"
    path.write_text(
        "Lens Data\nSurface,Radius,Thickness,Material,nd,vd\nOBJ,0,10,,,\n",
        encoding="utf-8",
    )
    prescription = load_sectioned_csv(path)
    output = tmp_path / "output.csv"
    write_prescription_csv(prescription, output)
    assert (
        output.read_text(encoding="utf-8").splitlines()[1]
        == "Surface,Radius,Thickness,Material,nd,vd"
    )


def test_lowercase_asphere_header_is_canonicalized(tmp_path):
    path = tmp_path / "lowercase.csv"
    path.write_text(
        "Lens Data\nSurface,Radius,Thickness,Material,nd,vd\n"
        "1,10,2,,,\n\nEven Aspheres\nSurface,k,a4\n1,0,1.00E-5\n",
        encoding="utf-8",
    )
    result = load_sectioned_csv(path)
    assert result.aspheres[0].coefficients[4] == "1.00E-5"


@pytest.mark.parametrize(
    ("section", "message"),
    [
        ("Even Aspheres\nSurface,k,A4\n2,0,1E-5\n", "unknown surface id"),
        (
            "Multiconfiguration Data\n,far\nunknown_gap,2.0\n",
            "unknown surface or symbol",
        ),
        (
            "Even Aspheres\nSurface,k,A4,a04\n1,0,1E-5,2E-5\n",
            "duplicate coefficient power",
        ),
    ],
)
def test_csv_collections_receive_canonical_validation(tmp_path, section, message):
    path = tmp_path / "invalid.csv"
    path.write_text(
        "Lens Data\nSurface,Radius,Thickness,Material,nd,vd\n1,10,2,,,\n\n" + section,
        encoding="utf-8",
    )
    with pytest.raises(InputError, match=message):
        load_sectioned_csv(path)


def test_csv_round_trip_preserves_stop_and_normalization(tmp_path):
    path = tmp_path / "input.csv"
    path.write_text(
        "Lens Data\nSurface,Radius,Thickness,Material,nd,vd,Stop\n"
        "1,10,2,,,,true\n\nEven Aspheres\n"
        "Surface,k,A4,Normalization,Normalization Radius\n"
        "1,0,1E-5,normalized,12.50\n",
        encoding="utf-8",
    )
    source = load_sectioned_csv(path)
    output = tmp_path / "output.csv"
    write_prescription_csv(source, output)
    reread = load_sectioned_csv(output)
    assert reread.surfaces[0].stop is True
    assert reread.aspheres[0].normalization == "normalized"
    assert reread.aspheres[0].normalization_radius == "12.50"


def test_internal_blank_lens_header_is_rejected_without_column_shift(tmp_path):
    path = tmp_path / "blank_header.csv"
    path.write_text(
        "Lens Data\nSurface,,Radius,Thickness,Material,nd,vd\n1,0,10,2,,,,\n",
        encoding="utf-8",
    )
    with pytest.raises(InputError, match="blank columns"):
        load_sectioned_csv(path)


@pytest.mark.parametrize(
    "tail",
    [
        "Multiconfiguration Data\n,far,,near\nd0,10,,2\n",
        "Even Aspheres\nSurface,k,A4\n1,0,1E-5,unexpected\n",
    ],
)
def test_csv_rejects_internal_blank_headers_and_extra_values(tmp_path, tail):
    path = tmp_path / "lossy.csv"
    path.write_text(
        "Lens Data\nSurface,Radius,Thickness,Material,nd,vd\nOBJ,0,d0,,,\n\n" + tail,
        encoding="utf-8",
    )
    with pytest.raises(InputError):
        load_sectioned_csv(path)
