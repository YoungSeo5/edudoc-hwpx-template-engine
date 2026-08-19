# template_spec 3단계 재설계 — historical analysis

> Historical evidence only. This document predates the section-based authoring
> implementation and is not a current schema or product contract. The current
> E2E contract is [`product-workflow-contract.md`](product-workflow-contract.md)
> and pre-authoring schema ownership is
> [`contracts/template-authoring-contracts.md`](contracts/template-authoring-contracts.md).
> Its proposed `group: "A" | "B"` model is rejected: A/B is an observation
> grouping, not a product or runtime enum.

> **Status: historical design analysis — partially superseded**
>
> This document preserves the analysis and decisions made on 2026-08-13.
> It is not the current system contract.
>
> Current precedence:
>
> 1. `docs/product-workflow-contract.md`
> 2. the active task contract
> 3. this analysis as supporting evidence
>
> The following conclusion in this document is superseded:
>
> - using `group: "A" | "B"` as a required `template_spec` domain field or
>   rendering branch.
>
> Group A/B remains valid only as classification used while analyzing the
> reference layout samples.
>
> The following findings remain valid unless disproven by later implementation
> evidence:
>
> - the existing `create_document.py` materializer cannot express the required
>   baseline layout;
> - authoring requires materially richer HWPX layout control;
> - page, masthead, heading hierarchy, bullet hierarchy, table styling, footer,
>   and related observed layout properties remain relevant design evidence.

범위: baseline.md 확정 그룹 A(한장/원페이지형 보고서), 그룹 B(보도자료형).
아직 아무 코드도 바꾸지 않았다. 이 문서는 분석과 필요한 결정사항만 담는다.

## 0. minimal-abstraction.md 정지 조건 사전 점검

읽은 문서: `docs/agent-policies/minimal-abstraction.md`.

- "요청되지 않은 범용 타입 3개 이상" — 그룹 A/B라는 반복 축은 baseline.md에
  실제 관찰 2세트(그룹 A 5파일, 그룹 B 2파일)로 뒷받침되므로 조건 1(동일
  변화축의 실사용 사례 2개 이상)을 만족한다. 그룹별 필드 몇 개 추가는
  정지조건에 해당하지 않는다고 판단.
- "새로운 범용 파서/규칙 엔진 필요" — 해당 없음. 그룹 A/B 각각 baseline.md가
  실측한 고정된 몇 가지 shape(마스트헤드 구성, 불릿 위계)만 다루면 되고,
  임의 레이아웃을 표현하는 범용 DSL은 필요 없다.
- **"기존 계획보다 수정 범위가 크게 증가함" — 해당함.** 아래 1장 참고.
  template_spec 스키마 확장 자체보다, 그 스키마를 실제 source.hwpx로
  materialize하는 경로(`generate_source_hwpx`)를 바꿔야 하는 문제라서,
  구현 착수 전에 먼저 보고한다.

## 1. 핵심 발견 — materializer(소재) 능력 격차

`core/adapters/hwpx_template_authoring.py`의 `generate_source_hwpx()`는
`skills/hwp-skill/scripts/create_document.py`를 subprocess로 호출하고,
`template_spec_to_blocks()`가 만든 blocks.json을 그 CLI에 넘긴다
(`author_hwpx_template.py` 참고). 이 CLI가 받는 block은 4종류뿐이다
(`create_document.py:135-176`):

- `paragraph`: `doc.add_paragraph(text)` — 스타일 인자 없음.
- `heading`: **level을 받지만 실제로는 버린다.** 코드가
  `doc.add_paragraph(text, section=section)`만 호출하고 `level`은 아무 데도
  쓰이지 않는다 (`create_document.py:141-143`). 즉 heading block은 지금
  paragraph와 완전히 동일하게 렌더된다 — 겉보기엔 "heading 지원"처럼
  보이지만 폰트/크기/정렬 차이가 전혀 없다.
- `table`: `rows`의 각 셀을 `set_cell_text`로 텍스트만 채운다. 폭·테두리·
  셀여백·배경색 인자가 없다.
- `header`/`footer`: `set_header_text`/`set_footer_text` 호출인데, 알려진
  `python-hwpx` 버그로 TypeError가 나면 경고만 찍고 건너뛴다(불안정).

즉 **현재 소재 경로로는 baseline.md가 요구하는 조판 계약(정렬, 들여쓰기
단계, 표 폭/테두리/셀여백, 배경색, 페이지 여백, masthead 구조) 중 단 하나도
표현할 수 없다.** template_spec 스키마에 아무리 정교한 필드를 추가해도,
`template_spec_to_blocks()`가 만드는 blocks가 이 4종류를 벗어날 수 없는 한
반영될 곳이 없다.

반면 `create_document.py`가 내부적으로 쓰는 `hwpx`(python-hwpx) 라이브러리
자체는 `requirements.txt`에 명시된 **별개의 독립 pip 의존성**이고
(`skills/hwp-skill` 하위가 아니라 `.venv/Lib/site-packages/hwpx`), API가
훨씬 풍부하다. 실제 확인한 시그니처:

| 필요 | `hwpx` 라이브러리 API |
|---|---|
| 페이지 여백(mm) | `doc.page.setup(margins_mm=..., header_margin_mm=..., footer_margin_mm=...)` |
| 문단 정렬/들여쓰기/폰트 | `doc.add_paragraph(style=, para_pr_id_ref=, char_pr_id_ref=)`, `doc.styles.apply_paragraph_format(...)` |
| 불릿 위계 | `doc.styles.apply_list_format(...)`, `doc.styles.ensure_numbering(...)` |
| 표 폭/테두리 | `doc.add_table(width=, border_fill_id_ref=, style=)`, `doc.styles.ensure_border_fill(...)` |
| 개요/제목 스타일 | `doc.add_heading(text, level, style=)` — `create_document.py`가 안 쓰는 API |

**결론**: baseline.md의 조판 계약을 실제로 만족하는 `source.hwpx`를 만들려면
`generate_source_hwpx()`가 `create_document.py` subprocess 호출을 그만두고
`hwpx` 라이브러리를 직접 호출하는 방식으로 바뀌어야 한다. 이건
`skills/hwp-skill` 수정이 아니다(별개 pip 패키지를 직접 쓰는 것이며,
`core/adapters/hwpx_table_fill_adapter.py`와 같은 "작은 어댑터" 결이다).
다만 `generate_source_hwpx()`의 구현 방식 자체(subprocess → in-process 라이브러리
호출)가 바뀌는 것이므로 현재 계획(1단계 MVP: "스킬 CLI 그대로 재사용")보다
수정 범위가 커진다 — 이것이 위 0장의 정지조건이 걸리는 지점이다.

## 2. baseline.md 대비 현재 template_spec 갭

현재 스키마(`tests/fixtures/template-spec/weekly_report.template_spec.json`,
`TemplateSpec` in `hwpx_template_authoring.py:39-58`)는
`{template_spec_version, heading, fields: [{label, sample_value}]}`뿐이고,
`template_spec_to_blocks()`는 이걸 무조건 "제목 문단 1개 + 2열 표 1개"로만
변환한다(`hwpx_template_authoring.py:110-125`, 주석 그대로: "No layout DSL,
no per-field type/style choices — this MVP uses one fixed shape only").

| baseline.md 항목 | 현재 template_spec 표현 | 상태 |
|---|---|---|
| 그룹 A/B 구분 | 없음(단일 고정 shape) | 미표현 |
| 페이지 크기/여백 | 없음 | 미표현 |
| masthead 구조(배너/상태줄/정보표) | 없음 | 미표현 |
| 제목 정렬(섹션=좌측, masthead=중앙) | 없음(heading이 그냥 paragraph) | 미표현 |
| 제목/본문 폰트 크기 위계 | 없음 | 미표현 |
| 개조식 불릿 위계(□→ㅇ→*→†) + 계단식 들여쓰기 | 없음(fields는 전부 평평한 표 행) | 미표현 |
| 표 폭(기본 100% / 옵션 좁은표) | 없음(표 크기 인자 자체 없음) | 미표현 |
| 표 테두리 2단계(0.12/0.4mm) | 없음 | 미표현 |
| 셀 여백(1.8/0.5mm, 배너는 0) | 없음 | 미표현 |
| 셀 배경(강조 표만) | 없음 | 미표현 |
| 색 사용 패턴(진한 배너+연한 표) | 없음, 실제 색값도 baseline 미확정 | 미표현 (색값은 확인 필요라 보류 대상) |
| 이미지 placeholder("그림N", 그룹B만) | 없음 | 미표현 |
| footer(쪽번호/끝./담당자) | 없음 | 미표현 |
| 그룹B 본문 작성 규칙(육하원칙 등) | 없음 | 미표현(필드 설명/placeholder 문구용) |

## 3. 필요한 스키마 확장 방향 (개념 수준 — 아직 미확정, 코드 없음)

baseline.md에 실제로 근거가 있는 것만 열거한다. 값이 없는 항목은 스키마에
자리만 두고 `null`/"확인 필요"로 남긴다(AGENTS.md 금지사항: 값 지어내지 않음).

- `group`: `"A" | "B"` — 그룹마다 masthead·정렬·표 규칙이 다르므로 최상위
  분기 필드로 필요. (반복 축 2개 이상 확인됨 → 최소 추상화 정책 조건 1 충족)
- `page`: `{ size: "A4", orientation: "portrait", margins_mm: { left, right,
  top, bottom, header, footer } }` — 그룹별 baseline 기본값 사용, 좌우
  20mm는 확정값, 상하 여백은 "채택값(재검증 필요)"라고 표시 유지.
- `masthead`: 그룹별로 다른 고정 shape (baseline이 실측한 두 가지뿐, 범용
  DSL 아님):
  - 그룹 A: 배너 셀(텍스트+배경색 슬롯), 상태 체크박스 줄, 강조 박스 슬롯.
  - 그룹 B: 로고 자리(레이아웃 슬롯만, 실제 이미지 아님) + "보도자료" 표,
    보도/배포일자 표, 담당부서 3단 정보표, 대제목/소제목(중앙정렬) 표.
- `heading_hierarchy`: 역할별 `{role, font_role, size_pt, align}` 목록.
  예: 그룹A `section_title`(좌측, headline, ~16pt), 그룹B `masthead_title`
  (중앙, 18pt) > `masthead_subtitle`(중앙, 13pt) > `section_title`(좌측,
  16pt) > `body`(16pt).
- `bullet_levels`: 그룹A 전용, 순서 있는 위계 `{marker, indent_step_cm≈0.5,
  font_role}` (□ → ㅇ/◦ → * → †).
- `fields`: 기존 `label/sample_value`는 유지하되, 각 field가 어떤
  `heading_hierarchy`/`bullet_level` 역할에 속하는지 선언 — "모든 field는
  평평한 표 행"이라는 현재 가정을 깨야 함.
- `table_style` (표를 만드는 field/섹션에 한해 optional): `width: "full" |
  "narrow" | mm값`, `border_weight: "thin"(0.12mm) | "thick"(0.4mm)`,
  `cell_margin_mm: {left, right, top, bottom}`, `shading: bool`.
- `image_slots` (그룹B만, optional): caption 패턴 `"그림N"` 텍스트 라벨
  자리 — 크기/위치 규칙은 baseline에 없으므로 "확인 필요"로 유지.
- `footer`: `{page_number: bool, end_marker: bool, contact_line: bool}` —
  전부 옵션(baseline상 과반이거나 하위유형 한정).
- `color`: 스키마에 필드를 만들더라도 기본값을 채우지 않는다. 브랜드 색이
  확정되기 전까지는 기관이 명시적으로 넘기지 않는 한 비워 둔다.

## 4. 결정이 필요한 사항 (구현 착수 전)

1. **(핵심, 정지조건)** `generate_source_hwpx()`를 지금처럼 `create_document.py`
   subprocess 호출로 유지할지, `hwpx` 라이브러리 직접 호출로 바꿀지.
   전자를 유지하면 위 3장의 스키마 확장 대부분이 "선언은 되지만 렌더에
   반영 안 됨"인 죽은 필드가 된다. 후자로 바꾸면 실제로 baseline.md의
   조판 계약을 만족하는 candidate를 만들 수 있지만 구현 범위가 커진다.
2. 그룹 A/B를 하나의 `template_spec_version`(예: `authoring-v2`) 안에서
   `group` 분기 필드로 표현할지, 아니면 그룹별로 별도 버전
   (`authoring-v2-group-a`, `authoring-v2-group-b`)을 둘지.
3. baseline.md의 미해결 3항목(그룹A 상하여백 10mm 채택값, 그룹B 표폭 규칙,
   기관 브랜드 색상)은 사용자가 이미 "template_spec 설계를 막지 않는다"고
   확정했으므로, 스키마에는 자리를 두되 값은 "채택값(재검증 필요)"
   또는 "확인 필요"로 명시하는 정도로 진행해도 되는지 확인.

## 5. 사용자 결정 (2026-08-13)

4장의 두 결정사항에 대해 사용자 확인을 받았다.

1. **소재 방식**: authored candidate가 baseline.md 조판(정렬·여백·표 스타일
   등)을 실제로 갖춘 채 나와야 한다 → `generate_source_hwpx()`를
   `create_document.py` subprocess 호출에서 `hwpx` 라이브러리 직접 호출로
   전환한다. (구현 범위 증가를 감수하는 쪽으로 결정됨.)
2. **스키마 분할 — SUPERSEDED ON 2026-08-14** : 그룹 A/B를 별도 `template_spec_version`으로 나누지 않고,
   단일 스키마 + `group` 분기 필드로 표현한다.

이 결정에 따라 아래 6장에 구체 스키마 초안을 작성한다. **아직 구현 코드는
없다** — 이 초안에 대한 사용자 확인 후 구현으로 넘어간다.

## 6. template_spec 스키마 초안 (`authoring-v2`, 설계만 — 미구현)

baseline.md에 실제 근거가 있는 값만 기본값으로 채웠다. 근거 없는 값은
`null`이고 주석으로 "확인 필요"/"채택값(재검증 필요)"를 표시했다(baseline.md 원문 그대로, 지어낸 값 없음).

```jsonc
{
  "template_spec_version": "authoring-v2",
  "group": "A",                     // "A" | "B" — 필수, masthead/정렬/표 규칙 분기 기준
  "heading": "8월 2주차 한장보고",   // 문서 고정 제목 (기존과 동일한 의미)

  "page": {
    "size": "A4",
    "orientation": "portrait",
    "margins_mm": {
      "left": 20.0, "right": 20.0,  // 그룹 A/B 공통, baseline 확정값
      "top": 10.0, "bottom": 10.0,  // 그룹 A: 채택값(8~15mm 범위 중 채택, 재검증 필요)
      "header": 10.0, "footer": 10.0
      // 그룹 B라면 top/bottom 15.0 (baseline 확정, 2/2 일치)
    }
  },

  // masthead는 group마다 shape가 다르다. 범용 DSL이 아니라 baseline이
  // 실측한 두 shape만 표현한다.
  "masthead": {
    // group "A" shape
    "banner": { "label": "현안(이슈)보고", "date": "...", "banner_text": "..." },
      // banner_text 배경색은 기관 브랜드색 확인 전까지 color 미지정
    "status_line": { "options": ["현안검토", "언론보도", "..."] },  // optional, 원장보고형
    "summary_box": { "sample_value": "..." }                        // optional
    // group "B" shape라면 대신:
    // "logo_slot": true,               // 실제 이미지 아님, 레이아웃 자리만
    // "title_table": { "kicker": "보 도 자 료", "slogan": "..." },
    // "release_info_table": { "release_at": "...", "department": "...", "contact": "..." }
  },

  "heading_hierarchy": [
    // group "A" 예시
    { "role": "section_title", "align": "left", "font_role": "headline", "size_pt": 16 },
    { "role": "body", "align": "left", "font_role": "serif_body", "size_pt": 15 },
    { "role": "detail", "align": "left", "font_role": "gothic_small", "size_pt": 12 },
    { "role": "footnote", "align": "left", "font_role": "gothic_small", "size_pt": 11 }
    // group "B"라면 masthead_title(center,18)/masthead_subtitle(center,13)/
    // section_title(left,16)/body(left,16) 순
  ],

  "bullet_levels": [                 // group "A" 전용 (baseline 4번 절)
    { "marker": "□", "indent_step_cm": 0.0,  "role": "section_title" },
    { "marker": "ㅇ", "indent_step_cm": 0.5,  "role": "body" },
    { "marker": "*",  "indent_step_cm": 1.0,  "role": "detail" },
    { "marker": "†",  "indent_step_cm": 1.3,  "role": "footnote" }
    // 정확한 mm는 baseline상 "약 0.5cm 단위"로만 채택, 구현 시 재검증 필요
  ],

  "fields": [
    // 기존 label/sample_value 유지 + 어떤 hierarchy/bullet role에 속하는지 선언
    { "label": "추진 배경", "sample_value": "...", "role": "section_title" },
    { "label": "본문", "sample_value": "...", "role": "body", "bullet": "ㅇ" }
  ],

  "table_style": {                   // 표를 만드는 field/섹션에 적용
    "width": "full",                 // "full"(170mm) | "narrow"(~68mm, 옵션) | mm값
    "border_weight": "thin",         // "thin"(0.12mm) | "thick"(0.4mm)
    "cell_margin_mm": { "left": 1.8, "right": 1.8, "top": 0.5, "bottom": 0.5 },
    "shading": false                 // 강조 표만 true, 배경색 자체는 미지정
  },

  "image_slots": [],                 // group "B" 전용, 관찰 근거: "그림1"/"그림2" 텍스트 라벨
                                      // 크기/위치 규칙 없음 → 확인 필요로 빈 배열 기본값

  "footer": {
    "page_number": false,            // 옵션 (5개 중 3개, 과반이나 1페이지 문서는 꺼도 됨)
    "end_marker": false,             // 옵션 (1/5 단일 관찰)
    "contact_line": false            // 옵션, 원장보고 하위유형 한정
  },

  "color": null                      // 기관 브랜드색 미확정 — 확인 필요, 값 지어내지 않음
}
```

## 7. 남는 확인 필요 (구현 착수 시 함께 처리)

- `hwpx` 라이브러리로 계단식 들여쓰기(0.5cm 단위)를 문단 스타일/번호매기기
  중 어느 API로 구현할지는 실제 호출해보며 검증 필요(`doc.styles.
  apply_list_format`/`ensure_numbering` 후보).
- masthead의 표 기반 구조(배너 셀 배경색 포함 1행 N열 표)를 `doc.add_table`
  + `doc.styles.ensure_border_fill`로 만들 때, 배경색 없이(색은 null) 구조만
  먼저 만드는 것으로 충분한지 확인 필요.
- 위 스키마가 `template_spec_to_blocks()`를 완전히 대체하므로, 기존
  `weekly_report.template_spec.json` 픽스처와
  `test_hwpx_template_authoring_weekly_report.py`는 이 스키마로 마이그레이션
  필요 (task-scoped-testing.md에 따라 새 테스트 추가 필수, 기존 테스트 수정만으로는
  불충분).
