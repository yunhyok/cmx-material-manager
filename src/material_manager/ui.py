"""Qt editor; document parsing and disk writes live in cmx and sync."""

import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from lxml import etree
from PySide6.QtCore import QItemSelectionModel, QSettings, QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QFontDatabase, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSplitter, QTabWidget,
    QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from material_manager import __version__
from material_manager.cmx import CmxDocument, create_material, material_xml, parse_material
from material_manager.export import export_cmx
from material_manager.sync import Change, apply_sync, prepare_sync


def button(text, callback, primary=False):
    widget = QPushButton(text)
    widget.setProperty("primary", primary)
    widget.clicked.connect(callback)
    return widget


def label(text, muted=False):
    widget = QLabel(text)
    widget.setProperty("muted", muted)
    widget.setWordWrap(True)
    return widget


def table(headers):
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    widget.horizontalHeader().setStretchLastSection(True)
    widget.setAlternatingRowColors(True)
    widget.setSelectionBehavior(QAbstractItemView.SelectItems)
    return widget


def cell_text(widget, row, col):
    item = widget.item(row, col)
    return item.text().strip() if item else ""


class MaterialEditor(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.working = None
        self.node = None
        self.descriptions = None
        self.loading = False
        self.dirty = False
        self.last_tab = 1
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.material_heading = label("물질을 선택하세요")
        layout.addWidget(self.material_heading)
        self.tabs = QTabWidget()
        structured = QWidget()
        body = QVBoxLayout(structured)
        metadata = QWidget()
        metadata_layout = QVBoxLayout(metadata)
        fields = QGridLayout()
        self.fields = {}
        for i, (key, title) in enumerate([
            ("name", "물질 이름"), ("DefaultThickness", "기본 두께"),
            ("UpperTolerance", "상한 공차"), ("LowerTolerance", "하한 공차"),
        ]):
            edit = QLineEdit()
            edit.setPlaceholderText("예: 1.4MIL / 35um" if i else "고유한 물질 이름")
            edit.textEdited.connect(self.mark_dirty)
            fields.addWidget(QLabel(title), i // 2 * 2, i % 2)
            fields.addWidget(edit, i // 2 * 2 + 1, i % 2)
            self.fields[key] = edit
        metadata_layout.addLayout(fields)
        metadata_layout.addWidget(label("두께·공차는 숫자와 단위로 입력 · 예: 35um, 1.4MIL\n추가 속성은 XML 편집에서 수정", True))
        metadata_layout.addStretch()
        self.splitter = QSplitter()
        self.splitter.setChildrenCollapsible(False)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(label("속성 / 모델", True))
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(130)
        self.tree.currentItemChanged.connect(self.node_changed)
        left_layout.addWidget(self.tree)
        left_layout.addWidget(button("선택 모델 복제", self.duplicate_node))
        right = QWidget()
        right.setMinimumHeight(340)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.node_title = label("모델을 선택하세요")
        right_layout.addWidget(self.node_title)
        self.attributes = table(["속성", "값"])
        self.attributes.setMaximumHeight(100)
        self.attributes.setMinimumHeight(75)
        self.attributes.itemChanged.connect(self.mark_dirty)
        right_layout.addWidget(self.attributes)
        row = QHBoxLayout()
        row.addWidget(button("속성 추가", self.add_attribute))
        row.addWidget(button("속성 삭제", self.remove_attribute))
        row.addStretch()
        right_layout.addLayout(row)
        self.data = table([])
        self.data.setMinimumHeight(140)
        self.data.itemChanged.connect(self.mark_dirty)
        right_layout.addWidget(self.data, 1)
        row = QHBoxLayout()
        row.addWidget(button("행 추가", self.add_row))
        row.addWidget(button("행 삭제", self.remove_row))
        row.addStretch()
        right_layout.addLayout(row)
        self.column_hint = label("표의 값은 원본 단위를 따릅니다.", True)
        right_layout.addWidget(self.column_hint)
        self.splitter.addWidget(left)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([190, 440])
        body.addWidget(self.splitter, 1)
        self.xml = QPlainTextEdit()
        self.xml.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.xml.textChanged.connect(self.mark_dirty)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(structured)
        self.tabs.addTab(metadata, "물질 정보")
        self.tabs.addTab(scroll, "속성 / 모델")
        self.tabs.addTab(self.xml, "XML 편집")
        self.tabs.setCurrentIndex(1)
        self.tabs.currentChanged.connect(self.tab_changed)
        layout.addWidget(self.tabs)
        self.setEnabled(False)

    def mark_dirty(self, *_):
        if not self.loading:
            self.dirty = True
            self.changed.emit()

    def load(self, element, descriptions=None):
        self.loading = True
        self.working = copy.deepcopy(element)
        self.material_heading.setText(element.get("name", ""))
        self.descriptions = descriptions
        self.node = None
        self.fill_structured()
        self.xml.setPlainText(material_xml(self.working))
        self.last_tab = self.tabs.currentIndex()
        self.dirty = False
        self.setEnabled(True)
        self.loading = False

    def fill_structured(self):
        for key, edit in self.fields.items():
            edit.setText(self.working.get(key, ""))
        self.node = None
        self.tree.clear()

        def append(parent, element):
            if not isinstance(element.tag, str):
                return
            details = ", ".join(f"{k}={v}" for k, v in element.attrib.items())
            item = QTreeWidgetItem([element.tag + (f" · {details}" if details else "")])
            item.setData(0, Qt.UserRole, element)
            item.setToolTip(0, item.text(0))
            parent.addChild(item) if isinstance(parent, QTreeWidgetItem) else parent.addTopLevelItem(item)
            for child in element:
                append(item, child)

        for element in self.working:
            append(self.tree, element)
        self.tree.expandAll()
        if self.tree.topLevelItemCount():
            item = self.tree.topLevelItem(0)
            while item.childCount():
                item = item.child(0)
            self.tree.setCurrentItem(item)
            self.read_node(item.data(0, Qt.UserRole))
        else:
            self.attributes.setRowCount(0)
            self.data.setRowCount(0)
            self.data.setColumnCount(0)

    def node_changed(self, current, previous):
        if self.loading or current is None:
            return
        try:
            self.write_node()
        except ValueError as error:
            QMessageBox.warning(self, "속성 확인", str(error))
            self.loading = True
            self.tree.setCurrentItem(previous)
            self.loading = False
            return
        self.loading = True
        self.read_node(current.data(0, Qt.UserRole))
        self.loading = False

    def headers(self, element, width):
        parts = []
        current = element
        while current is not None and current is not self.working:
            if current.tag != "Model":
                parts.insert(0, current.tag)
            current = current.getparent()
        desc = self.descriptions.find("/".join(parts)) if self.descriptions is not None and parts else None
        columns = list(desc.findall("Column")) if desc is not None else []
        if len(columns) == width + 1 and columns[0].get("name") in ("Temperature", "Reference Temperature"):
            columns = columns[1:]
        if len(columns) != width:
            return [f"값 {i + 1}" for i in range(width)]
        return [c.get("name", "값") + (f" [{c.get('unit')}]" if c.get("unit") else "") for c in columns]

    def read_node(self, element):
        self.node = element
        self.node_title.setText(element.tag)
        self.attributes.setRowCount(len(element.attrib))
        for row, (key, value) in enumerate(element.attrib.items()):
            self.attributes.setItem(row, 0, QTableWidgetItem(key))
            self.attributes.setItem(row, 1, QTableWidgetItem(value))
        self.rows = [line.split() for line in (element.text or "").splitlines() if line.strip()]
        self.data.setRowCount(len(self.rows))
        width = max((len(row) for row in self.rows), default=0)
        self.data.setColumnCount(width)
        self.data.setHorizontalHeaderLabels(self.headers(element, width))
        for row, values in enumerate(self.rows):
            for col, value in enumerate(values):
                self.data.setItem(row, col, QTableWidgetItem(value))
        self.data.resizeColumnsToContents()
        self.data.setEnabled(not any(isinstance(c.tag, str) for c in element))
        self.column_hint.setText("행 단위로 입력 · 주파수 / 온도와 단위 확인" if width else "값이 없는 항목 · 새 구조는 XML 편집에서 추가")

    def write_node(self):
        if self.node is None:
            return
        attrs = {}
        for row in range(self.attributes.rowCount()):
            key, value = cell_text(self.attributes, row, 0), cell_text(self.attributes, row, 1)
            if not key:
                raise ValueError("비어 있는 속성 이름을 입력하거나 해당 행을 삭제하세요.")
            if key in attrs:
                raise ValueError(f"속성 이름 중복: {key}")
            attrs[key] = value
        probe = etree.Element("check")
        for key, value in attrs.items():
            probe.set(key, value)
        self.node.attrib.clear()
        self.node.attrib.update(attrs)
        rows = [[cell_text(self.data, row, col) for col in range(self.data.columnCount())]
                for row in range(self.data.rowCount())]
        if rows != self.rows:
            if any(not value for row in rows for value in row):
                raise ValueError("표의 빈 셀을 입력하거나 해당 행을 삭제하세요.")
            self.node.text = "\n" + "\n".join(" ".join(row) for row in rows) + "\n"
            self.rows = rows

    def capture_structured(self):
        self.write_node()
        for key, edit in self.fields.items():
            value = edit.text().strip()
            if value:
                self.working.set(key, value)
            else:
                self.working.attrib.pop(key, None)

    def capture(self):
        if self.tabs.currentIndex() == 2:
            return parse_material(self.xml.toPlainText())
        self.capture_structured()
        return parse_material(material_xml(self.working))

    def tab_changed(self, index):
        if self.loading or self.working is None:
            return
        self.loading = True
        try:
            if self.last_tab != 2:
                self.capture_structured()
                if index == 2:
                    self.xml.setPlainText(material_xml(self.working))
            else:
                self.working = parse_material(self.xml.toPlainText())
                self.fill_structured()
                self.material_heading.setText(self.working.get("name", ""))
            self.last_tab = index
        except (ValueError, etree.Error) as error:
            self.tabs.setCurrentIndex(self.last_tab)
            QMessageBox.warning(self, "입력 확인", str(error))
        finally:
            self.loading = False

    def add_attribute(self):
        if self.node is not None:
            row = self.attributes.rowCount()
            self.attributes.insertRow(row)
            self.attributes.setItem(row, 0, QTableWidgetItem(""))
            self.attributes.setItem(row, 1, QTableWidgetItem(""))
            self.attributes.editItem(self.attributes.item(row, 0))
            self.mark_dirty()

    def remove_attribute(self):
        row = self.attributes.currentRow()
        if row >= 0:
            self.attributes.removeRow(row)
            self.mark_dirty()

    def add_row(self):
        if self.data.isEnabled() and self.data.columnCount():
            row = self.data.rowCount()
            self.data.insertRow(row)
            for col in range(self.data.columnCount()):
                self.data.setItem(row, col, QTableWidgetItem("0"))
            self.data.setCurrentCell(row, 0)
            self.mark_dirty()

    def remove_row(self):
        rows = sorted({i.row() for i in self.data.selectedIndexes()}, reverse=True)
        for row in rows:
            self.data.removeRow(row)
        if rows:
            self.mark_dirty()

    def duplicate_node(self):
        if self.node is None or self.node.tag != "Model":
            QMessageBox.information(self, "모델 복제", "Model 항목을 선택하세요. 복제 후 Temperature 등의 조건을 수정하세요.")
            return
        try:
            self.capture_structured()
            clone = copy.deepcopy(self.node)
            self.node.addnext(clone)
            self.loading = True
            self.fill_structured()
            self.loading = False
            self.mark_dirty()
        except (ValueError, etree.Error) as error:
            self.loading = False
            QMessageBox.warning(self, "입력 확인", str(error))


@dataclass
class Entry:
    original_name: str | None
    original_xml: str
    element: object
    included: bool = False

    @property
    def pending(self):
        return self.included or self.original_name is None or material_xml(self.element) != self.original_xml


class MaterialListItem(QListWidgetItem):
    def refresh(self, entry):
        name = entry.element.get("name", "")
        types = " / ".join(child.tag for child in entry.element if isinstance(child.tag, str))
        self.setToolTip(name + "\n" + types)
        self.setText(("● " if entry.pending else "") + self.toolTip())

    def __lt__(self, other):
        return self.toolTip().casefold() < other.toolTip().casefold()


class PreviewDialog(QDialog):
    def __init__(self, plans, parent):
        super().__init__(parent)
        self.setWindowTitle("일괄 저장 미리보기")
        self.resize(940, 650)
        layout = QVBoxLayout(self)
        layout.addWidget(label("대상에 없는 물질은 추가하고, 같은 이름의 물질은 기준 물질의 내용으로 교체합니다."))
        layout.addWidget(label("파일별 백업 후 순차 저장 · 오류 시 이미 저장한 파일 복구 시도", True))
        split = QSplitter(Qt.Vertical)
        self.paths = QListWidget()
        for plan in plans:
            self.paths.addItem(f"{plan.status}  |  {plan.path}")
        self.diff = QPlainTextEdit()
        self.diff.setReadOnly(True)
        self.diff.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))

        def show_file(row):
            if row >= 0:
                plan = plans[row]
                actions = "\n".join(plan.actions)
                self.diff.setPlainText((plan.diff or "변경 없음") + "\n\n" + actions)

        self.paths.currentRowChanged.connect(show_file)
        split.addWidget(self.paths)
        split.addWidget(self.diff)
        split.setSizes([180, 400])
        layout.addWidget(split, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Cancel).setText("취소")
        save = buttons.addButton("백업 후 저장", QDialogButtonBox.AcceptRole)
        save.setProperty("primary", True)
        save.setEnabled(any(p.changed for p in plans))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.paths.setCurrentRow(next((i for i, plan in enumerate(plans) if plan.changed), 0))


class MainWindow(QMainWindow):
    def __init__(self, persist=True):
        super().__init__()
        self.persist = persist
        self.settings = QSettings()
        self.source = None
        self.source_path = None
        self.entries = {}
        self.current_key = None
        self.material_items = {}
        self.visible_count = 0
        self.setWindowTitle(f"CMX Material Manager  {__version__}")
        self.resize(1260, 860)
        self.setMinimumSize(920, 660)
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(16, 12, 16, 10)
        title_row = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(QPixmap(str(Path(__file__).parent / "assets" / "app.png")).scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        title_row.addWidget(icon)
        title = label("CMX Material Manager")
        title.setWordWrap(False)
        title.setProperty("heading", True)
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(button("CMX 열기", self.open_file))
        self.export_button = button("CMX 내보내기", self.export_file)
        title_row.addWidget(self.export_button)
        title_row.addWidget(button("사용 안내", self.show_help))
        outer.addLayout(title_row)
        self.file_label = label("CMX 라이브러리를 열어 시작하세요.", True)
        self.file_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        outer.addWidget(self.file_label)
        self.vertical = QSplitter(Qt.Vertical)
        self.horizontal = QSplitter()
        self.vertical.setChildrenCollapsible(False)
        self.horizontal.setChildrenCollapsible(False)
        library = QGroupBox("01  물질 라이브러리")
        lib = QVBoxLayout(library)
        self.search = QLineEdit()
        self.search.setPlaceholderText("이름 / 속성 검색")
        self.search.textChanged.connect(self.filter_materials)
        lib.addWidget(self.search)
        self.count = label("0개 물질", True)
        lib.addWidget(self.count)
        self.materials = QListWidget()
        self.materials.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.materials.currentItemChanged.connect(self.selection_changed)
        self.materials.itemSelectionChanged.connect(self.update_selection_status)
        lib.addWidget(self.materials, 1)
        actions = QHBoxLayout()
        self.new_button = button("새 물질", self.new_material)
        self.copy_button = button("복제", self.copy_material)
        actions.addWidget(self.new_button)
        actions.addWidget(self.copy_button)
        lib.addLayout(actions)
        self.include_button = button("선택 물질 동기화에 포함", self.include_material)
        self.include_button.setToolTip("목록에서 Ctrl+클릭으로 개별 선택, Shift+클릭으로 범위 선택, Ctrl+A로 검색 결과 전체 선택")
        lib.addWidget(self.include_button)
        library.setMinimumWidth(225)
        edit_box = QGroupBox("02  물질 속성")
        edit_layout = QVBoxLayout(edit_box)
        self.editor = MaterialEditor()
        self.editor.changed.connect(self.update_status)
        edit_layout.addWidget(self.editor, 1)
        edit_actions = QHBoxLayout()
        self.edit_status = label("물질을 선택하세요.", True)
        edit_actions.addWidget(self.edit_status, 1)
        self.revert_button = button("선택 변경 취소", self.revert_editor)
        self.stage_button = button("편집 반영", self.stage_current, True)
        edit_actions.addWidget(self.revert_button)
        edit_actions.addWidget(self.stage_button)
        edit_layout.addLayout(edit_actions)
        self.horizontal.addWidget(library)
        self.horizontal.addWidget(edit_box)
        self.horizontal.setStretchFactor(1, 1)
        self.horizontal.setSizes([285, 930])
        self.vertical.addWidget(self.horizontal)
        targets_box = QGroupBox("03  일괄 저장 경로")
        targets_layout = QVBoxLayout(targets_box)
        targets_top = QHBoxLayout()
        targets_top.addWidget(label("기준 파일 + 체크한 대상에 반영", True), 1)
        targets_top.addWidget(button("파일 추가", self.add_files))
        targets_top.addWidget(button("경로 붙여넣기", self.paste_paths))
        targets_top.addWidget(button("목록 열기", self.import_paths))
        targets_top.addWidget(button("목록 저장", self.export_paths))
        targets_top.addWidget(button("제거", self.remove_paths))
        targets_layout.addLayout(targets_top)
        self.targets = QListWidget()
        self.targets.setMinimumHeight(65)
        self.targets.setSelectionMode(QAbstractItemView.ExtendedSelection)
        targets_layout.addWidget(self.targets)
        footer = QHBoxLayout()
        self.pending_label = label("저장 대기 0개 물질", True)
        footer.addWidget(self.pending_label, 1)
        self.sync_all_button = button("전체 자동 동기화", lambda: self.sync_files(all_materials=True))
        self.sync_all_button.setToolTip("검색과 선택에 관계없이 기준 파일의 모든 물질을 체크한 대상과 비교합니다.")
        footer.addWidget(self.sync_all_button)
        self.save_button = button("변경 미리보기 / 일괄 저장", self.sync_files, True)
        footer.addWidget(self.save_button)
        targets_layout.addLayout(footer)
        self.vertical.addWidget(targets_box)
        self.vertical.setSizes([590, 180])
        self.vertical.setStretchFactor(0, 1)
        outer.addWidget(self.vertical, 1)
        self.setCentralWidget(central)
        for text, shortcut, callback in [("열기", QKeySequence.Open, self.open_file),
                                          ("저장", QKeySequence.Save, self.sync_files),
                                          ("검색", QKeySequence.Find, self.search.setFocus)]:
            action = QAction(text, self)
            action.setShortcut(shortcut)
            action.triggered.connect(callback)
            self.addAction(action)
        if persist:
            try:
                self.add_paths(json.loads(self.settings.value("target_paths", "[]")), checked=False)
                geometry = self.settings.value("geometry")
                if geometry:
                    self.restoreGeometry(geometry)
            except (ValueError, TypeError):
                pass
        self.update_status()

    def error(self, message):
        QMessageBox.warning(self, "작업 확인", str(message))

    def open_file(self):
        filename, _ = QFileDialog.getOpenFileName(self, "기준 CMX 파일 열기", str(self.source_path or ""), "CMX library (*.cmx);;XML (*.xml);;All files (*)")
        if filename:
            self.load_file(Path(filename))

    def discard_pending(self):
        if self.editor.dirty or any(entry.pending for entry in self.entries.values()):
            return QMessageBox.question(self, "저장하지 않은 변경", "저장하지 않은 편집과 대기 중인 변경을 버릴까요?", QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel) == QMessageBox.Discard
        return True

    def load_file(self, path, confirm=True):
        if confirm and not self.discard_pending():
            return False
        try:
            document = CmxDocument.load(path)
        except (ValueError, OSError, etree.Error) as error:
            self.error(error)
            return False
        old_source = self.source_path
        self.source = document
        self.source_path = Path(path).resolve()
        self.entries = {element.get("name"): Entry(element.get("name"), material_xml(element), copy.deepcopy(element)) for element in document.materials}
        self.current_key = None
        self.editor.dirty = False
        self.editor.setEnabled(False)
        self.search.clear()
        self.refresh_materials()
        if old_source:
            for index in range(self.targets.count() - 1, -1, -1):
                if self.targets.item(index).data(Qt.UserRole) == str(old_source):
                    self.targets.takeItem(index)
        self.add_paths([str(self.source_path)])
        self.file_label.setText(f"{self.source_path}  ·  형식 {document.root.get('Version', '?')}")
        self.setWindowTitle(f"{self.source_path.name} — CMX Material Manager {__version__}")
        if self.materials.count():
            self.materials.setCurrentRow(0)
        self.update_status()
        return True

    def refresh_materials(self, key=None):
        with QSignalBlocker(self.materials):
            self.material_items.clear()
            self.materials.clear()
            for entry_key, entry in self.entries.items():
                item = MaterialListItem()
                item.setData(Qt.UserRole, entry_key)
                item.refresh(entry)
                self.materials.addItem(item)
                self.material_items[entry_key] = item
            self.materials.sortItems()
            if key is not None:
                self.materials.setCurrentItem(self.material_items[key])
        self.filter_materials()

    def filter_materials(self):
        query = self.search.text().strip().casefold()
        self.visible_count = 0
        with QSignalBlocker(self.materials):
            for item in self.material_items.values():
                hidden = query not in item.text().casefold()
                item.setHidden(hidden)
                if hidden:
                    item.setSelected(False)
                self.visible_count += not hidden
        self.update_selection_status()

    def update_selection_status(self):
        selected = len(self.materials.selectedItems())
        self.count.setText(f"{self.visible_count} / {len(self.entries)}개 물질 · 선택 {selected}개")
        self.include_button.setEnabled(bool(selected))
        current = self.materials.currentItem()
        if current is None or current.data(Qt.UserRole) == self.current_key:
            self.accepted_selection = self.materials.selectionModel().selection()

    def resolve_editor(self):
        if not self.editor.dirty:
            return True
        box = QMessageBox(self)
        box.setWindowTitle("현재 물질 편집")
        box.setText("현재 편집을 저장 대기 목록에 반영할까요?")
        apply = box.addButton("편집 반영", QMessageBox.AcceptRole)
        discard = box.addButton("버리기", QMessageBox.DestructiveRole)
        box.addButton("취소", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is apply:
            return self.stage_current()
        return box.clickedButton() is discard

    def selection_changed(self, current, previous):
        if current is None:
            return
        key = current.data(Qt.UserRole)
        if key == self.current_key:
            return
        if not self.resolve_editor():
            selection = self.accepted_selection
            self.materials.setCurrentItem(previous, QItemSelectionModel.NoUpdate)

            def restore_selection():
                if self.materials.currentItem() is previous:
                    self.materials.selectionModel().select(selection, QItemSelectionModel.ClearAndSelect)

            restore_selection()
            # Qt finishes mouse selection after currentItemChanged returns.
            QTimer.singleShot(0, self, restore_selection)
            return
        self.current_key = key
        self.editor.load(self.entries[key].element, self.source.root.find("DataDescriptions"))
        self.update_status()

    def stage_current(self):
        if self.current_key is None:
            return False
        if self.editor.isAncestorOf(QApplication.focusWidget()):
            self.stage_button.setFocus()
        try:
            element = self.editor.capture()
            name = element.get("name")
            if any(key != self.current_key and entry.element.get("name") == name for key, entry in self.entries.items()):
                raise ValueError(f"이미 존재하는 물질 이름: {name}")
            entry = self.entries[self.current_key]
            renamed = name != entry.element.get("name")
            entry.element = element
            self.editor.load(element, self.source.root.find("DataDescriptions"))
            self.material_items[self.current_key].refresh(entry)
            if renamed:
                self.materials.sortItems()
            self.filter_materials()
            self.update_status()
            return True
        except (ValueError, etree.Error) as error:
            self.error(error)
            return False

    def revert_editor(self):
        if self.current_key is None:
            return
        entry = self.entries[self.current_key]
        if (entry.pending or self.editor.dirty) and QMessageBox.question(
            self, "선택 변경 취소", "이 물질의 편집과 저장 대기 변경을 취소할까요?\n새로 만든 물질은 목록에서 제거됩니다.",
            QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel,
        ) != QMessageBox.Discard:
            return
        if entry.original_name is None:
            del self.entries[self.current_key]
            self.current_key = None
            self.editor.dirty = False
            self.editor.setEnabled(False)
            self.refresh_materials()
            if self.materials.count():
                self.materials.setCurrentRow(0)
        else:
            entry.element = copy.deepcopy(self.source.get(entry.original_name))
            entry.included = False
            self.editor.load(entry.element, self.source.root.find("DataDescriptions"))
            self.material_items[self.current_key].refresh(entry)
            self.materials.sortItems()
            self.filter_materials()
        self.update_status()

    def new_material(self):
        if self.source is None or not self.resolve_editor():
            return
        name, ok = QInputDialog.getText(self, "새 물질", "물질 이름")
        if not ok or not name.strip():
            return
        kind, ok = QInputDialog.getItem(self, "새 물질", "시작 모델 · 초기값은 예제이므로 실제 물성으로 수정하세요.", ["Dielectric", "Metal", "Thermal"], 0, False)
        if ok:
            try:
                self.add_entry(create_material(name.strip(), kind))
            except ValueError as error:
                self.error(error)

    def copy_material(self):
        if self.current_key is None or not self.resolve_editor():
            return
        element = copy.deepcopy(self.entries[self.current_key].element)
        name, ok = QInputDialog.getText(self, "물질 복제", "새 물질 이름", text=element.get("name") + "_copy")
        if ok and name.strip():
            element.set("name", name.strip())
            self.add_entry(element)

    def add_entry(self, element):
        if any(e.element.get("name") == element.get("name") for e in self.entries.values()):
            self.error("이미 존재하는 물질 이름입니다.")
            return
        key = uuid4().hex
        self.entries[key] = Entry(None, "", element)
        self.current_key = key
        self.search.clear()
        self.editor.load(element, self.source.root.find("DataDescriptions"))
        self.refresh_materials(key)
        self.update_status()

    def include_material(self):
        self.include_button.setFocus()
        selected = self.materials.selectedItems()
        if self.materials.currentItem() in selected and self.editor.dirty and not self.stage_current():
            return
        for item in selected:
            if not item.isHidden():
                entry = self.entries[item.data(Qt.UserRole)]
                entry.included = True
                item.refresh(entry)
        self.update_status()

    def add_paths(self, paths, checked=True):
        existing = {os.path.normcase(self.targets.item(i).data(Qt.UserRole)) for i in range(self.targets.count())}
        for raw in paths:
            if not isinstance(raw, str) or not raw.strip():
                continue
            path = str(Path(os.path.expandvars(raw.strip().strip('"'))).expanduser().resolve())
            if os.path.normcase(path) in existing:
                continue
            item = QListWidgetItem(path)
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            self.targets.addItem(item)
            existing.add(os.path.normcase(path))
        for i in range(self.targets.count()):
            item = self.targets.item(i)
            if self.source_path and item.data(Qt.UserRole) == str(self.source_path):
                item.setText("기준  |  " + str(self.source_path))
                item.setCheckState(Qt.Checked)
                item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "일괄 저장 대상", "", "CMX library (*.cmx);;All files (*)")
        self.add_paths(paths)

    def paste_paths(self):
        text, ok = QInputDialog.getMultiLineText(self, "경로 목록", "한 줄에 파일 경로 하나씩 입력하세요.")
        if ok:
            self.add_paths(text.splitlines())

    def import_paths(self):
        filename, _ = QFileDialog.getOpenFileName(self, "경로 목록 열기", "", "경로 목록 (*.txt)")
        if filename:
            try:
                self.add_paths(Path(filename).read_text(encoding="utf-8-sig").splitlines())
            except (OSError, ValueError) as error:
                self.error(error)

    def export_paths(self):
        filename, _ = QFileDialog.getSaveFileName(self, "경로 목록 저장", "cmx-paths.txt", "경로 목록 (*.txt)")
        if filename:
            try:
                Path(filename).write_text("\n".join(self.targets.item(i).data(Qt.UserRole) for i in range(self.targets.count())) + "\n", encoding="utf-8")
            except OSError as error:
                self.error(error)

    def remove_paths(self):
        for item in self.targets.selectedItems():
            if item.data(Qt.UserRole) != str(self.source_path):
                self.targets.takeItem(self.targets.row(item))

    def sync_files(self, *, all_materials=False):
        self.save_button.setFocus()
        if self.source is None:
            return
        if self.editor.dirty and not self.stage_current():
            return
        changes = [Change(entry.original_name, material_xml(entry.element)) for entry in self.entries.values()
                   if all_materials or entry.pending]
        if not changes:
            QMessageBox.information(self, "변경 없음", "물질을 편집하거나 '선택 물질 동기화에 포함'을 누르세요.")
            return
        paths = [self.targets.item(i).data(Qt.UserRole) for i in range(self.targets.count()) if self.targets.item(i).checkState() == Qt.Checked]
        try:
            plans = prepare_sync(paths, changes, source=self.source)
            preview = PreviewDialog(plans, self)
            if all_materials:
                preview.setWindowTitle(f"전체 자동 동기화 · 기준 물질 {len(changes)}개")
            if preview.exec() != QDialog.Accepted:
                return
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                backups = apply_sync(plans)
            finally:
                QApplication.restoreOverrideCursor()
            self.load_file(self.source_path, confirm=False)
            report = "\n".join(f"{path}\n  백업: {backup}" for path, backup in backups.items())
            box = QMessageBox(self)
            box.setWindowTitle("저장 완료")
            box.setText(f"{len(backups)}개 파일 저장 완료.\nCadence 애플리케이션에서 라이브러리를 다시 불러오세요.")
            box.setDetailedText(report)
            box.exec()
            self.statusBar().showMessage(f"{len(backups)}개 파일 저장 · 각 원본 폴더에 백업 생성")
        except (ValueError, OSError, RuntimeError, etree.Error) as error:
            self.error(error)

    def export_file(self):
        self.export_button.setFocus()
        if self.source is None or (self.editor.dirty and not self.stage_current()):
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "현재 라이브러리 CMX 내보내기",
            str(self.source_path.with_name(self.source_path.stem + "-export.cmx")),
            "CMX library (*.cmx)",
        )
        if not filename:
            return
        path = Path(filename)
        if not path.suffix:
            path = path.with_suffix(".cmx")
        try:
            changes = [Change(e.original_name, material_xml(e.element)) for e in self.entries.values() if e.pending]
            backup = export_cmx(path, self.source, changes)
            message = f"CMX 내보내기 완료\n{path}\n\n기준 파일과 일괄 저장 대상은 변경하지 않았습니다."
            if backup:
                message += f"\n백업: {backup}"
            QMessageBox.information(self, "내보내기 완료", message)
        except (ValueError, OSError, RuntimeError, etree.Error) as error:
            self.error(error)

    def update_status(self):
        loaded = self.source is not None
        self.sync_all_button.setEnabled(bool(self.entries))
        selected = self.current_key is not None
        for widget in (self.new_button, self.save_button, self.export_button):
            widget.setEnabled(loaded)
        for widget in (self.copy_button, self.stage_button, self.revert_button):
            widget.setEnabled(selected)
        self.update_selection_status()
        count = sum(entry.pending for entry in self.entries.values())
        self.pending_label.setText(f"저장 대기 {count}개 물질 · 원본 폴더에 자동 백업")
        self.edit_status.setText("반영하지 않은 편집 있음" if self.editor.dirty else "편집 반영 후 일괄 저장" if selected else "물질을 선택하세요.")
        self.statusBar().showMessage("Ctrl+O 열기  ·  Ctrl+F 검색  ·  Ctrl+S 미리보기 / 저장")

    def show_help(self):
        QMessageBox.information(self, "사용 안내", "1. 기준 CMX 파일 열기\n2. 물질 선택 → 표 또는 XML 편집 → 편집 반영\n3. 대상 파일 추가 또는 줄 단위 경로 목록 입력\n4. 변경 미리보기 확인 → 백업 후 저장\n\n별도 파일: 'CMX 내보내기'로 현재 라이브러리 전체를 저장합니다.\n내보내기는 기준 파일과 일괄 저장 대상을 변경하지 않습니다.\nCtrl·Shift로 여러 물질을 선택해 저장 대기에 포함할 수 있습니다.\n'전체 자동 동기화'는 검색 범위와 관계없이 모든 물질을 비교합니다.\n같은 이름의 대상 물질 전체가 교체됩니다.\n기준 파일은 항상 일괄 저장 대상에 포함됩니다.\n재시작하면 기억한 경로는 체크 해제됩니다.\n\nCadence에서 파일을 사용 중이라면 닫고 저장하세요.\nProgram Files 등 보호된 대상은 쓰기 권한이 필요합니다.\n새 물질의 초기값은 예제이며 실제 사양으로 바꿔야 합니다.\n\n독립 도구 · Cadence 공식 제품이 아닙니다.")

    def closeEvent(self, event):
        if not self.discard_pending():
            event.ignore()
            return
        if self.persist:
            self.settings.setValue("geometry", self.saveGeometry())
            self.settings.setValue("target_paths", json.dumps([self.targets.item(i).data(Qt.UserRole) for i in range(self.targets.count())]))
        event.accept()
