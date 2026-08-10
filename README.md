# HWPX 승인 템플릿 렌더링·QA 엔진

`edudoc`에서 승인 템플릿 최종 렌더링과 후보 템플릿 QA 왕복이 공유하는 부분만
잘라낸 엔진입니다. 어떤 모듈이 왜 여기 포함/제외됐는지는
[docs/agent-policies/hwpx-render-pipeline-diagram.md](docs/agent-policies/hwpx-render-pipeline-diagram.md)의
Mermaid 다이어그램과 대조해서 실제 `import`를 하나씩 추적해 확정했습니다.

## 이 저장소가 다루지 않는 것

- `core/compose/` (docx/pptx exporter, gongmun 스타일 프로필, 일반 `md2hwpx` 경로) — 이
  파이프라인의 institution-hwpx 분기도 결국 `orchestrate_hwpx_render()`만 호출하므로
  compose 자체는 불필요합니다.
- `core/templates/quality/refine.py`를 제외한 나머지 후보 생성 파이프라인 —
  `core/templates/pipeline.py`와 `quality/refine.py`는 `core/templates/__init__.py`가
  즉시 import하기 때문에 실행 시점 의존성으로 포함돼 있지만, QA/렌더 경로에서 직접
  호출되지는 않습니다.
- `templates/institutions/` (실제 기관 템플릿 데이터) — 별도 **비공개** 저장소로
  분리했습니다. 금감원 내부 보고 양식의 실제 구조(원본 바이트, 서식 문구)가 들어있어
  공개 저장소에 함께 둘 수 없습니다. 이 저장소 루트에 같은 경로(`templates/institutions/`)로
  git submodule을 걸어야 `core/document_api/service.py`의 `_TEMPLATE_ROOT`가 정상 동작합니다.

## 외부 의존성

- `skills/hwp-skill` — git submodule, `https://github.com/YoungSeo5/edudoc_hwp_skill.git`.
  table_cell 필드 치환을 이 스킬의 `scripts/fill_hwpx.py` 서브프로세스로 위임합니다.
- `python-hwpx`, `lxml`, `fonttools` (`requirements.txt`).

## 검증

`templates/institutions/`에 데이터 저장소를 submodule로 건 뒤 `skills/hwp-skill`
submodule을 초기화하고:

```bash
python -m pytest tests/ -q
```

2026-08-10, edudoc HEAD `07b0f94` (+ 추출 시점의 미커밋 작업트리 변경분) 기준으로
150개 중 149개 통과를 확인했습니다. 나머지 1개
(`test_one_page_restores_table_cell_leading_fwspaces_after_skill_fill`)는 이
추출과 무관하게 원본 edudoc 저장소에서도 동일하게 실패하는, 아직 고쳐지지 않은
기존 이슈입니다 — 이 엔진 저장소가 새로 만든 문제가 아닙니다.
