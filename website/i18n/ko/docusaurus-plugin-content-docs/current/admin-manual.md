---
sidebar_position: 6
title: 관리자 가이드
---

# 관리자 가이드

**관리자 콘솔**에서는 조직·부서·사용자 관리, 크레딧 배분 및 요청 처리, 세션 모니터링을 수행할 수 있습니다. 플랫폼 관리자는 추가로 GPU 카탈로그, 자원 정책, 클러스터 및 노드, 스토리지, 이미지, 시스템 전반의 설정을 구성할 수 있습니다.

작업 전 [역할과 범위](./admin/roles.md) 안내를 먼저 확인하세요. 관리자 역할별 접근 권한 및 관리 범위에 대해 다룹니다.

## 테넌트 관리

조직 및 부서 관리자를 위한 주요 관리 기능입니다.

- [대시보드](./admin/dashboard.md) — 관리 범위 내 자원 및 세션 현황 모니터링
- [조직](./admin/organizations.md) — 최상위 조직 구조, 관리자 지정 및 예산 관리
- [부서](./admin/groups.md) — 부서(팀) 생성, 구성원 및 부서 관리자 관리
- [사용자](./admin/users.md) — 계정 목록 및 소속별 권한 관리
  - [사용자 추가](./admin/users-add.md) — 개별 생성, CSV 일괄 등록, 가입 승인
  - [계정 관리](./admin/users-manage.md) — 역할 변경, 비밀번호 초기화, 계정 비활성화 및 삭제
- [크레딧](./admin/credits.md) — 크레딧 체계 및 과금 대상
  - [크레딧 배분](./admin/credits-allocate.md) — 크레딧 풀 관리, 하위 배분, 회수, 월간 자동 충전
  - [크레딧 요청 관리](./admin/credits-requests.md) — 요청 승인 체인, 승인 및 반려 처리
  - [정산 리포트](./admin/credits-settlement.md) — 실크레딧 소비량 및 정산 리포트
- [세션 관제](./admin/monitoring.md) — 실시간 세션 모니터링 및 자동 종료 규칙 설정
  - [개입하기](./admin/monitoring-control.md) — 세션 강제 종료, 일괄 정리, 대기열 관리
- [감사 로그](./admin/audit.md) — 시스템 조작 이력 필터링, 데이터 내보내기, 감사를 위한 추적 방법

## 플랫폼 관리

시스템 전체를 관리하는 최고 관리자 전용 기능입니다.

- [자원과 정책](./admin/resources.md) — 자원 카탈로그 및 쿼터 정책 구성
  - [오퍼링](./admin/resources-offerings.md) — GPU 모델, 식별 문자열, 시간당 단가 설정
  - [프리셋](./admin/resources-presets.md) — 컴퓨트 스펙 및 GPU 티어 구성
  - [자원 정책](./admin/resources-policies.md) — 쿼터 한도, 시간 제한, 증액 요청 처리
- [클러스터](./admin/clusters.md) — 클러스터 등록, 세션 도메인 설정, 등록 해제
  - [노드](./admin/nodes.md) — 노드 상태 헬스체크, 스케줄링 차단(Cordon), 노드 비우기(Drain), 삭제
  - [노드 풀](./admin/node-pools.md) — 전용 하드웨어 풀 구성 및 오버플로우 관리
- [GPU 디바이스](./admin/gpus.md) — 디바이스 에일리어스, 결함 카드 관리, 할당량 및 사용률 모니터링
- [스토리지](./admin/storage.md) — 스토리지 풀 관리, 공용 볼륨, 용량 부족 대응
- [이미지](./admin/images.md) — 컨테이너 이미지 가져오기, 빌드, 카탈로그 관리
- [지표](./admin/platform-monitoring.md) — DCGM 및 호스트 인프라 메트릭 모니터링
- [시스템 설정](./admin/system.md) — 브랜딩 설정, 회원가입 정책, GPU 스케줄링 배치 정책

플랫폼 자체의 인프라 설치, 스토리지 구성, 모니터링 구축, 시스템 업그레이드 및 백업에 대한 내용은 **운영** 가이드의 [시작하기](./getting-started.md) 문서를 참고하세요.