# OSS 환경

`../setup.sh`는 `scripts/dev.py setup`으로 이어지고, 예제의 `lifecycle.py`가 이 디렉터리의
`setup.py`에서 고정 소스·데이터·driver·평가 이미지와 별도 OpenCode 이미지를 준비합니다.
평가 이미지는 공식 CVDP Dockerfile.sim을 변경 없이 재사용합니다.
`external/environment-lock.json`에 repo SHA, 이미지 ID, Python 패키지 목록을 남깁니다.
OpenCode 이미지는 별도 빌드하며 `setup.py`가 고정된 `OPENCODE_VERSION`을 build arg로 전달합니다.
Docker image tag는 변경 가능하므로 실행 전에 lock의 tag와 로컬 ID/platform을 검사하고,
Docker run에는 검증된 ID를, 공식 driver의 Dockerfile FROM에는 검증된 로컬 tag를 사용합니다.
프록시/사내 CA가 필요하면 [네트워크 안내](../../../docs/network.md)에 따라 설정하세요. 인증정보는 커밋하지 않습니다.
