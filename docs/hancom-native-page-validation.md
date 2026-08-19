# Hancom Native Page Validation

## 1. 목적

이 프로젝트는 HWPX 자체의 XML만으로 최종 조판 페이지 수를 확정하지 않는다.

특히 `one_page_report`처럼 실제 결과물이 반드시 1페이지여야 하는 경우에는 **한컴 한글의 실제 조판 엔진으로 HWPX를 열고 `PageCount`를 읽어 검증**한다.

기본 흐름:

```text
candidate HWPX
→ Hancom Automation COM
→ security module registration
→ HWPX Open
→ native PageCount
→ required page count 비교
→ PASS / FAIL
```

예:

```text
page_count = 1
required_pages = 1
→ PASS

page_count = 2
required_pages = 1
→ FAIL
```

`required_pages`는 문서를 해당 페이지 수로 강제로 만드는 옵션이 아니다.

```text
page_count
= 한글이 실제로 조판한 페이지 수

required_pages
= 해당 문서 family/QA가 요구하는 페이지 수
```

---

# 2. 절대경로를 하드코딩하지 않는다

한글 실행파일의 예시 로컬 경로:

```text
C:\Program Files (x86)\HNC\Office 2022\HOffice120\bin\Hwp.exe
```

이 경로는 **현재 개발 PC의 설치 위치일 뿐이며 repository 코드에 사용하지 않는다.**

금지:

```python
HWP_PATH = r"C:\Program Files (x86)\HNC\Office 2022\HOffice120\bin\Hwp.exe"
```

Hancom Automation은 Windows에 등록된 COM ProgID를 이용한다.

```text
HWPFrame.HwpObject
```

따라서 사용자마다:

```text
한글 버전
설치 경로
Program Files 위치
32/64bit 환경
```

이 달라도 COM이 정상 등록되어 있다면 실행파일 절대경로를 알 필요가 없다.

---

# 3. Runtime discovery

구현:

```text
core/adapters/hancom_page_count.py
```

Hancom Automation 존재 여부는 COM 등록정보를 통해 확인한다.

```text
HWPFrame.HwpObject
```

상태:

```text
hancom_automation = available
```

또는:

```text
hancom_automation = missing
```

한글이 없는 환경에서도 HWPX 생성 자체는 가능해야 한다.

Native page validation만 사용할 수 없게 처리한다.

---

# 4. Automation 보안모듈

보안모듈은 **한글 실행파일을 찾기 위한 모듈이 아니다.**

역할:

```text
Automation
→ 로컬 HWP/HWPX Open
→ 파일 접근 보안 승인
```

즉 다음에는 필요하지 않다.

```text
HWPX 생성
COM 탐지
한글 설치 여부 확인
일반 XML QA
```

다음 작업에는 필요하다.

```text
Automation으로 HWPX를 무인 Open
→ PageCount 읽기
```

보안모듈이 없으면 Automation의 파일 접근 승인 과정 때문에 자동 `Open()`이 차단될 수 있다.

---

# 5. 보안모듈 등록 위치

현재 구현은 다음 registry 위치를 runtime discovery한다.

```text
HKCU\Software\HNC\HwpAutomation\Modules
```

예시:

```text
value name:
FilePathCheckerModuleExample

value data:
C:\Users\<USER>\...\FilePathCheckerModuleExample.dll
```

중요:

```text
FilePathCheckerModuleExample
```

이라는 이름 자체를 application code에 하드코딩하지 않는다.

구현은 registry에 실제 등록된:

```text
value name
DLL path
```

을 읽고, DLL이 실제 존재하는 경우에만 해당 모듈을 사용한다.

호출:

```text
RegisterModule(
    "FilePathCheckDLL",
    <runtime-discovered registry value name>
)
```

보안모듈 DLL도 repository에 포함하거나 사용자별 절대경로를 저장하지 않는다.

---

# 6. Codex sandbox와 실제 Windows 사용자 HKCU

Codex 실행 환경에서는 다음과 같은 별도 sandbox 계정을 사용할 수 있다.

```text
CodexSandboxOffline
```

Windows의 `HKCU`는 **현재 프로세스를 실행하는 사용자별 registry hive**다.

따라서:

```text
CodexSandboxOffline의 HKCU
≠
실제 Windows 사용자 ohyou의 HKCU
```

이다.

Codex sandbox에서:

```text
security_module = missing
```

이라고 나오더라도 실제 사용자 환경에 모듈이 등록되어 있을 수 있다.

Native Hancom E2E 검증은 필요할 경우 **실제 Windows 사용자 PowerShell에서 실행한다.**

현재 개발 환경에서는:

```text
BOOK-0CRUMB5IVE\ohyou
```

사용자 컨텍스트에서 검증되었다.

---

# 7. Python → PowerShell payload 전달

## 잘못된 방식

기존 구현은 다음처럼 PowerShell `-Command` 뒤에 payload를 positional argument로 전달했다.

```python
[
    "powershell.exe",
    "-NoProfile",
    "-NonInteractive",
    "-Command",
    script,
    payload,
]
```

PowerShell에서는:

```powershell
$args[0]
```

으로 읽으려고 했다.

그러나 실제 실행에서 payload가 정상 전달되지 않아:

```text
path=
module=
```

상태가 발생했다.

그 결과:

```text
RegisterModule = True
Open = False
```

가 발생했고 실제 파일 문제처럼 보였다.

---

## 현재 방식

payload는 child process 전용 environment variable로 전달한다.

Python:

```python
env = os.environ.copy()
env["EDUDOC_HANCOM_PAYLOAD"] = payload

completed = subprocess.run(
    [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        script,
    ],
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    check=False,
    timeout=30,
    env=env,
)
```

PowerShell:

```powershell
$payload = [Text.Encoding]::UTF8.GetString(
    [Convert]::FromBase64String($env:EDUDOC_HANCOM_PAYLOAD)
) | ConvertFrom-Json
```

`EDUDOC_HANCOM_PAYLOAD`에는 실행 시점에 다음 정보가 들어간다.

```json
{
  "path": "<candidate HWPX path>",
  "security_module_name": "<runtime-discovered module name>"
}
```

이 환경변수는 사용자에게 영구 설정을 요구하는 configuration이 아니다.

```text
Python parent process
→ child PowerShell에 임시 전달
→ child process 종료
```

용도로만 사용한다.

---

# 8. Native validation 단계별 결과

`NativePageValidation`은 각 단계를 독립적으로 보존한다.

```python
register_module_result: bool | None
open_succeeded: bool
observed_pages: int | None
```

의미:

### `register_module_result`

```text
None
= RegisterModule을 실행할 수 없는 상태

False
= RegisterModule()을 실제 호출했으나 실패

True
= RegisterModule() 성공
```

### `open_succeeded`

```text
False
= HWPX Open 성공 전

True
= HWPX Open 성공
```

### `observed_pages`

```text
None
= PageCount까지 읽지 못함

1, 2, ...
= 한글에서 실제로 읽은 PageCount
```

앞 단계의 성공 여부를 `observed_pages` 존재 여부로 역추론하지 않는다.

---

# 9. PowerShell subprocess exit code

현재 native read 과정에서는 주요 실패 단계를 구분한다.

```text
exit 2
→ security module registration failed

exit 3
→ HWPX Open failed
```

Python에서는 이를 각각 보존한다.

예:

```text
register_module_result = False
open_succeeded = False
observed_pages = None
reason = security_module_registration_failed
```

또는:

```text
register_module_result = True
open_succeeded = False
observed_pages = None
reason = native_page_open_failed
```

모든 실패를 `None` 하나로 뭉개지 않는다.

---

# 10. 사용자용 smoke test

CLI:

```text
scripts/templates/check_native_page_count.py
```

실행 예:

```powershell
.\.venv\Scripts\python.exe scripts\templates\check_native_page_count.py `
  --input "C:\Users\work\edudoc-hwpx-template-engine\sandbox\template-candidates\weekly-report-one-page-family\roundtrip.sample.hwpx" `
  --required-pages 1
```

성공적인 native execution 예:

```text
hancom_automation = available
security_module = available
register_module = true
open = success
page_count = 2
required_pages = 1
native_page_validation = fail
```

이 결과에서 `fail`은 Automation 실패를 의미하지 않는다.

Automation은 정상 동작했고:

```text
실제 PageCount = 2
요구 PageCount = 1
```

이므로 문서 조판 QA가 실패한 것이다.

---

# 11. 2026-08-19 E2E 검증 결과

대상:

```text
sandbox\template-candidates\
weekly-report-one-page-family\
roundtrip.sample.hwpx
```

실제 사용자 PowerShell 및 Hancom 2022 Automation에서 확인:

```text
user=BOOK-0CRUMB5IVE\ohyou
path_exists=True
module=FilePathCheckerModuleExample
register=True
open=True
page_count=2
child_exit_code=0
```

최종 CLI에서도:

```text
hancom_automation = available
security_module = available
register_module = true
open = success
page_count = 2
required_pages = 1
native_page_validation = fail
```

까지 확인했다.

따라서 다음 항목은 검증 완료 상태다.

```text
COM runtime discovery                  PASS
security-module runtime discovery      PASS
RegisterModule                         PASS
Python → PowerShell payload 전달       PASS
HWPX Open                              PASS
native PageCount read                  PASS
required page comparison               PASS
```

현재 weekly-report candidate 자체는 실제 한글 조판 기준 **2페이지**이므로 `one_page_report` 요구사항에는 실패한다.

---

# 12. one_page_report 계약

`one_page_report` family는 native page count requirement를 가진다.

예:

```json
{
  "native_page_count": 1
}
```

의미:

```text
한글 native PageCount == 1
```

이어야 candidate page QA를 통과한다.

XML 구조, `linesegarray`, Preview 이미지 등을 이용해 실제 페이지 수를 추정하여 PASS 처리하지 않는다.

Native renderer를 사용할 수 없는 환경에서는 실제 page-count 검증을 수행한 것으로 간주하지 않는다.

---

# 13. 관련 구현 파일

주요 구현:

```text
core/adapters/hancom_page_count.py
scripts/templates/check_native_page_count.py
scripts/templates/qa_hwpx_template.py
scripts/templates/author_hwpx_template.py
```

family 계약:

```text
templates/institutions/edudoc/_families/one_page_report/recipe.json
```

schema:

```text
docs/contracts/document-family-layout.schema.json
```

관련 테스트:

```text
tests/task_scoped/test_hancom_page_count_provider.py
```

---

# 14. 변경 시 지켜야 할 invariant

향후 agent는 이 기능을 수정할 때 다음 원칙을 깨뜨리지 않는다.

```text
1. Hwp.exe 절대경로를 repository에 하드코딩하지 않는다.

2. 특정 한컴 버전의 설치경로를 가정하지 않는다.

3. Hancom Automation은 COM runtime discovery를 사용한다.

4. 보안모듈 이름과 DLL 경로도 runtime discovery한다.

5. 보안모듈 DLL을 repository에 vendor하지 않는다.

6. Hancom이 없는 환경에서도 HWPX 생성 기능 자체는 동작한다.

7. native PageCount가 필요한 QA에서는 XML 추정으로 native 검증을 대체하지 않는다.

8. RegisterModule / Open / PageCount 결과를 하나의 최종 상태로 역추론하지 않는다.

9. Python → child PowerShell payload는 `$args[0]`에 의존하지 않는다.

10. one_page_report의 최종 1페이지 여부는 실제 Hancom PageCount로 검증한다.
```

---

# 15. 현재 다음 작업

Native page validation infrastructure 자체는 검증 완료됐다.

현재 남은 문제는 infrastructure가 아니라 문서 조판이다.

```text
weekly-report candidate
native PageCount = 2

one_page_report required pages = 1
```

따라서 다음 작업은:

```text
one_page_report layout 조정
→ candidate 재생성
→ native PageCount 재검증
→ PageCount == 1
```

이다.

Hancom COM, security module, payload 전달 구조를 다시 설계할 필요는 없다.