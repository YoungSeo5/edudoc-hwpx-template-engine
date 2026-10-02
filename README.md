# HWPX 템플릿 생성·렌더링 엔진

기관별 HWPX 서식을 재사용 가능한 템플릿으로 만들고, 검증·승인한 뒤 새로운
콘텐츠를 반복적으로 채워 최종 HWPX 문서를 생성하는 참조 기반 문서 생성
엔진입니다.

## 핵심 특징

- 기존 HWPX에서 템플릿 후보(candidate) 추출
- 기존 HWPX가 없어도 계약(요구사항·문서 구조·기관 디자인)으로 신규 템플릿 작성
- candidate와 approved template의 명확한 분리 — 자동 QA를 통과해도 사람이
  승인하기 전까지는 최종 문서 생성에 쓸 수 없음
- 승인된 템플릿 하나에 서로 다른 content를 반복 적용해 여러 문서 생성
- 렌더마다 HWPX 구조·레이아웃 계약 재검증(시각적 품질 검증은 아님 — [Limitations](#limitations) 참고)

## 무엇이 아닌가

자유 형식 문서 생성기도, 범용 파일 변환기도 아닙니다. Markdown → HWPX
범용 변환기가 아니고, HWP/DOCX/PDF 범용 포맷 변환기도 아닙니다. 모든 최종
문서는 특정 기관·문서 유형의 **승인된 템플릿 한 건**에 묶여 있습니다.

---

## Quick Start

가장 흔한 경로: **승인된 템플릿이 이미 있는 경우**입니다. 이 경우 새
candidate를 만들지 마십시오.

```powershell
git submodule update --init --recursive
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

.\.venv\Scripts\python.exe scripts/templates/render_hwpx_template.py `
  --institution <기관명> `
  --document-type <문서유형> `
  --content <content.json> `
  --output sandbox/<출력.hwpx> `
  --requester-name <요청자>
```

`content.json`은 `{ "template_id": "...", "fields": { "<field_id 또는 별칭>": "<값>" } }`
형태이며, `template_id`와 field 이름은 승인 템플릿의 `placeholder_map.json`/
`alias_map.json`에 실제로 존재해야 합니다. 성공하면 출력 JSON에
`filled_fields`/`missing_fields`/`leftover_placeholders`가 담깁니다.

승인 템플릿이 아직 없다면 [Creating a Template](#creating-a-template)로
넘어가십시오.

---

## AI Agent / Skill로 사용하기

루트 [SKILL.md](SKILL.md)가 `hwpx-institution-template` Agent Skill을
정의합니다. Skill은 별도 CLI가 아니라, 에이전트가 이 저장소를 언제·어떤
순서로 호출할지 정하는 실행 규칙입니다("승인 템플릿으로 문서 작성해줘",
"이 HWPX를 템플릿 후보로 추출해줘" 같은 요청에 쓰입니다).

```text
요청 → institution + document_type 확인 → 승인된 템플릿이 있는가?
   ├─ YES → 최종 문서 생성
   └─ NO  → 후보 추출/작성 → 사람 검토 → 사람이 승인한 경우에만 등록
```

`SKILL.md`는 기존 HWPX 추출과 self-authoring(계약 기반 신규 작성)을 모두
`TEMPLATE_CREATE`로 라우팅하고, 승인 템플릿 사용은 `DOCUMENT_RENDER`로
라우팅합니다.

세부 금지 목록과 라우팅 규칙은 [SKILL.md](SKILL.md) 원문을 확인하십시오.

---

## What can it do?

| 작업 | 지원 상태 | 진입점 |
|---|---|---|
| approved template으로 HWPX 생성 | 지원 | `render_hwpx_template.py` |
| 기존 HWPX에서 candidate 추출 | 지원 | `qa_hwpx_template.py` |
| 계약 기반 신규 candidate 작성 | 부분 지원 (title/info_table/body_section/one_page_report만) | `author_hwpx_template.py` |
| candidate 자동 QA | 지원 | `qa_hwpx_template.py` |
| candidate 승인·등록 | 지원(candidate 종류별 조건 다름) | `register_hwpx_template.py --approve` |
| 사람의 시각 검토 기록 도구 | 미지원(수동 작성) | — |
| 시각적 품질 자동 검증 | 미지원 | — |
| PDF/DOCX/HWP/이미지 → HWPX 변환 | 미지원 | — |

---

## Installation

- Python: [.python-version](.python-version)의 `3.13`
- 의존성: [requirements.txt](requirements.txt) / [requirements-dev.txt](requirements-dev.txt)
- submodule 두 개가 없으면 동작하지 않습니다: `templates/institutions/`(기관
  템플릿 데이터, 없으면 승인 템플릿을 찾을 수 없음), `skills/hwp-skill/`
  (`table_cell` 필드 치환에 필요)

```powershell
git submodule update --init --recursive
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

macOS/Linux는 `python3 -m venv .venv` + `./.venv/bin/python -m pip install ...`로
동일하게 동작합니다.

**Hancom Automation(한글 프로그램)**은 native PageCount 검증을 요청했을 때만
필요하며 Windows 전용입니다. 없으면 해당 검증만 항상 실패로 보고되고, 나머지
기능에는 영향이 없습니다.

---

## Using an Approved Template

승인 템플릿에 `content.json`을 채워 문서를 반복 생성합니다.

```powershell
.\.venv\Scripts\python.exe scripts/templates/render_hwpx_template.py `
  --institution <기관명> --document-type <문서유형> `
  --content <content.json> --output sandbox/<출력.hwpx> `
  --requester-name <요청자>
```

- `--requester-name`은 최종 문서에 반드시 필요합니다(`content.hpf`의
  작성자·최종저장자로 기록). 누락 시 예외가 아니라 `{"ok": false, ...}`로
  보고됩니다.
- `content.json`의 `template_id`가 승인 템플릿과 다르면 렌더가 거부됩니다.
- 승인 템플릿에 `semantic_contract.json`이 있으면, 필수(`required: true`)로
  선언된 CONTENT 필드(반복 collection 포함)가 비어 있거나 `확인 필요`인 채면
  렌더 전에 거부됩니다. 그 계약이 없는 템플릿은 결과물에 `{{placeholder}}`가
  남으면 렌더가 실패하는 방식으로만 미입력을 걸러냅니다.

같은 승인 템플릿에 서로 다른 `content.json`을 넣으면 여러 문서를 생성할 수
있습니다 — 템플릿 제작은 한 번, 문서 생성은 여러 번입니다. `.md`/`.txt`/
`.hwpx` 원본에서 결정적 필드만 채워 렌더하는 `render_hwpx_template_from_source.py`
경로도 있으며, 판단이 필요한 필드가 남으면 렌더를 거부합니다.

---

## Creating a Template

새 템플릿은 두 경로 중 하나로 만들고, 둘 다 candidate QA → 사람 검토 →
승인·등록으로 합류합니다.

### Existing HWPX

```powershell
.\.venv\Scripts\python.exe scripts/templates/qa_hwpx_template.py `
  --source <원본.hwpx> `
  --output-dir sandbox/template-candidates/<새-후보> `
  --institution <기관명> `
  --document-type <문서유형>
```

### Self-authoring

기존 원본이 없으면 "요구사항 + 문서 구조 + 기관 디자인 규칙"으로 template을
직접 작성합니다.

```text
무엇을 만들고 싶은가        → TemplateRequest
어떤 정보가 들어가는가       → Semantic Template Contract
그 정보를 어디에 놓을 것인가  → TemplateSpec
어떤 기관 디자인을 쓸 것인가  → Institution Design Contract
```

```powershell
.\.venv\Scripts\python.exe scripts/templates/author_hwpx_template.py `
  --template-request <template_request.json> `
  --semantic-contract <semantic_contract.json> `
  --template-spec <template_spec.json> `
  --institution-design <design.json> `
  --institution <기관명> --document-type <문서유형>
```

각 계약의 스키마는
[docs/contracts/template-authoring-contracts.md](docs/contracts/template-authoring-contracts.md)를
따릅니다. 이 스크립트는 source HWPX를 만든 뒤 `qa_hwpx_template.py`를 내부
호출해 candidate까지만 만듭니다 — **승인이나 최종 렌더는 수행하지 않습니다.**
지원 범위는 `title`/`info_table`/`body_section`/`one_page_report`뿐이며,
반복 섹션과 병합 셀 복합 표는 아직 지원하지 않습니다.

---

## Reviewing and Approving a Candidate

**자동 QA가 확인하는 것** — HWPX 패키지/XML strict 검증, sample/test 값
round-trip 렌더, leftover placeholder 없음, 렌더 후 레이아웃 계약 유지,
기존 등록 템플릿과의 field 정체성 드리프트, (`--required-native-pages`를
줬을 때만) native PageCount.

**사람이 확인해야 하는 것** — 시각적 완성도, hierarchy marker 모양·간격,
반복 행이 실제로 늘어났을 때의 표 확장 결과, 텍스트 overflow, 콘텐츠 밀도
(sparse/normal/dense) 변화, 페이지 균형. 이 중 어느 것도 자동 QA가 검사하지
않습니다. `roundtrip.sample.hwpx`/`roundtrip.test.hwpx`를 한컴에서 직접 열어
확인하십시오.

> **QA passed ≠ visual quality passed.**

검토 후 사람이 승인하기로 결정한 경우에만 등록합니다.

```powershell
.\.venv\Scripts\python.exe scripts/templates/register_hwpx_template.py `
  --candidate sandbox/template-candidates/<후보> `
  --approve
```

`--approve`는 사용자의 명시적 승인 의사이며, 없으면 등록이 거부됩니다.
candidate에 `semantic_contract.json`이 있으면(self-authoring 경로)
`human_review.json`(사람이 검토했다는 기록)을 포함한 계약 파일 일체가
있어야 등록되고, 없으면(순수 추출 경로) round-trip 렌더 성공만으로도
등록될 수 있습니다 — 두 경로의 승인 강도가 다릅니다. `human_review.json`을
자동으로 만들어 주는 도구는 없어 지금은 사람이 직접 작성해야 합니다.

---

## Limitations

- **Visual QA** — 자동 QA는 HWPX 구조와 렌더 가능성을 검사하지만 실제
  시각적 완성도를 보장하지 않습니다. candidate의 roundtrip 결과를 직접
  확인해야 합니다.
- **Content density** — sparse/normal/dense 데이터를 자동으로 변주해
  검사하지 않습니다.
- **Text overflow** — 셀이나 문단에서 텍스트가 잘리는지 직접 검출하지
  않습니다. 검사되는 것은 문서 전체 PageCount 비교뿐입니다.
- **Native PageCount** — Windows + Hancom Automation + 등록된 로컬 보안
  모듈이 필요한 조건부 검증입니다. 환경이 없으면 통과가 아니라 항상 실패로
  보고됩니다.
- **Approval workflow** — human review 자동화가 아직 완성되지 않았고,
  legacy candidate(추출 경로)는 self-authoring candidate보다 더 느슨한
  승인 경로를 거칩니다.
- **Self-authoring** — 지원 layout은 title/info_table/body_section/
  one_page_report뿐이며, 반복 섹션·병합 셀 복합 표는 지원하지 않습니다.
- **입력 포맷** — `DOCUMENT_RENDER`가 지원하는 소스는 `.md`/`.markdown`/
  `.txt`/`.hwpx`뿐입니다. PDF/DOCX/HWP/이미지는 지원하지 않습니다.
- **`approved`의 의미** — "Registry에 등록되어 최종 렌더가 가능하다"는
  뜻이며, "기관이 시각적으로 최종 승인했다"는 것을 자동으로 보장하지
  않습니다.

---

## Python API

```python
from datetime import datetime, timezone
from pathlib import Path
from core.adapters.hwpx_template_input import RenderExecutionContext
from core.document_api import render_approved_document, validate_template_content

context = RenderExecutionContext(requester_name="<요청자>", requested_at=datetime.now(timezone.utc))
content = {"<field_id 또는 별칭>": "<값>"}

validate_template_content("<기관명>", "<문서유형>", content, context)
render_approved_document(
    "<기관명>", "<문서유형>", content, Path("sandbox/<출력>.hwpx"), context,
    content_template_id="<content.json의 template_id>",
)
```

`core/document_api/__init__.py`가 공개하는 함수: `list_approved_templates()`,
`get_template_contract()`, `validate_template_content()`,
`render_approved_document()`, `render_document_from_source()`(`.md`/`.txt`/
`.hwpx` 소스에서 결정적 필드만 렌더). 내부 렌더러·QA·승인 함수를 직접
호출하지 말고 이 API를 연결 경계로 사용하십시오.

---

## Development

```bash
python -m pytest tests/ -q --basetemp=sandbox/pytest
```

테스트가 실패하거나 경고하면 완료·검증됨으로 간주하지 않습니다.

---

## Documentation

- [AGENTS.md](AGENTS.md) — 프로젝트 목표, 금지사항, 테스트·문서 정책
- [SKILL.md](SKILL.md) — Agent 라우팅 규칙
- [docs/product-workflow-contract.md](docs/product-workflow-contract.md) — 전체 워크플로 계약과 구현 현황
- [docs/agent-policies/hwpx-template-rendering.md](docs/agent-policies/hwpx-template-rendering.md) — 템플릿 라우팅·반복 계약
- [docs/agent-policies/hwpx-render-pipeline-diagram.md](docs/agent-policies/hwpx-render-pipeline-diagram.md) — 렌더·QA 파이프라인 call graph
- [docs/agent-policies/hwpx-layout-context.md](docs/agent-policies/hwpx-layout-context.md) — 레이아웃 보존 계약
- [docs/contracts/template-authoring-contracts.md](docs/contracts/template-authoring-contracts.md) — self-authoring 계약 스키마

공개 저장소는 엔진 코드·CLI·테스트를, `templates/institutions/`와
`skills/hwp-skill/`은 submodule로 데이터·치환 기능을, `sandbox/`는 candidate/
pytest 임시 산출물을, `docs/`는 장기 아키텍처·정책 문서를 담습니다.

---

## 외부 출처

- [hwpx-skill](https://github.com/jkf87/hwpx-skill)(MIT) — `skills/hwp-skill/`의 기반 오픈소스
- python-hwpx — HWPX strict package validation에 사용하는 라이브러리
- 예시 입력으로 쓴 범정부오피스 관련 HWPX 문서는 행정안전부 공식 게시물 등
  공개 자료를 참고했으며, 이 프로젝트의 코드나 업무 규칙에 포함된 것은
  아닙니다.
