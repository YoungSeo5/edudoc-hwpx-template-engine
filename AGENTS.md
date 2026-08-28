# AGENTS.md

Project-level contract for Codex, Claude, and other coding agents. Keep this file
short; durable architecture belongs in `docs/`.

## Project goal

이 저장소는 기관이 승인한 HWPX 서식의 레이아웃을 보존한 채 내용을 채워 문서를
생성하는 참조 기반 문서 생성 엔진이며, 최상위 E2E workflow는 두 개다.

1. `TEMPLATE_CREATE` — 새 재사용 HWPX template candidate를 만든다. 정상 진입
   경로는 사용자 요구사항·계약·layout knowledge로 self-authored candidate를
   만드는 경로와 정확한 기존 HWPX source에서 추출하는 경로 두 개이며, 둘 다
   candidate QA, human review, human approval, approved-template registration
   으로 합류한다.
2. `DOCUMENT_RENDER` — approved template을 resolve하고 supplied document
   content를 해석·검증한 뒤, approved template contract를 보존하며 content를
   적용해 최종 HWPX를 생성한다.

이 저장소는 포맷 변환기가 아니다. 일반 문서 변환, 마크다운→HWPX,
DOCX/PPTX/PDF 내보내기, 공문 생성은 이 저장소 소관이 아니다. Source-based
extraction을 `TEMPLATE_CREATE` 전체 workflow로 취급하지 않는다.

canonical E2E workflow와 이 저장소가 아직 책임을 정의하지 않은 단계는
[Product workflow contract](docs/product-workflow-contract.md)가 다룬다.
Source-based candidate extraction과 approved-template rendering의 세부 규칙은
[HWPX template rendering policy](docs/agent-policies/hwpx-template-rendering.md)에
있고, candidate QA와 final rendering이 공유하는 실제 실행 흐름은
[HWPX render pipeline diagram](docs/agent-policies/hwpx-render-pipeline-diagram.md)이
보여준다.

## Response language

Always respond to the user in Korean, including implementation summaries,
test results, review findings, and explanations. Keep code identifiers,
commands, paths, and literal error messages in their original language.

## Absolute prohibitions

- 필드 값, 기관 규칙, 출력 형식, 템플릿 의미, 추출된 서식을 지어내지 않는다.
  모르면 `확인 필요` 또는 `null`.
- 오래된 문서에 맞추려고 코드를 조용히 바꾸지 않는다. 현재 동작을 그대로 기술하고
  해소되지 않은 충돌은 `확인 필요`로 보고한다.
- 파일 형식에서 문서 정책이나 템플릿 정체성을 추론하지 않는다.
- 렌더러, 템플릿, 프로파일을 조용히 다른 것으로 대체하거나 일반 `md2hwpx`
  경로로 폴백하지 않는다.
- 사용자나 프로젝트 정책이 고정한 경로, 렌더러, 템플릿, 실행 명령은 하드 제약이다.
- 고정 경로가 실패하면 정확한 실패를 보고하고, 다른 경로·임시 디렉터리·실행 환경으로
  우회하지 않는다.
- pytest 임시 파일, 후보 QA 출력, staging 산출물을 저장소 루트에 만들지 않는다.
- pytest와 QA 임시 산출물은 `sandbox/`만 사용한다. 이 경로가 없거나 쓸 수 없으면
  대체 경로를 만들지 말고 중단한다.
- 승인되지 않은 우회 경로로 얻은 결과는 구현·검증 근거가 아니다.
- `skills/hwp-skill/` 하위를 수정하지 않는다. 별도 저장소의 submodule이다.
- `templates/institutions/` 하위 템플릿 데이터를 임의로 수정하지 않는다.
  별도 비공개 저장소의 submodule이다.
- 사람의 명시적 승인 없이 후보의 `status`를 `approved`로 바꾸지 않는다.
- 명시적 승인 없이 자동 설치, 자동 clone, 전역 상태 변경, 유료 LLM API 호출,
  commit, push, 파일 삭제를 하지 않는다.
- 변경 범위를 요청에 한정하고 사용자의 작업 트리 변경을 보존한다.
- 생성된 출력물, 캐시, 로그, 추적되지 않는 파일을 구현 근거로 쓰지 않는다.
- 현재 소스·연결·테스트 근거 없이 완료, 검증, 사용 가능, 승인, 배포를 주장하지 않는다.
- 계획만 제시하고 실행 없이 작업을 종료하지 않는다. 사람의 승인이 필요한 지점(예: 후보
  승인, commit/push, 파일 삭제)이 아니라면 구현과 검증까지 진행한다.
- 사용자가 요청하지 않은 capability, 옵션, 설정 가능성을 임의로 추가하지 않는다.
- 임시 worktree 안에서 실제 repository, submodule, template registry 또는
  삭제되면 안 되는 사용자 데이터 폴더를 가리키는 Windows Junction,
  directory symlink 등의 디렉터리 링크를 만들지 않는다.
- `git worktree remove --force` 실행 전 해당 worktree에 외부 디렉터리로
  연결되는 Junction, symlink 등의 reparse point가 없는지 확인한다.
  외부 경로로 연결된 항목이 있으면 worktree를 강제 삭제하지 않는다.
  자세한 cleanup 규칙은
  [Work-Unit Execution Policy](docs/agent-policies/work-unit-execution.md)를 따른다.

## Dependencies

이 저장소는 submodule 두 개 없이는 동작하지 않는다. `templates/institutions/`가
없으면 승인 템플릿을 찾을 수 없고, `skills/hwp-skill/`이 없으면 `table_cell`
필드를 가진 템플릿 렌더가 실패한다. submodule 초기화와 실행 환경 준비 절차는
[README](README.md)의 `1. 실행 환경 준비`가 소유한다.

## Work-unit execution contract

모든 scoped task는 substantive work 전에 explicit task contract가 있어야 한다.

Before starting a task, read in this order:

1. this root `AGENTS.md`;
2. [Product workflow contract](docs/product-workflow-contract.md);
3. the active task contract in `docs/tasks/`;
4. only the policies, references, and source files required by that task.

task contract authority(`PRESERVE` / `REVISE`), 발견 이슈 분류
(`BLOCKER` / `FOLLOW-UP` / `OUT_OF_SCOPE`), DONE 판단의 상세 규칙은
[Work-Unit Execution Policy](docs/agent-policies/work-unit-execution.md)가
authoritative하다.

## Implementation scope

- 구현이나 리팩터링 전에 [Minimal Abstraction Policy](docs/agent-policies/minimal-abstraction.md)를
  읽고 따른다.
- 그 정지 조건에 해당하면 구현을 멈추고, 추가 구조가 왜 필요한지 먼저 보고한다.

## Contract interpretation

Contract, Schema, Institution Design을 기존 구현이나 테스트에 맞추기 위해 임의로
재해석하거나 약화하지 않는다. 구현을 계약에 맞게 고치거나, 고칠 수 없으면 충돌을
`확인 필요`로 보고한다. 계약별 책임 경계와 해석 규칙은
[Template authoring contracts](docs/contracts/template-authoring-contracts.md)가
authoritative하다.

## Test and build requirements

- Git `HEAD`의 현재 코드와 자동화 테스트가 현재 동작의 최우선 근거다.
- 실행 동작을 추가·변경·수정·제거하는 모든 작업은
  [Task-Scoped Testing Policy](docs/agent-policies/task-scoped-testing.md)를 읽고
  따른다. 이 정책 파일이 없거나 읽을 수 없으면 작업을 중단하고 보고한다.
- 최종 HWPX 출력은 strict `hwpx.validate_package`와
  [HWPX template rendering policy](docs/agent-policies/hwpx-template-rendering.md)가
  정의한 의미·구조 검사를 통과해야 한다.
- strict 검증 통과는 시각적 충실도나 기관 승인을 뜻하지 않는다.

## Documentation changes

문서를 만들거나 옮기거나 이름을 바꾸거나 나누거나 합치거나 줄이거나 보관하거나
삭제하기 전에 [Documentation Migration Safety](docs/agent-policies/documentation-migration-safety.md)를
읽고 따른다. 모든 문서 변경에 필수다.

참조된 정책 파일이 없거나 읽을 수 없으면 문서 작업을 중단하고 누락을 보고한다.
정책이 확보될 때까지 어떤 문서도 수정하지 않는다.

## Commands

운영·개발 명령은 [README](README.md)의 `운영 매뉴얼`이 소유하고, 스크립트별 역할과
경계는 [scripts/AGENTS.md](scripts/AGENTS.md)가 소유한다. 저장소 전체 검증은 다음
명령이다.

```bash
python -m pytest tests/ -q --basetemp=sandbox/pytest
```

## Concurrent work

- 작업 시작 시 `git status`와 관련 diff를 확인한다.
- unrelated change를 reset, revert, checkout, 삭제하지 않는다.
- dirty working tree, 첫 테스트 실패, 변경 범위 확대, LSP 부재는 단독으로 작업 중단 사유가 아니다.
- 현재 상태 위에서 요청 범위의 최소 변경을 적용하고, 실패가 현재 변경 때문인지 가능한 범위에서 구분한다.
