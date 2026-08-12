# scripts/AGENTS.md

`scripts/`는 사람이 호출하는 명령 래퍼다.

## Responsibility

기존 프로젝트 로직을 호출하는 스크립트만 둔다. `scripts/templates/`가 승인 템플릿
출력과 후보 제작 워크플로를 제공한다.

| 스크립트 | 역할 |
|---|---|
| `render_hwpx_template.py` | 승인 템플릿에 `content.json`을 채워 HWPX 생성. 승인 템플릿이 없거나 `template_id`가 다르면 거부한다 |
| `render_hwpx_template_from_source.py` | 승인 템플릿에 source 파일(`.md`/`.txt`/`.hwpx`)을 매핑해 HWPX 생성. 결정적 필드(날짜·제목·부서·연락처)만 추출하고, 판단이 필요한 필드가 하나라도 미해결이면 렌더를 거부한다 |
| `qa_hwpx_template.py` | 원본 HWPX를 후보로 분리하고 sample/test 왕복 출력을 strict 검증. `template.json`을 `candidate` 상태로 남긴다 |
| `register_hwpx_template.py` | 사람이 승인한 후보를 정식 경로에 등록. `--approve`가 사용자의 명시적 승인 의사다 |

## Rules

- 스크립트는 `core/`와 `validators/`를 호출할 수 있다.
- core 로직을 스크립트에서 중복 구현하지 않는다.
- 후보 QA와 승인 템플릿 출력은 별개 경로다. 하나가 다른 하나로 폴백하지 않는다.
- `qa_hwpx_template.py`는 `template.json`을 `candidate`로 남겨야 한다. 이 스크립트가
  템플릿을 승인하지 않는다.
- 기존 후보 폴더를 덮어쓰지 않는다. 후보는 저장소 밖 무시되는 경로에 만든다.
- 숨은 설치 동작을 추가하지 않는다.
- 외부 저장소를 자동으로 clone하지 않는다.
- 실패는 예외로 죽지 않고 `{"ok": false, ...}` JSON 요약으로 보고하는 현재 방식을
  유지한다.

경로 선택의 완전한 규칙은
[HWPX template routing rules](../docs/agent-policies/hwpx-template-rendering.md)에 있다.
