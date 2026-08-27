"""Read template candidate and approved-template artifacts back into memory."""
from __future__ import annotations

import json
from pathlib import Path

from .models import TemplateCandidate

# 이 모듈은 ACTIVE candidate 역직렬화 경계다. 품질 파이프라인 산출물을 기록하는
# write_pipeline_artifacts()는 pipeline_artifacts.py로 분리했다 — 그 함수의
# quality/* 의존이 여기 module-level에 남아 있으면 TemplateRegistry.find()와
# register_hwpx_template_candidate()가 품질 파이프라인 구현까지 함께 로드한다.


# TemplateRegistry가 template.json을 다시 TemplateCandidate로 읽을 때 쓰는
# 역직렬화 경계다.
def load_candidate(path: Path | str) -> TemplateCandidate:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return TemplateCandidate.from_dict(data)
