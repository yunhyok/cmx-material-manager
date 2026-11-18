"""End-to-end editor checks without modifying user files."""
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QMessageBox

from material_manager.cmx import CmxDocument, create_material, material_xml
from material_manager.ui import MainWindow, PreviewDialog
from material_manager.theme import apply_theme


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    apply_theme(instance)
    yield instance


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    original = Path(__file__).parents[1] / "examples" / "demo.cmx"
    source = tmp_path / "source.cmx"
    source.write_bytes(original.read_bytes())
    widget = MainWindow(persist=False)
    assert widget.load_file(source)
    widget.show()
    app.processEvents()
    monkeypatch.setattr(widget, "error", lambda msg: pytest.fail(str(msg)))
    yield widget
    widget.hide()
    widget.deleteLater()
    app.processEvents()


def select(window, name):
    for i in range(window.materials.count()):
        item = window.materials.item(i)
        if window.entries[item.data(Qt.UserRole)].element.get("name") == name:
            window.materials.setCurrentItem(item)
            return
    raise AssertionError(name)


def test_read_only_capture_preserves_all_demo_data(window):
    for name, entry in list(window.entries.items()):
        select(window, name)
        assert material_xml(window.editor.capture()) == entry.original_xml
        assert not window.editor.dirty
        window.editor.tabs.setCurrentIndex(2)
        window.editor.tabs.setCurrentIndex(1)
        assert material_xml(window.editor.capture()) == entry.original_xml


def test_staging_during_selection_keeps_list_and_editor_in_sync(window, monkeypatch):
    window.editor.fields["DefaultThickness"].setText("40um")
    window.editor.mark_dirty()
    monkeypatch.setattr(window, "resolve_editor", lambda: window.stage_current())
    select(window, "DEMO_Dielectric")
    assert window.current_key == window.materials.currentItem().data(Qt.UserRole)
    assert window.editor.fields["name"].text() == "DEMO_Dielectric"
    assert window.entries["DEMO_Conductor"].pending


def test_ctrl_s_commits_active_table_cell(window, app, monkeypatch):
    captured = []
    monkeypatch.setattr("material_manager.ui.prepare_sync", lambda paths, changes, source: captured.extend(changes) or [])
    monkeypatch.setattr(PreviewDialog, "exec", lambda self: QDialog.Rejected)
    widget = window.editor.data
    widget.setCurrentCell(0, 1)
    widget.editItem(widget.item(0, 1))
    app.processEvents()
    editor = QApplication.focusWidget()
    assert isinstance(editor, QLineEdit)
    QTest.keyClick(editor, Qt.Key_A, Qt.ControlModifier)
    QTest.keyClicks(editor, "123456")
    QTest.keyClick(editor, Qt.Key_S, Qt.ControlModifier)
    app.processEvents()
    assert captured and "123456" in captured[0].material


def test_cancel_one_pending_change_preserves_other_work(window, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Discard)
    window.include_material()
    select(window, "DEMO_Dielectric")
    window.editor.fields["name"].setText("RENAMED")
    window.editor.mark_dirty()
    assert window.stage_current()
    window.revert_editor()
    assert not window.entries["DEMO_Dielectric"].pending
    assert window.entries["DEMO_Conductor"].pending
    window.add_entry(create_material("NEW"))
    window.revert_editor()
    assert not any(e.element.get("name") == "NEW" for e in window.entries.values())
    assert window.entries["DEMO_Conductor"].pending


def test_batch_ui_updates_two_files_and_leaves_backup(window, tmp_path, monkeypatch):
    target = tmp_path / "other.cmx"
    initial = window.source_path.read_bytes()
    target.write_bytes(initial)
    window.add_paths([str(target)])
    window.editor.data.item(0, 1).setText("57000000")
    monkeypatch.setattr(PreviewDialog, "exec", lambda self: QDialog.Accepted)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    window.sync_files()
    for path in (window.source_path, target):
        assert b"57000000" in path.read_bytes()
        backups = list(tmp_path.glob(path.name + ".*.bak"))
        assert len(backups) == 1 and backups[0].read_bytes() == initial
    assert not any(e.pending for e in window.entries.values())


def test_export_ui_keeps_source_and_pending_changes(window, tmp_path, monkeypatch):
    output = tmp_path / "exported.cmx"
    initial = window.source_path.read_bytes()
    window.editor.data.item(0, 1).setText("56000000")
    monkeypatch.setattr("material_manager.ui.QFileDialog.getSaveFileName", lambda *args, **kwargs: (str(output), ""))
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)
    window.export_file()
    assert window.source_path.read_bytes() == initial
    assert b"56000000" in output.read_bytes()
    assert len(CmxDocument.load(output).materials) == 3
    assert any(e.pending for e in window.entries.values())


def test_restored_targets_remain_unchecked(window, tmp_path):
    previous = tmp_path / "previously-unchecked.cmx"
    window.add_paths([str(previous)], checked=False)
    assert window.targets.item(window.targets.count() - 1).checkState() == Qt.Unchecked
    source = next(window.targets.item(i) for i in range(window.targets.count()) if window.targets.item(i).data(Qt.UserRole) == str(window.source_path))
    assert source.checkState() == Qt.Checked
    assert not source.flags() & Qt.ItemIsUserCheckable
