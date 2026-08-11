---
name: hwpx-institution-template
description: "기관 승인 HWPX 템플릿에 내용을 채워 문서를 생성하거나, 새 원본 HWPX에서 템플릿 후보를 추출·QA·등록하는 스킬. '금감원 원장보고', '금감원 원페이지', '승인 템플릿으로 작성', '기관 템플릿', '템플릿 후보 추출', '템플릿 등록', 'placeholder_map', 'alias_map', '원장보고 만들어줘' 등 특정 기관의 정해진 서식을 채우는 작업에 사용한다. 자유 형식 문서를 새로 만들거나 HWP↔HWPX 변환, 마크다운→HWPX 변환에는 사용하지 않는다(그건 hwpx 스킬 소관)."
allowed-tools: Bash(python *), Bash(git submodule *), Read, Write, Glob, Grep
---

# 기관 승인 HWPX 템플릿 생성

기관이 정한 서식(원본 HWPX)의 레이아웃을 **바이트 단위로 보존**한 채 내용만 채워
문서를 생성한다. 포맷 변환기가 아니라 참조 기반 문서 생성 시스템이다.

## 절대 금지

- 필드 값, 기관 규칙, 템플릿 의미, 추출된 서식을 **지어내지 않는다.** 모르면 `확인 필요` 또는 `null`.
- `TemplateRegistry.find()`를 호출하기 전에 후보를 만들지 않는다.
- 승인된 템플릿이 있는데 사용자가 예시 파일을 첨부했다는 이유만으로 재추출하지 않는다.
- `exports/`, `sandbox/`, 캐시, 로그를 뒤져서 어떤 템플릿인지 추측하지 않는다.
- 렌더러·템플릿·프로파일을 조용히 다른 것으로 대체하지 않는다. 일반 `md2hwpx`로 폴백하지 않는다.
- 후보(`status: candidate`)를 사람 승인 없이 `approved`로 바꾸지 않는다.

## 경로 선택

먼저 `institution`과 `document_type`을 확보한다. 없거나 모호하면 **묻는다**. 그 다음:

```
승인된 템플릿이 있는가?  →  있다 → [A] 문서 생성
                          →  없다 → [B] 후보 추출 → 사람 검토 → [C] 등록
```

### [A] 승인 템플릿으로 문서 생성

```bash
python scripts/templates/render_hwpx_template.py \
  --institution <기관명> --document-type <문서유형> \
  --content <content.json> --output <출력.hwpx> \
  --requester-name <요청자 이름>
```

`--requester-name`은 최종 생성에 **반드시** 필요하다 — `content.hpf`의 작성자·최종저장자로
기록된다. 누락 시 예외가 아니라 `{"ok": false, ...}` JSON으로 보고된다.

`content.json`의 `template_id`가 승인 템플릿과 다르면 거부된다. 사람이 읽는 이름으로
입력하려면 해당 템플릿의 `alias_map.json`을 먼저 읽어 어떤 이름이 허용되는지 확인한다.

Python에서 부를 때는 `core.document_api`가 연결 경계다 —
`list_approved_templates()`, `get_template_contract()`, `validate_template_content()`,
`render_approved_document()`. 렌더러를 직접 부르지 않는다.

### [B] 새 원본에서 후보 추출 + QA

```bash
python scripts/templates/qa_hwpx_template.py \
  --source <원본.hwpx> --output-dir <새 후보 폴더> \
  --institution <기관명> --document-type <문서유형>
```

`--template-id`는 사용자가 명시적으로 준 경우에만 넣는다(생략하면 기관·유형·원본 해시로
안정적인 ID를 만든다). 후보 폴더는 저장소 밖 무시되는 경로에 만들고, 기존 후보 폴더를
덮어쓰지 않는다. 레거시 `.hwp`는 먼저 HWPX로 변환한다.

이 명령은 `template.json`을 `candidate` 상태로 두고, sample/test 왕복 출력을 만들어
strict 검증까지 돌린다. 이미 등록된 템플릿이 있으면 `field_id` 정체성 드리프트도 함께
검사한다 — `field_id`는 순번이라 앞쪽 분류가 하나만 달라져도 뒤 번호가 조용히 밀린다.

**strict 검증 통과는 시각적 충실도나 기관 승인을 뜻하지 않는다.** 사람 검토가 필요하다.

### [C] 사람이 승인한 후보 등록

```bash
python scripts/templates/register_hwpx_template.py --candidate <후보 폴더> --approve
```

`--approve`는 사용자의 명시적 승인 의사다. 사용자가 승인하지 않았으면 붙이지 않는다.

## 상세 규칙

작업 전에 해당 문서를 읽는다. SKILL.md에 중복하지 않는다.

- [HWPX 템플릿 라우팅 규칙](docs/agent-policies/hwpx-template-rendering.md) — 경로 선택의 완전한 규칙
- [렌더링·QA 파이프라인 다이어그램](docs/agent-policies/hwpx-render-pipeline-diagram.md) — 두 경로가 공유하는 커널
- [레이아웃 보존 계약](docs/agent-policies/hwpx-layout-context.md) — `layout-context-v1` 설계

## 준비 상태 확인

이 저장소는 submodule 두 개에 의존한다. 둘 다 없으면 동작하지 않는다.

```bash
git submodule update --init --recursive
pip install -r requirements.txt
```

- `templates/institutions/` — 기관 템플릿 데이터(**비공개** 저장소). 없으면 승인 템플릿을 찾을 수 없다.
- `skills/hwp-skill/` — `table_cell` 필드 치환을 이 스킬의 `scripts/fill_hwpx.py`에 위임한다.

동작 여부가 의심되면 `python -m pytest tests/ -q`로 확인한다.
