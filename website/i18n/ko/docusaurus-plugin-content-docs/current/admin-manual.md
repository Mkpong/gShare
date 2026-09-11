---
sidebar_position: 6
title: 관리자 가이드
---

# 관리자 가이드

**관리자 콘솔**에서는 조직·부서·사용자를 관리하고, 크레딧을 배분하고 요청을 처리하고, 세션을
관제하며 — 플랫폼 관리자라면 — GPU 카탈로그, 정책, 클러스터, 노드, 스토리지, 이미지, 시스템 설정을
구성합니다.

먼저 [역할과 범위](./admin/roles.md)를 읽어 보세요. 각 관리자 역할이 무엇을 보는지가 이후 모든
페이지의 열쇠입니다.

## 테넌트 관리

조직·부서 관리자의 일상입니다.

- [대시보드](./admin/dashboard.md) — 내 범위에서 무엇이 돌고 있는지
- [조직](./admin/organizations.md) — 트리의 꼭대기, 관리자와 예산
- [부서](./admin/groups.md) — 팀, 구성원, 부서 관리자
- [사용자](./admin/users.md) — 계정 목록과 소속이 정하는 것
  - [사용자 추가](./admin/users-add.md) — 한 명씩, CSV 일괄, 가입 승인
  - [계정 관리](./admin/users-manage.md) — 역할, 비밀번호 초기화, 비활성화, 삭제
- [크레딧](./admin/credits.md) — 계층과 과금 대상
  - [크레딧 배분](./admin/credits-allocate.md) — 풀, 내려주기, 회수, 월 리필
  - [크레딧 요청 관리](./admin/credits-requests.md) — 요청 체인, 승인과 반려
  - [정산 리포트](./admin/credits-settlement.md) — 실제로 소비된 양
- [세션 관제](./admin/monitoring.md) — 실시간 화면과 스스로 끝나는 규칙
  - [개입하기](./admin/monitoring-control.md) — 강제 종료, 일괄 정리, 대기열
- [감사 로그](./admin/audit.md) — 필터, 내보내기, 통하는 조사 방법

## 플랫폼 관리

시스템 관리자 전용입니다.

- [자원과 정책](./admin/resources.md) — 카탈로그와 쿼터의 구분
  - [오퍼링](./admin/resources-offerings.md) — GPU 모델, 모델 문자열, 단가
  - [프리셋](./admin/resources-presets.md) — 컴퓨트 형태와 GPU 티어
  - [자원 정책](./admin/resources-policies.md) — 쿼터, 시간 제한, 증액 요청
- [클러스터](./admin/clusters.md) — 등록, 세션 도메인, 등록 해제
  - [노드](./admin/nodes.md) — 생존 판정, 차단, 비우기, 삭제
  - [노드 풀](./admin/node-pools.md) — 전용 하드웨어와 넘침 문제
- [GPU 디바이스](./admin/gpus.md) — 별칭, 장애 카드, 할당과 사용률
- [스토리지](./admin/storage.md) — 풀, 전체 볼륨, 공간 부족 대응
- [이미지](./admin/images.md) — 가져오기, 빌드, 카탈로그 관리
- [지표](./admin/platform-monitoring.md) — DCGM·호스트 지표가 알려 주는 것
- [시스템 설정](./admin/system.md) — 브랜딩, 가입 정책, GPU 배치

플랫폼 자체의 설치·스토리지·모니터링·업그레이드·백업은 **운영** 탭의
[시작하기](./getting-started.md)부터 다룹니다.
