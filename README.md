# CMX Material Manager

Cadence Allegro·Sigrity에서 사용하는 CMX 물질 라이브러리의 독립 Windows 편집기. XML 읽기·물질 생성·속성 편집·여러 파일 일괄 저장·별도 CMX 내보내기 지원.

[Windows 설치 파일](https://github.com/yunhyok/cmx-material-manager/releases/latest) · [사용 가이드](docs/USER_GUIDE.md) · [빌드 방법](docs/BUILD.md) · [오픈소스 고지](THIRD_PARTY_NOTICES.md)

## 01 / 주요 기능

| 기능 | 동작 |
| --- | --- |
| 물질 탐색 | 이름·속성 검색, 금속·유전체·열 모델 표시 |
| 물질 편집 | 물질 정보, 모델별 수치 표, 속성, XML 편집 |
| 새 물질 | 유전체·금속·열 모델 생성, 기존 물질 복제 |
| 선택 동기화 | Ctrl·Shift로 여러 물질 선택 후 저장 대기에 추가 |
| 전체 자동 동기화 | 기준 라이브러리 전체를 체크한 대상과 비교해 추가·변경 사항을 한 번에 반영 |
| 일괄 저장 | 경로 붙여넣기, UTF-8 텍스트 경로 목록, 대상별 변경 미리보기 |
| CMX 내보내기 | 편집을 포함한 전체 라이브러리를 별도 파일로 저장 |
| 저장 보호 | 자동 백업, 외부 변경 감지, 파일별 교체, 오류 시 복원 시도 |

같은 이름의 물질 전체를 대상 파일에 반영. 다른 물질·주석·확장 항목·파일 인코딩·줄바꿈 보존. 이름 변경 시 다른 물질과 충돌하면 중단. **대상 물질 안에만 존재하던 속성도 기준 물질의 내용으로 교체됨. 저장 전 차이 확인 필요.**

## 02 / 설치와 시작

1. [Releases](https://github.com/yunhyok/cmx-material-manager/releases/latest)에서 `windows-x64-setup.exe` 다운로드.
2. 설치 경로 확인. 기본값 `Program Files\CMX Material Manager`; 다른 드라이브·폴더 선택 가능.
3. 시작 메뉴에서 **CMX Material Manager** 실행 후 CMX 열기.
4. 물질 편집 → **편집 반영** → 대상 경로 추가 → **변경 미리보기 / 일괄 저장**.

원본을 유지하려면 **CMX 내보내기** 사용. 설치 폴더의 `examples/demo.cmx`는 합성 예제이며 설계용 물성 데이터가 아님. 새 물질의 초기값도 실제 사양으로 수정할 것.

## 03 / 검증과 한계

- 제공된 CMX 형식 `1.05`와 물질 347개 읽기·재직렬화 검증. 실제 원본은 저장소·설치 파일에 미포함.
- 단위·열 정의와 CMX 버전이 일치하는 대상끼리 일괄 저장. 스키마 변환 기능 없음.
- Cadence 애플리케이션 내부 캐시 갱신은 자동 처리하지 않음. 해당 애플리케이션에서 라이브러리를 다시 불러올 것.
- 다중 파일 저장은 순차 처리. 전원 차단까지 포함한 전체 파일 원자성 보장 불가. 각 파일의 `.bak`로 복원 가능.
- 초기 릴리스의 실행 파일·설치 파일은 코드 서명 없음. Windows에서 게시자 확인 경고가 표시될 수 있음.
- Allegro·Sigrity 제품 안에서의 실제 재로딩 검증은 별도 필요.

## 04 / 개발

Python 3.12 x64·PySide6 Essentials·lxml 사용. 설치 프로그램은 PyInstaller·Inno Setup 사용. [상세 빌드 안내](docs/BUILD.md) 참고.

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m material_manager
```

MIT License. Cadence 또는 해당 제품의 공식·인증 도구가 아님. 각 상표는 해당 소유자에게 귀속.
