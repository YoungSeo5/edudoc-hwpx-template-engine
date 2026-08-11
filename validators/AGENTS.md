# validators/AGENTS.md

`validators/`는 결정론적 검증 규칙이다.

## Responsibility

이 저장소의 검증 범위는 HWPX 패키지 하나다.

| 검증기 | 입력 | 범위 |
|---|---|---|
| `hwpx_package_rules.py` | 생성된 `.hwpx` 패키지 | ZIP·패키지·XML 요구사항. 문서 작성 규칙이 아니다 |

## Rules

- 검증기는 문서를 생성하지 않는다.
- 검증기는 파일을 내보내지 않는다.
- 검증기는 원본 문서를 변형하지 않는다.
- 검증 영역이 늘어나면 서로 분리해서 둔다.
- 검증 보고서의 존재는 위 표에 적힌 그 검증기에 대해서만 근거가 된다.
  패키지 검증 통과는 레이아웃 충실도나 기관 승인의 근거가 아니다.
- 출력 형식이 검증기를 선택하지 않는다.

렌더 결과의 레이아웃 계약 검사는 별개다. 그것은
`core/templates/hwpx_layout_context.py`의 `verify_recorded_layout()`이 담당하며
렌더 커널 안에서 실행된다.
