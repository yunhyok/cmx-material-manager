import os
from pathlib import Path

import pytest


def test_ambiguous_legacy_encoding_is_rejected_before_rewriting():
    from material_manager.cmx import CmxDocument, create_material

    data = b'<?xml version="1.0" encoding="CP932"?><Cadence_Material_Lib Version="1.05"><Material name="A"/><Material name="B" info="\xfa\x4a"/></Cadence_Material_Lib>'
    document = CmxDocument.from_bytes(data)
    assert document.to_bytes() == data
    with pytest.raises(ValueError, match="인코딩"):
        document.patched_bytes({"A": create_material("A")}, [])

from material_manager.cmx import CmxDocument, create_material, material_xml, parse_material


def test_document_rejects_unsafe_and_duplicate_xml():
    for data in (
        b'<!DOCTYPE Cadence_Material_Lib [<!ENTITY x "x">]><Cadence_Material_Lib/>',
        b'<!DOCTYPE Cadence_Material_Lib SYSTEM "file:///missing"><Cadence_Material_Lib/>',
        b'<Cadence_Material_Lib><Material name="a"/><Material name="a"/></Cadence_Material_Lib>',
        b'<Cadence_Material_Lib><Material name=" "/></Cadence_Material_Lib>',
        b'<other/>', b'<broken',
    ):
        with pytest.raises(ValueError):
            CmxDocument.from_bytes(data)


def test_material_validates_specific_table_paths_only():
    raw = """<Material name="Synthetic"><Dielectric>
    <Model>1 2 0</Model><Model Temperature="30">1 3 0</Model></Dielectric>
    <Extension><Model Temperature="hot">vendor syntax</Model></Extension>
    <!--marker--><Structural><CTE RefTemperature="23">0 1e-4</CTE></Structural></Material>"""
    assert "<!--marker-->" in material_xml(parse_material(raw))
    for bad in (raw.replace("1 3 0", "1 NaN 2"), raw.replace("1 3 0", "1 3"),
                raw.replace('"30"', '"Infinity"'), raw.replace("1e-4", "unknown")):
        with pytest.raises(ValueError):
            parse_material(bad)
    for kind in ("Metal", "Thermal", "Dielectric"):
        assert parse_material(material_xml(create_material("x<&", kind))).find(kind) is not None


def test_empty_sections_and_unedited_legacy_tables_are_readable():
    data = b"<Cadence_Material_Lib><Material name='A'><Metal><Model>legacy</Model></Metal></Material></Cadence_Material_Lib>"
    assert CmxDocument.from_bytes(data).to_bytes() == data
    assert parse_material('<Material name="X"><Structural><Elasticity/></Structural></Material>') is not None


def test_dimensions_and_roughness_tables():
    for value in ("0", "20MIL", "0.1mil", "-.25 mm", "2e-2cm", "2um", "2µm", "4IN", "0.2m", "2nm"):
        raw = f'<Material name="x" DefaultThickness="{value}"/>'
        assert parse_material(raw).get("DefaultThickness") == value
    for key, value in (("DefaultThickness", "typo"), ("UpperTolerance", "NaNmm"),
                       ("LowerTolerance", "1e400 um"), ("DefaultThickness", "2watts")):
        with pytest.raises(ValueError, match=key):
            parse_material(f'<Material name="x" {key}="{value}"/>')
    for kind in ("Huray", "ModHammerstad", "ModGroisse"):
        raw = f'<Material name="x"><SurfaceRoughness><{kind}>0.1 2</{kind}></SurfaceRoughness></Material>'
        assert parse_material(raw) is not None
        with pytest.raises(ValueError, match=kind):
            parse_material(raw.replace("0.1 2", "bogus"))
    for empty in ("<!-- marker -->", "<?marker keep?>"):
        with pytest.raises(ValueError, match="Model"):
            parse_material(f'<Material name="x"><Dielectric><Model>{empty}</Model></Dielectric></Material>')


@pytest.mark.skipif(not os.environ.get("CMX_LOCAL_SAMPLE"), reason="optional private sample")
def test_private_sample_read_only():
    path = Path(os.environ["CMX_LOCAL_SAMPLE"])
    data = path.read_bytes()
    doc = CmxDocument.load(path)
    assert doc.to_bytes() == data
    assert doc.materials
    for item in doc.materials:
        assert parse_material(material_xml(item)).get("name") == item.get("name")
    assert path.read_bytes() == data
