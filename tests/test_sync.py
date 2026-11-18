import codecs
from pathlib import Path

import pytest

from material_manager.cmx import CmxDocument
from material_manager import sync
from material_manager.sync import Change, apply_sync, prepare_sync


META = "<DataDescriptions><Metal><Column unit='S/m' name='C'/></Metal></DataDescriptions>"
OTHER = "<Material name='B' vendor='x'><Private><![CDATA[a>b]]></Private></Material>"
OLD = "<Material name='A'><Metal><Model>20 5</Model></Metal></Material>"
NEW = '<Material name="Z"><Metal><Model>30 6</Model></Metal></Material>'
EDIT = Change("A", NEW)


def write_lib(path, contents=None, meta=META, version="1.05"):
    if contents is None:
        contents = "  " + OLD + "\r\n  <!--Between-->\r\n  " + OTHER
    data = ("<?xml version='1.0' encoding='utf-8'?>\r\n<?vendor test?>\r\n"
            f"<Cadence_Material_Lib Version='{version}'>\r\n{meta}\r\n{contents}\r\n"
            "</Cadence_Material_Lib>\r\n<!--End-->\r\n").encode("utf-8")
    path.write_bytes(data)
    return data


def test_rename_across_files_and_missing_original(tmp_path):
    a, b = tmp_path / "a.cmx", tmp_path / "b.cmx"
    original = write_lib(a)
    other = write_lib(b, contents=OTHER)
    source = CmxDocument.load(a)
    plans = prepare_sync([a, b, a], [EDIT], source)
    assert len(plans) == 2 and all(p.changed and p.diff for p in plans)
    assert a.read_bytes() == original
    backups = apply_sync(plans)
    assert backups[a].read_bytes() == original and backups[b].read_bytes() == other
    assert a.read_bytes() == original.replace(OLD.encode(), NEW.encode())
    assert b.read_bytes() == other.replace(OTHER.encode(), (OTHER + "\r\n" + NEW).encode())
    assert apply_sync(prepare_sync([a, b], [EDIT])) == {}
    assert len(list(tmp_path.glob("*.bak"))) == 2


@pytest.mark.parametrize("contents", [OLD + OTHER, OTHER])
def test_colliding_name_fails_even_when_original_missing(tmp_path, contents):
    path = tmp_path / "lib.cmx"
    write_lib(path, contents=contents)
    with pytest.raises(ValueError, match="충돌"):
        prepare_sync([path], [Change("A", NEW.replace('"Z"', '"B"'))])


def test_stale_source_and_preview(tmp_path):
    a, b = tmp_path / "a.cmx", tmp_path / "b.cmx"
    original = write_lib(a)
    write_lib(b)
    loaded = CmxDocument.load(b)
    plans = prepare_sync([a, b], [EDIT], loaded)
    with b.open("ab") as f:
        f.write(b"\r\n")
    with pytest.raises(ValueError, match="변경"):
        prepare_sync([b], [EDIT], loaded)
    with pytest.raises(ValueError, match="변경"):
        apply_sync(plans)
    assert a.read_bytes() == original and not list(tmp_path.glob("*.bak"))


@pytest.mark.parametrize("mode", ["malformed", "version", "units", "duplicate"])
def test_invalid_second_file_leaves_first_untouched(tmp_path, mode):
    a, b = tmp_path / "a.cmx", tmp_path / "b.cmx"
    original = write_lib(a)
    if mode == "malformed":
        b.write_bytes(b"broken")
    elif mode == "version":
        write_lib(b, version="2.0")
    elif mode == "units":
        write_lib(b, meta=META.replace("S/m", "mS/m"))
    else:
        write_lib(b, contents=OLD * 2)
    with pytest.raises(ValueError):
        prepare_sync([a, b], [EDIT], CmxDocument.load(a))
    assert a.read_bytes() == original and not list(tmp_path.glob("*.bak"))


def test_schema_ignores_attribute_order_formatting_and_comments(tmp_path):
    a, b = tmp_path / "a.cmx", tmp_path / "b.cmx"
    write_lib(a)
    write_lib(b, meta=META.replace("<Metal>", "\n<Metal><!--keep-->").replace(
        "unit='S/m' name='C'", "name='C' unit='S/m'"))
    assert len(prepare_sync([a, b], [EDIT], CmxDocument.load(a))) == 2


def test_failed_second_write_restores_first_and_lists_backups(tmp_path, monkeypatch):
    a, b = tmp_path / "a.cmx", tmp_path / "b.cmx"
    original = write_lib(a)
    write_lib(b)
    plans = prepare_sync([a, b], [EDIT])
    replace = sync.os.replace

    def fail_second(src, dest):
        if Path(dest) == b:
            raise OSError("injected failure")
        replace(src, dest)

    monkeypatch.setattr(sync.os, "replace", fail_second)
    with pytest.raises(RuntimeError, match="injected failure") as error:
        apply_sync(plans)
    assert "1/1" in str(error.value) and ".bak" in str(error.value)
    assert a.read_bytes() == b.read_bytes() == original
    assert len(list(tmp_path.glob("*.bak"))) == 2 and not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("source", [
    "<Cadence_Material_Lib/>",
    "<Cadence_Material_Lib><!--extension--></Cadence_Material_Lib>",
    "<Cadence_Material_Lib><Material name='A'/></Cadence_Material_Lib>",
])
def test_utf16_empty_library_and_self_closing_material(tmp_path, source):
    path = tmp_path / "wide.cmx"
    data = codecs.BOM_UTF16_LE + source.encode("utf-16-le")
    path.write_bytes(data)
    apply_sync(prepare_sync([path], [EDIT]))
    assert path.read_bytes().startswith(codecs.BOM_UTF16_LE)
    assert CmxDocument.load(path).get("Z") is not None


def test_duplicate_paths(tmp_path):
    p = tmp_path / "lib.cmx"
    write_lib(p)
    alias = tmp_path / "alias.cmx"
    try:
        alias.symlink_to(p)
    except OSError:
        if Path("A") == Path("a"):
            alias = tmp_path / "LIB.CMX"
        else:
            pytest.skip("symlinks unavailable")
    assert len(prepare_sync([p, alias], [EDIT])) == 1


def test_destination_namespace_does_not_force_repeat_write(tmp_path):
    path = tmp_path / "lib.cmx"
    original = b'<Cadence_Material_Lib xmlns:private="urn:local"><Material name="X"/></Cadence_Material_Lib>'
    path.write_bytes(original)
    for original_name in (None, "X", "previous"):
        plans = prepare_sync([path], [Change(original_name, '<Material name="X"/>')])
        assert not plans[0].changed and not apply_sync(plans)
    assert path.read_bytes() == original


def test_new_material_updates_same_name_in_target(tmp_path):
    source, target = tmp_path / "source.cmx", tmp_path / "target.cmx"
    before_source = write_lib(source, contents=OTHER)
    before_target = write_lib(target)
    new_a = NEW.replace('"Z"', '"A"')
    plans = prepare_sync([target], [Change(None, new_a)], CmxDocument.load(source))
    assert plans[0].actions == ("수정 · A",)
    apply_sync(plans)
    assert target.read_bytes() == before_target.replace(OLD.encode(), new_a.encode())
    assert source.read_bytes() == before_source


def test_external_change_after_backup_and_during_rollback(tmp_path, monkeypatch):
    a, b = tmp_path / "a.cmx", tmp_path / "b.cmx"
    original = write_lib(a)
    write_lib(b)
    plans = prepare_sync([a, b], [EDIT])
    sibling = sync._sibling

    def inject(path, data, suffix):
        temp = sibling(path, data, suffix)
        if path == b and suffix == ".tmp":
            a.write_bytes(b"external A")
            b.write_bytes(b"external B")
        return temp

    monkeypatch.setattr(sync, "_sibling", inject)
    with pytest.raises(RuntimeError, match="0/1") as error:
        apply_sync(plans)
    assert a.read_bytes() == b"external A" and b.read_bytes() == b"external B"
    for backup in tmp_path.glob("*.bak"):
        assert str(backup) in str(error.value) and backup.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))
