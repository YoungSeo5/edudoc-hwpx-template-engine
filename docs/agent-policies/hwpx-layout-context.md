# HWPX 레이아웃 보존 계약

상태: **구현됨**. `core/templates/hwpx_layout_context.py` 가 계약을 소유하고,
분리·QA 왕복·최종 렌더가 같은 함수로 검증한다.
검증 테스트는 `tests/task_scoped/test_hwpx_layout_contract.py`.

소유 문서: [HWPX template rendering policy](hwpx-template-rendering.md).

## 1. 해결한 문제

변경 전에는 보존해야 할 서식이 한 종류 늘어날 때마다 **네 곳이 함께 늘어났다.**

| 단계 | 변경 전 위치 |
| --- | --- |
| 추출 | `core/templates/hwpx_content_separator.py:177` `_section_decisions` 가 `para_pr_id_ref`, `cell_margin` 을 각각 개별 키로 붙인다 |
| 기록 | `placeholder_map.json` 의 field 항목에 평평한 형제 키로 쌓인다 |
| 분리 검증 | `hwpx_content_separator.py:370` `_validate_placeholder_paragraph_contract` + `:416` `_paragraph_style_ids_with_margins` + `:440` `_validate_cell_margin` + `:455` `_cell_margins` |
| 렌더 검증 | `core/adapters/hwpx_template_renderer.py:555` `_validate_rendered_paragraph_styles` + `:613` `_paragraph_style_ids_with_margins` + `:637` `_validate_rendered_cell_margin` + `:667` `_section_cell_margins` — 분리 검증 코드의 두 번째 사본이다 |

두 번째 문제는 계약이 **템플릿마다 선택적**이었다는 점이다. `hwpx_template_renderer.py:559-561` 은
`section_paragraph_counts` 가 없으면 조기 return 한다. 실제로 `금감원 원장보고` 와
`금감원 원장보고 가상자산` 의 `placeholder_map.json` 에는 그 키가 없으므로, 두 템플릿은
**렌더 시 서식 검증이 통째로 건너뛰어진다.** 계약을 가진 템플릿은 `금감원 원페이지` 하나뿐이다.

즉 새 템플릿을 뽑을 때마다 (a) 그 템플릿이 쓰는 서식 종류만큼 코드를 추가하고,
(b) 계약을 손으로 붙이지 않으면 무방비 상태로 렌더된다.

## 2. 계약

placeholder마다 원본의 layout context를 추출·기록·검증한다.

```text
source.hwpx
→ placeholder 위치의 서식 출처 추출   (DocumentLayout.context_for)
→ placeholder_map.json 에 기록        (field["layout_context"])
→ 렌더러는 원본 구조를 복제하고 텍스트만 변경 (현재 동작 유지)
→ 분리·QA 왕복·최종 렌더가 같은 함수로 재추출해 비교 (verify_recorded_layout)
```

핵심 규칙:

1. 보존 아스펙트 목록은 `DocumentLayout.context_for` **한 곳**에만 존재한다.
   아스펙트를 추가한다는 것은 `DocumentLayout.read` 에서 읽고 `context_for` 에서 이름을 붙이는
   것이며, separator에 분기 하나 + renderer에 분기 둘을 추가하는 일이어서는 안 된다.
2. 계약은 **원본이 실제로 가진 것**을 기록한다. 원본에 없는 서식을 요구하지 않는다.
3. `layout_context` 가 없는 placeholder는 렌더할 수 없다. 무방비 구멍은 조용히 채우지 않고 보고한다.
4. 계약 선언(`layout_contract`)이 없는 템플릿은 렌더를 거부한다. 선택적 계약을 없앤다.

## 3. 기록 형식 (`layout-context-v1`)

`placeholder_map.json` 최상위. 스타일 정의는 여러 placeholder가 공유하므로
문서 단위 표에 한 번만 기록한다 (field마다 복사하면 27개 field짜리 맵이 42KB로 불어난다).

```json
{
  "layout_contract": "layout-context-v1",
  "section_paragraph_counts": { "section0.xml": 60 },
  "paragraph_style_margins": {
    "25": [
      { "intent": { "value": "-3360", "unit": "HWPUNIT" },
        "left":   { "value": "0", "unit": "HWPUNIT" },
        "right":  { "value": "0", "unit": "HWPUNIT" },
        "prev":   { "value": "0", "unit": "HWPUNIT" },
        "next":   { "value": "0", "unit": "HWPUNIT" } },
      { "intent": { "value": "-6720", "unit": "HWPUNIT" }, "left": { "value": "0", "unit": "HWPUNIT" } }
    ]
  }
}
```

field 항목: anchor(어디)와 layout_context(무엇이 유지되어야 하는가)를 분리한다.

```json
{
  "field_id": "body_bullet_01",
  "placeholder": "{{body_bullet_01}}",
  "section": "section0.xml",
  "text_node_index": 12,
  "paragraph_index": 14,
  "table": null, "row": null, "col": null,
  "layout_context": { "para_pr_id_ref": "25" }
}
```

- `table/row/col` 은 anchor이자 `replacement_mode: "table_cell"` 의 채우기 주소이므로 그대로 둔다.
- `paragraph_style_margins` 는 placeholder가 참조하는 `paraPrIDRef` 의 header 정의를 문서 순서대로
  모두 기록한다. 한 `paraPr` 는 `hp:switch` 의 `case`/`default` 마다 다른 margin을 가질 수 있다
  (`금감원 원페이지` 의 paraPr 25는 intent가 각각 `-3360`, `-6720`).
- 표 안의 placeholder만 `cell_margin` 키를 추가로 가진다. 아스펙트 유무 자체가 비교 대상이다.
- 검증은 두 층을 한 번에 본다. placeholder마다 `layout_context` 를 비교하고, 그 문단이 참조하는
  스타일의 margin 정의를 문서 단위 표와 비교한다 (`_verify_section`).

## 4. 아스펙트 정의 — 단일 지점

새 모듈 `core/templates/hwpx_layout_context.py`.

```python
@dataclass(frozen=True, slots=True)
class DocumentLayout:
    """한 section과 그 header가 placeholder 위치에서 드러내는 레이아웃 사실."""

    paragraph_styles: tuple[str | None, ...]
    fwspace_counts: tuple[tuple[int, int], ...]
    cell_margins: Mapping[tuple[int, int, int], dict[str, str] | None]
    style_margins: Mapping[str, list[dict[str, dict[str, str]]]]

    @classmethod
    def read(cls, section_xml, header_xml) -> DocumentLayout: ...

    def context_for(self, field: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
        """placeholder anchor에서 보존되는 모든 레이아웃 아스펙트.

        이 목록이 곧 계약이다. 프로젝트의 다른 어떤 코드도
        placeholder가 어떤 서식에 의존하는지 따로 판단하지 않는다.
        """
        index = paragraph_anchor(field)
        context = {"para_pr_id_ref": self.paragraph_styles[index]}
        # fwSpace는 문단이 아니라 text node 단위다. 기록이 없거나 범위를 벗어나면 붙이지 않는다.
        text_node_index = field.get("text_node_index")
        if isinstance(text_node_index, int) and 0 <= text_node_index < len(
            self.fwspace_counts
        ):
            leading, trailing = self.fwspace_counts[text_node_index]
            if leading:
                context["leading_fwspace_count"] = leading
            if trailing:
                context["trailing_fwspace_count"] = trailing
        cell = _cell_anchor(field)
        if cell is not None:
            context["cell_margin"] = self.cell_margins[cell]
        return context
```

`fwspace_counts` 는 `_nodes(section, "t")` 순서로 읽으므로 `text_node_index` 는 **섹션 전역
`hp:t` 순번**이다. 셀 안에서 몇 번째인지가 아니다. 실제 구현은 위 가드에 더해 `bool` 도
`int` 로 통과하지 않도록 배제한다.

`tab`, `container` 등을 추가할 때 손대는 곳은 `read` 와 `context_for` 뿐이다.
스타일처럼 여러 placeholder가 공유하는 정의는 `margins_of_referenced_styles` 와 같은 방식으로
문서 단위 표에 기록한다.

## 5. 검증 — 단일 지점

```python
def verify_recorded_layout(
    placeholder_map: Mapping[str, JsonValue],
    read_section: Callable[[str], str | bytes],
    header_xml: str | bytes,
    *,
    where: str,
    rewritten: RewrittenRanges | None = None,
) -> None:
    """기록된 layout context를 재추출해 비교한다. 불일치는 LayoutContractError."""
```

호출 지점 세 곳이 같은 함수를 쓴다.

| 호출 지점 | `read_section` | `header_xml` | `where` |
| --- | --- | --- | --- |
| 분리 (원본) | `raw/section*.xml` | `raw/header.xml` | `separated raw` |
| 분리 (템플릿) | `template/section*.template.xml` | `template/header.xml` | `separated template` |
| 렌더·QA 왕복 | 출력 패키지의 `Contents/section*.xml` | 출력 패키지의 `Contents/header.xml` | `the rendered document` |

오류 메시지는 `{aspect} changed in {where} for {field_id}: recorded ..., found ...` 형태로
아스펙트 이름을 그대로 쓴다. 아스펙트가 늘어도 메시지 코드를 늘리지 않는다.

### 반복 블록이 있는 섹션

`paragraph_index` 는 섹션 내 인덱스이므로, 문단을 삽입하는 반복 확장이 일어나면 anchor가 밀린다.
이 때문에 지금은 `금감원 원장보고` 가 계약 자체를 갖지 못했다.

`render_repeat_block` 이 다시 만든 문단 구간을 `(원본 문단 index, 원본 문단 수, 렌더된 문단 수)` 로
선언하면 검증이 가능하다.

- 구간 **뒤**의 anchor는 길이 변화만큼 이동시켜 비교한다.
- 구간 **안**의 anchor는 비교하지 않는다. `_render_repeat_items` 는 원본 레벨 문단과 구분자 문단의
  복사본에 텍스트만 바꿔 넣으므로, 그 문단들의 서식은 구조상 원본과 같다.
- 한 섹션에 반복 블록이 둘 이상이면 뒤 블록의 구간 시작이 이미 확장된 좌표계에서 세어지므로,
  앞 블록이 늘린 문단 수를 빼서 원본 좌표로 되돌린다 (`render_repeat_block`).
  현재 저장소에는 블록이 둘인 템플릿이 없어 이 경로는 테스트로 덮이지 않았다.

### 표 셀 leading fwSpace — 검증이 아니라 복원

다른 모든 아스펙트는 "재추출해서 다르면 실패"로 끝난다. 표 셀 안의 **leading** fwSpace만
예외로, 검증 **전에** 능동 복원 단계가 하나 더 있다.

`_apply_table_fills` 가 부르는 `skills/hwp-skill` 은 셀을 채울 때 출력 HWPX를 통째로 다시
쓰고, 스킬은 보호 대상이라 내부를 고칠 수 없다. 복원 단계는 그 출력에서 채운 셀의 leading
`<hp:fwSpace/>` 와 같은 셀에 얹혀 있던 다른 field의 `hp:t` 내용이 유실된 경우를 전제하고
짜여 있다. 다만 스킬이 실제로 무엇을 지우는지는 확인하지 않았다 (`10. 확인 필요` 참고) —
복원이 불필요한 경우에도 이 단계는 무해한 no-op이다. `verify_recorded_layout` 은 유실을
실패로 잡아낼 뿐 되돌리지 못하므로, 복원은 검증보다 먼저 와야 한다.

`core/adapters/hwpx_template_renderer.py` 의 `_restore_table_cell_leading_fwspaces` 가
그 사이를 메운다.

- **본문 전체 복원의 기준본은 `table_cell` 치환 직전의 렌더 패키지다.**
  `_write_hwpx_package` 가 일반 field와 package metadata를 반영해 만든 `output_path` 를
  스킬 호출 전에 `reference_path` 로 넘기고, `shutil.copyfile` 로 스킬 출력을 확정하기
  **전에** 복원한다. raw `source.hwpx` 를 직접 기준으로 삼는 것이 아니다. 순서가 뒤집히면
  기준본과 대상이 같은 파일이 되어 **이 복원이 조용히 no-op이 된다.** 반면 fwSpace 개수
  보정은 기록된 `leading_fwspace_count` 를 기대값으로 쓰므로(`missing = expected - count`)
  `reference` 를 읽지 않는다. 두 경로가 기준으로 삼는 것이 서로 다르다.
- **키는 `(table, row, col, text_node_index)`.** 한 셀에 `hp:t` 가 여럿일 수 있어
  셀 좌표만으로는 어느 노드를 복원할지 정해지지 않는다. 여기까지 도달한 field에
  `text_node_index` 가 없으면 `HwpxTemplateRenderError` 다.
- **`replacement_mode` 에 따라 복원 방식이 갈린다.** `table_cell` 인 field는 부족한
  **leading** `<hp:fwSpace/>` 개수만 채운다. `trailing_fwspace_count` 는 기록·검증되지만
  복원되지 않으므로, 스킬이 trailing을 지웠다면 `verify_recorded_layout` 이 불일치로
  렌더를 실패시킨다. 그렇지 않은 field는 `table_cell` 치환 직전 렌더 패키지의 해당
  `hp:t` 본문 전체를 되돌리므로 trailing까지 함께 복원된다.
- `section`/`table`/`row`/`col` 타입이 맞지 않거나 현재 채운 셀과 좌표가 일치하지 않는
  field는 건너뛴다. 반면 `section_index` 를 정수로 변환할 수 없으면 렌더가 중단되고,
  복원 대상 field의 `text_node_index` 가 없거나 0 이상의 정수가 아니면
  `HwpxTemplateRenderError` 가 발생한다.

테스트는 `tests/task_scoped/test_fss_one_page_final_rendering.py` 의
`test_one_page_restores_each_field_fwspace_in_a_filled_table_cell` — 한 셀 안의 여러
field가 각자 기록한 `leading_fwspace_count` 를 유지하는지 본다.

## 6. 변경 지점 (구현 완료)

| 파일 | 변경 |
| --- | --- |
| `core/templates/hwpx_layout_context.py` | 신규. 위 4·5장 전부 |
| `core/templates/hwpx_content_separator.py` | `_section_decisions` 에서 `para_pr_id_ref`/`cell_margin` 수집 제거, 섹션당 `DocumentLayout` 하나로 `layout_context` 부착. `_validate_placeholder_paragraph_contract` 는 `verify_recorded_layout` 두 번 호출 + "placeholder가 anchor 문단 안에 있는가" 확인만 남긴다. `:416` `_paragraph_style_ids_with_margins`, `:440` `_validate_cell_margin`, `:455` `_cell_margins` 삭제 |
| `core/adapters/hwpx_template_renderer.py` | `:555`, `:605`, `:613`, `:637`, `:667` 삭제하고 `verify_recorded_layout` 호출로 대체. `render_repeat_block` 이 다시 만든 문단 구간을 함께 돌려준다 |
| `core/templates/hwpx_content_classifier.py`, `hwpx_separation_rules.py` | `TextLocation.para_pr_id_ref` 는 이 변경 후 읽는 곳이 없어지므로 함께 제거 |
| `core/templates/hwpx_content_artifacts.py` | `template.review.md` 에 계약 이름과 아스펙트 목록 한 줄 추가 (사람이 승인 전에 읽는 자료) |
| `templates/institutions/…/placeholder_map.json` × 3 | 7장 마이그레이션 |

## 7. 승인된 템플릿 마이그레이션 (완료)

`field_id`, `sample_value`, 분류 결과, `alias_map.json` 은 건드리지 않는다. 재추출하지 않는다
(재추출은 field_id를 바꿔 `alias_map.json` 을 깨뜨린다).

| 템플릿 | 작업 |
| --- | --- |
| `금감원 원페이지` | `para_pr_id_ref`/`cell_margin` 을 `layout_context` 안으로 옮기고, 참조 스타일의 margin 정의를 `paragraph_style_margins` 에 채운다. `layout_contract` 선언 추가 |
| `금감원 원장보고` | `template/section0.template.xml` 에서 `text_node_index` → `paragraph_index` 를 구해 anchor를 채우고, `layout_context` 와 `section_paragraph_counts`, `layout_contract` 를 추가 |
| `금감원 원장보고 가상자산` | 위와 동일 |

마이그레이션 중 확인한 사실: `금감원 원장보고` 의 맵에 든 `text_node_index` 는 `raw/section0.xml`
(텍스트 노드 19개)이 아니라 `template/section0.template.xml`(30개)을 가리킨다. 템플릿에서 run이 더
쪼개졌기 때문이며, 문단 수(32개)와 header는 양쪽이 같다. 그래서 anchor와 layout context는
렌더 대상인 template XML에서 읽었다.

마이그레이션 후 세 템플릿 모두 계약을 선언하므로, 렌더러의 "계약 없으면 건너뛴다" 분기를 없앴다.

## 8. 의도적으로 바꾼 기존 규칙

변경 전 `_paragraph_style_ids_with_margins` (양쪽 사본 모두)는 placeholder가 참조하는 `paraPr` 에
`margin` 하위의 `intent` 와 `left` 가 **있어야 한다**고 요구하고, 없으면
`header margin is missing for <field>` 로 실패했다.

이 규칙은 `금감원 원페이지` 의 들여쓰기에서 역산된 것이며, 원본이 무엇을 가졌는지와 무관하게
특정 margin 구성을 요구한다. 프로젝트 규칙상 기관 서식을 발명하지 않으므로,
**"원본이 가진 margin 정의를 `para_margins` 로 기록하고 그대로인지 검증"** 으로 대체했다.
`intent`/`left` 가 없는 스타일은 "없음"이 기록되고, 렌더 결과에서 없음이 유지되면 통과한다.

이 대체는 동작 변경이다. `intent`/`left` 가 없는 스타일을 쓰는 템플릿은 변경 전에는 렌더가
거부됐고 지금은 통과한다. 반대로 header의 margin 값이 렌더 중 바뀌면 변경 전에는 통과했고
지금은 거부된다.

## 9. 테스트

`tests/task_scoped/test_hwpx_layout_contract.py` (신규, 7건). 변경 전 동작에서는 7건 모두 실패한다.

1. 분리 결과의 모든 placeholder가 `layout_context` 를 기록하고 `layout_contract` 를 선언한다.
2. `layout_context` 가 없는 placeholder를 가진 템플릿은 렌더가 거부한다.
3. `layout_contract` 선언이 없는 템플릿은 렌더가 거부한다.
4. 렌더 결과의 `paraPrIDRef` 가 바뀌면 렌더가 실패한다.
5. 렌더 결과의 `cellMargin` 이 바뀌면 렌더가 실패한다.
6. header의 margin 정의가 바뀌면 렌더가 실패한다 (기존 "intent/left 필수" 규칙의 대체 증명).
7. 반복 확장이 일어난 섹션도 문단 수와 서식이 검증된다.

기존 테스트 중 형식 변경으로 함께 고친 것 (사유: 기록 형식이 요구사항 변경으로 바뀜):

- `tests/test_hwpx_content_separator.py::test_separator_records_paragraph_style_contract`
- `tests/task_scoped/test_fss_one_page_final_rendering.py` 의 `para_pr_id_ref`/`cell_margin` 참조
- `tests/test_hwpx_template_renderer.py::_write_template_dir` 과
  `tests/task_scoped/test_hwpx_render_requires_metadata.py::_candidate_template_dir` 이 만드는
  합성 템플릿의 `placeholder_map.json` (계약을 선언하도록 `DocumentLayout` 로 직접 채운다)
- `render_repeat_block` 반환값이 3개가 되어 호출부를 고친 곳:
  `tests/test_hwpx_template_renderer.py`, `tests/task_scoped/test_fss_director_report_item_separators.py`

## 10. 확인 필요

- 한 섹션에 반복 블록이 둘 이상인 경우: 좌표 보정 코드는 있으나 해당 템플릿이 없어 테스트로
  덮이지 않았다.
- `_apply_table_fills` 가 호출하는 `skills/hwp-skill` 이 header/스타일을 다시 쓰는지 여부는
  이 계약이 렌더 후 검증으로 잡아내지만, 스킬 내부 동작 자체는 확인하지 않았다.
