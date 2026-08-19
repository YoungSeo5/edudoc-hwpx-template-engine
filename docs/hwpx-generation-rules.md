# HWPX 구조와 기관 조판 Baseline 관리 기준

## 1. 목적

HWPX 기반 템플릿 생성 시 다음 두 종류의 정보를 구분하여 관리한다.

1. **HWPX 파일 형식 자체의 구조**

   * HWPX가 어떤 파일과 XML 구조로 구성되는지에 대한 기술적 기준
   * 기관이나 문서 종류와 관계없이 거의 변하지 않는 정보

2. **기관 문서의 공통 조판 구조**

   * 기존 기관 HWPX 문서들을 분석하여 추출한 디자인·레이아웃 기준
   * 새 템플릿을 생성할 때 기본값으로 사용하는 기관별 조판 Baseline

두 정보는 목적이 다르므로 별도의 문서와 계약으로 관리한다. 이 문서는 HWPX
형식 및 공통 생성 규칙을 소유한다. baseline 관찰과 institution-level 실행 정책의
경계는 [`product-workflow-contract.md`](product-workflow-contract.md)와
[`contracts/template-authoring-contracts.md`](contracts/template-authoring-contracts.md)가
소유한다.

```text
docs/
└─ hwpx/
   └─ hwpx-structure.md

templates/
└─ institutions/
   └─ <기관명>/
      └─ _design/
         └─ layout-baseline.md
```

---

# 2. HWPX 파일 구조

HWPX는 여러 XML 파일과 이미지 등의 리소스를 하나의 패키지로 구성한 문서 형식이다.

대표적인 내부 구조는 다음과 같다.

```text
document.hwpx
│
├─ mimetype
├─ version.xml
├─ settings.xml
│
├─ Contents/
│  ├─ content.hpf
│  ├─ header.xml
│  ├─ section0.xml
│  ├─ section1.xml
│  └─ ...
│
├─ BinData/
│  ├─ image1.png
│  ├─ image2.jpg
│  └─ ...
│
├─ META-INF/
│  ├─ container.xml
│  ├─ container.rdf
│  └─ manifest.xml
│
├─ Preview/
│  ├─ PrvImage.png
│  └─ PrvText.txt
│
└─ Scripts/
```

구역이 하나인 일반적인 문서는 `section0.xml`만 존재할 수 있으며, 구역이 추가되면 `section1.xml`, `section2.xml` 등이 생성될 수 있다.

---

## 3. 주요 HWPX 구성 요소

### 3.1 `Contents/header.xml`

문서에서 사용하는 서식 정보를 정의하는 영역이다.

대표적으로 다음 정보를 포함한다.

* 글꼴 정의
* 글자 모양
* 문단 모양
* 스타일
* 기타 서식 및 매핑 정보

본문의 `section*.xml`에서는 이러한 서식을 ID로 참조한다.

예:

```xml
<hp:p paraPrIDRef="20">
    <hp:run charPrIDRef="7">
        <hp:t>문서 제목</hp:t>
    </hp:run>
</hp:p>
```

여기서 `paraPrIDRef`, `charPrIDRef`는 `header.xml`에 정의된 서식 정보를 참조하는 식별자이다.

---

### 3.2 `Contents/section*.xml`

실제 문서 본문의 구조와 내용을 저장한다.

개념적으로 다음과 같은 계층을 가진다.

```text
Section
 ├─ Paragraph
 │   ├─ Run
 │   │   └─ Text
 │   ├─ Run
 │   │   └─ Picture
 │   └─ Run
 │       └─ Table
 │
 ├─ Paragraph
 │   └─ ...
 │
 └─ ...
```

주요 요소의 의미는 다음과 같다.

```text
hp:p
= 문단

hp:run
= 동일한 글자 서식을 공유하는 구간

hp:t
= 실제 텍스트
```

하나의 문단 안에서도 글꼴, 크기, 굵기 등 글자 서식이 달라지면 여러 `run`으로 분리될 수 있다.

---

### 3.3 `BinData/`

문서가 사용하는 바이너리 리소스를 저장한다.

대표적인 예:

* 기관 로고
* 사진
* 삽입 이미지
* 기타 바이너리 객체

본문 XML에서는 해당 리소스를 직접 포함하지 않고 참조하여 배치할 수 있다.

---

# 4. HWPX의 논리적 조판 구조

사람이 문서를 볼 때는 다음과 같이 인식할 수 있다.

```text
A4 페이지
 ├─ 로고
 ├─ 제목
 ├─ 기본정보 표
 ├─ 본문
 └─ 푸터
```

하지만 HWPX 내부가 반드시 이러한 구조로 저장되는 것은 아니다.

실제 화면은 다음 요소들의 조합으로 만들어진다.

```text
Section
 ↓
페이지 크기 / 방향 / 여백 / 구역 설정

Paragraph
 ↓
정렬 / 들여쓰기 / 줄간격 / 문단 간격

Run
 ↓
글꼴 / 크기 / 굵기 / 자간 / 색상

Control / Object
 ↓
표 / 그림 / 글상자 / 도형 등의 객체
```

따라서 템플릿 생성 시 단순히 `페이지 → 제목 → 표 → 본문` 구조만 복제하는 것이 아니라 각 요소의 조판 속성을 함께 처리해야 한다.

---

# 5. 페이지와 구역의 관계

HWPX에서 페이지는 독립적인 XML 객체로 항상 명시되어 있는 구조가 아니다.

문서의 실제 페이지 분리는 다음 요소에 의해 결정된다.

* 편집 용지 크기
* 페이지 방향
* 상·하·좌·우 여백
* 문단 크기
* 줄간격
* 표 크기
* 이미지 및 객체 크기
* 페이지 나누기
* 구역 나누기

`Section`은 서로 다른 페이지 설정이나 구역별 조판 규칙을 적용하기 위한 단위이다.

실제 한글 조판 기준 페이지 수 검증 및 Hancom Automation 운영 규칙은
[Hancom Native Page Validation](./hancom-native-page-validation.md)을 따른다.

---

# 6. 기관 조판 Baseline

`layout-baseline.md`는 기존 기관 HWPX 문서를 분석하여 추출한 **관찰 evidence의
Source of Truth**다. 새 self-authored 문서에 실제로 적용할 institution-level
default는 별도 `templates/institutions/<institution>/_design/design.json` 계약에서
명시한다. baseline 자체가 곧 runtime default라는 뜻은 아니다.

새로운 템플릿을 만들 때마다 기존 HWPX 전체를 다시 분석하지 않는다.

```text
기존 기관 HWPX 여러 개
        ↓
공통 조판 규칙 분석
        ↓
layout-baseline.md 확정
        ↓
반복적으로 재사용
        ↓
template_spec
+
문서 유형별 요구사항
        ↓
authoring generator
        ↓
새 HWPX 생성
```

새로운 레퍼런스 문서에서 기존 Baseline에 존재하지 않는 중요한 공통 규칙이 발견될 경우 Baseline을 다시 검토하여 갱신한다.

```text
새 reference 추가
        ↓
기존 baseline과 비교
        ↓
기관 공통 규칙인지 판단
        ↓
layout-baseline.md 갱신
        ↓
이후 생성되는 템플릿부터 적용
```

---

# 7. 기관 조판 Baseline 기록 항목

## 7.1 페이지

* 용지 크기
* 세로 / 가로 방향
* 상단 여백
* 하단 여백
* 좌측 여백
* 우측 여백
* 머리말 영역
* 꼬리말 영역

## 7.2 기본 글꼴

### 본문

* 한글 글꼴
* 영문 글꼴
* 글자 크기
* 굵기
* 장평
* 자간
* 글자 색상

### 제목

* 글꼴
* 글자 크기
* 굵기
* 정렬
* 문단 전 간격
* 문단 후 간격

### 소제목

* 글꼴
* 글자 크기
* 굵기
* 정렬
* 들여쓰기
* 문단 간격

---

## 7.3 문단

* 기본 정렬
* 줄간격
* 첫 줄 들여쓰기
* 왼쪽 여백
* 오른쪽 여백
* 문단 전 간격
* 문단 후 간격
* 번호 및 목록 규칙

---

## 7.4 제목 및 Masthead 영역

* 기관 로고 사용 여부
* 로고 종류
* 로고 크기
* 로고 위치
* 기관명 표시 여부
* 기관명 위치
* 문서 제목 위치
* 제목 정렬
* 제목 상자 사용 여부
* 배경 사용 여부
* 구분선 사용 여부
* 제목 영역 높이 및 간격

---

## 7.5 표

* 기본 표 너비
* 표 정렬
* 기본 행 높이
* 열 너비 결정 방식
* 셀 내부 여백
* 셀 세로 정렬
* 헤더 행 스타일
* 테두리 종류
* 테두리 굵기
* 배경색
* 표 내부 글꼴
* 표 내부 글자 크기
* 표 내부 문단 정렬
* 반복적으로 사용하는 표 구조

---

## 7.6 이미지 및 객체

* 기본 배치 방식
* 문단과의 관계
* 가로 위치 기준
* 세로 위치 기준
* 본문과 겹침 허용 여부
* 이미지 비율 유지 여부
* 기본 최대 크기
* 캡션 사용 여부
* 캡션 스타일

---

## 7.7 반복되는 문서 구조

기존 기관 문서에서 반복적으로 나타나는 구조를 분석한다.

예:

* 대제목
* 소제목
* 본문
* 목록
* 번호 목록
* 강조 문구
* 기본정보 표
* 설명 표
* 주석
* 참고 문구
* 서명 영역
* 첨부 영역

각 구조에 대해 다음 속성을 기록한다.

* 배치 위치
* 글꼴
* 글자 크기
* 굵기
* 정렬
* 들여쓰기
* 문단 간격
* 반복 패턴

---

# 8. 고정 요소

기관의 모든 자체 생성 문서에서 공통적으로 사용하는 요소를 별도로 정의한다.

예:

* 기관 로고
* 기관명
* 공통 Masthead
* 공통 Footer
* 대표 색상
* 공통 구분선
* 공통 표 스타일
* 공통 제목 스타일

고정 요소의 이미지 파일 등 실제 리소스는 별도의 `assets` 영역에서 관리하고, Baseline에는 해당 요소의 사용 규칙과 배치 기준을 기록한다.

---

# 9. 문서 유형별 재정의

기관 Baseline은 공통 기본값이며 모든 문서가 완전히 동일해야 한다는 의미는 아니다.

특정 문서 유형에서는 필요한 경우 다음 항목을 재정의할 수 있다.

* 제목 크기
* 제목 배치
* 섹션 구성
* 표 구조
* 표 열 구성
* 특정 강조 영역
* 이미지 영역
* 문서별 특수 Footer
* 문서별 특수 레이아웃

문서 유형별 명시적인 규칙이 없는 항목은 기관 Baseline을 사용한다.

우선순위는 다음과 같다.

```text
문서 유형별 명시 규칙
        ↓
기관 layout-baseline
        ↓
HWPX 생성기의 일반 기본값
```

---

# 10. XML ID 저장 금지

`layout-baseline.md`에는 특정 HWPX 파일 내부의 XML ID를 조판 규칙으로 저장하지 않는다.

잘못된 예:

```text
제목 = charPrIDRef 17
본문 = paraPrIDRef 23
```

`charPrIDRef`, `paraPrIDRef` 등의 ID는 특정 HWPX 파일의 `header.xml` 내부에서만 의미가 있는 식별자이므로 다른 HWPX에서는 같은 ID가 다른 서식을 의미할 수 있다.

Baseline에는 XML ID 대신 실제 의미가 있는 조판 값을 저장한다.

예:

```yaml
title:
  font_family: ...
  font_size_pt: ...
  bold: true
  align: center
  spacing_before_mm: ...
  spacing_after_mm: ...

body:
  font_family: ...
  font_size_pt: ...
  line_spacing: ...
  first_line_indent_mm: ...
```

실제 HWPX 생성 시 authoring generator가 이 값을 기반으로 필요한 `charPr`, `paraPr` 등의 서식을 생성하고 해당 문서 내부의 ID를 배정한다.

---

# 11. 역할 구분

## `hwpx-structure.md`

HWPX 파일 형식을 이해하기 위한 기술 문서이다.

주요 대상:

* HWPX package 구조
* `header.xml`
* `section*.xml`
* Paragraph
* Run
* Text
* Table
* Picture
* BinData
* 서식 참조 관계
* 구역 및 페이지 조판 구조

기관별 디자인 규칙은 이 문서에 포함하지 않는다.

## `layout-baseline.md`

기관의 기존 문서에서 추출한 공통 조판 규칙을 정의하는 실행 기준 문서이다.

다음 작업에서 직접 참고한다.

* 신규 `template_spec` 작성
* 자체 HWPX 템플릿 생성
* 기관 공통 디자인 적용
* 신규 템플릿의 조판 검증
* 레퍼런스 문서와 생성 결과 비교

템플릿 생성기가 실제로 따라야 하는 기관별 조판 기준의 Source of Truth는 `layout-baseline.md`로 한다.
