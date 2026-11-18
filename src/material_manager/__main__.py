import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from material_manager import __version__
from material_manager.theme import apply_theme
from material_manager.ui import MainWindow


def main() -> int:
    parser = argparse.ArgumentParser(description="CMX Material Manager")
    parser.add_argument("--version", action="version", version=f"CMX Material Manager {__version__}")
    parser.add_argument("file", nargs="?", help="CMX library to open")
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setOrganizationName("CMX Material Manager")
    app.setApplicationName("CMX Material Manager")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "assets" / "app.ico")))
    apply_theme(app)
    window = MainWindow(persist=not args.smoke_test)
    if args.file:
        window.load_file(Path(args.file))
    window.show()
    if args.smoke_test:
        QTimer.singleShot(800, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
