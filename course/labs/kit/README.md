# labs/kit — 오프라인 실습 장치

전부 Python 표준 라이브러리만 쓰는 로컬 모의 도구다. 외부 호출·계정·키·설정 변경 없음. "모의(O) 증거"만 만들며 실제 모델·카카오·대회 수용을 대체하지 않는다.

| 폴더 | 역할 | 대표 명령 |
|---|---|---|
| `personas/` | 01 인터뷰 인물(P01) — `p01-role.md`는 CLI가 읽는다(학습자 미열람), `p01-open.md`는 공개 소개, `materials/`는 자료 묶음(충돌·인젝션 포함) | — |
| `agent/` | 규칙 기반 모의 응답기 — 입출력 계약의 기준 예제 | `python3 mock_agent.py --request ... --data ... --out ...` |
| `tests/` | 시험 실행기 `run.py`(`--agent` 실행 / `--responses` 채점, 케이스 입력·응답 스키마·근거 인용 검증, send_twice 시도별 보존) + 개발용 `cases-dev/`(14개) + 확인용 `cases-verify/`(6개, 답은 ANSWERS.md 분리) + `selfcheck.py`(양성+음성 프로브) | `python3 tests/selfcheck.py` |
| `failures/` | 실제 사고 재현 시뮬레이션 7종 + `selfcheck.py` | `python3 failures/selfcheck.py` |
| `kakao/` | 카카오 스킬 요청→응답 모의 어댑터(loopback 전용) | `python3 kakao/selfcheck.py` |
| `exams/` | 모의전 1~3회 인물·자료·미공개 기대 | `round*/role.md`를 CLI에 읽혀 인터뷰 |

응답 계약(labs/README.md 참조): `--request/--data/--out` → `<out>/<request_id>.json`에 `request_id,status,answer,evidence,duplicate,notes`.
