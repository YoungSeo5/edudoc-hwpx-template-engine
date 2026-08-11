# tests/AGENTS.md

`tests/`는 자동화 테스트와 테스트 픽스처다.

## Responsibility

- 단위 테스트
- 회귀 테스트
- 작은 익명화 픽스처

`tests/task_scoped/`는 작업 단위로 추가된 테스트를 모아 둔 곳이다. 이름은
[Task-Scoped Testing Policy](../docs/agent-policies/task-scoped-testing.md)에서 왔다.
동작을 바꾸는 모든 작업은 그 작업 전용의 새 테스트를 여기 추가한다.

## Rules

- 테스트는 임시 출력 디렉터리를 쓴다.
- 생성된 출력물이나 이전 실행 결과에 의존하지 않는다.
- 실제 기관 문서를 픽스처로 커밋하지 않는다. 실제 템플릿 데이터는 비공개
  submodule(`templates/institutions/`)에 있고, 이 저장소는 공개다.
- 테스트 전용 입력은 `tests/fixtures/`에 둔다.
- 구현을 통과시키려고 기대값, ID, 개수, 스냅샷, 단언을 바꾸지 않는다.
  요구사항이 바뀌었거나 테스트가 틀렸음을 입증한 경우에만 바꾸고 이유를 보고한다.

## 출력 검증 규칙

"파일이 만들어졌다"를 품질의 근거로 삼지 않는다. strict 패키지 검증 통과도
시각적 충실도나 기관 승인을 뜻하지 않는다.

다음을 확인한다.

- 내용 보존
- 표 구조 보존
- 레이아웃 계약 유지 (`verify_recorded_layout()`)
- placeholder 잔여물 없음
- 알려진 한계

## 템플릿 데이터 의존

일부 테스트는 `templates/institutions/` submodule의 실제 승인 템플릿을 읽는다.
submodule이 초기화되지 않으면 그 테스트들은 실패한다. 이때 테스트를 고치지 말고
`git submodule update --init --recursive`를 먼저 실행한다.
