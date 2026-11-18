"""Previewed CMX updates with per-file replacement and recoverable batch writes."""

from copy import deepcopy
from dataclasses import dataclass
import difflib
import hashlib
import os
from pathlib import Path
import stat
import tempfile

from .cmx import CmxDocument, material_xml, parse_material


@dataclass(frozen=True)
class Change:
    original_name: str | None
    material: str


@dataclass(frozen=True)
class SyncPlan:
    path: Path
    digest: str
    output: bytes
    actions: tuple[str, ...]
    diff: str

    @property
    def changed(self):
        return bool(self.diff)

    @property
    def status(self):
        return "변경 예정" if self.changed else "변경 없음"


def _schema_node(node):
    return (node.tag, sorted(node.attrib.items()), (node.text or "").strip(),
            [_schema_node(child) for child in node if isinstance(child.tag, str)])


def _schema(doc):
    return (doc.root.get("Version"), [_schema_node(n) for n in doc.root.findall("DataDescriptions")])


def _plan(doc, edits):
    materials = {m.get("name"): m for m in doc.materials}
    replacements, additions, actions, diffs = {}, [], [], []
    for original, material in edits:
        name = material.get("name")
        lookup_name = original if original is not None else name
        current = materials.get(lookup_name)
        existing = materials.get(name)
        xml = material_xml(material)
        # Material fragments inherit the destination root's namespace declarations.
        target_xml = xml
        if doc.root.nsmap:
            parent = doc.root.makeelement("Cadence_Material_Lib", nsmap=doc.root.nsmap)
            parent.append(deepcopy(material))
            target_xml = material_xml(parent[0])
        if existing is not None and existing is not current:
            if current is None and material_xml(existing) == target_xml:
                actions.append(f"동일 · {name}")
                continue
            raise ValueError(f"재질 이름 충돌 · {name}")
        old_xml = material_xml(current) if current is not None else ""
        if old_xml == target_xml:
            actions.append(f"동일 · {name}")
            continue
        if current is None:
            additions.append(material)
            actions.append(f"추가 · {name}")
        else:
            replacements[lookup_name] = material
            actions.append(f"수정 · {name}" if lookup_name == name else f"이름 변경 · {original} → {name}")
        diffs.extend(difflib.unified_diff(old_xml.splitlines(), xml.splitlines(),
                                          fromfile=lookup_name if current is not None else "(새 재질)",
                                          tofile=name, lineterm=""))
    return SyncPlan(doc.path, doc.digest, doc.patched_bytes(replacements, additions),
                    tuple(actions), "\n".join(diffs))


def _parse_changes(changes):
    edits = [(c.original_name, parse_material(c.material)) for c in changes]
    names = [m.get("name") for _, m in edits]
    originals = [old for old, _ in edits if old is not None]
    if len(set(names)) != len(names) or len(set(originals)) != len(originals):
        raise ValueError("적용할 재질 이름이 중복됩니다.")
    if any(name in originals and old != name for (old, _), name in zip(edits, names)):
        raise ValueError("다른 변경과 새 이름이 충돌합니다.")
    return edits


def prepare_sync(paths, changes, source=None):
    paths = list(dict.fromkeys(Path(p).resolve() for p in paths))
    if not paths:
        raise ValueError("적용할 CMX 파일을 선택하세요.")
    edits = _parse_changes(changes)
    schema = _schema(source) if source is not None else None
    plans = []
    for path in paths:
        try:
            doc = CmxDocument.load(path)
            if source is not None and path == source.path and doc.digest != source.digest:
                raise ValueError("원본을 연 뒤 파일이 변경되었습니다. 다시 열어 주세요.")
            if schema is None:
                schema = _schema(doc)
            if _schema(doc) != schema:
                raise ValueError("CMX 버전 또는 데이터 열·단위 정의가 다릅니다.")
            plans.append(_plan(doc, edits))
        except (OSError, ValueError) as exc:
            raise ValueError(f"{path}\n{exc}") from exc
    return plans


def _read_checked(plan):
    data = plan.path.read_bytes()
    if hashlib.sha256(data).hexdigest() != plan.digest:
        raise ValueError(f"미리보기 후 파일이 변경되었습니다. 다시 확인하세요.\n{plan.path}")
    return data


def _sibling(path, data, suffix):
    fd, filename = tempfile.mkstemp(prefix=path.name + ".", suffix=suffix, dir=path.parent)
    temporary = Path(filename)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
        return temporary
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _replace(path, data, expected_digest):
    temporary = _sibling(path, data, ".tmp")
    try:
        if expected_digest is None:
            # Both operations fail if a competing writer created this destination.
            if os.name == "nt":
                os.rename(temporary, path)
            else:
                os.link(temporary, path)
            return
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected_digest:
            raise ValueError(f"파일이 변경되어 교체를 중단했습니다.\n{path}")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def apply_sync(plans):
    plans = list(plans)
    if len({plan.path for plan in plans}) != len(plans):
        raise ValueError("같은 대상 파일이 두 번 지정되었습니다.")
    for plan in plans:
        _read_checked(plan)
        if plan.changed and not plan.path.stat().st_mode & stat.S_IWRITE:
            raise OSError(f"읽기 전용 파일은 교체할 수 없습니다.\n{plan.path}")

    backups, written = {}, []
    try:
        for plan in plans:
            if plan.changed:
                backups[plan.path] = _sibling(plan.path, _read_checked(plan), ".bak")
        for plan in plans:
            if plan.changed:
                _replace(plan.path, plan.output, plan.digest)
                written.append(plan)
    except (OSError, ValueError) as exc:
        failures = []
        for plan in reversed(written):
            try:
                recovery = backups[plan.path].read_bytes()
                if hashlib.sha256(recovery).hexdigest() != plan.digest:
                    raise ValueError("백업 파일의 내용이 바뀌었습니다.")
                _replace(plan.path, recovery, hashlib.sha256(plan.output).hexdigest())
            except (ValueError, OSError) as restore_exc:
                failures.append(f"{plan.path} · {restore_exc}")
        details = [f"적용 중단 · {exc}"]
        if written:
            details.append(f"자동 복원 · {len(written) - len(failures)}/{len(written)}개")
        details.extend(failures)
        details.extend(f"백업 · {path} → {backup}" for path, backup in backups.items())
        raise RuntimeError("\n".join(details)) from exc
    return backups
