---
sidebar_position: 12
title: 이미지
---

# 이미지와 템플릿

![이미지](/img/screens/admin-images.png)

이미지 카탈로그는 세션 마법사가 제안하는 목록입니다. 각 이미지는 이름, 레지스트리 참조, 빌드된
**CUDA 버전**, 공개 여부(또는 특정 부서 제한)를 가집니다. 마법사는 선택한 GPU가 지원하는 CUDA
버전의 이미지만 제안합니다.

## 가져오기

**가져오기**는 기존 이미지를 참조(예: `boanlab/gshare-session:ml-cuda12.8-cudnn9`)와 CUDA 버전으로
등록합니다. 사설 레지스트리의 이미지는 노드가 그 레지스트리를 신뢰해야 합니다
([클러스터 구축 → 로컬 레지스트리](../cluster-setup.md#local-registry-optional) 참고).

## 빌드

**빌드**는 Dockerfile로 콘솔 주도 이미지 빌드를 시작해 `api.buildRegistry`로 설정한 레지스트리에
푸시합니다. 빌드 로그가 페이지로 스트리밍되고, 결과 이미지는 자동 등록됩니다.

## 시드 이미지

`api.seedSessionImages: true`(기본값)이면 시작 시 CUDA 12.4/12.5 계열과 Blackwell 12.8/12.9 계열의
`boanlab/gshare-session` 이미지를 카탈로그에 시드합니다. 사설 레지스트리로 세션 이미지를
제공하는 사이트는 `false`로 두고 직접 가져옵니다.
