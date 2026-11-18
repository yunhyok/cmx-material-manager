import sys
import tomllib
from importlib.metadata import distribution
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable,
    VSVersionInfo, VarFileInfo, VarStruct,
)

root = Path(SPECPATH).parent
name = "CMX Material Manager"
version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
numeric_version = tuple(map(int, version.split("."))) + (0,)
strings = {
    "CompanyName": "yunhyok", "FileDescription": name, "ProductName": name,
    "FileVersion": version, "ProductVersion": version, "OriginalFilename": name + ".exe",
}
metadata = VSVersionInfo(
    ffi=FixedFileInfo(filevers=numeric_version, prodvers=numeric_version),
    kids=[
        StringFileInfo([StringTable("040904B0", [StringStruct(k, v) for k, v in strings.items()])]),
        VarFileInfo([VarStruct("Translation", [0x409, 1200])]),
    ],
)

assets = root / "src/material_manager/assets"
datas = [
    (str(assets / "app.ico"), "material_manager/assets"),
    (str(assets / "app.png"), "material_manager/assets"),
    (str(root / "LICENSE"), "licenses/application"),
    (str(root / "THIRD_PARTY_NOTICES.md"), "licenses"),
    (str(root / "packaging/licenses"), "licenses"),
    (str(Path(sys.base_prefix) / "LICENSE.txt"), "licenses/python"),
]
for package, names in (
    ("lxml", ["LICENSE.txt", "LICENSES.txt"]),
    ("pyinstaller", ["COPYING.txt"]),
):
    wheel = distribution(package)
    for filename in names:
        item = next(p for p in wheel.files if p.as_posix().endswith(".dist-info/licenses/" + filename))
        datas.append((str(wheel.locate_file(item)), "licenses/" + package))

a = Analysis(
    [str(root / "packaging/launcher.py")],
    pathex=[str(root / "src")], datas=datas,
    hookspath=[str(root / "packaging/hooks")],
    hiddenimports=["PySide6.support.deprecated"],
    module_collection_mode={"PySide6": "py", "shiboken6": "py"},
    excludes=["PyQt5", "PyQt6", "PySide2", "PySide6.QtNetwork", "tkinter"],
)
# Qt Widgets uses raster painting here. No OpenGL software fallback is used.
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() != "opengl32sw.dll"]
exe = EXE(
    PYZ(a.pure), a.scripts, [], exclude_binaries=True, name=name,
    console=False, icon=str(assets / "app.ico"), version=metadata, upx=False,
)
COLLECT(exe, a.binaries, a.datas, name=name, upx=False)
