# 04 — 실제 사고를 손으로 재현하기

목표: 네가 실제로 겪은 장애들을 **읽는 게 아니라 재현**한다. 각 시나리오는 `kit/failures/` 안의 안전한 모의 장치로, 실서비스·실제 폴더·자동 승인 키는 건드리지 않는다.

시간(교육 설정): 45분. 전부 하려 하지 말고 최소 3개 시나리오를 완주한다.

## 준비

```sh
cd <학습 폴더>
python3 labs/kit/failures/selfcheck.py   # 대표 명령의 출력이 기대와 맞는지 먼저 확인
```

기대 출력: `15/15 통과`. 주의 — 이건 고정된 사례들의 출력 문자열 subset 검사다. 장치가 정상이라는 증명이나 "실제 사건과 원리가 같다"는 증명이 아니며, 7개 시나리오 전체를 커버하지도 않는다. 실패한 항목이 있으면 그 시나리오는 건너뛰고 나머지부터 한다.

## 실행 행동 — 7개 시나리오

각 시나리오는 "예측 → 실행 → 실제와 대조 → 왜" 순서다.

### ① 경쟁 조건 — 확인과 실행 사이 (race)

네 사건: 자동 승인기가 확인과 실행 사이의 경쟁 조건으로 7차까지 BLOCK.

```sh
python3 labs/kit/failures/race/sim.py --mode order --events check,cancel,act
python3 labs/kit/failures/race/sim.py --mode order --events check,act,cancel
python3 labs/kit/failures/race/sim.py --mode counter --lock off
python3 labs/kit/failures/race/sim.py --mode counter --lock on
```

- 예측 먼저 적는다: check,cancel,act 순서면 결과가 뭘까?
- `counter --lock off`는 실행할 때마다 실제 값이 달라질 수 있다 — 그게 경쟁 조건의 본질이다. `--lock on`과 비교한다.

### ② 중복 이벤트 — 멱등성 (dup)

네 사건: 같은 답이 중복 전송됐다.

```sh
python3 labs/kit/failures/dup/sim.py --dedupe off
python3 labs/kit/failures/dup/sim.py --dedupe on
python3 labs/kit/failures/dup/sim.py --dedupe on --replay
```

- `--replay`는 보존된 `state.json`을 지우지 않고 큐를 다시 유입한다 — 저장된 중복 방지 정보가 살아 있으면 재실행해도 skip이 유지됨을 확인할 뿐이다. **상태 상실(state.json 유실)은 이 명령으로 재현되지 않는다** — 그 경우 다시 중복된다는 건 이 장치의 시연 범위 밖이다.
- 포인트: request_id 없이 "내용이 같다"로는 진짜 중복과 "같은 내용의 다른 요청"을 구별 못 한다.
- **한계 명시:** `mock_agent.py`의 out 파일 존재 확인과 이 시뮬의 dedupe는 "순차 재입력"만 잡는 모형이다. 동시에 두 요청이 도착하거나(①의 경쟁 조건), 프로세스가 재시작되거나, 외부 시스템이 "한 번만 처리"를 약속해야 하는 상황(exactly-once)은 이 장치가 보장하지 않는다 — 그걸 증명하려면 잠금·영속 상태·수신 확인이 따로 필요하다.

### ③ timeout ≠ 실패 (timeout)

```sh
# 먼저 첫 시도만 본다 — 두 경우의 ledger가 다르다
python3 labs/kit/failures/timeout/sim.py --fail request
python3 labs/kit/failures/timeout/sim.py --fail response

# 그 다음 같은 요청을 재시도한 경우를 본다
python3 labs/kit/failures/timeout/sim.py --fail request --retry
python3 labs/kit/failures/timeout/sim.py --fail response --retry
```

- **첫 시도만 보면** ledger(실제 부수효과)가 다르다: 요청 상실은 `[]`(작업 안 됨, D0E0), 응답 상실은 `["r1"]`(작업은 됐지만 응답만 잃음, D1E1). 클라이언트가 본 것은 둘 다 "응답 없음"뿐이다 — 그래서 구별할 수 없는 게 문제다.
- **`--retry` 후 최종 ledger는 둘 다 `["r1"]`로 같아진다.** 서버가 request_id로 중복 처리를 막았기 때문이다. 최종 상태가 같다고 첫 시도에 일어난 일이 같았다는 뜻이 아니다 — dedup은 "중복 처리 방지"이지 "전달 보장"이 아니다.
- 질문: "응답 상실" 상태에서 무조건 재시도하면 왜 위험한가? → 서버가 request_id로 중복을 막지 않으면 작업이 두 번 된다.

### ④ 설정 덮어쓰기 (config)

네 사건: 채널 설정이 전역 설정을 덮어 모델 교체가 안 먹혔다.

```sh
python3 labs/kit/failures/config/sim.py --reset --set-global model=sol
python3 labs/kit/failures/config/sim.py --set-channel ch1 model=ds --channel ch1
python3 labs/kit/failures/config/sim.py --channel ch1 --set-model opus
```

- 포인트: 각 값에 ← 출처가 붙어 나온다. "바꿨는데 안 먹힌다"는 대부분 위 층이 덮고 있는 것이다.
- 실제 설정 파일은 이 시뮬레이션의 `_work/` 안 json뿐이다. 네 실제 CLI 설정은 건드리지 않는다.

### ⑤ DNS와 HTTP는 다른 층 (net)

```sh
for m in dns refused http502 timeout; do
  echo "== $m =="; python3 labs/kit/failures/net/sim.py --fail $m
done
```

- `--reveal` 없이 먼저 증상만 보고 "어느 층?"을 적는다. 그 다음 `--reveal`로 대조.
- 네 사건 대조: 502는 앞단까지는 도달했고 게이트웨이가 upstream에서 무효 응답을 받았다는 뜻이다 — "뒤 서버가 죽었다"는 원인 후보 중 하나일 뿐 502가 확정해 주지 않는다(연결 불능·깨진 응답·설정 오류 등). DNS 실패는 서버에 닿지도 못했다는 뜻 — 고치는 곳이 다르다.
- **한계 명시:** 이 시뮬은 각 층의 "관찰 증상 모양"을 미리 만든 문자열로 보여줄 뿐이다. sim 출력만으로 실제 네트워크 장애를 진단할 수 없다 — 실제 진단은 실제 조회(`dig`·`curl` 등)와 증거가 필요하다.

### ⑥ 권한의 층 (perms)

```sh
python3 labs/kit/failures/perms/sim.py
```

- kit 안의 sandbox 폴더만 만들고 권한을 바꿨다 되돌린다. 네 실제 폴더는 안 건드린다.
- 포인트: "권한 오류"의 원인 후보는 층별로 다르다 — ① 파일 모드(rwx), ② macOS TCC(앱별 접근 허용), ③ 앱 샌드박스(격리 컨테이너 — TCC와 별개 장치), ④ 도구의 승인 정책. 어느 층인지 단서를 먼저 본다.
- **한계 명시:** 이 시뮬이 실제로 재현하는 건 kit 사본의 rwx 변경뿐이다 — 실제 TCC 동작이나 샌드박스 격리를 검증한 게 아니다. ②③의 실증은 이 장치 범위 밖이다.

### ⑦ 컨텍스트 오염 (context)

네 사건: 긴 대화에서 모델이 규칙을 잊어 매 턴 규칙을 다시 넣는 훅을 썼다.

```sh
python3 labs/kit/failures/context/sim.py --window 20
python3 labs/kit/failures/context/sim.py --window 20 --reinject
```

- 포인트: 이 모의가 보여주는 건 하나의 원인 후보뿐이다 — "유한 줄 창 + 규칙 문자열 검출" 모형에서 규칙이 창 밖으로 밀려나면 못 지킨다.
- **단정 금지:** 실제 사건에서 모델이 규칙을 잊은 원인이 "시야 밖으로 밀려난 것"이었다고 이 장치가 증명하지 않는다 — 이 코드는 그 사건을 진단하지 않았다. 실제 원인 후보는 압축 손실·주의 경쟁·명령 충돌 등 여럿이고, 별도 시험으로 좁혀야 한다.
- 재주입은 대책 후보일 뿐이며 "보인다 ≠ 지킨다" — 시험으로 검증해야 한다.

## 출력 예 / 기대 결과

- selfcheck: `15/15 통과`
- race order A: 마지막 상태에 `acted` + "취소된 요청을 승인" 판독문.
- dup off: `'m1': 3` — 중복 3번 기록.

## 산출물

- 학습 기록(learning-log)에 시나리오별로: 내 예측 / 실제 출력 / 왜 달랐나(또는 맞았나).
- 최소 3개 시나리오를 완주했다면 나머지는 재개 지점에 남긴다.

## 실패 분기

| 증상 | 원인 후보 | 다음 행동 |
|---|---|---|
| selfcheck에서 특정 항목 FAIL | 스크립트 의존 경로 문제 | `cd` 위치를 repo 루트로 확인, 명령을 절대경로로 재시도 |
| counter --lock off가 매번 400 | 경쟁이 우연히 안 생김(빠른 머신) | rounds를 올려 재시도하거나 order 모드로 원리만 확인 |
| 권한 되돌리기 실패로 폴더 잔류 | 중간에 Ctrl+C | `_work`, `sandbox` 폴더를 손으로 삭제(kit 안이므로 안전) |
| "이게 내 사건과 뭐가 다른가" 막힘 | 모형은 원인 후보 하나를 보여줄 뿐이며, 동일 증상이어도 실제 원인은 다를 수 있음(추가 관측 전 미확인) | learning-log에 모형과 실제 사건의 원인 후보·차이·판별 증거를 분리해 적고, 동일성은 미확인으로 남긴다 |

## 합격 기준 (실행 전 고정: N=3)

1. 최소 3개 시나리오를 직접 실행하고 출력을 기록했다.
2. 하나 이상에서 "내 예측"과 "실제"를 적고 차이를 설명했다.
3. timeout과 응답 상실의 차이, 권한 오류의 층별 후보(rwx·TCC·샌드박스·도구 정책) 중 하나 이상을 자기 말로 썼다.

합격 = 3/3. 7개 다 돌릴 필요는 없다 — 다만 selfcheck 통과는 "대표 명령이 기대 출력을 냈다"는 고정 사례 subset 확인일 뿐, 장치 정상·실제 사건과의 원리 동일성·시나리오 전체 증명이 아니다.
