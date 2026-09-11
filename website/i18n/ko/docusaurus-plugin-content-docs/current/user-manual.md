---
sidebar_position: 5
title: 사용자 가이드
---

# 사용자 가이드

gShare는 여러 사람이 하나의 Kubernetes GPU 클러스터를 **공유(fractional)** 또는 **전용(exclusive)**
방식으로 나누어 쓰고, 사용량을 크레딧으로 정산하는 플랫폼입니다. 이 가이드는 **사용자 콘솔** —
세션을 실행하고, 데이터를 보관하고, 크레딧을 관리하는 화면 — 을 하나씩 안내합니다.

- [로그인](./user/signing-in.md) — 첫 로그인, 언어·테마, 클러스터 선택
- [대시보드](./user/dashboard.md) — 잔액, 소진 속도, 할당량, 가용성
- [세션](./user/sessions.md) — 세션이란 무엇인지, 상태, 목록 화면
  - [세션 만들기](./user/sessions-create.md) — 5단계 마법사를 항목별로
  - [접속하기](./user/sessions-connect.md) — VS Code, JupyterLab, 웹 터미널
  - [세션 관리](./user/sessions-manage.md) — 일시정지·재개·재시작, 실시간 사용량
  - [대기열에서 기다리기](./user/sessions-queue.md) — 왜 기다리는지, 무엇을 할지
  - [세션 종료](./user/sessions-end.md) — 종료, 과금, 남는 것
- [데이터와 볼륨](./user/data.md) — 영구 스토리지: 범위, 종류, 목록
  - [볼륨 만들기](./user/data-create.md) — 범위, 종류, 접근 모드, 용량
  - [세션에서 쓰기](./user/data-mount.md) — 마운트, 경로, 지금 누가 쓰는지
  - [볼륨 공유](./user/data-share.md) — 권한 주기, 해제, 공유 나가기
  - [용량 변경·잠금·삭제](./user/data-manage.md) — 쿼터, 잠금, 안전한 삭제
- [지갑과 크레딧](./user/wallet.md) — 예약·사용·정산으로 이어지는 과금 방식
  - [거래 내역](./user/wallet-ledger.md) — 원장에 남는 모든 이동
  - [크레딧 요청](./user/wallet-request.md) — 부서에 요청하고 진행 확인하기
- [계정](./user/account.md) — 프로필과 소속
  - [비밀번호](./user/account-password.md) — 변경, 첫 로그인, 초기화
  - [내 한도](./user/account-limits.md) — 자원 정책과 증액 요청
  - [알림](./user/account-notifications.md) — 종 아이콘과 내역

조직·부서·사용자·크레딧·클러스터·관제 등 관리 기능은 [관리자 가이드](./admin-manual.md)에 있습니다.

:::tip GPU 시간만 크레딧을 씁니다
CPU 세션과 볼륨은 무료입니다. GPU 세션이 실행 중이 아닐 때 잔액은 절대 줄지 않습니다.
:::
