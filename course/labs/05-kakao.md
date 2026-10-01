# 05 — 카카오 경로 구별과 로컬 모의 어댑터 (선택 실습)

> 이 실습은 **선택**이다. 대회가 참가자에게 카카오 연결을 어떤 방식으로 요구하는지는 미확인이므로, 기본 경로는 인터뷰→요구→시험까지다. 여기서는 ① 다섯 경로를 구별하고 ② 로컬 모의 어댑터로 요청→응답 계약을 연습한다. **이 작성 세션·네 실습 모두 실제 카카오 메시지를 보내지 않는다.**

시간(교육 설정): 30분.

## 준비 — 다섯 경로는 서로 대체가 안 된다

아래 표는 [research/FINDINGS.md](../research/FINDINGS.md) §2의 요약이다. 문서 확인일은 2026-10-01.

| 경로 | 되는 일 | 필요 조건 | 증거 한계 |
|---|---|---|---|
| 카카오 로그인 [K01](https://developers.kakao.com/docs/ko/kakaologin/common) | 사용자 인증·토큰 발급 | 개발자 앱·로그인 설정 | 메시지 수신 능력의 증거 아님 |
| 나에게 보내기 [K03](https://developers.kakao.com/docs/ko/kakaotalk-message/rest-api) | 본인 채팅으로 발송 | 앱·토큰·`talk_message` 동의 | 다른 사람에게 보내기·수신의 증거 아님 |
| 친구 메시지 [K04](https://developers.kakao.com/docs/ko/tutorial/message) | 같은 서비스 친구에게 발송 | 친구 관계·앱 연결·동의. 심사 전 앱 멤버 제한, 일 30건 등 쿼터 | 일방적 자동 발송 봇 경로 아님 |
| 채널 챗봇 [K05](https://kakaobusiness.gitbook.io/main/tool/chatbot/tutorial/make_chatbot/tutorial_1)·[K06](https://kakaobusiness.gitbook.io/main/tool/chatbot/skill_guide/make_skill) | 채널 사용자 발화를 블록/스킬로 처리 | 봇 마스터+채널 매니저 이상 권한. 외부 처리는 공인 IP/공중망 도메인의 스킬 서버 | localhost 성공은 카카오 접근 증거 아님 |
| 비공식 개인계정 자동화 | 개인 메신저 화면 조작 등 | 공식 문서에 지원 경로로 확인 안 됨 | 허용성·안정성·대회 인정 모두 미확인 → 채택 안 함 |

주의할 상충: K07 콜백 문서는 유효시간을 개요 5분·오류 표 1분으로 다르게 적고 있다 — **문서 내부 상충 = 미확인**으로 남긴다. 어느 쪽도 보장값으로 채택하지 않는다.

## 실행 행동 — 로컬 모의 어댑터 (외부 연결 0)

목표는 카카오가 보내는 스킬 요청 JSON이 들어왔을 때 네 에이전트의 답을 카카오 응답 형식으로 돌려주는 **경계**를 연습하는 것이다.

1. 먼저 장치가 도는지 본다:

```sh
cd <학습 폴더>
python3 labs/kit/kakao/selfcheck.py
```

기대: `11/11 통과 — 모의(O) 수준. 네이티브(K) 미검증.` (응답 형식·왕복·예산 경로 5개 + 에이전트 실패·깨진 JSON·응답 누락·잘못된 payload의 제어된 error 변환 6개)

2. 요청→응답 형식을 직접 본다:

```sh
# 모의 스킬 서버를 띄운다(127.0.0.1 전용 — 외부에서 접근 불가)
python3 labs/kit/kakao/serve.py --port 8787 \
  --agent "python3 labs/kit/agent/mock_agent.py" \
  --data labs/kit/personas/materials \
  --out labs/kit/kakao/_work &

# 다른 터미널에서 fixture 요청을 보낸다
python3 labs/kit/kakao/send.py --port 8787
python3 labs/kit/kakao/send.py --port 8787 --text "월요일에 열어요?"
```

3. 응답을 확인한다: `version:"2.0"`, `template.outputs[0].simpleText.text`에 에이전트 답변이 들어가고, `_mock_meta`에 소요 시간과 예산(학습 설정 4초 — K06 문서의 5초와 다른 값)이 붙는다. `within_budget`은 시간 비교일 뿐 성공의 증거가 아니다.
4. 콜백 형태도 본다. `--internal`은 필수 인자다 — 먼저 내부 응답 파일을 하나 만들고 넘긴다:

```sh
# 내부 응답 파일을 만든다(모의 응답기)
python3 labs/kit/agent/mock_agent.py \
  --request labs/kit/agent/requests/q01.json \
  --data labs/kit/personas/materials \
  --out labs/kit/kakao/_work

# 콜백 첫 응답 형태로 변환해 본다
python3 labs/kit/kakao/adapter.py \
  --internal labs/kit/kakao/_work/q01.json --callback
```

기대: `useCallback:true`와 `data.request_id`가 있는 첫 응답. 이건 콜백 첫 응답의 형식 확인일 뿐, 실제 콜백 왕복 성공이 아니다.
5. 서버를 끈다: `kill %1` 또는 Ctrl+C.

## 출력 예 / 기대 결과

```json
{"version": "2.0",
 "template": {"outputs": [{"simpleText": {"text": "화~금 07:00–15:00, ..."}}]},
 "_mock_meta": {"elapsed_sec": 0.41, "budget_sec": 4.0, "within_budget": true}}
```

## 산출물

- [templates/channel-contract.md](../templates/channel-contract.md)를 채운 연결 계약 — 요구 경로, 응답 기한, 중복·타임아웃 정책, 사람 결정이 필요한 행동.
- 모의 왕복의 출력 저장(응답 JSON).
- 증거 구분 기록: 이번 실습은 D(문서 확인)+O(오프라인 왕복)뿐이다. M·K·J는 미실행.

## 실패 분기

| 증상 | 원인 후보 | 다음 행동 |
|---|---|---|
| send.py 연결 거부 | serve.py가 안 떴거나 포트 다름 | 서버가 살아 있는지, 같은 포트인지 확인 |
| 응답에 "처리 시간 초과" | 예산 4초 안에 에이전트가 못 끝남 | `--budget`을 올려 재시도, 어디서 느린지 기록 |
| "이제 카카오 연결되나?" | 모의를 실제로 착각 | 아니다 — 공인 주소·계정·권한·실제 왕복 증거가 없다 |

## 실제 연결로 넘어가는 조건 (R∧A∧Q∧E — FINDINGS §4)

모의(O) 합격만으로 실제 연결을 시작하지 않는다. 아래 넷이 전부 확인일 때만:

- **R**: 대회가 요구하는 정확한 연결 방식·제출 형식이 공개 규정으로 확인됐다(현재 미확인).
- **A**: 그 구체적 행위(계정 연결·발송 등)가 사용자 승인을 받았다.
- **Q**: 필요한 계정·권한·비용·쿼터 조건이 확인됐다.
- **E**: 실제 시험 환경과 성공 증거 수집 방법이 있다.

하나라도 미확인·부정이면 오프라인 모의로 종료한다. 실제 연결은 **승인·공개 요구 범위 확정·테스트 채널**이 갖춰진 뒤 사용자가 직접 한다. 불필요한 새 계정·키 발급은 하지 않는다.

## 합격 기준 (실행 전 고정: N=3)

1. 다섯 경로를 표로 구별해 적고, "한 경로의 성공이 다른 경로의 증거가 아님"을 명시했다.
2. 로컬 모의 왕복을 한 번 이상 실행하고 응답 JSON을 저장했다(O 증거).
3. 연결 계약을 채우고 R·A·Q·E 각각의 현재 값(확인/부정/미확인)을 적었다.

합격 = 3/3. "카카오에 보냈다"는 합격 조건이 아니며 이 실습 범위 밖이다.
