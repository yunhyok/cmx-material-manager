# Third-party notices

CMX Material Manager is an independent editor. Cadence and its product names belong to their respective owners. The original application is distributed under the MIT license in `LICENSE`.

## Qt, PySide6 and Shiboken6 6.11.0

Copyright The Qt Company Ltd. and other contributors. The Windows package uses the open-source LGPLv3 option for the Qt Widgets, GUI and Core libraries, their runtime plugins, PySide6 and Shiboken6. Full GNU LGPLv3 and GPLv3 texts, component notices and licenses are installed in `_internal/licenses`. The libraries are dynamically loaded from `_internal/PySide6` and `_internal/shiboken6`. Users may replace them with compatible modified builds and reverse-engineer the application to debug those modifications.

The corresponding unmodified sources, including build instructions, are available at these upstream locations.

- [Qt Base 6.11.0 and translations](https://download.qt.io/archive/qt/6.11/6.11.0/submodules/)
- [PySide6 and Shiboken6 6.11.0](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.0-src/)

## lxml 6.1.1

Copyright Infrae and contributors. lxml uses the BSD 3-Clause license and incorporates ElementTree-derived code. The upstream Windows wheel includes libxml2, libxslt, zlib and GNU libiconv. Their notices and terms accompany the application in `_internal/licenses`. The lxml extension can be rebuilt with modified native libraries and replaced in `_internal/lxml`. [lxml 6.1.1 source](https://github.com/lxml/lxml/tree/lxml-6.1.1) · [Windows dependency sources and build scripts](https://github.com/lxml/libxml2-win-binaries/tree/2026.05.17)

## Python, bootloader and installer

Python 3.12 is distributed under the PSF license and the additional notices in `_internal/licenses/python/LICENSE.txt`. The PyInstaller bootloader is distributed under GPLv2 or later with its bootloader exception, reproduced in `_internal/licenses/pyinstaller/COPYING.txt`. The Windows installer was built with Inno Setup, copyright Jordan Russell and Martijn Laan. [Python source](https://www.python.org/downloads/release/python-31210/) · [PyInstaller source](https://github.com/pyinstaller/pyinstaller/tree/v6.20.0) · [Inno Setup](https://jrsoftware.org/isinfo.php)
