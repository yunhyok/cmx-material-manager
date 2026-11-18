import pytest

from material_manager import sync
from material_manager.cmx import CmxDocument
from material_manager.export import export_cmx
from material_manager.sync import Change


DATA = (b"<?xml version='1.0'?><Cadence_Material_Lib Version='1.05'>"
        b"<DataDescriptions/><!--retain--><Material name='A'/>"
        b"<Material name='B'><Extra flag='x'>arbitrary</Extra></Material></Cadence_Material_Lib>")
EDIT = [Change("A", '<Material name="Renamed"><Metal><Model>20 1</Model></Metal></Material>'),
        Change(None, '<Material name="New"/>')]


def test_export_new_file_preserves_full_library_and_original(tmp_path):
    original = tmp_path / "source.cmx"
    original.write_bytes(DATA)
    source = CmxDocument.load(original)
    exported = tmp_path / "result.cmx"
    assert export_cmx(exported, source, EDIT) is None
    doc = CmxDocument.load(exported)
    assert [m.get("name") for m in doc.materials] == ["Renamed", "B", "New"]
    assert doc.get("Renamed").findtext("Metal/Model") == "20 1"
    assert b"<DataDescriptions/><!--retain-->" in exported.read_bytes()
    assert b"<Extra flag='x'>arbitrary</Extra>" in exported.read_bytes()
    assert original.read_bytes() == DATA == source.to_bytes()
    with pytest.raises(ValueError):
        export_cmx(original, source, EDIT)
    assert not list(tmp_path.glob("*.bak"))


def test_existing_output_has_unique_backup_on_each_export(tmp_path):
    path = tmp_path / "export.cmx"
    path.write_bytes(b"old output")
    source = CmxDocument.from_bytes(DATA)
    backup = export_cmx(path, source, [])
    assert backup.read_bytes() == b"old output" and path.read_bytes() == DATA
    second_backup = export_cmx(path, source, EDIT)
    assert second_backup != backup and second_backup.read_bytes() == DATA
    assert backup.read_bytes() == b"old output"


def test_failed_replace_preserves_destination(tmp_path, monkeypatch):
    path = tmp_path / "export.cmx"
    path.write_bytes(b"old")

    def fail_replace(*args):
        raise PermissionError("injected")

    monkeypatch.setattr(sync.os, "replace", fail_replace)
    with pytest.raises(RuntimeError, match="injected") as exc:
        export_cmx(path, CmxDocument.from_bytes(DATA), EDIT)
    backup, = tmp_path.glob("*.bak")
    assert backup.read_bytes() == path.read_bytes() == b"old"
    assert str(backup) in str(exc.value) and not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("already_exists", [True, False])
def test_concurrent_destination_write_is_preserved(tmp_path, monkeypatch, already_exists):
    path = tmp_path / "result.cmx"
    if already_exists:
        path.write_bytes(b"previous")
    sibling = sync._sibling

    def competing_write(dest, data, suffix):
        result = sibling(dest, data, suffix)
        if suffix == ".tmp":
            path.write_bytes(b"other writer")
        return result

    monkeypatch.setattr(sync, "_sibling", competing_write)
    with pytest.raises((RuntimeError, FileExistsError)):
        export_cmx(path, CmxDocument.from_bytes(DATA), EDIT)
    assert path.read_bytes() == b"other writer"


def test_invalid_change_does_not_touch_export_destination(tmp_path):
    path = tmp_path / "result.cmx"
    path.write_bytes(b"old")
    with pytest.raises(ValueError):
        export_cmx(path, CmxDocument.from_bytes(DATA), [Change(None, "<bad>")])
    assert path.read_bytes() == b"old" and not list(tmp_path.glob("*.bak"))
