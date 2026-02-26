# Quality Gate Checklist (Spec-first + Test-first + Docs-as-code)

이 체크리스트는 "코드 생성 결과물"의 품질을 코드/문서 모두에서 보장하기 위한 기본 게이트입니다.

## 0) 시작 전: Spec-first

- [ ] 변경 목적/범위를 PR 설명에 3~5줄로 명시했다.
- [ ] 수용 기준(acceptance criteria)을 항목형으로 작성했다.
- [ ] 비범위(Non-goals)를 1개 이상 명시했다.
- [ ] 리스크/롤백 포인트를 한 줄 이상 작성했다.

권장 산출물:
- 간단 변경: PR 본문 내 `## Spec` 섹션
- 중간 이상 변경: `docs/specs/<topic>.md` 작성 후 PR 링크

## 1) 구현 전: Test-first

- [ ] 실패하는 테스트(또는 재현 시나리오)를 먼저 추가/기록했다.
- [ ] 핵심 경로(성공/실패 최소 1개씩)에 대한 검증이 있다.
- [ ] 회귀 방지 테스트를 포함했다.

필수 로컬 명령:
```bash
make ci-fast
```

## 2) 구현 후: Code gates

- [ ] `ruff` 통과
- [ ] `mypy` 통과 (strict lane 기준)
- [ ] `pytest` 통과
- [ ] 템플릿 거버넌스 점검 통과 (`check-template`, `check-locks`)

릴리즈 전 필수:
```bash
make ci-strict
```

## 3) 구현 후: Docs-as-code gates

- [ ] 사용자/운영자 관점에서 변경된 동작을 문서화했다 (README 또는 docs/*).
- [ ] 실행 예시/CLI 옵션 변경 시 예시 명령을 업데이트했다.
- [ ] 문서 링크 검증을 통과했다 (`make check-docs`).
- [ ] PR 본문에 "어떤 문서가 왜 바뀌었는지" 근거를 남겼다.

## 4) PR 증빙 체크

- [ ] Spec 링크 또는 요약
- [ ] 테스트 증빙 (추가/변경 테스트, 실행 결과)
- [ ] 문서 증빙 (변경 파일 + 이유)
- [ ] 리스크/롤백

## 5) 일상 운영 루틴 (팀 권장)

- 개발 중: `make ci-fast`
- PR 열기 전: `make check-docs`
- 머지 전: `make ci-strict`

이 순서만 지켜도 "기능은 되는데 문서가 깨짐" 또는 "문서만 있고 테스트 없음"을 크게 줄일 수 있습니다.
