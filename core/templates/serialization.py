"""Read template candidate and approved-template artifacts back into memory."""
from __future__ import annotations

import json
from pathlib import Path

from .models import TemplateCandidate

# 이 모듈은 ACTIVE candidate 역직렬화 경계다. TemplateRegistry가 template.json을
# 다시 TemplateCandidate로 읽을 때 쓴다.
def load_candidate(path: Path | str) -> TemplateCandidate:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return TemplateCandidate.from_dict(data)
