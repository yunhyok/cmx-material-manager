# Windows x64 빌드

## 01 / 개발 환경 준비

Windows x64, Python 3.12.10 x64, Inno Setup 6.3 이상 또는 7 필요. `ISCC.exe`를 PATH에 추가할 것. 기본 경로에 설치한 Inno Setup 6은 자동 검색. 저장소 루트에서 PowerShell 사용.

설치 대상은 Windows 10 버전 1809 이상 또는 Windows 11. [Qt 6.11 지원 플랫폼](https://doc.qt.io/qt-6.11/supported-platforms.html)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m material_manager
```

핵심 의존성은 PySide6 Essentials·Shiboken6 6.11.0, lxml 6.1.1, PyInstaller 6.20.0, pytest 9.0.3. 전체 버전은 `pyproject.toml`과 `requirements-dev.txt`에 지정.

## 02 / 설치 파일 생성

```powershell
.\scripts\build.ps1
```

PyInstaller 실행 폴더 생성 후 Qt 비표시 화면에서 앱 기동·종료 확인. Inno Setup 설치 파일 생성과 SHA-256 출력.

| 결과 | 경로 |
| --- | --- |
| 실행 파일 | `dist/CMX Material Manager/CMX Material Manager.exe` |
| Windows 설치 파일 | `dist/CMX-Material-Manager-0.2.0-windows-x64-setup.exe` |
| 배포 라이선스 | 실행 폴더의 `_internal/licenses/` |
| 사용 가이드·예제 | 실행 폴더의 `docs/USER_GUIDE.md`, `examples/demo.cmx` |

설치 경로 기본값은 Windows의 `Program Files\CMX Material Manager`. 설치 화면에서 다른 드라이브·폴더 선택 가능. 설치에는 관리자 권한 필요. 앱은 실행한 사용자의 권한으로 동작.

## 03 / GitHub Actions

푸시·PR에서 Windows 테스트 실행. `v*` 태그 푸시 또는 수동 실행 시 설치 파일 빌드, 지정 폴더 설치·실행·제거 검증. 완료된 실행의 **Windows-x64-installer** 아티팩트에서 다운로드.
