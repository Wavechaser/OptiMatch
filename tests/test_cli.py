import json

import pytest

from optics_prescription_matcher.__main__ import main


@pytest.mark.parametrize("via_metadata", [False, True])
def test_cli_setup_defaults_and_zero_aperture_warning(tmp_path, capsys, via_metadata):
    source, catalog = write_inputs(tmp_path)
    data = json.loads(source.read_text(encoding="utf-8"))
    data["surfaces"] = [
        {"id": "OBJ", "radius": "0", "thickness": "infinity"},
        {"id": "stop", "radius": "10", "thickness": "2", "stop": True},
        {"id": "IMG", "radius": "0", "thickness": ""},
    ]
    if via_metadata:
        data["system"] = {"field_preset": "full-frame"}
    source.write_text(json.dumps(data), encoding="utf-8")
    args = [
        str(source),
        "--catalog",
        str(catalog),
        "--output",
        str(tmp_path / "preset"),
    ]
    if not via_metadata:
        args.extend(["--field-preset", "full-frame"])
    assert main(args) == 0
    assert "incomplete setup placeholder" in capsys.readouterr().err
    text = (tmp_path / "preset.zmx").read_text(encoding="utf-16")
    assert "YFLN 0 4 8 12 17 22" in text
    assert "PWAV 2" in text and "FNUM 0 1" in text


def write_inputs(tmp_path):
    source = tmp_path / "input.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "title": "CLI",
                "units": "mm",
                "surfaces": [
                    {
                        "id": "1",
                        "radius": "10",
                        "thickness": "2",
                        "nd": "1.5",
                        "vd": "50",
                    },
                    {"id": "2", "radius": "0", "thickness": "0"},
                ],
            }
        ),
        encoding="utf-8",
    )
    catalog = tmp_path / "catalog.csv"
    catalog.write_text(
        'Manufacturer,Typecode,nd,vd,"P_g,F","d_Pg,F"\nOhara,S-BSL7,1.5,50,,\n',
        encoding="utf-8",
    )
    return source, catalog


def test_cli_writes_csv_and_deterministic_report(tmp_path, capsys):
    source, catalog = write_inputs(tmp_path)
    prefix = tmp_path / "study"
    assert (
        main(
            [
                str(source),
                "--catalog",
                str(catalog),
                "--output",
                str(prefix),
                "--format",
                "csv",
            ]
        )
        == 0
    )
    report = json.loads((tmp_path / "study.report.json").read_text(encoding="utf-8"))
    assert report["summary"] == {
        "air": 1,
        "supplied": 0,
        "close": 1,
        "offset": 0,
        "unmatched": 0,
    }
    assert "S-BSL7" in (tmp_path / "study.csv").read_text(encoding="utf-8")
    assert "matched=1, unmatched=0" in capsys.readouterr().out


def test_cli_refuses_existing_target_without_overwrite(tmp_path, capsys):
    source, catalog = write_inputs(tmp_path)
    prefix = tmp_path / "study"
    (tmp_path / "study.csv").write_text("mine", encoding="utf-8")
    assert (
        main(
            [
                str(source),
                "--catalog",
                str(catalog),
                "--output",
                str(prefix),
                "--format",
                "csv",
            ]
        )
        == 2
    )
    assert (tmp_path / "study.csv").read_text(encoding="utf-8") == "mine"
    assert not (tmp_path / "study.report.json").exists()
    assert "--overwrite" in capsys.readouterr().err


def test_cli_refuses_source_collision_even_with_overwrite(tmp_path):
    source, catalog = write_inputs(tmp_path)
    # with_suffix makes input.json the report source only for this deliberately chosen prefix
    prefix = tmp_path / "catalog"
    catalog_report = tmp_path / "catalog.report.json"
    catalog_report.write_text("metadata", encoding="utf-8")
    assert (
        main(
            [
                str(catalog_report),
                "--catalog",
                str(catalog),
                "--output",
                str(prefix),
                "--overwrite",
                "--format",
                "csv",
            ]
        )
        == 2
    )


def test_cli_appends_suffixes_to_dotted_prefix_and_rejects_json_metadata(tmp_path):
    source, catalog = write_inputs(tmp_path)
    prefix = tmp_path / "study.v1"
    assert (
        main(
            [
                str(source),
                "--catalog",
                str(catalog),
                "--output",
                str(prefix),
                "--format",
                "csv",
            ]
        )
        == 0
    )
    assert (tmp_path / "study.v1.csv").exists()
    metadata = tmp_path / "metadata.json"
    metadata.write_text("{}", encoding="utf-8")
    assert (
        main(
            [
                str(source),
                "--catalog",
                str(catalog),
                "--output",
                str(tmp_path / "other"),
                "--metadata",
                str(metadata),
                "--format",
                "csv",
            ]
        )
        == 2
    )
    assert not (tmp_path / "other.csv").exists()


def test_cli_invalid_input_creates_no_outputs(tmp_path):
    source, catalog = write_inputs(tmp_path)
    source.write_text("{broken", encoding="utf-8")
    prefix = tmp_path / "bad"
    assert (
        main(
            [
                str(source),
                "--catalog",
                str(catalog),
                "--output",
                str(prefix),
                "--format",
                "csv",
            ]
        )
        == 2
    )
    assert not (tmp_path / "bad.csv").exists()
    assert not (tmp_path / "bad.report.json").exists()


def test_cli_no_overwrite_publish_race_cleans_new_outputs(tmp_path, monkeypatch):
    from optics_prescription_matcher import __main__ as cli

    source, catalog = write_inputs(tmp_path)
    prefix = tmp_path / "race"
    real_link = cli.os.link
    calls = 0

    def raced_link(source_path, target_path):
        nonlocal calls
        calls += 1
        if calls == 2:
            target_path.write_text("racer", encoding="utf-8")
        real_link(source_path, target_path)

    monkeypatch.setattr(cli.os, "link", raced_link)
    assert (
        main(
            [
                str(source),
                "--catalog",
                str(catalog),
                "--output",
                str(prefix),
                "--format",
                "csv",
            ]
        )
        == 2
    )
    assert not (tmp_path / "race.csv").exists()
    assert (tmp_path / "race.report.json").read_text(encoding="utf-8") == "racer"


def test_cli_defaults_to_both_and_writes_binary_zmx(tmp_path):
    source, catalog = write_inputs(tmp_path)
    data = json.loads(source.read_text(encoding="utf-8"))
    data["surfaces"] = [
        {"id": "OBJ", "radius": "0", "thickness": "infinity"},
        {
            "id": "1",
            "radius": "10",
            "thickness": "2",
            "material": "S-BSL7",
            "stop": True,
        },
        {"id": "IMG", "radius": "0", "thickness": ""},
    ]
    data["system"] = {
        "aperture_type": "f_number",
        "aperture_value": "4",
        "field_type": "angle",
        "fields": ["0"],
        "wavelengths": [{"value": "0.55", "weight": "1", "primary": True}],
    }
    source.write_text(json.dumps(data), encoding="utf-8")
    prefix = tmp_path / "both"
    assert main([str(source), "--catalog", str(catalog), "--output", str(prefix)]) == 0
    assert (tmp_path / "both.csv").exists()
    assert (tmp_path / "both.zmx").read_bytes().startswith(b"\xff\xfe")
    assert (tmp_path / "both.report.json").exists()


def test_both_validates_zmx_before_writing_but_csv_only_allows_unmatched(tmp_path):
    source, catalog = write_inputs(tmp_path)
    both = tmp_path / "both_invalid"
    assert main([str(source), "--catalog", str(catalog), "--output", str(both)]) == 2
    assert not any(tmp_path.glob("both_invalid.*"))
    data = json.loads(source.read_text(encoding="utf-8"))
    data["surfaces"][0]["nd"] = "1.9"
    data["surfaces"][0]["vd"] = "20"
    source.write_text(json.dumps(data), encoding="utf-8")
    csv_only = tmp_path / "unmatched"
    assert (
        main(
            [
                str(source),
                "--catalog",
                str(catalog),
                "--output",
                str(csv_only),
                "--format",
                "csv",
            ]
        )
        == 0
    )
    assert (tmp_path / "unmatched.csv").exists()
