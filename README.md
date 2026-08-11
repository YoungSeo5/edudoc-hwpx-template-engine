# HWPX 승인 템플릿 렌더링·QA 엔진

`edudoc`에서 승인 템플릿 최종 렌더링과 후보 템플릿 QA 왕복이 공유하는 부분만
잘라낸 엔진입니다. 어떤 모듈이 왜 여기 포함/제외됐는지는
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

## 준비

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

## 새 HWPX에서 후보 만들기

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

### 반복 처리 경계

후보 생성기는 원본 바이트에서 확인되는 구조만 기록합니다. 어떤 문단이 의미상 반복되는지는
임의로 추측하지 않습니다.

- `alias_map.json`의 반복 블록 계약이 없으면 각 교체 위치를 독립 필드로 만든다.
- 사람이 반복 anchor·level·separator를 확인해 `alias_map.json`의 `blocks`로 선언하면,
  이후 렌더러가 입력 항목 수만큼 해당 원본 문단 구조를 반복 전개한다.
- 반복이 필요 없는 템플릿은 별도 반복 계약 없이 그대로 후보 생성·QA가 가능하다.

따라서 “아무 HWPX나 넣으면 안전한 비반복 후보가 만들어지는 경로”는 자동화되어 있지만,
“문서 의미를 읽어 반복 구간까지 자동 확정”하는 기능은 제공하지 않습니다. 이는 잘못된 반복
판단으로 기관 서식을 바꾸지 않기 위한 의도적인 경계입니다.

## 승인 후보 등록과 최종 생성

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

승인 템플릿은 `template_id`와 metadata 계약을 가진 입력으로 렌더합니다.

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

## 검증

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
