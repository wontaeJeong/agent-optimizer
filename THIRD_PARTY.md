# External references

이 저장소에는 ACE-RTL/CVDP/Verilog-Eval의 전체 소스·데이터셋·시뮬레이터 바이너리를 포함하지 않습니다.
setup에서 공식 repo를 내려받으며 각 프로젝트의 LICENSE/데이터 사용 조건을 유지해야 합니다.
이 문서는 라이선스 검토를 대체하지 않습니다.
각 출처가 뒷받침하는 판단, 로컬 소비 파일, 확인 여부와 버전 변경 점검은 [docs/SOURCES.md](docs/SOURCES.md)에 기록합니다.

- ACE-RTL: https://github.com/NVlabs/ACE-RTL/tree/fead921f18bb57345b5a41ef93ba625be208e99c
- CVDP: https://github.com/NVlabs/cvdp_benchmark/tree/8e894cf74414ab1eaea1e2b4e80a02f123df07b6
- CVDP Dockerfile: https://github.com/NVlabs/cvdp_benchmark/blob/8e894cf74414ab1eaea1e2b4e80a02f123df07b6/docker/Dockerfile.sim
- OpenCode CLI: https://opencode.ai/docs/cli/
- CVDP dataset/license/notice: https://huggingface.co/datasets/nvidia/cvdp-benchmark-dataset/tree/5b807d945f6a99aa645f7e43a64a2115e281b4bf
- Verilog-Eval v2 (MIT): https://github.com/NVlabs/verilog-eval/tree/c498220d0a52248f8e3fdffe279075215bde2da6
- Icarus Verilog v12 소스 (GPL-2.0 또는 이후 버전; 빌드한 Docker 이미지와 소스는 Git 제외): https://github.com/steveicarus/iverilog/tree/4fd5291632232fbe1ba49b2c26bb6b2bf1c6c9cf
- GEPA 방법 참고: https://github.com/gepa-ai/gepa/tree/d771eb21b5dd3228bc3f567293d2ccfc423fc900
- Meta-Harness 방법 참고: https://github.com/stanford-iris-lab/meta-harness/tree/0cbc31e97c9e6d24232d1dc754827c02e1ec415c
- Ecdysis 방법 참고: https://github.com/cuiyu-ai/Ecdysis/tree/ec3105de6fb1017e79c9f113da8459fec6cf9b04

고정 데이터의 LICENSE는 non-code에 CC BY 4.0, original code에 Apache-2.0을 기재하며
NOTICE에 개별 파생 소스의 별도 조건을 기록합니다. `no_commercial`은 상용 EDA 의존성 구분이며
데이터 전체에 대한 단일 라이선스 선언이 아닙니다. setup은 LICENSE/NOTICE를 원본 그대로
`external/cvdp-data/<revision>/`에 보존합니다. 과제 변환은 정답을 제거하고 평가 입력을 분리합니다.

세 알고리즘은 위 연구의 공개 메서드를 참고한 자체 구현이며 upstream 전체 소스를 vendoring하지 않습니다.
알고리즘 이름은 공식 구현·논문 성능 재현의 증거가 아닙니다. `.references/`의 로컬 참고 checkout은
런타임 입력이나 Git 배포 자산이 아닙니다.
