# Task-Scoped Testing Policy

This policy applies to every task that changes executable behavior.

- Every changed behavior or acceptance criterion MUST have at least one newly added automated test case.
- A new test case may be added to an existing test file, but reusing or merely modifying an existing test does not satisfy this requirement.
- Each new test must directly verify the requested behavior, fail against the pre-change behavior, pass after implementation, and remain as regression protection.
- Manual inspection, generated files, package validation, and existing tests do not replace the new test.
- Do not change expected values, IDs, counts, snapshots, assertions, or test status merely to make the implementation pass.
- Existing tests may change only when the requirement changed or the test is proven incorrect. Report the reason.
- Do not modify unrelated source code, tests, fixtures, or expected outputs.
- If an existing test fails and its requirement did not change, fix the implementation rather than the test.
- Without the required new test, `구현됨`, `검증됨`, `사용 가능`, and `완료` are `아니오`.
- If any relevant test fails or warns, `검증됨`, `사용 가능`, and `완료` are `아니오`.
- Non-behavioral documentation, comment, spelling, and formatting changes are exempt.

The completion report MUST include:

- each changed behavior and its corresponding new test path and test name
- the exact pre-change command and failing result
- the exact post-change command and passing result
- affected regression-test commands and results
- every failure or warning
- the reason for modifying any existing test