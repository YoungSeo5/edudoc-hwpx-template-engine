"""Load explicitly approved institution templates."""
from __future__ import annotations

from pathlib import Path

from ..adapters.hwpx_alias_map import load_alias_map
from ..adapters.hwpx_template_input import load_placeholder_map
from .models import TemplateCandidate
from .serialization import load_candidate


class TemplateRegistry:
    def __init__(self, root: Path | str = "templates/institutions") -> None:
        self.root = Path(root)

    def template_path(self, institution: str, document_type: str) -> Path:
        return self.root / _slug(institution) / _slug(document_type) / "template.json"

    def find(self, institution: str, document_type: str) -> TemplateCandidate | None:
        path = self.template_path(institution, document_type)
        if not path.is_file():
            return None
        candidate = load_candidate(path)
        return candidate if candidate.status == "approved" else None

    def verify_candidate_field_identity(
        self,
        institution: str,
        document_type: str,
        candidate_dir: Path | str,
    ) -> dict:
        """Refuse a candidate whose bound field IDs point at other content.

        ``field_id`` is a positional counter, so a re-extraction that classifies
        one earlier text differently shifts every later number. ``alias_map.json``
        binds human input to those counters, so the binding survives and silently
        fills a different place. Only the IDs the alias map binds are compared;
        the recorded ``category`` + ``sample_value`` say what each pointed at.
        """
        registered = self.template_path(institution, document_type).parent
        if not (registered / "placeholder_map.json").is_file():
            return {"checked": False, "reason": "등록된 템플릿 없음"}
        registered_map = load_placeholder_map(registered)
        existing = _fields_by_id(registered_map)
        alias_map = load_alias_map(
            registered,
            field_ids=frozenset(existing),
            template_id=registered_map.get("template_id"),
        )
        if alias_map is None:
            return {"checked": False, "reason": "등록된 템플릿에 alias_map.json 없음"}

        candidate = _fields_by_id(load_placeholder_map(candidate_dir))
        bound = sorted(alias_map.referenced_field_ids & set(existing))
        drift = [
            f"{field_id}: {_identity(existing[field_id])} -> "
            f"{_identity(candidate[field_id]) if field_id in candidate else '없음'}"
            f"{_semantic_evidence_suffix(candidate.get(field_id))}"
            for field_id in bound
            if _identity(existing[field_id]) != _identity(candidate.get(field_id, {}))
        ]
        if drift:
            raise ValueError(
                "alias_map.json이 묶은 field_id가 후보에서 다른 내용을 가리킨다: "
                + "; ".join(drift)
            )
        # 묶이지 않은 field는 재배치를 허용하지만, 드리프트 자체는 검토 근거로
        # 남긴다(자동 승인으로 취급하지 않는다).
        unbound_drift = [
            f"{field_id}: {_identity(existing[field_id])} -> "
            f"{_identity(candidate[field_id]) if field_id in candidate else '없음'}"
            for field_id in sorted(set(existing) - set(bound))
            if _identity(existing[field_id]) != _identity(candidate.get(field_id, {}))
        ]
        return {
            "checked": True,
            "compared_with": str(registered),
            "bound_field_count": len(bound),
            "unbound_drift": unbound_drift,
        }


def _semantic_evidence_suffix(field: dict | None) -> str:
    if not field or not field.get("semantic_role"):
        return ""
    return f" [semantic_role={field['semantic_role']}]"


def _fields_by_id(placeholder_map) -> dict:
    return {entry["field_id"]: entry for entry in placeholder_map.get("fields", [])}


def _identity(field) -> tuple:
    return field.get("category"), field.get("sample_value")


def _slug(value: str) -> str:
    clean = value.strip().replace("\\", "_").replace("/", "_")
    if not clean or clean in {".", ".."}:
        raise ValueError("institution and document_type must be non-empty safe names")
    return clean
