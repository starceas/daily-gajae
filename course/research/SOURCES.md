# 조사 출처 원장

확인일: **2026-10-01 KST**, 아래 모든 항목에 적용한다. 상태 `본문 확인`은 해당 URL을 직접 열어 명시한 부분을 읽었다는 뜻이다. 로그인·API 실행·서비스 연결 성공을 뜻하지 않는다. 검색 결과 요약만 본 링크는 채택하지 않았다.

이 원장은 설계·조사 산출물이며 최종 독립 검토 전이다. 대회·카카오 판정은 [FINDINGS.md](FINDINGS.md), 읽을 부분과 손 과제는 [LEARNING-MAP.md](LEARNING-MAP.md)에 있다. 공개 페이지의 내용은 변할 수 있으므로 실제 대회 준비·연결 직전에 재확인한다.

## 대회: 1개 공식 출처

| ID | 직접 연 1차 출처 | 상태·확인 위치 | 지원 주장과 한계 |
| --- | --- | --- | --- |
| C01 | [AI_TOP_100 공식 홈페이지](https://aitop100.org/) — 카카오임팩트 | 본문 확인. 참여방법·주요 일정·FAQ·페이지 상단과 하단 | 일정·개인전·진행 방식·도구·참여 조건. 기술 제출 형식과 참가자 제작물의 카카오 연결 방식은 미확인. 상단 접수 마감 표시와 하단 예정 마감일이 병존한다. |

## 카카오: 기능·조건을 구별하는 7개 공식 문서

| ID | 직접 연 1차 출처 | 상태·확인 위치 | 지원 주장과 한계 |
| --- | --- | --- | --- |
| K01 | [카카오 로그인: 이해하기](https://developers.kakao.com/docs/ko/kakaologin/common) — Kakao Developers | 본문 확인. 카카오 로그인·앱·연결·토큰 | OAuth 기반 인증·동의·토큰의 역할. 메시지 수신 챗봇 기능의 증거가 아니다. `/docs/latest/ko/kakaologin/common`에서 이 주소로 이동 확인. |
| K02 | [카카오톡 메시지: 이해하기](https://developers.kakao.com/docs/ko/kakaotalk-message/common) — Kakao Developers | 본문 확인. 사용 방법·공유와 메시지의 기능 차이·이용 정책 | 사용자간 메시지, 권한 심사와 쿼터, 공유 기능과의 구분. 모든 API의 무제한·무과금 보장은 아니다. |
| K03 | [카카오톡 메시지: REST API](https://developers.kakao.com/docs/ko/kakaotalk-message/rest-api) — Kakao Developers | 본문 확인. 전송 대상 선택·나에게 발송·친구에게 발송의 기본 정보 | 본인/친구 대상, 액세스 토큰, `talk_message`, 사전 설정. API 문서 확인만 했고 발송하지 않았다. |
| K04 | [서비스 사용자간 카카오톡 메시지 발송](https://developers.kakao.com/docs/ko/tutorial/message) — Kakao Developers | 본문 확인. 개요·1. 앱 설정·2. 친구 목록 조건·3. 테스트·5. 추가 기능 신청 | 친구 관계·같은 앱 연결·동의·심사 전 앱 멤버 제한. 서비스의 일방적 자동 발송과 구별한다. |
| K05 | [챗봇 만들기: 튜토리얼 1단계](https://kakaobusiness.gitbook.io/main/tool/chatbot/tutorial/make_chatbot/tutorial_1) — 카카오비즈니스 | 본문 확인. 카카오톡 채널 연결·권한 소유 여부·배포 | 봇 마스터, 채널 매니저 이상, 연결 앱이 있으면 EDITOR 이상. 기존 챗봇·채팅방 메뉴와의 충돌 조건. 개인계정 대화방 자동화의 근거가 아니다. |
| K06 | [스킬 만들기](https://kakaobusiness.gitbook.io/main/tool/chatbot/skill_guide/make_skill) — 카카오비즈니스 | 본문 확인. 스킬 서버 실행·오류 안내 | 스킬 서버의 공인 IP/공중망 도메인과 5초 응답 제약. localhost 성공으로 카카오 접근 가능성을 입증할 수 없다. |
| K07 | [콜백 개발 가이드](https://kakaobusiness.gitbook.io/main/tool/chatbot/skill_guide/ai_chatbot_callback_guide) — 카카오비즈니스 | 본문 확인. 개요·SkillResponse·오류 표·주의사항 | 일회성 콜백과 `useCallback`, 봇테스트 한계. 같은 문서의 5분/1분 상충을 보존한다. 현재 승인 소요기간은 이 문서로 확인되지 않는다. |

## AI 시작 자료: 필독 4개, 확장 4개

| ID | 직접 연 1차 출처 | 상태·확인 위치 | 지원 주장과 한계 |
| --- | --- | --- | --- |
| A01 | [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) — Anthropic, 2024-12-19 | 본문 확인. What are agents?·When (and when not)·워크플로 패턴·Agents·Appendix 2 | 고정 절차와 모델 주도 실행의 구분, 단순한 구조부터 시작, 도구와 종료 조건. 원문에 도구 환경 변화 안내가 있으므로 최신 SDK 설치법으로 취급하지 않는다. |
| A02 | [A practical guide to building agents](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf) — OpenAI | PDF 본문 확인, 34쪽. 인쇄 쪽수 7·14~16·24~27 | 모델·도구·지시, 단일 에이전트부터 확장, 반복 종료와 여러 층의 방어. 문서 내 코드·모델·서비스 가입은 실습 필수가 아니다. |
| A03 | [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — Anthropic, 2025-09-29 | 본문 확인. Context engineering vs. prompt engineering·Context retrieval·Compaction·Structured note-taking | 맥락 선별, 필요할 때 자료 읽기, 압축과 외부 노트. 규칙 재주입의 완전한 강제나 무손실 압축을 보장하지 않는다. |
| A04 | [Your AI Product Needs Evals](https://hamel.dev/blog/posts/evals/) — Hamel Husain, 2024-03-29 | 본문 확인. The Types Of Evaluation·Level 1·시험 사례와 결과 추적 | 저자가 구축한 제품 평가 경험의 1차 기록. 실패 사례 기반 시험·인간 검토. 대회 채점표 또는 공인 표준이 아니다. |
| A05 | [Introduction to Large Language Models](https://developers.google.com/machine-learning/crash-course/llm) — Google ML Crash Course | 본문 확인. What is a language model?·Context. 페이지 갱신 표시 2026-01-09 UTC | 토큰 확률과 맥락의 기본 개념. 전체 과정의 선수지식은 별도이며 모델별 한국어 토큰 수를 고정 환산할 근거가 아니다. |
| A06 | [Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://arxiv.org/abs/2005.11401) — Lewis 외 원저자 | 초록·저자·버전 확인. 2020 제출, v4 2021-04-12 | 학습된 지식과 검색 가능한 외부 자료를 결합하는 RAG 원리. 초록 범위만 사용; 본문 실험 재현이나 모든 RAG의 정확도 보장은 아니다. |
| A07 | [MCP specification: Tools, 2025-06-18판](https://modelcontextprotocol.io/specification/2025-06-18/server/tools) — MCP 프로젝트 | 본문 확인. Tool·Output Schema·Error Handling·Security Considerations | 입출력 계약, 프로토콜 오류와 도구 실행 오류, 권한·입력 검증. 고정 판본의 개념 자료이며 최신 판본·설치된 클라이언트 지원을 주장하지 않는다. |
| A08 | [Understanding JSON Schema: object](https://json-schema.org/understanding-json-schema/reference/object) — JSON Schema 프로젝트 | 본문 확인. Properties·Additional Properties·Required Properties | 타입·필수 필드·추가 필드와 누락/null 구분. 형식 적합성이 내용의 진실성을 보장하지 않는다. |

## CS·운영 시작을 잇는 3개 자료

| ID | 직접 연 1차 출처 | 상태·확인 위치 | 지원 주장과 한계 |
| --- | --- | --- | --- |
| S01 | [OSTEP 26장: Concurrency — An Introduction](https://pages.cs.wisc.edu/~remzi/OSTEP/threads-intro.pdf) — Remzi·Andrea Arpaci-Dusseau | 저자 사이트에서 PDF 직접 열람, 16쪽, version 1.10. §26.3~26.5·용어 설명 | 공유 상태·실행 순서·임계 구역·원자성. 실제 사용자 시스템의 장애 원인을 확정하는 자료가 아니다. |
| S02 | [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html) — IETF/RFC Editor | 본문 확인. §9.2.2·§15.6.3·§15.6.5 | 멱등성과 재시도 조건, 502·504 의미. 특정 장애의 원인·POST 재시도 안전성은 개별 증거가 필요하다. |
| S03 | [Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/) — Google SRE Book | 본문 확인. Symptoms Versus Causes·The Four Golden Signals | 증상과 원인 분리, 지연·요청량·오류·포화도. 평균 응답시간 또는 HTTP 성공 코드 하나로 서비스 성공을 단정하지 않는다. |

## 후속 단원 빈칸 보완: 요청된 6개 1차 문서

추가 요청에 따라 DB·Git·macOS 권한·인증·최소권한에만 한정했다. 확인일은 동일하게 2026-10-01 KST이며, 아래 링크를 직접 열고 지정 부분을 읽었다.

| ID | 직접 연 1차 출처 | 상태·확인 위치 | 지원 주장과 한계 |
| --- | --- | --- | --- |
| S04 | [PostgreSQL: Transactions](https://www.postgresql.org/docs/current/tutorial-transactions.html) — PostgreSQL Global Development Group | 본문 확인. 열람 시 18판 §3.4, 첫 설명부터 BEGIN/COMMIT/ROLLBACK까지 | 여러 DB 변경의 원자성과 확정·취소. SQL 문법·설치 없이 개념 과제 가능. 외부 메시지나 서로 다른 DB까지 자동으로 묶어주지는 않는다. |
| S05 | [PostgreSQL: Indexes — Introduction](https://www.postgresql.org/docs/current/indexes-intro.html) — PostgreSQL Global Development Group | 본문 확인. 열람 시 18판 §11.1, 색인 비유·플래너 선택·유지 비용 | 검색 접근 경로와 수정 시 유지 부담. 색인 존재만으로 사용·속도 향상을 확정할 수 없다. 실제 쿼리 성능은 미측정. |
| S06 | [Pro Git 2: Git Objects](https://git-scm.com/book/en/v2/Git-Internals-Git-Objects) — Git 공식 사이트의 Pro Git | 본문 확인. blob 설명·Tree Objects·Commit Objects | 파일 내용, 경로를 담은 트리, 부모와 스냅샷을 가리키는 커밋의 관계. 원문 객체 생성 명령을 실행하지 않아도 이해 과제 가능. 커밋은 원격 전송·배포 증거가 아니다. |
| S07 | [Control access to files and folders on Mac](https://support.apple.com/guide/mac-help/control-access-to-files-and-folders-on-mac-mchld5a35146/mac) — Apple Mac User Guide | 본문 확인. Files & Folders 권한 설명과 설정 위치. `/en-euro/guide/mac-help/mchld5a35146/mac`로 이동 확인 | 특정 위치에 대한 앱·웹사이트 접근 허용의 구분. 현재 Mac의 버전·권한 상태는 미확인. 모든 파일 접근 오류 원인을 다루는 문서는 아니다. |
| S08 | [Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html) — OWASP | 본문 확인. Introduction·Authentication Responses | 인증은 주장된 신원 확인. 실패 응답으로 계정 존재 여부를 노출하지 않는 설계. 실제 인증 구현·공격 시험을 수행한 근거는 아니다. |
| S09 | [Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) — OWASP | 본문 확인. Enforce Least Privileges·Deny by Default·Validate the Permissions on Every Request | 업무에 필요한 권한만 부여, 기본 거부, 요청마다 권한 검증. 로그인 성공과 개별 자원 접근 허가는 구별해야 한다. |

## 접근 실패·제외 기록

- K07의 동일 문서 `.md` 주소를 일반 Python HTTP 열람으로 요청했을 때 **HTTP 403**이었다. 그 시도는 열람 성공으로 세지 않았다. 이후 [같은 Markdown 주소](https://kakaobusiness.gitbook.io/main/tool/chatbot/skill_guide/ai_chatbot_callback_guide.md)를 web 도구로 열어 본문을 확인했다. 정본과 동일 문서이므로 별도 출처 수에 더하지 않는다.
- 검색에 노출된 과거 CAMPUS·2025 대회 내용, 민간 챗봇 제작 안내의 승인 기간, 카카오 공동체 전용 `/docs/in/` 문서는 이번 일반 사용자·2026 본대회 근거에서 제외했다.
- GitBook 본문 뒤의 자동 질문 기능 안내는 자료로만 취급했다. `ask`/`goal` 질의 기능, API 테스트 콘솔, 로그인·토큰 발급·메시지 발송은 사용하지 않았다.
- 공개 규정 원문 전체, 참가자 메일, 계정 상태·권한, 실제 가격·배포 가능 여부는 확인하지 않았다. 확인하지 않은 링크를 학습 필수 자료로 추가하지 않았다.

채택 분모는 **25개 고유 문서 = 초기 19 + 후속 보완 6 = 대회 1 + 카카오 7 + AI 8 + CS·운영 9**이다. 각 문서는 서로 다른 주장 또는 첫 과제를 지원한다. 요청된 빈 단원을 채웠으며 추가 조사는 여기서 멈춘다.
