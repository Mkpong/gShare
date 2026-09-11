---
sidebar_position: 0
slug: /
title: 개요
---
# gShare 문서

gShare는 여러 조직·부서·사용자가 하나의 Kubernetes GPU 클러스터를 **공유(fractional)** 또는
**전용(exclusive)** 모드로 나누어 쓰고, 사용한 만큼을 **크레딧**으로 정산하는 플랫폼입니다.

## 어디서 시작할까

| 당신이… | 이 순서로 읽으세요 |
|---|---|
| 프로젝트가 처음이라면 | [아키텍처와 개념](architecture.md) → [시작하기](getting-started.md) |
| 세션을 실행할 사용자라면 | [사용자 가이드](user-manual.md) |
| 조직과 자원을 관리하는 관리자라면 | [관리자 가이드](admin-manual.md) |
| GPU 클러스터에 배포할 운영자라면 | [시작하기](getting-started.md) → [클러스터 구축](cluster-setup.md) → [클러스터 연결](cluster-connect.md) |
| 두 번째 GPU 클러스터를 붙일 운영자라면 | [멀티 클러스터](multi-cluster.md) |
| 코드에 기여할 개발자라면 | [기여 가이드](../CONTRIBUTING.md) → 각 구성 요소의 README |
| 콘솔 화면을 추가·수정할 개발자라면 | [콘솔 UX 표준](console-ux.md) → [페르소나 감사](../test/e2e/ux/README.md) |

## 전체 문서

### 시스템 이해하기

- [**아키텍처와 개념**](architecture.md) — 구성 요소, 데이터 흐름, 그리고 이후 문서가 전제하는
  용어: 오퍼링, 프리셋, 세션, 점유율, 크레딧, 정책, 일시정지. **먼저 읽으세요.**

### 콘솔 사용하기

- [**사용자 가이드**](user-manual.md) — 로그인, 대시보드, 세션, 지갑, 볼륨, 계정 설정을 화면별로.
- [**관리자 가이드**](admin-manual.md) — 조직, 부서, 사용자, 자원 카탈로그와 정책, 크레딧 배분,
  클러스터와 노드, 세션 관제, 감사.

### 배포와 운영

- [**시작하기**](getting-started.md) — 새 클론에서 동작하는 플랫폼까지. 로컬 둘러보기와 실제 배포
  모두.
- [클러스터 구축](cluster-setup.md) — kubeadm과 HAMi로 전제 GPU Kubernetes 클러스터를 처음부터
  만들기.
- [클러스터 연결](cluster-connect.md) — 제어 플레인에 클러스터를 등록하고 오퍼레이터를 붙이기.
- [멀티 클러스터](multi-cluster.md) — 제어 플레인 하나에 GPU 클러스터를 더 붙이기: 전제 조건,
  `hack/attach-cluster.sh`, 검증, 토큰 회전.

### 개발과 설계

- [기여 가이드](../CONTRIBUTING.md) — 환경, 테스트, 풀 리퀘스트 절차.
- 구성 요소: [`backend/`](../backend/README.md)(제어 플레인) ·
  [`operator/`](../operator/README.md)(실행 플레인) · [`frontend/`](../frontend/README.md)(콘솔).
- [콘솔 UX 표준](console-ux.md) — 모든 화면이 사용자에게 지켜야 할 것과, 그것을 제공하는 공용
  컴포넌트. 제어 플레인만으로 도는 [페르소나 감사](../test/e2e/ux/README.md)가 검사합니다.

> 현재 동작의 기준은 루트 [`README.md`](../README.md)와 코드입니다. 이 문서들은 그 위에서 플랫폼을
> 배우고, 쓰고, 운영하도록 돕습니다.
