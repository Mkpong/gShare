---
sidebar_position: 8
title: 콘솔 UX 표준
---
# 콘솔 UX 표준

콘솔의 모든 화면이 지켜야 할 것과, 그것을 값싸게 만들어 주는 컴포넌트. 대부분은
[`test/e2e/ux`](../test/e2e/ux)가 자동으로 검사합니다 — 페르소나 8개, 뷰포트 4개, 언어 2개, GPU 없는
제어 플레인 대상.

## 모든 화면

| 보장 | 방법 | 검사 |
|---|---|---|
| 브라우저 탭 이름이 화면 이름 | `<PageHeader title>`이 `useDocumentTitle` 호출 | `page.title.notPerScreen` |
| 문서 순서상 `<h1>` 하나 | `<PageHeader>` | `page.heading.noH1` |
| `<main>`, `<nav>`, `<header>` 랜드마크와 건너뛰기 링크 | `Layout` | `page.landmark.*`, `page.skipLink.missing` |
| `<html lang>`이 선택 언어를 따름 | `frontend/src/i18n/index.ts` | `i18n.htmlLangMismatch` |
| 모든 컨트롤에 보이는 포커스 링 | `frontend/src/styles/index.css`의 `:focus-visible` | `keyboard.noFocusRing` |
| 텍스트가 자기 배경 대비 WCAG AA 충족 | 테마 토큰 | `contrast.belowWcagAA` |
| 390px에서 가로 스크롤 없음 | `.gs-shell`, `hideOnMobile` 열 | `responsive.horizontalScroll` |
| 폰에서 터치 대상 ≥ 44px, 텍스트 ≥ 12px | `frontend/src/styles/index.css` 끝의 폰 오버라이드 | `responsive.tapTargetTooSmall` |
| 애니메이션이 `prefers-reduced-motion` 존중 | `frontend/src/styles/index.css` | — |

## 최상위 아래의 화면

- **브레드크럼과 돌아갈 길.** `<PageHeader crumbs={[…]}>` + `<BackLink>`. 없으면 올라갈 방법이
  브라우저 뒤로 가기뿐인데, 반쯤 채운 폼에서는 작업을 잃습니다.
- **제목에 대상 이름을 넣습니다.** 종류만이 아니라: "부서 편집 — NLP팀".

## 목록

모두 `frontend/src/components/Table.tsx`와 `frontend/src/hooks/useTableState.ts`에 있으므로 화면은
`sort`, `dir`, `onSort`를 넘기기만 하면 됩니다.

- **정렬 가능한 열.** 렌더된 노드가 아니라 바탕 값으로 정렬. 순서가 의미 없으면
  `sortable: false`.
- **검색, 실시간 일치 수, 한 번에 지우기**(`<TableToolbar>`).
- **URL에 상태.** 검색·정렬·페이지·탭이 쿼리 파라미터라 북마크·공유가 되고, 행을 눌렀다가
  뒤로 가도 복구됩니다.
- **두 가지 빈 상태.** 아직 아무것도 없을 때는 첫 항목을 만드는 액션과 함께 `<EmptyState>`,
  필터가 아무것도 못 찾았을 때는 지우는 길과 함께 `<NoResults>`. 빈 표는 고장 난 화면으로
  읽힙니다.
- **로딩 중 스켈레톤**(`<TableSkeleton>`). 빈 패널도, 맨 스피너도 아님.
- 15행을 넘으면 **고정 헤더**, 25행을 넘으면 **페이지네이션**.
- 다섯 개에 한 번에 할 만한 액션이 있는 곳마다 **행 선택**.
- 표가 "table" 말고 다른 것으로 읽히도록 **캡션**.

## 폼

- **진짜 라벨.** `<Field>`가 `<label for>`, 필수 표시, 힌트, 오류 메시지를 컨트롤에 연결하고
  `aria-describedby` / `aria-invalid` / `aria-required`를 설정합니다. 플레이스홀더는 라벨이
  아닙니다. 타이핑하는 순간 사라집니다.
- **`<form>` 요소**, 그래서 Enter로 제출. 키보드 사용자에게 가장 빠른 길이고 공짜입니다.
- **제출이 아니라 blur에 검증.** 명백히 틀린 이메일이나 수량은 입력한 자리에서, 액션에 확정하기
  전에 표시합니다.
- 받을 수 있는 필드에 **`autocomplete`, `inputmode`, `min`, `max`, `step`**. 비밀번호 관리자가
  동작하고 폰이 맞는 키보드를 띄웁니다.
- **주 버튼이 비활성일 때 이유를 이름 붙여서**(`<DisabledReason>`). 설명 없는 죽은 버튼은 어느
  필드가 문제인지 추측하게 만듭니다.
- **저장 안 된 변경 보호**(`useUnsavedGuard`). 앱 내 이동과 탭 닫기 모두.

## 숫자

모든 숫자 필드는 `min`, `max`, `step`, `inputmode`를 선언하고 떠날 때 범위로 클램프합니다. 속성은
스피너와 브라우저 자체 검증을 묶지만 타이핑·붙여넣기로 범위 밖 값이 들어가는 건 막지 못합니다.
클램프가 없으면 음수 수량이나 엉뚱한 자릿수가 API까지 가서 사용자가 해독해야 하는 422로
돌아옵니다.

## 파괴적 작업

`useConfirm()`이 `window.confirm`을 대체합니다. 후자는 무엇을 잃는지 보여 줄 수 없고, 콘솔의
나머지와 함께 번역할 수 없고, 탭 전체를 막습니다.

- **대상을 이름으로** — "정말요?"가 아니라 "vit-base-ft를 종료할까요?".
- **결과를 나열**: 정산될 크레딧, 볼륨과 함께 사라질 데이터, 고아가 될 세션.
- 되돌릴 수 없는 것에는 **이름 입력 요구**: 조직·클러스터·공유 데이터셋 삭제, 세션 다섯 개 동시
  종료.
- Escape와 오버레이는 취소. 열려 있는 동안 포커스는 갇히고 닫히면 연 컨트롤로 돌아갑니다.
- **되돌릴 수 있는 곳엔 실행 취소.** 예컨대 접근 해제는 즉시 적용되고 토스트가 되돌리는 길을
  들고 있습니다(`pushToast(kind, message, { label, run })`). 확인창보다 낫습니다. 흔한 경우에
  비용이 없기 때문입니다. 입력식 확인은 되돌릴 수 없는 것에만.

## 서버 오류

거부된 저장은 토스트만이 아니라 **폼 위에** 보고합니다. 5초 후 사라지고 어느 필드 때문인지 말하지
않는 메시지는 오류 메시지가 아닙니다. 다음 시도까지, 실패한 액션 옆에 유지하세요.

## 실시간 데이터

- **마지막 조회 시각을 말하고 새로고침을 제공**(`<PageHeader updatedAt onRefresh>`). 없으면
  오래된 데이터와 멈춘 작업을 구분할 수 없습니다.
- **상대 시간 + 호버 시 정확한 값**(`<Timestamp>`): "6시간 전"이 사람들의 질문에 답하고,
  `datetime` 속성과 툴팁이 로그와 대조하게 합니다. 상대 텍스트는 타이머로 다시 렌더되므로
  밤새 열어 둔 탭이 "2분 전 시작"이라고 우기지 않습니다.

## 식별자와 복사

세션·클러스터·디바이스·지갑 식별자는 티켓, `kubectl` 명령, 채팅에 끊임없이 인용됩니다. 모두
보이는 확인이 있는 `<CopyButton>`을 가집니다. 침묵은 두 번 누르게 하고 둘 다 의심하게 합니다.

## 언어

- 영어가 원본이자 대체이고, 한국어는 완전한 번역입니다. 두 번들의 키 일치를 검사합니다.
- 문장을 조각으로 조립하지 않습니다. 플레이스홀더를 쓰고, 문장 일부에 마크업이 필요하면
  `<Trans>`를 써서 어순이 번역 가능하게 둡니다.
- 언어 컨트롤은 로그아웃·오류 화면을 포함한 모든 화면에서 닿습니다.
- 관리자가 입력한 이름은 어느 언어에서든 입력한 그대로 둡니다.

### 한국어 표현

한국어 번들은 문자열 종류마다 한 가지 문체를 따르므로 화면이 어조를 섞지 않습니다.

- **명사구**(동사 어미 없음): 화면 제목·부제, 표 헤더, 필드 라벨, 탭, 버튼, 상태 배지, 필터 이름.
  `노드 비우기`, `예약`, `차단 / 오프라인 노드`.
- **문장**은 무슨 일이 있었는지·무엇을 할지 말하는 곳에 허용: 대화 상자 본문, 오류 메시지,
  토스트, 빈 상태, 필드 힌트. `~합니다` / `~하세요`로 끝나며 `~해요`, `~함`은 쓰지 않습니다.
  확인창 제목은 질문: `{{name}}을(를) 삭제할까요?`.
- 제품명과 단위는 그대로(GPU, VRAM, CUDA, GiB, DCGM, kubeconfig, CSV). 그 밖의 영어 용어는 한국어
  단어 하나로 어디서나 같게:

| 영어(코드 / Kubernetes) | 콘솔의 한국어 |
|---|---|
| cordon / uncordon | 차단 / 차단 해제 |
| drain | 비우기 |
| hold(크레딧 예약) | 예약 |
| operator | 오퍼레이터 |
| super_admin | 시스템 관리자 |
| org_admin | 조직 관리자 |
| group_admin / member / guest | 부서 관리자 / 구성원 / 게스트 |
| group(project) | 부서 |
| organization | 조직 |
| offering / preset / policy | 오퍼링 / 프리셋 / 정책 |
| quota | 쿼터(스토리지) · 한도(정책) |
| session / volume / wallet / credit | 세션 / 볼륨 / 지갑 / 크레딧 |
| pause / terminate / paused | 일시정지 / 종료 / 일시정지됨 |
| exclusive / fractional | 전용 / 공유 |

## 화면 추가하기

`PageHeader` + `Table`/`Field`에서 시작하면 대부분이 공짜로 따라옵니다. 그다음 그 화면을 쓸
페르소나로 감사를 돌리세요.

```bash
UX_PERSONA=researcher node test/e2e/ux/audit.js
```
