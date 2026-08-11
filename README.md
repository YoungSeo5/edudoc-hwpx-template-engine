# HWPX 승인 템플릿 렌더링·QA 엔진

## 이 저장소의 역할

이 저장소는 **기관 HWPX 원본을 재사용 가능한 템플릿 후보로 만들고, 사람이 승인한
템플릿에 데이터만 채워 최종 HWPX를 생성하는 전용 엔진**입니다. 자유 형식 문서 생성기나
HWPX 포맷 변환기가 아닙니다.

최근 작업한 금융감독원 원장보고·원페이지 계열에서 공통으로 쓰는 다음 두 경로를
`edudoc`에서 분리했습니다.

1. **템플릿 제작 경로**: 원본 HWPX → 구조 분리 → 후보 생성 → QA 왕복 → 사람 검토 → 등록
2. **문서 생성 경로**: 승인 템플릿 조회 → 입력 계약 해석 → 내용·반복 블록 치환 → strict 검증

공개 저장소에는 엔진 코드·CLI·검증 정책·테스트가 들어 있습니다. 실제 기관 템플릿은
비공개 `templates/institutions/` submodule에, 표 셀 치환 구현은 `skills/hwp-skill/`
submodule에 있습니다. 따라서 코드만 clone한 상태로는 전체 기능을 실행할 수 없습니다.

### 누가 무엇을 하는가

| 역할 | 하는 일 | 사용하는 진입점 |
|---|---|---|
| 템플릿 관리자 | 원본 HWPX를 후보로 만들고 field·반복·metadata 계약을 검토한 뒤 승인 등록 | `qa_hwpx_template.py`, `register_hwpx_template.py` |
| 문서 생성 호출자 | 승인된 템플릿의 계약에 맞는 값을 넣어 최종 HWPX 생성 | `render_hwpx_template.py`, `core.document_api` |

### 현재 연결된 금융감독원 템플릿

아래 상태는 현재 체크아웃된 비공개 `templates/institutions/` submodule 기준입니다.

| 문서 유형 | `template_id` | 상태 | 가능한 경로 |
|---|---|---|---|
| 금감원 원장보고 | `fss_director_report` | `approved` | 최종 문서 생성 가능 |
| 금감원 원페이지 | `fss_one_page` | `candidate` | 후보 QA·계약 검토만 가능 |
| 금감원 원장보고 가상자산 이상거래 | `fss_virtual_asset_report` | `candidate` | 후보 QA·계약 검토만 가능 |

`candidate`는 운영 `TemplateRegistry`가 조회하지 않으므로 최종 생성에 사용할 수 없습니다.
코드가 스스로 상태를 올리지 않으며, 사람이 명시적으로 승인한 후보만 등록할 수 있습니다.

## 이 저장소에서 할 수 있는 일

| 순서 | 작업 | 입력 | 결과 |
|---|---|---|---|
| 1 | 새 템플릿 후보 생성·QA | 기관 원본 `.hwpx` | `candidate` 폴더와 sample/test 왕복 출력 |
| 2 | 템플릿 계약 검토 | `placeholder_map.json`, `template.review.md` | field 위치·별칭·반복·metadata 계약 확정 |
| 3 | 승인 후보 등록 | 사람이 승인한 `candidate` 폴더 | 비공개 Registry의 `approved` 템플릿 |
| 4 | 승인 템플릿 계약 조회·입력 검사 | 기관명·문서유형·입력값 | `placeholder_map`, `alias_map`, `PreparedRenderContent` |
| 5 | 최종 HWPX 생성·검증 | 승인 템플릿과 `content.json` | strict 검증을 통과한 출력 HWPX와 `RenderResult` |

## 전체 작업 흐름

```mermaid
flowchart TD
    SOURCE["기관 원본 HWPX"] --> QA["후보 생성·QA<br/>qa_hwpx_template.py"]
    QA --> CANDIDATE["candidate 폴더<br/>원본 snapshot·field map·왕복 출력"]
    CANDIDATE --> REVIEW["사람 검토<br/>field·alias·반복·metadata 계약"]
    REVIEW --> DECISION{"승인할 것인가?"}
    DECISION -- "아니오" --> CANDIDATE
    DECISION -- "예" --> REGISTER["승인 등록<br/>register_hwpx_template.py --approve"]
    REGISTER --> REGISTRY["운영 Registry<br/>approved만 조회"]
    REGISTRY --> INPUT["content.json 또는 Python API 입력"]
    INPUT --> RENDER["최종 렌더<br/>render_hwpx_template.py"]
    RENDER --> VALIDATE["레이아웃·metadata·strict HWPX 검증"]
    VALIDATE --> OUTPUT["최종 HWPX + 생성 결과"]
```

처음부터 새 템플릿을 만드는 경우에는 1단계부터 진행합니다. 이미 `approved`인 원장보고처럼
등록이 끝난 템플릿으로 문서만 생성하려면 4단계부터 시작하면 됩니다. 반복 구간은 후보
생성기가 의미를 추측하지 않으며, 사람이 `alias_map.json`의 `blocks` 계약으로 선언한 경우에만
입력 항목 수만큼 전개됩니다.

어떤 모듈이 왜 여기 포함/제외됐는지는
[docs/agent-policies/hwpx-render-pipeline-diagram.md](docs/agent-policies/hwpx-render-pipeline-diagram.md)의
Mermaid 다이어그램과 대조해서 실제 `import`를 하나씩 추적해 확정했습니다.

## 이 저장소가 다루지 않는 것

- `core/compose/` (docx/pptx exporter, gongmun 스타일 프로필, 일반 `md2hwpx` 경로) — 이
  파이프라인의 institution-hwpx 분기도 결국 `orchestrate_hwpx_render()`만 호출하므로
  compose 자체는 불필요합니다.
- `core/templates/quality/refine.py`를 제외한 나머지 후보 생성 파이프라인 —
  `core/templates/pipeline.py`와 `quality/refine.py`는 `core/templates/__init__.py`가
  즉시 import하기 때문에 실행 시점 의존성으로 포함돼 있지만, QA/렌더 경로에서 직접
  호출되지는 않습니다.
- `templates/institutions/` (실제 기관 템플릿 데이터) — 별도 **비공개** 저장소로
  분리했습니다. 금감원 내부 보고 양식의 실제 구조(원본 바이트, 서식 문구)가 들어있어
  공개 저장소에 함께 둘 수 없습니다. 이 저장소 루트에 같은 경로(`templates/institutions/`)로
  git submodule을 걸어야 `core/document_api/service.py`의 `_TEMPLATE_ROOT`가 정상 동작합니다.

## 외부 의존성

- `skills/hwp-skill` — git submodule, `https://github.com/YoungSeo5/edudoc_hwp_skill.git`.
  table_cell 필드 치환을 이 스킬의 `scripts/fill_hwpx.py` 서브프로세스로 위임합니다.
- `python-hwpx`, `lxml`, `fonttools` (`requirements.txt`).

## 1. 실행 환경 준비

Python은 [.python-version](.python-version)의 3.13으로 고정합니다. 비공개
`templates/institutions/` 저장소를 읽을 권한이 있는 환경에서 submodule과 개발 의존성을
준비합니다.

Windows PowerShell:

```powershell
git submodule update --init --recursive
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

macOS/Linux Bash:

```bash
git submodule update --init --recursive
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements-dev.txt
```

## 2. 새 원본 HWPX에서 후보 만들기

임의의 정상 HWPX는 아래 명령으로 `candidate` 템플릿을 만들 수 있습니다. 출력 폴더는
기존 경로를 덮어쓰지 않으며 `sandbox/` 아래의 새 경로를 사용합니다.

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts/templates/qa_hwpx_template.py `
  --source <원본.hwpx> `
  --output-dir sandbox/template-candidates/<새-후보> `
  --institution <기관명> `
  --document-type <문서유형>
```

macOS/Linux Bash:

```bash
./.venv/bin/python scripts/templates/qa_hwpx_template.py \
  --source <원본.hwpx> \
  --output-dir sandbox/template-candidates/<새-후보> \
  --institution <기관명> \
  --document-type <문서유형>
```

이 명령은 원본 패키지 보존, 고정 문구와 교체 필드의 구조적 분류,
`placeholder_map.json`·`content.sample.json` 생성, sample/test 왕복 렌더와 strict
검증까지 자동으로 수행합니다. 결과는 승인 템플릿이 아니라 사람이 검토해야 하는
`candidate`입니다.

## 3. 후보 계약 검토

QA 명령이 성공하면 후보 폴더에서 아래 항목을 함께 검토합니다.

| 파일 | 확인할 내용 |
|---|---|
| `source.hwpx` | 입력 원본과 동일한 snapshot인지 |
| `template.json` | 기관·문서유형·`template_id`와 `status: candidate` |
| `placeholder_map.json` | field 위치, `replacement_mode`, 레이아웃 계약 |
| `template.review.md` | 자동 분류 결과를 사람이 승인할 수 있는지 |
| `content.sample.json`, `content.test.json` | 모든 field가 의도한 값을 받는지 |
| `roundtrip.sample.hwpx`, `roundtrip.test.hwpx` | 원본 구조와 서식이 보존되는지 |
| `qa.report.json` | source snapshot, field identity, strict 검증 결과 |
| `alias_map.json` | 별칭·choice·text rule·반복·metadata 계약. 최종 생성용 후보라면 사람이 작성 |

strict 검증 성공만으로 의미상 field 분류, 반복 구간, 기관 승인이 자동 확정되는 것은 아닙니다.
최종 문서 생성 경로는 `alias_map.json`의 metadata 계약과 요청자 정보도 요구합니다. 등록 CLI는
후보의 필수 파일·식별자·상태를 검사하지만 이 metadata 계약까지 대신 작성하거나 승인하지
않으므로, 최종 생성용 후보는 등록 전에 계약을 완성하고 왕복 결과를 다시 확인해야 합니다.

### 반복 계약을 정하는 기준

후보 생성기는 원본 바이트에서 확인되는 구조만 기록합니다. 어떤 문단이 의미상 반복되는지는
임의로 추측하지 않습니다.

- `alias_map.json`의 반복 블록 계약이 없으면 각 교체 위치를 독립 필드로 만든다.
- 사람이 반복 anchor·level·separator를 확인해 `alias_map.json`의 `blocks`로 선언하면,
  이후 렌더러가 입력 항목 수만큼 해당 원본 문단 구조를 반복 전개한다.
- 반복이 필요 없는 템플릿은 별도 반복 계약 없이 그대로 후보 생성·QA가 가능하다.

따라서 “아무 HWPX나 넣으면 안전한 비반복 후보가 만들어지는 경로”는 자동화되어 있지만,
“문서 의미를 읽어 반복 구간까지 자동 확정”하는 기능은 제공하지 않습니다. 이는 잘못된 반복
판단으로 기관 서식을 바꾸지 않기 위한 의도적인 경계입니다.

## 4. 승인 후보 등록

사람이 후보를 검토하고 승인한 경우에만 등록합니다.

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts/templates/register_hwpx_template.py `
  --candidate sandbox/template-candidates/<후보> --approve
```

macOS/Linux Bash:

```bash
./.venv/bin/python scripts/templates/register_hwpx_template.py \
  --candidate sandbox/template-candidates/<후보> --approve
```

등록은 후보를 정식 Registry 경로에 복사해 `approved`로 바꾸고 Registry 조회를 확인한 뒤,
성공한 경우 원래 후보 폴더를 삭제합니다. 정식 경로는 비공개 `templates/institutions/`
submodule 내부이므로 등록 결과는 템플릿 데이터 저장소에서 별도로 검토·커밋해야 합니다.
이 명령은 Git commit이나 push를 자동으로 수행하지 않습니다.

## 5. 승인 템플릿으로 최종 문서 생성

승인 템플릿은 `template_id`와 metadata 계약을 가진 입력으로 렌더합니다.

`content.json`은 최상위에 `template_id`와 `fields` 두 키를 요구합니다(`load_template_content`).
`template_id`가 승인 템플릿의 값과 다르면 `template_id mismatch`로 렌더를 거부합니다.

```json
{
  "template_id": "<승인 템플릿의 template_id>",
  "fields": {
    "<사람용 별칭 또는 field_id>": "<값>"
  }
}
```

`fields`의 키로 무엇을 쓸 수 있는지는 그 템플릿의 `alias_map.json`이 정합니다. 최종 생성은
metadata 계약을 포함한 alias 계약의 사람용 이름을 사용합니다. `alias_map.json`이 아직 없는
후보의 QA 왕복에서만 `field_id`를 그대로 입력합니다.

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts/templates/render_hwpx_template.py `
  --institution <기관명> --document-type <문서유형> `
  --content <content.json> --output sandbox/<출력.hwpx> `
  --requester-name <요청자>
```

macOS/Linux Bash:

```bash
./.venv/bin/python scripts/templates/render_hwpx_template.py \
  --institution <기관명> --document-type <문서유형> \
  --content <content.json> --output sandbox/<출력.hwpx> \
  --requester-name <요청자>
```

성공 JSON의 `missing_fields`, `leftover_placeholders`를 함께 확인하고, Python API를
직접 호출했다면 `RenderResult.unknown_keys`도 확인해야 합니다.
strict 패키지 검증 통과만으로 시각적 충실도나 기관 승인을 뜻하지 않습니다.

## 6. Python API로 승인 템플릿 사용하기

CLI 대신 라이브러리로 쓸 때의 공개 진입점은 `core.document_api`의 네 함수뿐입니다.
저장소 루트가 `sys.path`에 있어야 하고, `templates/institutions/` submodule이 없으면
승인 템플릿을 찾지 못해 `HwpxTemplateRenderError`가 납니다.

```python
from datetime import datetime, timezone
from pathlib import Path

from core.adapters.hwpx_template_input import RenderExecutionContext
from core.document_api import (
    get_template_contract,
    list_approved_templates,
    render_approved_document,
    validate_template_content,
)

# 등록된 승인 템플릿 목록 (reference_format == "hwpx" 인 것만)
for candidate in list_approved_templates():
    identity = candidate.identity  # institution·document_type·template_id는 여기 있다
    print(identity.institution, identity.document_type, identity.template_id)

# 채워야 할 field와 사람용 별칭 계약. alias_map이 없으면 두 번째 값은 None
placeholder_map, alias_map = get_template_contract("<기관명>", "<문서유형>")

# requested_at은 반드시 UTC. 아니면 HwpxTemplateRenderError
context = RenderExecutionContext(
    requester_name="<요청자>",
    requested_at=datetime.now(timezone.utc),
)

content = {"<사람용 별칭 또는 field_id>": "<값>"}

# 파일을 쓰지 않고 입력만 검사한다
prepared = validate_template_content("<기관명>", "<문서유형>", content, context)

result = render_approved_document(
    "<기관명>", "<문서유형>", content, Path("sandbox/<출력>.hwpx"), context
)
```

`render_approved_document`가 돌려주는 `RenderResult`는 예외가 없어도 문제를 담고 있을 수
있습니다. 아래 셋을 직접 확인해야 합니다.

| 필드 | 뜻 |
|---|---|
| `missing_fields` | 템플릿이 요구했으나 입력에 없던 field |
| `leftover_placeholders` | 치환되지 않고 출력에 남은 `{{...}}` |
| `unknown_keys` | 입력에 있었으나 템플릿이 쓰지 않은 키 (CLI JSON에는 나오지 않음) |

Python API 인자의 `content`는 CLI `content.json`의 `fields` 객체에 해당합니다.
`template_id`는 인자로 받지 않고 기관·문서유형으로 승인 템플릿을 찾습니다.

## 7. 저장소 검증

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q --basetemp=sandbox/pytest
```

macOS/Linux Bash:

```bash
./.venv/bin/python -m pytest tests/ -q --basetemp=sandbox/pytest
```

CI는 설치 Python을 3.13으로 고정한 뒤 운영체제별 venv 경로 대신 실행합니다.

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests/ -q --basetemp=sandbox/pytest
```
