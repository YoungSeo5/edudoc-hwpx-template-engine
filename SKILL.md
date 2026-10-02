---
name: hwpx-institution-template
description: "기관 요구사항 또는 정확한 HWPX 원본으로 재사용 양식 후보를 만들고, 사람이 승인한 기관 양식으로 HWPX 문서를 생성한다. 기관 양식 제작, 후보 QA·승인·등록, 원장보고·원페이지 보고서에 사용한다. 범용 HWP/HWPX 변환, Markdown→HWPX 변환, 자유 형식 문서 생성에는 사용하지 않는다."
---

# 기관 HWPX 템플릿

이 standalone 패키지는 참조 기반 HWPX 문서 시스템이다.

```text
새 재사용 양식 제작  -> TEMPLATE_CREATE
승인된 양식으로 작성 -> DOCUMENT_RENDER
```

포맷 변환기가 아니다. 일반 HWP/HWPX 변환, Markdown→HWPX, 자유 형식 문서
생성, 공문 생성, 레거시 `.hwp` 입력·변환은 범위 밖이다. 전체 제품 책임은
[Product workflow contract](docs/product-workflow-contract.md)를 따른다.

## 외부 registry

패키지에는 코드, 읽기 전용 `edudoc` provision, `skills/hwp-skill` 런타임
의존성만 둔다. `self-authored`, candidate, approved, audit, workflow 임시 파일은
스킬 패키지 안에 저장하지 않는다. `skills/hwp-skill`은 수정하지 않고
`table_cell` 치환에만 사용한다. repo-scoped `.agents/skills`를 만들지 않는다.

```text
<registry>/
├─ provision/edudoc/{_design,_families}/
├─ self-authored/edudoc/<document_type>/
├─ candidates/<candidate_id>/
├─ approved/<institution>/<document_type>/
├─ _audit/<template_id>/
└─ _tmp/
```

스킬을 로딩할 때 registry를 묻지 않는다. 실제 `TEMPLATE_CREATE` 또는
`DOCUMENT_RENDER` 요청에서 다음 순서로 해석한다.

1. 사용자가 `--registry-root <absolute path>`를 제공했으면 그것을 사용한다.
2. 없으면 `~/.edudoc-hwpx-template/config.json`의 사용자 설정을 사용한다.
3. 둘 다 없을 때만 멈추고 “기존 registry 연결” 또는 “신규 registry 초기화” 중
   하나를 선택하도록 요청한다.

사용자가 기존 registry 연결을 명시하면 다음을 사용한다.

```bash
python scripts/templates/configure_hwpx_registry.py connect \
  --registry-root <existing-registry>
```

사용자가 신규 초기화를 명시하면 다음을 사용한다. 초기화는 사용자의 명시 요청
없이 실행하지 않는다.

```bash
python scripts/templates/configure_hwpx_registry.py initialize \
  --registry-root <new-empty-registry>
```

설정은 이후 같은 사용자의 작업에 재사용하므로 매번 저장 위치를 묻지 않는다.
Google Drive 동기화 폴더는 조직 공용 registry가 될 수 있는 경로의 예시일 뿐이다.
Drive 업로드·공유나 이메일 전송은 이 패키지의 구현 기능이 아니다.

registry 구조와 설정·임시 파일의 상세 경계는
[External template registry](docs/tasks/external-template-registry.md)를 읽는다.

## TEMPLATE_CREATE

새 양식은 두 경로 중 하나로 candidate QA에 합류한다.

초기 승인 템플릿이 없는 상태가 정상이며, 다른 기관의 예제나 과거 승인본(금융감독원
포함)을 대신 사용하지 않는다. 이를 조회·추출·렌더 경로의 폴백으로도 사용하지 않는다.

### 요구사항 기반 self-authoring

정확한 HWPX source가 없는 신규 양식 요청에 사용한다. 사용자가 필드나 표 구조를
설계하도록 요구하지 않는다. 사용자 목적과 제공 근거, `edudoc` Institution Design
Contract를 분석해 다음 순서로 결정한다.

```text
TemplateRequest
-> 고정 문구·고정 라벨·입력 필드·계층 구조 결정
-> Semantic Template Contract
-> Institution Design Contract + TemplateSpec
-> candidate
```

기관 업무 의미를 지어내야 하는 항목만 `확인 필요`로 묻는다. 확인 전에는 계약이나
candidate를 만들지 않는다.

production 입력은 registry의 다음 경로만 사용한다.

```text
<registry>/self-authored/edudoc/<document_type>/template_request.json
<registry>/self-authored/edudoc/<document_type>/semantic_contract.json
<registry>/self-authored/edudoc/<document_type>/template_spec.json
<registry>/provision/edudoc/_design/design.json
```

```bash
python scripts/templates/author_hwpx_template.py \
  --template-request <registry>/self-authored/edudoc/<document_type>/template_request.json \
  --semantic-contract <registry>/self-authored/edudoc/<document_type>/semantic_contract.json \
  --template-spec <registry>/self-authored/edudoc/<document_type>/template_spec.json \
  --institution-design <registry>/provision/edudoc/_design/design.json \
  --institution edudoc --document-type <document_type> \
  --registry-root <registry>
```

현재 지원 materializer는 `title`, `info_table`, `body_section`,
`one_page_report`다. `repeat_section`과 병합 셀 복합 표는 지원된다고 주장하지
않는다. 계약 의미는 [Template authoring contracts](docs/contracts/template-authoring-contracts.md)를
읽는다. 이 명령은 candidate까지만 만들며, 승인 등록이나 최종 렌더를 이어서 실행하지
않는다. `--template-id`는 사용자가 명시적으로 제공한 경우에만 넣고, 기존 candidate
폴더를 대상으로 하는 `--candidate-id` 또는 `--output-dir`를 지정하지 않는다.

### 정확한 HWPX source 추출

기관과 문서 유형을 확보한 뒤 approved registry를 먼저 조회한다. 승인본이 있으면
재사용하며, 사용자가 명시적으로 재추출을 요청한 경우에만 새 candidate를 만든다.
source가 없거나 여러 파일 중 정확한 원본이 불명확하면 묻고 멈춘다.

```bash
python scripts/templates/qa_hwpx_template.py \
  --source <exact-source.hwpx> \
  --institution <institution> --document-type <document_type> \
  --registry-root <registry>
```

candidate는 `<registry>/candidates/<candidate_id>/`에만 만든다. strict QA 통과는
기관 승인이나 시각적 충실도를 뜻하지 않는다. 이 명령은 candidate까지만 만들며,
승인 등록이나 최종 렌더를 이어서 실행하지 않는다. `--template-id`는 사용자가
명시적으로 제공한 경우에만 넣고, 기존 candidate 폴더를 덮어쓰지 않는다.

### 사람 검토와 등록

두 경로 모두 다음 승인 경계를 지킨다.

```text
candidate -> machine QA -> human visual review
-> candidate ID와 digest를 확인한 explicit approval -> registration
```

사람이 roundtrip HWPX를 한컴에서 검토하고, 특정 candidate ID와 현재 digest에
대한 승인을 명시한 뒤에만 실행한다.

```bash
python scripts/templates/register_hwpx_template.py \
  --candidate <registry>/candidates/<candidate_id> \
  --registry-root <registry> --approve
```

승인 의사·candidate ID·digest 중 하나라도 불명확하면 등록하지 않는다.

## DOCUMENT_RENDER

`institution`과 `document_type`으로 `<registry>/approved/`만 조회한다. approved
template이 없으면 렌더하지 않으며, candidate나 다른 렌더러로 폴백하지 않는다.

```bash
python scripts/templates/render_hwpx_template.py \
  --institution <institution> --document-type <document_type> \
  --content <content.json> --output <output.hwpx> \
  --requester-name <requester> --registry-root <registry>
```

`.md`, `.markdown`, `.txt`, `.hwpx` source 입력은 다음 경로를 사용한다.

```bash
python scripts/templates/render_hwpx_template_from_source.py \
  --institution <institution> --document-type <document_type> \
  --source <source-file> --output <output.hwpx> \
  --requester-name <requester> --registry-root <registry>
```

required 값, `확인 필요`, 판단이 필요한 미해결 필드, `template_id` 불일치가
있으면 최종 output을 만들지 않는다.

Python 호출은 `core.document_api` 공개 경계만 사용한다.
`list_approved_templates()`, `get_template_contract()`,
`validate_template_content()`, `render_approved_document()`,
`render_document_from_source()` 외에 renderer·registry 내부 구현을 직접 호출하지
않는다.

## 준비 상태와 상세 규칙

실행 전 패키지 root, Python 및 requirements, `skills/hwp-skill/`,
`<registry>/provision/edudoc/_design/design.json`과 `_families/`를 확인한다.
패키지의 `templates/institutions/edudoc/_design/`·`_families/`는 신규 registry
초기화에만 쓰는 읽기 전용 provision 원본이다.
registry 미설정·미연결·손상 상태에서는 정확한 실패와 필요한 사용자 조치만 보고한다.
자동 설치, 자동 clone, registry 자동 생성, 다른 임시 경로 폴백은 하지 않는다.

- [HWPX template rendering policy](docs/agent-policies/hwpx-template-rendering.md) — source 추출과 approved-template 렌더 경계
- [Layout context contract](docs/agent-policies/hwpx-layout-context.md) — layout-context-v1 검증
