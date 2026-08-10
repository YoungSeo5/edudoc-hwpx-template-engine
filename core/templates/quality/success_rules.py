"""Load deterministic success rules for template candidates."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class SuccessRules:
    require_evidence: bool = True
    require_structure_signal: bool = True
    forbid_fake_placeholders: bool = True
    forbid_unproven_style: bool = True
    max_error_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def load_success_rules(path: Path | str | None = None) -> SuccessRules:
    if path is None:
        return SuccessRules()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    known = SuccessRules.__dataclass_fields__
    return SuccessRules(**{key: value for key, value in data.items() if key in known})
