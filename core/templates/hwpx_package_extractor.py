"""Read-only HWPX package extraction for reusable template candidates."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import BadZipFile, ZipFile, is_zipfile

from .extractors.style import extract_style
from .models import RendererContract, TemplateCandidate, TemplateIdentity

# 이 모듈의 경계:
# 원본 HWPX ZIP → 선택 자산을 raw/와 template/에 바이트 그대로 복사
#                → 구조·스타일 분석 결과와 candidate template.json 작성
# 여기서는 실제 텍스트를 {{placeholder}}로 바꾸지 않는다.
_SECTION_RE = re.compile(r"^Contents/section(\d+)\.xml$", re.IGNORECASE)
_MAX_ENTRY_BYTES = 100 * 1024 * 1024
_MAX_SELECTED_BYTES = 512 * 1024 * 1024
_COMMON_SECTIONS = ("요약", "배경", "추진 배경", "진행현황")
_DATE_RE = re.compile(
    r"(?:\b20\d{2}[.-]\s*\d{1,2}(?:[.-]\s*\d{1,2})?\.?|"
    r"\b20\d{2}년\s*\d{1,2}월(?:\s*\d{1,2}일)?)"
)
_PHONE_RE = re.compile(
    r"(?:0\d{1,2}[- )]\d{3,4}[-]\d{4}|\d{3,4}-\d{4}|☎\s*\d{3,5})"
)
_PERSON_CONTEXT_RE = re.compile(
    r"(?:담당자|작성자|보고자|성명|원장)\s*[:：]?\s*([가-힣]{2,4})"
)
_DEPARTMENT_RE = re.compile(
    r"^[가-힣A-Za-z0-9·ㆍ\s]{2,30}(?:부|과|실|팀|국|원|센터)$"
)


@dataclass(frozen=True)
class HwpxExtractionResult:
    output_dir: Path
    template_json: Path
    extraction_report: Path
    candidate: TemplateCandidate


def extract_hwpx_template(
    source: Path | str,
    output_dir: Path | str,
    *,
    template_id: str,
    template_name: str | None = None,
    institution: str = "확인 필요",
    fixture_dir: Path | str | None = None,
) -> HwpxExtractionResult:
    """Extract selected HWPX assets without modifying or reserializing XML."""
    source = Path(source)
    output_dir = Path(output_dir)

    # 흐름 1: 입력이 실제 HWPX ZIP인지, template_id와 출력 경로가 안전한지
    # 먼저 확인한다. 기존 폴더에 덮어쓰지 않고 새 후보 폴더만 만든다.
    _validate_inputs(source, output_dir, template_id)
    output_dir.mkdir(parents=True, exist_ok=False)

    warnings: list[str] = []
    parse_errors: list[str] = []
    package_entries: list[str] = []
    copied_assets: list[dict[str, Any]] = []
    section_analyses: list[dict[str, Any]] = []
    fixture_comparison: list[dict[str, Any]] = []

    try:
        # 흐름 2: ZIP에서 템플릿 분석에 필요한 항목만 임시 작업공간으로
        # 안전하게 꺼낸다. 경로 탈출과 과도한 압축 해제 크기는 하위 함수가 막는다.
        with tempfile.TemporaryDirectory(prefix=".extracting-", dir=output_dir) as temp_name:
            workspace = Path(temp_name)
            with ZipFile(source, "r") as package:
                package_entries = [info.filename for info in package.infolist()]
                selected = _select_members(package, warnings)
                extracted = _extract_selected_to_workspace(package, selected, workspace)

            # 흐름 3: raw/는 원본 증거 보존용이고 template/은 이후
            # hwpx_content_separator가 placeholder를 넣을 작업본이다.
            raw_dir = output_dir / "raw"
            template_dir = output_dir / "template"
            for archive_name, workspace_path, raw_relative in extracted:
                raw_path = raw_dir / raw_relative
                _copy_exact(workspace_path, raw_path, output_dir)
                copied_assets.append(
                    {
                        "archive_path": archive_name,
                        "raw_path": raw_path.relative_to(output_dir).as_posix(),
                        "size_bytes": raw_path.stat().st_size,
                        "sha256": _sha256(raw_path),
                    }
                )

                template_relative = _template_relative(archive_name)
                if template_relative is not None:
                    template_path = template_dir / template_relative
                    _copy_exact(workspace_path, template_path, output_dir)

            # 흐름 4: 복사한 XML은 수정하지 않고 읽기만 하며, 글꼴·문단·표·
            # 보이는 텍스트와 placeholder 후보를 분석 기록으로 만든다.
            raw_header = raw_dir / "header.xml"
            raw_content = raw_dir / "content.hpf"
            section_paths = sorted(
                raw_dir.glob("section*.xml"),
                key=_section_sort_key,
            )
            style_summary = _analyze_header(raw_header, parse_errors)
            content_summary = _analyze_content_hpf(raw_content, parse_errors)
            all_candidates: list[dict[str, Any]] = []
            for section_path in section_paths:
                analysis = _analyze_section(section_path, parse_errors)
                section_analyses.append(analysis)
                all_candidates.extend(analysis["candidate_placeholders"])

            fixture_comparison = _compare_fixtures(
                raw_dir,
                fixture_dir,
                section_paths,
                warnings,
            )

        # 흐름 5: 선택하지 않은 패키지 항목과 필수 자산 누락은 삭제하거나
        # 보정하지 않고 경고로 남긴다.
        missing = _missing_required_assets(output_dir)
        warnings.extend(f"missing expected asset: {item}" for item in missing)
        unprocessed = _unprocessed_entries(package_entries)
        if unprocessed:
            warnings.append(
                "Unselected package entries were preserved only in the source HWPX "
                "and are listed in the report."
            )

        style_profile = extract_style(source)
        section_files = [
            f"raw/{path.name}"
            for path in sorted((output_dir / "raw").glob("section*.xml"), key=_section_sort_key)
        ]

        # 흐름 6: 지금까지의 관찰 결과를 통합 모델로 묶는다. status는 반드시
        # candidate이며, 자동 분석만으로 승인된 템플릿이 되지 않는다.
        candidate = TemplateCandidate(
            identity=TemplateIdentity(
                institution=institution,
                document_type=template_name or template_id,
                template_id=template_id,
                template_name=template_name or template_id,
            ),
            reference_path=source.name,
            reference_format="hwpx",
            structure={
                "section_files": section_files,
                "sections": section_analyses,
                "candidate_placeholders": _deduplicate_candidates(all_candidates),
            },
            style_profile=style_profile,
            renderer=RendererContract(
                preferred_format="hwpx",
                route=None,
                reference_hwpx="raw/header.xml",
                fallback="md2hwpx",
            ),
            source_summary={
                "file_name": source.name,
                "size_bytes": source.stat().st_size,
                "sha256": _sha256(source),
            },
            assets={
                "raw_directory": "raw",
                "template_directory": "template",
                "content_hpf": "raw/content.hpf" if raw_content.is_file() else None,
                "header_xml": "raw/header.xml" if raw_header.is_file() else None,
                "section_files": section_files,
                "copied_assets": copied_assets,
            },
            package_summary={
                "detected_internal_files": package_entries,
                "content_hpf": content_summary,
                "header_style_summary": style_summary,
                "header_xml_present": raw_header.is_file(),
                "content_hpf_present": raw_content.is_file(),
                "bin_data_present": (output_dir / "raw" / "BinData").is_dir(),
                "unprocessed_entries": unprocessed,
                "fixture_comparison": fixture_comparison,
                "analysis_warnings": warnings,
                "parse_errors": parse_errors,
            },
            rendering_rules={
                "preserve_header_xml": True,
                "replace_only_hp_t_text": True,
                "preserve_table_structure": True,
                "preserve_linesegarray": False,
                "do_not_modify_style_ids": True,
            },
            evidence=[
                "source HWPX opened directly with Python zipfile.ZipFile",
                "raw XML copied byte-for-byte without XML serialization",
                "candidate placeholders were reported but not applied",
            ],
            unknown_fields=["renderer.route"],
            status="candidate",
        )

        # 흐름 7: 기계가 읽는 candidate 메타데이터와 사람이 검토할 보고서를
        # 같은 출력 폴더에 기록해 다음 콘텐츠 분리 단계로 넘긴다.
        template_json = output_dir / "template.json"
        template_json.write_text(
            json.dumps(candidate.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        extraction_report = output_dir / "extraction_report.md"
        extraction_report.write_text(
            _render_report(candidate),
            encoding="utf-8",
        )
        return HwpxExtractionResult(
            output_dir=output_dir,
            template_json=template_json,
            extraction_report=extraction_report,
            candidate=candidate,
        )
    except Exception:
        # 추출 도중 실패하면 반쪽짜리 후보 폴더를 남기지 않는다.
        shutil.rmtree(output_dir, ignore_errors=True)
        raise


# ZIP 입력 경계: 형식, 크기, 중복 이름, 경로 탈출을 검사한 뒤
# 허용된 자산만 임시 작업공간과 후보 폴더로 복사한다.
def _validate_inputs(source: Path, output_dir: Path, template_id: str) -> None:
    if source.suffix.lower() != ".hwpx":
        raise ValueError(f"source must be a .hwpx file: {source}")
    if not source.is_file() or not is_zipfile(source):
        raise ValueError(f"source is not a readable HWPX ZIP package: {source}")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", template_id):
        raise ValueError("template_id may contain only ASCII letters, digits, '.', '_', and '-'")
    if output_dir.exists():
        raise FileExistsError(f"output template directory already exists: {output_dir}")


def _select_members(package: ZipFile, warnings: list[str]) -> list[tuple[str, Path]]:
    selected: list[tuple[str, Path]] = []
    seen: set[str] = set()
    total = 0
    for info in package.infolist():
        name = info.filename.replace("\\", "/")
        if info.is_dir():
            continue
        _validate_archive_name(name)
        raw_relative = _raw_relative(name)
        if raw_relative is None:
            continue
        normalized = raw_relative.as_posix().lower()
        if normalized in seen:
            raise ValueError(f"duplicate selected HWPX member: {name}")
        seen.add(normalized)
        if info.file_size > _MAX_ENTRY_BYTES:
            raise ValueError(f"HWPX member is too large: {name} ({info.file_size} bytes)")
        total += info.file_size
        if total > _MAX_SELECTED_BYTES:
            raise ValueError("selected HWPX assets exceed the extraction size limit")
        selected.append((name, raw_relative))
    if not selected:
        warnings.append("No supported HWPX template assets were detected.")
    return selected


def _extract_selected_to_workspace(
    package: ZipFile,
    selected: list[tuple[str, Path]],
    workspace: Path,
) -> list[tuple[str, Path, Path]]:
    extracted: list[tuple[str, Path, Path]] = []
    for archive_name, raw_relative in selected:
        workspace_path = _safe_destination(workspace, PurePosixPath(archive_name))
        workspace_path.parent.mkdir(parents=True, exist_ok=True)
        with package.open(archive_name, "r") as source_stream:
            with workspace_path.open("wb") as target_stream:
                shutil.copyfileobj(source_stream, target_stream)
        extracted.append((archive_name, workspace_path, raw_relative))
    return extracted


def _raw_relative(name: str) -> Path | None:
    lowered = name.lower()
    if lowered == "contents/content.hpf":
        return Path("content.hpf")
    if lowered == "contents/header.xml":
        return Path("header.xml")
    section_match = _SECTION_RE.fullmatch(name)
    if section_match:
        return Path(f"section{int(section_match.group(1))}.xml")
    if lowered == "settings.xml":
        return Path("settings.xml")
    for prefix, output_name in (
        ("scripts/", "Scripts"),
        ("meta-inf/", "META-INF"),
        ("bindata/", "BinData"),
        ("contents/bindata/", "BinData"),
    ):
        if lowered.startswith(prefix):
            relative = PurePosixPath(name).parts[len(PurePosixPath(prefix).parts):]
            return Path(output_name, *relative)
    return None


def _template_relative(archive_name: str) -> Path | None:
    lowered = archive_name.lower()
    if lowered == "contents/content.hpf":
        return Path("content.hpf")
    if lowered == "contents/header.xml":
        return Path("header.xml")
    match = _SECTION_RE.fullmatch(archive_name)
    if match:
        return Path(f"section{int(match.group(1))}.template.xml")
    return None


def _validate_archive_name(name: str) -> None:
    pure = PurePosixPath(name)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise ValueError(f"unsafe HWPX archive member: {name}")


def _safe_destination(root: Path, relative: PurePosixPath) -> Path:
    target = root.joinpath(*relative.parts)
    root_resolved = root.resolve()
    target_resolved = target.resolve()
    if target_resolved != root_resolved and root_resolved not in target_resolved.parents:
        raise ValueError(f"path escapes extraction root: {relative}")
    return target


def _copy_exact(source: Path, destination: Path, output_dir: Path) -> None:
    destination = _safe_destination(
        output_dir,
        PurePosixPath(destination.relative_to(output_dir).as_posix()),
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


# 분석 경계: 아래 함수들은 복사된 XML에서 요약 정보만 읽으며,
# raw/ 또는 template/ XML을 다시 직렬화하거나 수정하지 않는다.
def _analyze_header(path: Path, errors: list[str]) -> dict[str, Any]:
    root = _parse_xml(path, errors)
    if root is None:
        return {"parsed": False, "font_faces": []}
    font_faces: list[str] = []
    counts = {
        "font_count": 0,
        "char_property_count": 0,
        "paragraph_property_count": 0,
        "style_count": 0,
        "border_fill_count": 0,
    }
    for node in root.iter():
        local = _local_name(node.tag)
        if local == "font":
            face = _attribute(node, "face")
            if face and face not in font_faces:
                font_faces.append(face)
            counts["font_count"] += 1
        elif local == "charPr":
            counts["char_property_count"] += 1
        elif local == "paraPr":
            counts["paragraph_property_count"] += 1
        elif local == "style":
            counts["style_count"] += 1
        elif local == "borderFill":
            counts["border_fill_count"] += 1
    return {"parsed": True, "font_faces": font_faces, **counts}


def _analyze_content_hpf(path: Path, errors: list[str]) -> dict[str, Any]:
    root = _parse_xml(path, errors)
    if root is None:
        return {"parsed": False, "manifest_item_count": 0, "spine_item_count": 0}
    items: list[dict[str, str | None]] = []
    spine: list[str | None] = []
    for node in root.iter():
        local = _local_name(node.tag)
        if local == "item":
            items.append(
                {
                    "id": _attribute(node, "id"),
                    "href": _attribute(node, "href"),
                    "media_type": _attribute(node, "media-type"),
                }
            )
        elif local == "itemref":
            spine.append(_attribute(node, "idref"))
    return {
        "parsed": True,
        "manifest_item_count": len(items),
        "spine_item_count": len(spine),
        "items": items,
        "spine": spine,
    }


def _analyze_section(path: Path, errors: list[str]) -> dict[str, Any]:
    root = _parse_xml(path, errors)
    if root is None:
        return {
            "file": path.name,
            "parsed": False,
            "paragraph_count": 0,
            "table_count": 0,
            "tables": [],
            "visible_text": [],
            "candidate_placeholders": [],
        }
    paragraphs = 0
    tables: list[dict[str, int | None]] = []
    visible_text: list[str] = []
    for node in root.iter():
        local = _local_name(node.tag)
        if local == "p":
            paragraphs += 1
        elif local == "tbl":
            tables.append(
                {
                    "row_count": _int_attribute(node, "rowCnt"),
                    "column_count": _int_attribute(node, "colCnt"),
                }
            )
        elif local == "t":
            text = _normalize_text("".join(node.itertext()))
            if text:
                visible_text.append(text)
    candidates = _detect_candidates(path.name, visible_text)
    return {
        "file": path.name,
        "parsed": True,
        "paragraph_count": paragraphs,
        "table_count": len(tables),
        "tables": tables,
        "visible_text": visible_text,
        "candidate_placeholders": candidates,
    }


def _detect_candidates(section: str, values: list[str]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index, text in enumerate(values):
        checks: list[tuple[str, bool, str]] = [
            ("date", bool(_DATE_RE.search(text)), "날짜 형식"),
            ("phone_number", bool(_PHONE_RE.search(text)), "전화번호 형식"),
            (
                "report_title",
                _is_report_title(text),
                "보고·계획 제목 가능성",
            ),
            (
                "department_name",
                bool(_DEPARTMENT_RE.fullmatch(text)),
                "부서·기관명 형태",
            ),
            (
                "person_name",
                bool(_PERSON_CONTEXT_RE.search(text)),
                "담당자·작성자·보고자 문맥",
            ),
            (
                "placeholder_symbol",
                any(symbol in text for symbol in ("○", "◎", "☆")),
                "자리표시 기호 포함",
            ),
            (
                "checkbox",
                any(symbol in text for symbol in ("□", "☑")),
                "체크박스 기호 포함",
            ),
            (
                "common_report_section",
                any(section_name in text for section_name in _COMMON_SECTIONS),
                "공통 보고서 섹션명",
            ),
        ]
        for category, matched, reason in checks:
            if matched:
                candidates.append(
                    {
                        "category": category,
                        "text": text,
                        "section": section,
                        "text_index": index,
                        "reason": reason,
                    }
                )
    return _deduplicate_candidates(candidates)


def _is_report_title(text: str) -> bool:
    compact = text.strip(" \t:：.·-")
    if not compact or len(compact) > 100:
        return False
    return (
        "보고서" in compact
        or compact.endswith("보고")
        or compact.endswith("계획")
        or compact.endswith("계획서")
    )


def _deduplicate_candidates(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in values:
        key = (item["category"], item["text"], item["section"])
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _parse_xml(path: Path, errors: list[str]) -> ET.Element | None:
    if not path.is_file():
        return None
    try:
        return ET.fromstring(path.read_bytes())
    except ET.ParseError as exc:
        errors.append(f"{path.name}: XML parse error: {exc}")
        return None


def _attribute(node: ET.Element, name: str) -> str | None:
    for key, value in node.attrib.items():
        if _local_name(key) == name:
            return value
    return None


def _int_attribute(node: ET.Element, name: str) -> int | None:
    value = _attribute(node, name)
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1].split(":", 1)[-1]


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _section_sort_key(path: Path) -> int:
    match = re.search(r"section(\d+)", path.name, re.IGNORECASE)
    return int(match.group(1)) if match else 10**9


def _missing_required_assets(output_dir: Path) -> list[str]:
    missing = []
    for relative in ("raw/header.xml", "raw/content.hpf"):
        if not (output_dir / relative).is_file():
            missing.append(relative)
    if not list((output_dir / "raw").glob("section*.xml")):
        missing.append("raw/section*.xml")
    return missing


def _unprocessed_entries(entries: list[str]) -> list[str]:
    result = []
    for name in entries:
        normalized = name.replace("\\", "/")
        if _raw_relative(normalized) is None:
            result.append(name)
    return result


def _compare_fixtures(
    raw_dir: Path,
    fixture_dir: Path | str | None,
    section_paths: list[Path],
    warnings: list[str],
) -> list[dict[str, Any]]:
    if fixture_dir is None:
        return []
    fixture_root = Path(fixture_dir)
    if not fixture_root.is_dir():
        warnings.append(f"fixture directory not found: {fixture_root}")
        return []
    contents = fixture_root / "Contents"
    if contents.is_dir():
        fixture_contents = contents
    elif fixture_root.name.lower() == "contents":
        fixture_contents = fixture_root
    else:
        fixture_contents = fixture_root

    comparisons: list[dict[str, Any]] = []
    names = ["content.hpf", "header.xml", *[path.name for path in section_paths]]
    for name in names:
        raw_path = raw_dir / name
        fixture_path = fixture_contents / name
        if not fixture_path.is_file():
            comparisons.append({"file": name, "fixture_present": False, "matches": None})
            continue
        comparisons.append(
            {
                "file": name,
                "fixture_present": True,
                "matches": raw_path.is_file() and _sha256(raw_path) == _sha256(fixture_path),
            }
        )
    return comparisons


# 보고 경계: TemplateCandidate에 축적한 관찰 결과를 사람이 검토할 Markdown으로
# 펼친다. 이 보고서는 승인이나 placeholder 적용을 수행하지 않는다.
def _render_report(candidate: TemplateCandidate) -> str:
    package = candidate.package_summary
    structure = candidate.structure
    lines = [
        "# HWPX Template Extraction Report",
        "",
        f"- Input file: `{candidate.source_summary['file_name']}`",
        f"- Template ID: `{candidate.identity.template_id}`",
        f"- Template name: `{candidate.identity.template_name}`",
        f"- Status: `{candidate.status}`",
        f"- `Contents/header.xml`: `{package['header_xml_present']}`",
        f"- `Contents/content.hpf`: `{package['content_hpf_present']}`",
        f"- `BinData/`: `{package['bin_data_present']}`",
        "",
        "## Detected Internal HWPX Files",
        "",
    ]
    lines.extend(f"- `{_md(value)}`" for value in package["detected_internal_files"])

    lines.extend(["", "## Detected Sections", ""])
    for section in structure["sections"]:
        lines.append(
            f"### `{section['file']}` — paragraphs: {section['paragraph_count']}, "
            f"tables: {section['table_count']}"
        )
        lines.append("")
        if section["tables"]:
            for index, table in enumerate(section["tables"], 1):
                lines.append(
                    f"- Table {index}: rowCnt=`{table['row_count']}`, "
                    f"colCnt=`{table['column_count']}`"
                )
        else:
            lines.append("- Tables: none detected")
        lines.extend(["", "#### Visible `<hp:t>` Text", ""])
        if section["visible_text"]:
            lines.extend(
                f"{index}. `{_md(text)}`"
                for index, text in enumerate(section["visible_text"], 1)
            )
        else:
            lines.append("- No non-empty visible text detected.")
        lines.append("")

    lines.extend(["## Candidate Placeholders (Not Applied)", ""])
    candidates = structure["candidate_placeholders"]
    if candidates:
        lines.extend(
            f"- `{item['category']}` · `{_md(item['text'])}` "
            f"({item['section']} #{item['text_index']}: {item['reason']})"
            for item in candidates
        )
    else:
        lines.append("- No candidates detected.")

    lines.extend(["", "## Style Summary", ""])
    style = candidate.style_profile
    header_style = package["header_style_summary"]
    lines.extend(
        [
            f"- Source: `{style.source}`",
            f"- Font family: `{style.font_family}`",
            f"- Body size: `{style.body_font_size_pt}`",
            f"- Line spacing: `{style.line_spacing}`",
            f"- Page margins: `{style.page_margins_mm}`",
            f"- Confidence: `{style.confidence}`",
            f"- Header font faces: `{header_style.get('font_faces', [])}`",
            f"- Header char properties: `{header_style.get('char_property_count', 0)}`",
            f"- Header paragraph properties: `{header_style.get('paragraph_property_count', 0)}`",
            "",
            "## Rendering Preservation Rules",
            "",
        ]
    )
    lines.extend(
        f"- `{key}`: `{value}`"
        for key, value in candidate.rendering_rules.items()
    )
    lines.extend(
        [
            "- Source/template XML keeps extracted `linesegarray` caches.",
            "- Rendering removes `linesegarray` caches from changed sections and "
            "retains them in unchanged sections.",
        ]
    )

    lines.extend(["", "## Fixture Comparison", ""])
    comparisons = package["fixture_comparison"]
    if comparisons:
        lines.extend(
            f"- `{item['file']}`: fixture_present=`{item['fixture_present']}`, "
            f"matches=`{item['matches']}`"
            for item in comparisons
        )
    else:
        lines.append("- No external extracted fixture directory supplied.")

    lines.extend(["", "## Unsupported or Unprocessed Entries", ""])
    unprocessed = package["unprocessed_entries"]
    if unprocessed:
        lines.extend(f"- `{_md(item)}`" for item in unprocessed)
    else:
        lines.append("- None.")

    lines.extend(["", "## Warnings and Parse Errors", ""])
    issues = [*package["analysis_warnings"], *package["parse_errors"]]
    if issues:
        lines.extend(f"- {_md(item)}" for item in issues)
    else:
        lines.append("- None.")
    lines.append("")
    return "\n".join(lines)


def _md(value: Any) -> str:
    return str(value).replace("`", "\\`").replace("\r", " ").replace("\n", " ")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
