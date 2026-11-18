from pathlib import Path

from PyInstaller.utils.hooks.qt import add_qt6_dependencies

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
# The widget editor renders PNG natively and reads its Windows icon through qico.
plugins = {"qwindows.dll", "qoffscreen.dll", "qico.dll"}
binaries = [(path, folder) for path, folder in binaries if Path(path).name in plugins]
