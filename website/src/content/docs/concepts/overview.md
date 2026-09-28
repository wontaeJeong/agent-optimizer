---
title: 동작 원리
description: Agent Optimizer의 구성, 실행 순서, 최적화 반복과 팀 컴포넌트의 경계를 한눈에 봅니다.
---

Agent Optimizer는 **Agent를 실행하고, 결과를 채점하고, 허용된 파일을 바꾼 후보를 비교**하는 도구입니다. 아래 그림의 화살표는 정보가 이동하는 방향을 보여 줍니다. 실행 명령은 [합성 첫 실행](/agent-optimizer/getting-started/first-run/)과 [ACE 프리셋](/agent-optimizer/getting-started/presets/)에 있습니다.

## 전체 구조

![원본 Agent에서 스냅샷, Harness 실행, 별도 Evaluator 채점, Trial 기록과 보고서, Optimizer 후보 제안까지의 관계](../../../assets/diagram-architecture.svg)

작은 화면에서는 **그림 안을 좌우로 밀어** 전체 흐름을 읽으세요. 그림 바로 아래에 같은 관계를 글로 설명합니다.

**Agent**는 최적화할 대상, **Harness**는 이를 실행하는 방법, **Dataset**은 사용자가 고른 과제 모음, **Evaluator**(평가기)는 실행 산출물을 별도로 채점하는 컴포넌트입니다. 공개 입력만 Harness로 전달하며 채점 전용 자료는 Agent 실행 공간 밖에 둡니다. 실행·채점을 기록한 Trial에서 Report가 만들어지고, Optimizer는 원본을 고치지 않고 허용된 파일만 바꾼 스냅샷을 제안합니다. [역할별 상세 설명](/agent-optimizer/developer/overview/)도 참고하세요.

## 실험 단계

![설정·준비·정적 진단에서 실행, baseline validation, train 후보 탐색, validation 선택 고정, 선택적 test와 보고서까지 세 구간의 단계](../../../assets/diagram-stages.svg)

**설정·준비:** 사용자가 Agent·Harness·Optimizer·Dataset을 선택합니다. TUI 5번과 선택형 CLI는 같은 네 선택을 `experiment.toml`로 기록합니다. `catalog`는 읽기 전용 설명 조회, `init --yes`와 `prepare`는 고정 자산 다운로드/빌드·검사/재사용이 가능한 준비 단계입니다. `doctor --plan`과 `plan`은 **준비 전에도** 실행할 수 있지만 부족한 자산을 표시할 수 있습니다. 준비 뒤 다시 확인해도 실제 모델 호출이나 채점 성공을 보증하지 않습니다.

**실행·선택:** `run`은 부족한 자산을 자동 설치하지 않습니다. baseline validation을 기록한 다음 train에서 후보를 탐색하고 validation 수치로 선택을 고정합니다. **선택 후:** `final_test`를 켠 경우에만 고정 후보와 baseline의 test를 실행하고 보고서를 생성합니다. 그림이 화면보다 넓으면 그림 영역만 좌우로 밀어 보세요.

## 최적화 반복

![공통 baseline에서 train 평가와 후보 제안을 반복하고 validation 수치로 stage별 승자를 선택하는 순서](../../../assets/diagram-iteration.svg)

각 Optimizer stage는 공통 baseline에서 **독립적으로** 시작합니다. 수정 근거와 이력에는 baseline과 자기 stage의 train 결과만 들어갑니다. 일부 방법은 validation **수치**를 내부 후보 선택에 사용할 수 있지만, 비공개 채점 자료나 test 결과를 수정 근거로 받지 않습니다. [결과 읽기](/agent-optimizer/getting-started/results/)에서 선택된 후보와 실패 근거를 확인하세요.

## 컴포넌트 경계

![팀 코드가 공통 계약과 명시 등록을 통해 Runner에 연결되고 공개 Agent 입력과 채점 공간은 분리되는 경계](../../../assets/diagram-boundaries.svg)

팀 구현은 `experiments/<team>/`에서 관리하고 중앙 `registry.py`에 ID를 등록합니다. Runner가 공통 계약을 통해 컴포넌트를 호출하므로 알고리즘끼리 직접 연결하지 않습니다. 로컬 팀 플러그인에는 자동 OS 격리가 없으므로 신뢰한 코드를 연결합니다. [컴포넌트 연결](/agent-optimizer/developer/components/)에서 실제 파일과 메서드를 확인하세요.
