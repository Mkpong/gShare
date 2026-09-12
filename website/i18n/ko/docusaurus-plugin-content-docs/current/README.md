---
sidebar_position: 0
slug: /
title: 개요
---
# gShare 문서

gShare는 여러 조직, 부서, 사용자가 단일 또는 다수의 Kubernetes GPU 클러스터를 **공유(fractional)** 또는 **전용(exclusive)** 모드로 효율적으로 분할하여 사용하고, 사용한 리소스만큼 **크레딧** 기반으로 정산하는 GPU 오케스트레이션 플랫폼입니다.

## 문서 시작 가이드

| 사용자 역할 / 목적 | 추천 읽기 순서 |
|---|---|
| 프로젝트가 처음인 경우 | [아키텍처 및 핵심 개념](architecture.md) → [시작하기](getting-started.md) |
| GPU 세션을 실행하는 일반 사용자 | [사용자 가이드](user-manual.md) |
| 조직 및 자원을 관리하는 운영 관리자 | [관리자 가이드](admin-manual.md) |
| GPU 클러스터에 시스템을 배포하는 운영자 | [시작하기](getting-started.md) → [클러스터 구축](cluster-setup.md) → [클러스터 연동](cluster-connect.md) |
| 추가 GPU 클러스터를 확장 연동하는 운영자 | [멀티 클러스터](multi-cluster.md) |
| 프로젝트 소스 코드에 기여하는 개발자 | [기여 가이드](../CONTRIBUTING.md) → 구성 요소별 README |
| 콘솔 UI 화면을 신규 개발/수정하는 개발자 | [콘솔 UX 표준](console-ux.md) → [페르소나 기반 감사](../test/e2e/ux/README.md) |

## 전체 문서 목록

### 시스템 이해하기

- [**아키텍처 및 핵심 개념**](architecture.md) — 핵심 구성 요소, 데이터 흐름, 시스템에서 사용하는 주요 용어(오퍼링, 프리셋, 세션, 점유율, 크레딧, 정책, 일시 중지 등)를 안내합니다. **가장 먼저 읽으시는 것을 권장합니다.**

### 콘솔 사용하기

- [**사용자 가이드**](user-manual.md) — 로그인, 대시보드 활용, 세션 생성 및 관리, 지갑/크레딧 확인, 볼륨 설정, 사용자 계정 관리를 안내합니다.
- [**관리자 가이드**](admin-manual.md) — 조직/부서/사용자 관리, 자원 카탈로그 및 정책 설정, 크레딧 배분, 클러스터 및 노드 관리, 세션 관제, 감사 로그 조회를 다룹니다.

### 배포 및 운영

- [**시작하기**](getting-started.md) — 저장소 클론부터 시스템 실행까지 전체 절차를 안내합니다 (로컬 둘러보기 및 실제 배포 환경 포함).
- [클러스터 구축](cluster-setup.md) — `kubeadm` 및 HAMi 기반으로 사전 요구 사항인 GPU Kubernetes 클러스터를 처음부터 구축하는 절차를 다룹니다.
- [클러스터 연동](cluster-connect.md) — 제어 플레인에 대상 클러스터를 등록하고 오퍼레이터를 연동하는 방법을 설명합니다.
- [멀티 클러스터](multi-cluster.md) — 단일 제어 플레인에 다수의 GPU 클러스터를 추가 연동하는 방법, 사전 조건, `hack/attach-cluster.sh` 스크립트 활용, 정상 동작 검증 및 토큰 로테이션 절차를 다룹니다.

### 개발 및 설계

- [기여 가이드](../CONTRIBUTING.md) — 개발 환경 설정, 테스트 실행, Pull Request(PR) 작성 및 기여 절차를 안내합니다.
- **주요 구성 요소**: [`backend/`](../backend/README.md) (제어 플레인) · [`operator/`](../operator/README.md) (실행 플레인) · [`frontend/`](../frontend/README.md) (콘솔 UI)
- [콘솔 UX 표준](console-ux.md) — 모든 콘솔 화면이 준수해야 하는 UX 표준 규격과 공용 컴포넌트 목록을 설명합니다. 해당 규격은 제어 플레인 기반의 [페르소나 감사](../test/e2e/ux/README.md)를 통해 자동으로 검증됩니다.

> **참고**: 시스템의 최신 동작 기준은 저장소 루트의 [`README.md`](../README.md) 및 소스 코드입니다. 본 문서군은 플랫폼 학습, 이용, 운영 과정을 보조하기 위해 제공됩니다.