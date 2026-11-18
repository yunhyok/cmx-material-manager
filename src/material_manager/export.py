"""Export the working material library without changing the source."""

import hashlib
from pathlib import Path
import stat

from .cmx import CmxDocument
from .sync import Change, _parse_changes, _plan, _replace, _sibling


def export_cmx(path, source: CmxDocument, changes: list[Change]) -> Path | None:
    path = Path(path).resolve()
    if path == source.path:
        raise ValueError("원본 파일은 일괄 적용으로 저장하세요.")
    try:
        previous = path.read_bytes()
    except FileNotFoundError:
        previous = None
    if previous is not None and not path.stat().st_mode & stat.S_IWRITE:
        raise OSError(f"읽기 전용 파일에 내보낼 수 없습니다.\n{path}")
    output = _plan(source, _parse_changes(changes)).output
    if previous is None:
        _replace(path, output, None)
        return None
    digest = hashlib.sha256(previous).hexdigest()
    backup = _sibling(path, previous, ".bak")
    try:
        _replace(path, output, digest)
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"내보내기 중단 · {exc}\n백업 · {backup}") from exc
    return backup
