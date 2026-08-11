# AGENTS.md

Project-level contract for Codex, Claude, and other coding agents. Keep this file
short; durable architecture belongs in `docs/`.

## Project goal

기관이 승인한 HWPX 서식의 레이아웃을 보존한 채 내용만 채워 문서를 생성하는
참조 기반 문서 생성 엔진이다. 포맷 변환기가 아니다.

이 저장소가 다루는 것은 두 경로뿐이다.

- 승인 템플릿 최종 렌더링
- 후보 템플릿 추출·QA·등록

일반 문서 변환, 마크다운→HWPX, DOCX/PPTX/PDF 내보내기, 공문 생성은 이 저장소
소관이 아니다. `docs/agent-policies/hwpx-render-pipeline-diagram.md`가 두 경로가
공유하는 실제 실행 흐름을 보여준다.

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

## Dependencies

이 저장소는 submodule 두 개 없이는 동작하지 않는다.

| 경로 | 내용 | 없을 때 |
|---|---|---|
| `templates/institutions/` | 기관 템플릿 데이터 (비공개 저장소) | 승인 템플릿을 찾을 수 없다 |
| `skills/hwp-skill/` | `table_cell` 필드 치환을 위임하는 스킬 | 해당 필드를 가진 템플릿 렌더가 실패한다 |

Windows PowerShell:

```powershell
git submodule update --init --recursive
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

macOS/Linux Bash:

```bash
git submodule update --init --recursive
./.venv/bin/python -m pip install -r requirements-dev.txt
```

## Implementation scope

- 구현이나 리팩터링 전에 [Minimal Abstraction Policy](docs/agent-policies/minimal-abstraction.md)를
  읽고 따른다.
- 그 정지 조건에 해당하면 구현을 멈추고, 추가 구조가 왜 필요한지 먼저 보고한다.

## Test and build requirements

- Git `HEAD`의 현재 코드와 자동화 테스트가 현재 동작의 최우선 근거다.
- 실행 동작을 추가·변경·수정·제거하는 모든 작업은 그 작업 전용의 새 자동화 테스트를
  최소 하나 만들고 실행해야 한다. 기존 테스트를 재사용하거나 수정하는 것만으로는
  충족되지 않는다.
- 모든 동작 변경 작업은 [Task-Scoped Testing Policy](docs/agent-policies/task-scoped-testing.md)를
  읽고 따른다. 이 정책 파일이 없거나 읽을 수 없으면 작업을 중단하고 보고한다.
- 초점 테스트 → 직접 영향받는 테스트 → 요청된 전체 테스트 순으로 실행한다.
- 실행한 정확한 검증 명령과 결과를 실패·경고까지 포함해 보고한다.
- 관련 테스트가 하나라도 실패하거나 경고하면 `검증됨`, `사용 가능`, `완료`라고
  보고하지 않는다.
- 최종 HWPX 출력은 strict `hwpx.validate_package`와
  [HWPX template rendering policy](docs/agent-policies/hwpx-template-rendering.md)가
  정의한 의미·구조 검사를 통과해야 한다.
- strict 검증 통과는 시각적 충실도나 기관 승인을 뜻하지 않는다.

### 해결된 회귀

`tests/task_scoped/test_fss_one_page_final_rendering.py::test_one_page_restores_table_cell_leading_fwspaces_after_skill_fill`
와 같은 셀의 여러 text node를 함께 검증하는 작업 전용 테스트는 2026-08-11의
`text_node_index` 단위 복원 수정으로 통과한다. 회귀 시 기대값을 바꾸지 말고 렌더러를 고친다.

## Commands

Windows PowerShell:

```powershell
git submodule update --init --recursive
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

# 승인 템플릿으로 문서 생성
.\.venv\Scripts\python.exe scripts/templates/render_hwpx_template.py `
  --institution <기관명> --document-type <문서유형> `
  --content <content.json> --output <출력.hwpx> --requester-name <요청자>

# 새 원본에서 후보 추출 + QA 왕복 검증
.\.venv\Scripts\python.exe scripts/templates/qa_hwpx_template.py `
  --source <원본.hwpx> --output-dir <후보 폴더> `
  --institution <기관명> --document-type <문서유형>

# 사람이 승인한 후보 등록
.\.venv\Scripts\python.exe scripts/templates/register_hwpx_template.py --candidate <후보 폴더> --approve

.\.venv\Scripts\python.exe -m pytest tests/ -q --basetemp=sandbox/pytest
```

macOS/Linux Bash:

```bash
git submodule update --init --recursive
./.venv/bin/python -m pip install -r requirements-dev.txt

./.venv/bin/python scripts/templates/render_hwpx_template.py \
  --institution <기관명> --document-type <문서유형> \
  --content <content.json> --output <출력.hwpx> --requester-name <요청자>

./.venv/bin/python scripts/templates/qa_hwpx_template.py \
  --source <원본.hwpx> --output-dir <후보 폴더> \
  --institution <기관명> --document-type <문서유형>

./.venv/bin/python scripts/templates/register_hwpx_template.py --candidate <후보 폴더> --approve
./.venv/bin/python -m pytest tests/ -q --basetemp=sandbox/pytest
```

CI는 설치 Python을 3.13으로 고정한 뒤 운영체제별 venv 경로 대신 다음을 사용한다.

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests/ -q --basetemp=sandbox/pytest
```

## Documentation changes

문서를 만들거나 옮기거나 이름을 바꾸거나 나누거나 합치거나 줄이거나 보관하거나
삭제하기 전에 [Documentation Migration Safety](docs/agent-policies/documentation-migration-safety.md)를
읽고 따른다. 모든 문서 변경에 필수다.

참조된 정책 파일이 없거나 읽을 수 없으면 문서 작업을 중단하고 누락을 보고한다.
정책이 확보될 때까지 어떤 문서도 수정하지 않는다.
