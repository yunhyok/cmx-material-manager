"""CMX document parsing and material editing."""

import codecs
import hashlib
import io
import math
from pathlib import Path
import re
from xml.parsers import expat

from lxml import etree as ET


class _DenyExternal(ET.Resolver):
    def resolve(self, url, public_id, context):
        raise ValueError("외부 XML 리소스를 사용할 수 없습니다.")


def _parse(data):
    encoding = None
    if isinstance(data, str):
        # Editor text has already been decoded, irrespective of its declaration.
        data = data.encode("utf-8")
        encoding = "utf-8"
    parser = ET.XMLParser(resolve_entities=False, load_dtd=False, no_network=True,
                          remove_blank_text=False, strip_cdata=False, encoding=encoding)
    parser.resolvers.add(_DenyExternal())
    try:
        tree = ET.parse(io.BytesIO(data), parser)
    except (ET.XMLSyntaxError, LookupError) as exc:
        raise ValueError(f"XML 형식 오류 · {exc}") from exc
    if tree.docinfo.doctype:
        raise ValueError("DOCTYPE 선언을 포함한 XML은 열 수 없습니다.")
    return tree


_TABLE_WIDTHS = {
    "Dielectric/Model": 3, "Metal/Model": 2, "Thermal/Model": 6, "Magnetic/Model": 3,
    "Structural/Elasticity": 3, "Structural/CTE": 2,
    "Structural/Viscoplastic/Anand": 9, "Structural/Viscoplastic/ModifiedAnand": 14,
    "Structural/Fatigue/Darveaux": 7, "Structural/Fatigue/Solomon": 2,
    **{f"SurfaceRoughness/{tag}": 2 for tag in ("Huray", "ModHammerstad", "ModGroisse")},
    **{f"Structural/Failure/{tag}": 1 for tag in
       ("Tension", "Compression", "MaxPressure", "EffectiveStrain", "MaxStrain")},
}

_DIMENSION = re.compile(r"([+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)"
                        r"\s*(mil|mm|cm|um|µm|μm|m|in|nm)?", re.IGNORECASE)


def _finite(value):
    try:
        return "_" not in value and math.isfinite(float(value))
    except ValueError:
        return False


def _name(element):
    name = element.get("name", "")
    if not name.strip():
        raise ValueError("재질 이름을 입력하세요.")
    return name


def validate_material(element):
    if element.tag != "Material":
        raise ValueError("Material 요소가 필요합니다.")
    _name(element)
    for key in ("DefaultThickness", "UpperTolerance", "LowerTolerance"):
        if key in element.attrib:
            match = _DIMENSION.fullmatch(element.get(key).strip())
            if match is None or not _finite(match.group(1)):
                raise ValueError(f"{key}에는 유한한 숫자를 입력하세요. "
                                 "단위는 생략하거나 mil, mm, cm, um, µm, m, in, nm를 사용할 수 있습니다.")
    for path, width in _TABLE_WIDTHS.items():
        for node in element.findall(path):
            for key in ("Temperature", "RefTemperature", "Er", "Sigma"):
                if key in node.attrib and not _finite(node.get(key)):
                    raise ValueError(f"{path} @{key} 값은 유한한 숫자여야 합니다.")
            # Extension elements may have their own textual data.
            own_text = (node.text or "") + "".join(child.tail or "" for child in node)
            rows = [line.split() for line in own_text.splitlines() if line.strip()]
            if not rows and path.endswith("/Model") and not any(isinstance(child.tag, str) for child in node):
                raise ValueError(f"{path}에 데이터 행을 입력하세요.")
            for number, cells in enumerate(rows, 1):
                if len(cells) != width or not all(_finite(cell) for cell in cells):
                    raise ValueError(f"{path} {number}행에는 유한한 숫자 {width}개가 필요합니다.")


def material_xml(element):
    return ET.tostring(element, encoding="unicode", with_tail=False)


def parse_material(xml):
    tree = _parse(xml)
    element = tree.getroot()
    if element.getprevious() is not None or element.getnext() is not None:
        raise ValueError("편집할 Material 요소 안에 내용을 입력하세요.")
    validate_material(element)
    return element


def create_material(name, kind="Dielectric"):
    values = {"Dielectric": "1 1 0", "Metal": "20 0", "Thermal": "25 0 0 0 0 0"}
    if kind not in values:
        raise ValueError(f"지원하지 않는 새 재질 유형 · {kind}")
    material = ET.Element("Material", name=name)
    _name(material)
    model = ET.SubElement(ET.SubElement(material, kind), "Model")
    model.text = "\n" + values[kind] + "\n"
    ET.indent(material, space="  ")
    return material


def _material_spans(text):
    """Expat reports UTF-8 byte positions when parsing decoded Unicode."""
    data = text.encode("utf-8")
    parser = expat.ParserCreate(namespace_separator="|")
    depth = 0
    current = None
    spans = {}
    root_end = 0

    def start(tag, attrs):
        nonlocal depth, current
        if depth == 1 and tag == "Material":
            current = attrs["name"], parser.CurrentByteIndex
        depth += 1

    def end(tag):
        nonlocal depth, current, root_end
        depth -= 1
        pos = parser.CurrentByteIndex
        if depth == 1 and current is not None:
            # For an empty tag Expat points directly after '/>'.
            name, begin = current
            if data[pos:pos + 10] == b"</Material":
                pos = data.index(b">", pos) + 1
            spans[name] = (begin, pos)
            current = None
        if depth == 0:
            root_end = pos

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.Parse(text, True)
    return data, spans, root_end


class CmxDocument:
    def __init__(self, data):
        self._tree = _parse(data)
        self.root = self._tree.getroot()
        if self.root.tag != "Cadence_Material_Lib":
            raise ValueError("Cadence_Material_Lib 문서가 필요합니다.")
        self._original = data
        self._snapshot = ET.tostring(self._tree, encoding="utf-8")
        self.digest = hashlib.sha256(data).hexdigest()
        self.path = None
        names = set()
        for material in self.materials:
            name = _name(material)
            if name in names:
                raise ValueError(f"중복된 재질 이름 · {name}")
            names.add(name)

    @classmethod
    def from_bytes(cls, data):
        return cls(data)

    @classmethod
    def load(cls, path):
        path = Path(path).resolve()
        doc = cls.from_bytes(path.read_bytes())
        doc.path = path
        return doc

    @property
    def materials(self):
        return self.root.findall("Material")

    def get(self, name):
        return next((m for m in self.materials if m.get("name") == name), None)

    def to_bytes(self):
        if ET.tostring(self._tree, encoding="utf-8") == self._snapshot:
            return self._original
        return ET.tostring(self._tree, encoding=self._tree.docinfo.encoding, xml_declaration=True)

    def patched_bytes(self, replacements, additions):
        """Splice changed materials into the original file, preserving surrounding XML."""
        if not replacements and not additions:
            return self._original
        original = self._original
        encoding = self._tree.docinfo.encoding
        bom = b""
        # Retain the original BOM and byte order, including UTF-16 on Windows.
        for prefix, codec in ((codecs.BOM_UTF32_LE, "utf-32-le"),
                              (codecs.BOM_UTF32_BE, "utf-32-be"),
                              (codecs.BOM_UTF8, "utf-8"),
                              (codecs.BOM_UTF16_LE, "utf-16-le"),
                              (codecs.BOM_UTF16_BE, "utf-16-be")):
            if original.startswith(prefix):
                bom, encoding = prefix, codec
                break
        decoded = original[len(bom):].decode(encoding)
        if decoded.encode(encoding) != original[len(bom):]:
            raise ValueError("이 파일의 인코딩은 원본 바이트를 보존할 수 없습니다. 원본 애플리케이션에서 UTF-8 CMX로 내보낸 뒤 사용하세요.")
        data, spans, root_end = _material_spans(decoded)
        newline = b"\r\n" if b"\r\n" in data else b"\n"

        def render(node):
            return material_xml(node).encode("utf-8").replace(b"\n", newline)

        patches = [(*spans[name], render(node)) for name, node in replacements.items()]
        if additions:
            if spans:
                begin, pos = list(spans.values())[-1]
                indent = data[data.rfind(b"\n", 0, begin) + 1:begin]
                indent = indent if not indent.strip() else b""
                added = b"".join(newline + indent + render(node) for node in additions)
                patches.append((pos, pos, added))
            elif data[root_end:root_end + 2] == b"</":
                added = b"".join(render(node) + newline for node in additions)
                patches.append((root_end, root_end, added))
            else:
                # The library itself used the empty-element form.
                content = newline.join(render(node) for node in additions)
                patches.append((root_end - 2, root_end, b">" + newline + content + newline +
                                b"</Cadence_Material_Lib>"))
        parts = []
        last = 0
        for start, end, content in sorted(patches):
            parts.extend((data[last:start], content))
            last = end
        parts.append(data[last:])
        output = bom + b"".join(parts).decode("utf-8").encode(encoding, "xmlcharrefreplace")
        CmxDocument.from_bytes(output)
        return output
