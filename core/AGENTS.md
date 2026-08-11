# core/AGENTS.md

`core/`는 이 엔진의 런타임 구현 코드다.

## Responsibility

승인 템플릿 렌더링과 후보 템플릿 추출·QA에 필요한 런타임 로직만 둔다.

| 폴더 | 책임 |
|---|---|
| `core/adapters/` | HWPX 렌더링, 입력 해석(alias·choice·text_rules·반복 블록), table_cell 치환 위임, 템플릿별 패키지 metadata 준비 |
| `core/templates/` | HWPX 후보 추출, 콘텐츠 분리, 레이아웃 보존 계약, 품질 검사, 승인 템플릿 조회(`TemplateRegistry`) |
| `core/document_api/` | 외부 연동이 부르는 얇은 연결 경계. 별도 [AGENTS.md](document_api/AGENTS.md)를 따른다 |

## Rules

- `core/`에 생성된 출력물, 샘플, 참조 문서, 테스트를 두지 않는다.
- `core/`에 AI용 스킬 지시문을 두지 않는다.
- 템플릿 추출, 입력 해석, 렌더링, 검증 책임을 서로 섞지 않는다.
- 자동 검사는 후보를 `validated`로 표시할 수 있지만, 정식 `template.json`을
  쓰는 것은 사람의 명시적 승인만 할 수 있다.
- 넓은 재작성보다 작은 어댑터를 택한다.
- 입력은 한 방향으로만 변환한다. 정규화된 값을 사람용 입력이나 구형 구조로
  되돌리는 코드를 추가하지 않는다
  ([Minimal Abstraction Policy](../docs/agent-policies/minimal-abstraction.md)).

## 레이아웃 보존 계약

placeholder가 어떤 서식을 보존해야 하는지는 `core/templates/hwpx_layout_context.py`
한 곳에서 정의한다. 새로 보존할 서식 항목이 생겨도 분리기와 렌더러에 각각
전용 코드 경로를 추가하지 않는다. 설계는
[HWPX 레이아웃 보존 계약](../docs/agent-policies/hwpx-layout-context.md) 참조.

## Protected skills

`skills/hwp-skill/`은 별도 저장소의 submodule이다. 그 코드를 `core/`로 복사하지
않는다. 스킬 동작이 필요하면 테스트를 갖춘 작은 어댑터를 만든다
(`core/adapters/hwpx_table_fill_adapter.py`가 그 예다).
