# 프록시·CA·NO_PROXY 설정

호스트의 시스템 CA와 Docker 데몬 연결 설정은 준비되어 있다고 가정합니다.
이 기능은 프로젝트 명령, 이미지 내부 설치, Agent 실행, 지원하는 CVDP 평가 컨테이너에
네트워크 설정을 전달합니다. 호스트·데몬 설정을 변경하지 않습니다.

## 한 번 설정해서 사용

필요한 값만 셸에 export하세요. `.env`는 자동으로 읽지 않습니다.
실제 주소·인증정보·CA 파일은 Git에 넣지 않습니다.

```bash
export HTTP_PROXY=http://proxy.example:3128
export HTTPS_PROXY=http://proxy.example:3128
export NO_PROXY=localhost,127.0.0.1,::1,.example.internal
export AGENT_OPT_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

python3 scripts/network.py -- uv sync --frozen --extra dev
python3 scripts/dev.py setup
python3 scripts/dev.py smoke
```

`AGENT_OPT_CA_BUNDLE`은 **공개 루트와 필요한 추가 CA를 포함한 전체 PEM 신뢰 번들**입니다.
Ubuntu에서 추가 CA가 이미 설치됐다면 위 시스템 번들을 사용합니다. `scripts/dev.py`는 Linux에서
이 파일이 있으면 자동 선택하며 명시적 `AGENT_OPT_CA_BUNDLE`이 우선합니다.
자동 선택을 끄려면 `AGENT_OPT_CA_BUNDLE=''`를 export하세요. 코어 CLI와 network wrapper는 명시적 설정을 따릅니다.
단일 추가 CA만 지정하면 번들을 사용하는 클라이언트는 공개 사이트를 신뢰하지 못할 수 있습니다.
파일 부재·잘못된 PEM·개인키 포함은 명시적 오류입니다. TLS 검증은 끄지 않습니다.

프록시 없이 추가 CA만, 추가 CA 없이 프록시만 사용하는 것도 가능합니다.
직접 연결 환경에서는 proxy 변수를 생략합니다. Ubuntu 데모 명령은 시스템 CA를 계속 활용합니다.
이미 설정된 값을 없애려면 대문자·소문자를 모두 unset하세요.

```bash
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY http_proxy https_proxy all_proxy no_proxy
unset AGENT_OPT_CA_BUNDLE
```

## 전달 규칙

| 설정 | 동작 |
|---|---|
| `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY` | 소문자도 지원. 둘 다 있으면 **소문자 우선**, 빈 값도 유지. 정규화한 값을 양쪽 이름으로 전달. |
| `NO_PROXY` | 문자열을 그대로 전달. 로컬 OpenCode 연결을 위해 `localhost,127.0.0.1,::1`을 포함하고, 직접 연결할 모델/API 호스트를 추가. |
| `AGENT_OPT_CA_BUNDLE` | `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE`, `GIT_SSL_CAINFO`, `PIP_CERT`, `NODE_EXTRA_CA_CERTS`, `npm_config_cafile`로 연결. 명시한 프로젝트 번들이 이 도구별 변수보다 우선. |
| 도구별 CA 변수만 설정 | 호스트에서는 기존 값을 유지. 컨테이너에 호스트 경로를 자동 전달하지 않으므로 컨테이너 지원에는 프로젝트 번들을 사용. |

`NO_PROXY`의 도메인 suffix·포트·CIDR, `ALL_PROXY` 및 인증 방식 지원은 각 도구의 해석을 따릅니다.
일반 HTTP(S) 프록시를 기준으로 사용하고, 모든 도구가 같은 CIDR/NTLM/Kerberos 동작을 한다고
가정하지 마세요. HTTP CONNECT 프록시도 보통 `HTTPS_PROXY=http://...` 형태입니다.

## 적용 경로

- **부트스트랩:** repo clone 이전에는 셸의 프록시와 Git의 `GIT_SSL_CAINFO`를 직접 설정합니다.
  uv 설치 전 다운로드 도구에도 해당 CA를 설정하세요. clone 후에는
  `python3 scripts/network.py -- <명령과 인자>`로 uv·pip·Git 등을 실행할 수 있습니다.
- **프로젝트 CLI:** `agent-opt`/`python -m agent_optimizer`는 in-process 플러그인에 전달할 환경을
  먼저 설정합니다. 코어 Git 소스 확보와 local/Docker 실행도 같은 계약을 적용합니다.
  Python 라이브러리로 직접 호출하는 사용자 프로그램은 wrapper로 시작하거나
  `host_environment()`가 반환한 환경을 직접 적용해야 합니다.
- **개발 setup:** uv 프로젝트/driver 설치, 고정 Git checkout, HTTPS 데이터 다운로드와
  두 이미지 빌드에 적용합니다. CA hash는 환경 lock에 기록하며 proxy 값은 기록하지 않습니다.
- **이미지 빌드:** CA를 첫 RUN 이전에 추가하여 npm·apt·Git·curl·uv의 설치 요청부터 적용합니다.
  임시 Dockerfile과 CA 전용 named context를 사용하며 원본 Dockerfile·upstream checkout은 수정하지 않습니다.
  프록시는 이름만 `--build-arg`로 전달하고 이미지 `ENV`에 저장하지 않습니다.
  **CA는 이미지에 포함됩니다.** CA 포함 빌드는 BuildKit named context를 지원하는
  Docker/Buildx가 필요합니다(`docker buildx version`으로 확인).
- **Agent/평가 실행:** proxy를 이름으로 전달하고 CA를 `/opt/agent-optimizer/ca-bundle.pem`과
  Debian/Ubuntu 시스템 bundle 경로에 읽기 전용 mount합니다. 설정한 `network=none`은 그대로 유지합니다.
- **CVDP 하위 Compose:** 별도 driver가 실행용 private submission 사본의 환경·CA mount·build args만
  추가합니다. 채점 코드·원본 과제는 유지하고 모델 자격증명은 계속 제외합니다.
  지원하는 중첩 Dockerfile은 준비된 평가 이미지를 alias하는 형태이며 빌드 CA를 상속합니다.

Docker 런타임 mount는 **데몬에서 접근 가능한 동일 경로**여야 합니다. 로컬 Ubuntu에서는
일반 파일 경로를, Docker Desktop/Colima에서는 공유된 경로를 사용하세요.
원격 Docker 호스트로 CA 파일을 자동 전송하지 않습니다. 컨테이너 사용자가 파일을 읽을 수 있어야 합니다.

## 직접 이미지 빌드

```bash
python3 scripts/network.py -- docker build \
  -f examples/rtl-debugger/Dockerfile \
  -t agent-optimizer-opencode:local examples/rtl-debugger
```

CA 어댑터는 현재 제공하는 **단일 stage·단일 행 FROM·로컬 Dockerfile**을 대상으로 합니다.
다단계/원격/표준입력 Dockerfile은 별도 연결이 필요합니다. 직접 `docker build`만 실행하면
이 프로젝트의 CA 추가 처리가 적용되지 않습니다. 별도 BuildKit 데몬의 registry 연결 설정도
운영자가 준비해야 합니다.

## 갱신과 재사용

- CA 번들이 바뀌면 online `setup`으로 이미지와 lock을 갱신합니다. `setup --offline`은 이전 CA hash와
  다른 설정을 거부합니다. 프록시 주소 변경은 CA/image identity 변경으로 취급하지 않습니다.
- CA를 교체하면 `setup`을 다시 실행하세요. demo의 doctor/smoke/live도 준비 시점의 CA hash를 대조합니다.
  `python3 scripts/dev.py doctor --model`은 호스트와 Agent 컨테이너의 실제 모델/도구 호출을 확인합니다.
  일반 doctor는 모델 호출을 하지 않습니다.
- 기본 이미지 ENV/기존 Docker client 설정은 미설정 시 그대로 유지됩니다. 빌드에 사용한 도구가
  자신의 설정이나 로그에 환경값을 출력하지 않도록 하세요. 실행 중 proxy 환경은 Docker 권한을
  가진 사용자가 조회할 수 있습니다.

검증 명령·실제 수행 범위는 [verification.md](verification.md#2026-09-21-optional-network-environment)를 참고하세요.

### 실패 위치별 확인

- 이미지 `FROM`/pull 실패: Docker daemon 또는 별도 BuildKit daemon의 proxy/registry CA를 확인합니다.
- `RUN apt/npm/uv` 실패: 셸 proxy 변수와 전체 CA bundle, `docker buildx version`을 확인합니다.
- 호스트 모델만 성공: 컨테이너의 NO_PROXY, CA readonly mount 접근 권한, 모델 주소의 네트워크 도달성을 확인합니다.
- `localhost` 모델 주소: Docker 안에서는 컨테이너 자신을 뜻합니다. 서버에서 도달 가능한 실제 모델 주소를 사용하세요.
