from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    for role, color in {
        QPalette.Window: "#202226", QPalette.WindowText: "#eceef1",
        QPalette.Base: "#1d2025", QPalette.AlternateBase: "#25282e",
        QPalette.Text: "#eceef1", QPalette.Button: "#363b43",
        QPalette.ButtonText: "#eceef1", QPalette.Highlight: "#386cb0",
        QPalette.HighlightedText: "#ffffff", QPalette.PlaceholderText: "#a9b2bf",
        QPalette.ToolTipBase: "#2b2e34", QPalette.ToolTipText: "#eceef1",
        QPalette.Link: "#8fc1ff", QPalette.Light: "#626b78",
        QPalette.Dark: "#15181d", QPalette.Mid: "#555e6b",
    }.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor("#929ba8"))
    app.setPalette(palette)
    font = app.font()
    font.setFamily("Segoe UI")
    font.setPointSize(10)
    app.setFont(font)
    app.setStyleSheet("""
        QMainWindow, QDialog { background: #202226; }
        QGroupBox { background: #2b2e34; border: 1px solid #505761;
            border-radius: 5px; margin-top: 13px; padding: 13px 8px 8px; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px;
            color: #eceef1; font-weight: bold; }
        QLabel { background: transparent; }
        QLabel[muted="true"] { color: #b9c1cc; }
        QLabel[heading="true"] { font-size: 21px; font-weight: 700; }
        QLineEdit, QComboBox, QAbstractItemView, QPlainTextEdit {
            background: #1d2025; color: #eceef1; border: 1px solid #626c7a;
            border-radius: 3px; selection-background-color: #386cb0;
            selection-color: white; }
        QLineEdit, QComboBox { padding: 5px; min-height: 20px; }
        QLineEdit:focus, QComboBox:focus, QAbstractItemView:focus, QPlainTextEdit:focus {
            border: 1px solid #8fc1ff; }
        QPlainTextEdit { background: #15181d; padding: 5px; }
        QTreeWidget::item, QListWidget::item { padding: 5px 3px; }
        QAbstractItemView::item:selected { background: #345d8c; color: white; }
        QHeaderView::section { background: #353a42; color: #eceef1;
            padding: 6px; border: 1px solid #505761; font-weight: 600; }
        QTableWidget { gridline-color: #505761; }
        QPushButton { background: #363b43; border: 1px solid #626c7a;
            padding: 6px 11px; border-radius: 4px; min-height: 21px; }
        QPushButton:hover { background: #454c57; }
        QPushButton:focus { border: 1px solid #8fc1ff; }
        QPushButton:pressed { background: #252a31; }
        QPushButton:disabled { background: #292d33; color: #929ba8; border-color: #444b55; }
        QPushButton[primary="true"] { background: #386cb0; color: white; border-color: #6496d6; }
        QPushButton[primary="true"]:hover { background: #447fc8; }
        QTabWidget::pane { border: 1px solid #505761; }
        QTabBar::tab { background: #2b2e34; padding: 8px 14px; }
        QTabBar::tab:selected { background: #3b4656; color: #ffffff; }
        QSplitter::handle { background: #363b43; }
        QStatusBar { color: #b9c1cc; }
        QToolTip { border: 1px solid #626c7a; padding: 4px; }
    """)
