# OSS 환경

`../setup.sh`가 이 디렉터리의 setup.py를 실행합니다. 공식 CVDP Dockerfile.sim만 재사용합니다.
`external/environment-lock.json`에 repo SHA, 이미지 ID, Python 패키지 목록을 남깁니다.
OpenCode 이미지는 별도 빌드하며 정확한 버전을 OPENCODE_VERSION build arg로 전달하세요.
Docker image tag는 변경 가능하므로 재현 실험에서는 image digest/ID를 harness 설정에 사용하는 것이 좋습니다.
프록시/사내 CA가 필요한 경우 개발 서버의 Git/pip/Docker 설정에 반영하세요. 인증정보는 커밋하지 않습니다.
