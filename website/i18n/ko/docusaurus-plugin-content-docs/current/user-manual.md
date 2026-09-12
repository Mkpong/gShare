---
sidebar_position: 5
title: 사용자 가이드
---

# 사용자 가이드

gShare는 단일 또는 다수의 Kubernetes GPU 클러스터를 **공유(fractional)** 또는 **전용(exclusive)** 모드로 효율적으로 분할하여 사용하고, 리소스 사용량을 크레딧 기반으로 정산하는 플랫폼입니다. 본 가이드는 **사용자 콘솔**에서 세션을 실행하고 데이터를 보관하며 크레딧을 관리하는 주요 화면과 기능별 사용 방법을 안내합니다.

- [로그인](./user/signing-in.md) — 최초 로그인, 언어/테마 설정, 대상 클러스터 선택
- [대시보드](./user/dashboard.md) — 잔여 크레딧, 소진율, 자원 할당량, 클러스터 가용성 확인
- [세션](./user/sessions.md) — 세션 개요, 상태값 정의, 세션 목록 화면 안내
  - [세션 생성](./user/sessions-create.md) — 5단계 생성 마법사 항목별 안내
  - [세션 접속](./user/sessions-connect.md) — VS Code(code-server), JupyterLab, 웹 터미널 접속
  - [세션 관리](./user/sessions-manage.md) — 일시정지, 재개, 재시작 및 실시간 사용량 모니터링
  - [대기열 관리](./user/sessions-queue.md) — 세션 대기 상태 원인 분석 및 대처 방법
  - [세션 종료](./user/sessions-end.md) — 세션 종료 절차, 과금 정산 및 데이터 보존 방식
- [데이터 및 볼륨](./user/data.md) — 영구 스토리지 개요: 유효 범위, 스토리지 종류, 볼륨 목록
  - [볼륨 생성](./user/data-create.md) — 공유 범위, 스토리지 종류, 접근 모드, 용량 설정
  - [세션 볼륨 마운트](./user/data-mount.md) — 볼륨 마운트 설정, 경로 지정 및 마운트 상태 확인
  - [볼륨 공유](./user/data-share.md) — 접근 권한 부여, 권한 회수 및 공유 참여 해제
  - [볼륨 관리](./user/data-manage.md) — 용량(쿼터) 변경, 볼륨 잠금 및 안전한 삭제 절차
- [지갑 및 크레딧](./user/wallet.md) — 크레딧 예약, 사용 및 정산 방식 안내
  - [거래 내역](./user/wallet-ledger.md) — 원장(Ledger)에 기록된 모든 크레딧 변동 내역 조회
  - [크레딧 요청](./user/wallet-request.md) — 소속 부서에 크레딧 할당 요청 및 승인 상태 확인
- [계정 관리](./user/account.md) — 사용자 프로필 및 소속 정보 관리
  - [비밀번호 변경](./user/account-password.md) — 최초 로그인 비밀번호 변경 및 비밀번호 초기화
  - [내 리소스 한도](./user/account-limits.md) — 적용 중인 자원 정책 확인 및 한도 증액 요청
  - [알림 센터](./user/account-notifications.md) — 시스템 알림 및 수신 내역 확인

조직, 부서, 사용자 계정, 크레딧 배분, 클러스터 운영 및 시스템 관제 등 관리자 전용 기능은 [관리자 가이드](./admin-manual.md)를 참조하시기 바랍니다.

:::tip GPU 사용 시간에 대해서만 크레딧이 차감됩니다
CPU 전용 세션 및 볼륨 스토리지는 무료로 제공됩니다. GPU 세션이 실행 중인 상태가 아니면 잔여 크레딧은 차감되지 않습니다.
:::