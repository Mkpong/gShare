---
sidebar_position: 3
title: REST API
---

# REST API

콘솔이 하는 모든 일은 `/api/v1`의 공개 REST API를 거칩니다. 실행 중인 설치는 OpenAPI 문서를
`/api/v1/openapi.json`에, Swagger UI를 `/api/v1/docs`에 제공하며, 같은 문서가 저장소에
`frontend/openapi.json`으로 들어 있습니다.

:::note 범위
gShare는 의도적으로 콘솔 우선입니다. API 키, CLI, SDK는 없습니다. API는 콘솔을 위해, 그리고
운영자가 자기 토큰으로 관리 작업을 자동화하기 위해 존재합니다.
:::

## 인증

```bash
curl -s -X POST https://gshare.example.com/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"jieun@example.com","password":"…"}'
# → {"access_token": "…", "token_type": "bearer", …}
```

토큰을 `Authorization: Bearer <token>`으로 보냅니다. 토큰은 수명이 짧고 리프레시 엔드포인트는
없습니다 — 다시 로그인하세요. `must_change_password`가 켜진 사용자는 바꾸기 전까지 비밀번호
엔드포인트만 호출할 수 있습니다.

## 규약

- **페이지네이션** — 목록 엔드포인트는 `page`, `size`를 받고
  `{"data": [...], "pagination": {"page", "size", "total"}}`를 돌려줍니다.
- **멱등성** — 무언가를 만드는 모든 쓰기(`POST /sessions`, `POST /storage/volumes`, 크레딧 작업)는
  `Idempotency-Key` 헤더를 받습니다. 같은 키로 반복하면 중복 생성 대신 원래 결과를 돌려줍니다.
- **오류** — 봉투 하나:
  ```json
  {"error": {"code": "quota_exceeded", "message": "…", "details": {...}, "request_id": "…", "timestamp": "…"}}
  ```
  `code`는 안정적이며 콘솔이 메시지로 매핑하는 값입니다. `details`에는 고칠 것이 담깁니다(예:
  세션이 `unserviceable`일 때 플릿이 제공하는 `reported_models`).
- **테넌트 범위** — 모든 목록은 호출자의 역할로 필터됩니다. 범위보다 많이 요청하면 403이 아니라
  자기 범위가 돌아오므로 토큰으로 탐색할 수 없습니다.
- **실시간 갱신** — `GET /sessions/events`는 콘솔이 듣는 서버 전송 이벤트 스트림입니다. 스트림을
  유지할 수 없으면 목록을 폴링하세요.

## 리소스 그룹

| 접두어 | 내용 |
|---|---|
| `/auth`, `/users`, `/organizations`, `/projects` | 로그인, 계정, 조직, 부서(API에서는 `projects`)와 소속 |
| `/sessions` | 생성, 목록(`scope=mine|all`), 상세, 일시정지/재개/재시작/종료, 연결 링크, 로그, 사용량, `bulk-terminate`, `preview-cost`, `gpu-availability` |
| `/queue` | 대기열 항목, 취소, 우선순위 |
| `/credits`, `/budgets` | 지갑, 배분, 요청, 리필, 원장; 조직 예산 |
| `/storage/volumes`, `/storage/pools` | 볼륨, 공유, 쿼터, 잠금; 스토리지 풀 |
| `/offerings`, `/presets`, `/images`, `/resource-policies` | 카탈로그와 정책(쿼터 요청 포함) |
| `/clusters`, `/nodes`, `/gpu-devices`, `/node-pools` | 인프라: 등록, 차단/비우기/삭제, 카드, 풀 |
| `/monitoring`, `/dashboard`, `/metrics` | 지표 프록시와 요약 |
| `/audit` | 필터와 CSV 내보내기가 있는 감사 로그 |
| `/notifications`, `/webhooks` | 알림 종과 조직별 아웃바운드 웹훅 |
| `/system` | 브랜딩, 가입 정책, 배치 정책 |
| `/health` | 프로브용 생존 확인 |

**내부** 플레인(`/internal/...`, `/.well-known/gshare-internal-jwks.json`)은 오퍼레이터 전용이며
사용자 토큰이 아닌 RS256 내부 JWT로 인증합니다.
