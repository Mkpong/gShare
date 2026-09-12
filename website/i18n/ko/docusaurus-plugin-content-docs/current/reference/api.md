---
sidebar_position: 3
title: REST API
---

# REST API

gShare 콘솔의 모든 기능은 `/api/v1` 경로의 공개 REST API를 통해 처리됩니다. 시스템 실행 시 OpenAPI 스펙은 `/api/v1/openapi.json`에서 제공되며, Swagger UI는 `/api/v1/docs` 경로에서 확인할 수 있습니다. 저장소 내 `frontend/openapi.json` 파일에도 동일한 사양이 포함되어 있습니다.

:::note API 제공 범위
gShare는 콘솔 환경을 최우선으로 고려하여 설계되었습니다. 별도의 API 키, CLI, SDK는 제공하지 않습니다. API는 콘솔 UI 동작 및 운영자의 관리 작업 자동화 목적으로 활용됩니다.
:::

## 인증 (Authentication)

```bash
curl -s -X POST [https://gshare.example.com/api/v1/auth/login](https://gshare.example.com/api/v1/auth/login) \
  -H 'Content-Type: application/json' \
  -d '{"email":"jieun@example.com","password":"…"}'
# 응답 예시: {"access_token": "…", "token_type": "bearer", …}
```

발급받은 토큰은 요청 시 `Authorization: Bearer <token>` 헤더로 전달합니다. 토큰은 단기 유효 기간을 가지며 리프레시 엔드포인트를 제공하지 않으므로, 만료 시 재로그인이 필요합니다. `must_change_password` 플래그가 활성화된 계정은 비밀번호 변경 엔드포인트 외 타 API 호출이 제한됩니다.

## API 설계 규약

- **페이지네이션**: 목록 조회 엔드포인트는 `page`, `size` 쿼리 파라미터를 사용하며, `{"data": [...], "pagination": {"page", "size", "total"}}` 형태로 응답합니다.
- **멱등성 (Idempotency)**: 리소스를 생성하는 모든 생성/변경 요청(`POST /sessions`, `POST /storage/volumes`, 크레딧 관련 작업 등)은 `Idempotency-Key` 헤더를 지원합니다. 동일한 키로 중복 요청 시 신규 생성 대신 기존 처리 결과를 반환합니다.
- **오류 응답 구조**: 표준화된 오류 응답 객체를 사용합니다.
  ```json
  {"error": {"code": "quota_exceeded", "message": "…", "details": {...}, "request_id": "…", "timestamp": "…"}}
  ```
  `code` 속성은 고정된 에러 코드로 콘솔 UI의 오류 메시지 매핑에 사용됩니다. `details`에는 문제 해결을 위한 상세 정보(예: 세션 실행 불가(`unserviceable`) 상태 시 클러스터에서 보고된 `reported_models` 정보)가 포함됩니다.
- **테넌트 격리 및 권한 범위**: 모든 목록 조회는 요청자의 역할 및 권한 범위로 자동 필터링됩니다. 권한 범위를 초과하는 요청 시 403 에러 대신 해당 사용자의 허용 범위 내 결과만 반환하여 권한 탐색을 차단합니다.
- **실시간 데이터 스트리밍**: `GET /sessions/events` 엔드포인트를 통해 Server-Sent Events (SSE) 기반의 실시간 상태 변경 이벤트를 제공합니다. SSE 연결이 불가능한 환경에서는 목록 조회를 폴링 방식으로 대체합니다.

## 주요 리소스 그룹

| API 경로 접두어 | 주요 기능 및 대상 |
|---|---|
| `/auth`, `/users`, `/organizations`, `/projects` | 인증, 계정 관리, 조직 및 부서(`projects`) 관리, 소속 정보 |
| `/sessions` | 세션 생성, 목록 조회(`scope=mine\|all`), 상세 정보, 상태 변경(일시정지/재개/재시작/종료), 접속 링크, 로그, 실시간 사용량, 일괄 종료(`bulk-terminate`), 비용 예측(`preview-cost`), GPU 가용성(`gpu-availability`) |
| `/queue` | 대기열 항목 관리, 작업 취소, 우선순위 변경 |
| `/credits`, `/budgets` | 지갑 관리, 크레딧 배분, 할당 요청, 충전, 거래 원장 조회, 조직 예산 관리 |
| `/storage/volumes`, `/storage/pools` | 볼륨 생성/조회, 공유 설정, 쿼터 변경, 볼륨 잠금, 스토리지 풀 관리 |
| `/offerings`, `/resource-presets`, `/images`, `/resource-policies` | 자원 카탈로그, 이미지 관리, 자원 정책 및 한도 증액 요청 |
| `/clusters`, `/nodes`, `/gpu-devices`, `/node-pools` | 인프라 관리: 클러스터 등록, 노드 차단/비우기/삭제, GPU 디바이스 및 노드 풀 관리 |
| `/monitoring`, `/dashboard`, `/metrics` | 모니터링 지표 프록시 및 메트릭 요약 정보 |
| `/audit-logs` | 감사 로그 필터링 조회 및 CSV 다운로드 |
| `/notifications`, `/webhooks` | 시스템 알림 센터 및 조직별 아웃바운드 웹훅 설정 |
| `/system` | 브랜드 설정, 회원가입 정책, 워크로드 배치 정책 |
| `/healthz` | 시스템 헬스 체크 프로브 엔드포인트 (`/api/v1` 경로 외 루트 엔드포인트로 제공) |

> **내부 API 규약**: 데이터 플레인 오퍼레이터 통신 전용 내부 API(`/internal/...`, `/.well-known/gshare-internal-jwks.json`)는 사용자 Bearer 토큰이 아닌 RS256 기반 내부 JWT 인증을 사용합니다.