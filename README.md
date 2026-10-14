# WiaVoice

한국어·영어 음성을 생성하고, 저장·병합·공유하는 데스크톱 웹 서비스입니다. React 프론트엔드와 Python FastAPI 백엔드로 구성되며, AX for Works 플랫폼의 로그인과 세션을 공유합니다.

> GitHub 저장소 이름은 `stt_agent`이지만, 이 저장소의 서비스는 음성 합성(TTS) 서비스 **WiaVoice**입니다.

- 서비스 소개: https://axforwork.wia.co.kr/wiavoice/
- 서비스 실행: https://axforwork.wia.co.kr/wiavoice/agent
- 모바일 전용 UI는 제공하지 않습니다.

## 주요 기능

| 메뉴 | 기능 |
| --- | --- |
| Voice 생성 | 문장 입력, 모델·목소리·감정 선택, 조합별 샘플 듣기, WAV 다운로드 |
| My Voice | 이름을 지정해 저장, 검색·재생·다운로드·삭제, 페이지당 6개 표시 |
| Voice 병합 | 저장 음성 2~20개 순서 지정, 구간별 0~30초 공백 설정, 결과를 My Voice에 저장 |
| Market Place | Custom Voice 등록·공유·다운로드, 즐겨찾기, 내 등록 필터, 인기순·최신순, 페이지당 8개 표시 |
| 관리자 | 운영 통계, 생성·저장·병합 기록, 마켓플레이스 관리 |

마켓플레이스 등록 시 참조 음성으로 Higgs V3 중립 샘플을 생성합니다. 이름·성별·소개를 입력하고 음성 공유 동의 서약을 확인한 뒤 등록합니다.

생성 기록 상세에는 입력 멘트를 표시합니다. 관리자의 음성 재생은 관리 이력으로 기록하지 않으며, 마켓플레이스 수정·공개 중지·재공개·삭제는 사유와 함께 기록합니다.

## 지원 모델

아래는 모델 전체 기능이 아닌 **현재 WiaVoice에 노출된 옵션**입니다.

| 항목 | Qwen3 | Higgs V3 | Fish S2 Pro |
| --- | --- | --- | --- |
| 기본 목소리 | 9종 | 9종의 참조 음성 | 9종의 참조 음성 |
| Custom Voice 업로드 | 미지원 | 지원 | 지원 |
| 감정·말투 선택 | 중립 포함 11종 | 중립 포함 22종 | 중립 포함 12종 |
| 추가 지시 프롬프트 | 지원 | 미지원 | 지원 |
| 별도 조절 UI | — | 속도·음높이·표현 강도·발성 스타일 | — |
| 언어 처리 | Auto | 입력 문장에 따라 처리 | 입력 문장에 따라 처리 |

Higgs와 Fish의 기본 목소리는 Qwen으로 미리 생성한 샘플을 참조합니다. 같은 이름의 목소리도 모델에 따라 다르게 들릴 수 있습니다. Qwen과 Fish의 감정 선택지는 추천 프리셋이며 모델의 표현 범위 전체를 의미하지 않습니다.

- 입력 문장: 최대 500자. 한국어와 영어를 함께 입력할 수 있습니다.
- 참조 음성: WAV, MP3, FLAC, OGG / 3~30초 / 최대 20MB.
- 참조 음성 대본은 사용자가 입력하지 않습니다.
- 고유명사의 발음을 지정하려면 입력 문장에 원하는 발음으로 적습니다.

모델 가중치와 추론 런타임은 이 저장소에 포함하지 않습니다. 각 모델의 사용 조건은 해당 모델 라이선스를 별도로 확인해야 합니다.

## 구성

```text
AX for Works 게이트웨이
  └─ /wiavoice → Node 정적 서버 :1005
       ├─ React 빌드 파일
       └─ /api → FastAPI 127.0.0.1:1015
                    ├─ PostgreSQL: platform / wiavoice 스키마
                    ├─ /data/wiavoice: 음성 및 작업 데이터
                    └─ 모델 프로세스: Qwen 18180 / Fish 18181 / Higgs 18182
```

운영 환경은 H200 GPU를 사용하며 프론트 포트 `1005`는 외부 포트 `31025`에 매핑되어 있습니다. 모델은 한 번에 하나만 실행하며, 전환 시 기존 모델을 종료합니다. 10분 동안 사용하지 않은 모델은 메모리에서 내립니다.

```text
backend/             FastAPI, 인증, 생성·병합·저장·관리 API
backend/sql/         PostgreSQL 테이블 마이그레이션
frontend/src/        React 화면 및 스타일
frontend/public/     폰트·아이콘 등 정적 자원
frontend/server.mjs  정적 파일 제공 및 API 프록시
ops/                 마이그레이션, 샘플 생성, 운영 실행 스크립트
tests/               Python 및 Playwright 검증
OPERATIONS.txt       기존 운영 기록 및 세부 구현 메모
```

## 설치 전제

- 운영에서 사용하는 Python 3.12, Node.js 24 환경
- AX for Works의 `platform.users`, `platform.sessions` 등 기존 플랫폼 DB 구조
- 쓰기 가능한 `/data/wiavoice`와 미리 생성한 `wiavoice` DB 스키마
- 별도 설치된 모델 가중치 및 SGLang Omni 기반 추론 환경
- `WIATTS_ROOT/launch_model.sh`: `qwen`, `fish`, `higgs` 인수를 받아 해당 모델 서버를 실행하는 스크립트

독립 로그인 서버나 모델 다운로드·추론 환경 전체를 구성하는 저장소는 아닙니다. `requirements.txt`는 웹 백엔드 의존성이며 GPU 추론 의존성은 별도로 준비해야 합니다.

## 설치 및 실행

```bash
git clone https://github.com/ollehJW/stt_agent.git wiavoice
cd wiavoice

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
npm ci --prefix frontend
```

기존 개발 서버에서는 `/home/jongwook/wiatts/.venv`의 공유 추론 환경을 사용합니다. `ops/backend.sh`는 이 서버의 경로에 맞춰져 있으므로 다른 환경에서는 아래 직접 실행 명령을 사용하거나 경로를 수정합니다.

### 환경변수

DB 설정은 기본적으로 `/data/wiavoice/auth.env`에서 읽습니다. 실제 비밀번호나 인증 토큰은 Git에 저장하지 않습니다.

```dotenv
AX_DB_HOST=127.0.0.1
AX_DB_PORT=5432
AX_DB_NAME=wia_platform
AX_DB_USER=wia_platform_admin
AX_DB_PASSWORD=REPLACE_WITH_LOCAL_SECRET
```

| 변수 | 기본값 / 용도 |
| --- | --- |
| `WIAVOICE_AUTH_ENV` | `/data/wiavoice/auth.env`: DB 환경변수 파일 |
| `WIAVOICE_DATA` | `/data/wiavoice`: 서비스 데이터 경로 |
| `WIATTS_ROOT` | `/home/jongwook/wiatts`: 추론 실행 스크립트 경로 |
| `FRONTEND_PORT` | `1005`: Node 정적 서버 포트 |
| `BACKEND_ORIGIN` | `http://127.0.0.1:1015`: 프록시 대상, 로컬 HTTP만 허용 |

플랫폼 주소·쿠키·CSRF 정책은 `backend/auth.py`에 정의되어 있습니다. 다른 도메인으로 옮길 때에는 해당 설정과 게이트웨이, 로그인 복귀 경로를 함께 확인합니다.

### DB 마이그레이션

플랫폼 DB와 `wiavoice` 스키마가 준비된 상태에서 다음 순서로 실행합니다. 애플리케이션 시작 시 테이블을 자동 생성하지 않습니다.

```bash
python ops/migrate_voices.py
python ops/migrate_merge.py
python ops/migrate_marketplace.py
python ops/migrate_admin.py
python ops/migrate_generation_text.py
```

마지막 스크립트는 입력 멘트 컬럼을 준비하고, 기존 My Voice 또는 기본 데이터 경로에 남아 있는 세션에서 복구 가능한 원문을 채웁니다.

### 백엔드와 프론트엔드

각 명령은 별도 터미널에서 실행합니다.

```bash
# 백엔드: 단일 프로세스로 실행
python -m uvicorn backend.main:app --host 127.0.0.1 --port 1015 --no-proxy-headers
```

```bash
# 프론트엔드: 빌드 후 정적 서버 실행
npm run build --prefix frontend
npm run serve --prefix frontend
```

프론트 개발 시에는 `npm run dev --prefix frontend`를 사용할 수 있습니다. 로그인 기능은 플랫폼의 공통 세션·도메인 구성을 필요로 합니다.

기본 목소리와 조합별 미리듣기는 별도 준비가 필요합니다. 추론 환경을 설치한 뒤 `ops/seed_voices.py`, `ops/seed_previews.py`를 순서대로 실행합니다. 이 스크립트는 운영 데이터 경로와 모델 포트를 사용하므로 서비스의 음성 생성 작업과 겹치지 않게 실행합니다.

소개 영상·PDF 경로는 `frontend/src/introContent.js`에서 설정합니다. 운영 서버의 `frontend/public/media`는 `/data/wiavoice/media`를 가리키며 Git에서 제외됩니다. 새 설치에서는 해당 파일을 별도로 준비하거나 URL을 `null`로 설정한 뒤 빌드합니다.

## 인증과 데이터 보관

AX for Works가 발급한 `ax_platform_session` 쿠키로 플랫폼 세션을 검증합니다. WiaVoice는 별도 계정·세션을 발급하지 않으며, 로그아웃 시 공통 플랫폼 세션을 폐기합니다. 관리자는 플랫폼의 `is_admin` 권한으로 구분합니다.

| 경로 / 테이블 | 용도와 수명 |
| --- | --- |
| `sessions/{session_hash}/` | 임시 생성 작업·음성. 로그아웃·세션 만료 후 정리 |
| `uploads/` | 임시 참조 음성. 24시간 경과 후 정리하며 진행 중 작업은 보호 |
| `workspace/{user_id}/{voice_id}/` | My Voice 영구 저장. 로그아웃 후에도 유지하며 사용자가 삭제 가능 |
| `marketplace/{voice_id}/` | 등록된 참조 음성·샘플. 임시 업로드와 독립적으로 보관 |
| `voices/`, `previews/` | 사전 생성된 기본 목소리 및 조합별 샘플 |
| `telemetry/pending/` | DB 기록 재시도를 위한 작업 통계 임시 파일 |
| `wiavoice.generation_runs` | 입력 멘트·작업 상태·처리 시간 등 생성 기록. 세션 종료 후에도 유지 |
| `wiavoice.voices`, `wiavoice.merge_action` | 저장 음성 및 병합 작업 메타데이터 |
| `wiavoice.market_voices`, `wiavoice.market_favorites` | 마켓플레이스 등록 및 즐겨찾기 |
| `wiavoice.download_events`, `wiavoice.admin_audit` | 다운로드 이벤트 및 관리 작업 이력 |

브라우저 탭을 닫는 것만으로 세션이 종료되지는 않습니다. 정리 작업은 주기적으로 수행되며, 최근 생성에 개수 기준 자동 삭제는 적용하지 않습니다. 음성 파일 자체는 PostgreSQL에 저장하지 않습니다.

## 운영 및 검증

현재 서버는 Supervisor의 `wiavoice-backend`, `wiavoice-frontend`로 실행됩니다. `ops/install_runtime.py`는 기존 AX for Works의 Supervisor와 게이트웨이 설정을 수정하는 운영 전용 스크립트입니다.

```bash
curl http://127.0.0.1:1015/api/health
python -m unittest discover -s tests -p 'test_*.py'
npm run build --prefix frontend
```

DB 통합 테스트는 플랫폼 구조가 준비된 **테스트 DB**에 연결해 명시적으로 실행합니다. 임시 계정과 DB 레코드를 생성하므로 일반 실행과 구분합니다.

```bash
WIAVOICE_TEST_DB=1 python -m unittest discover -s tests -p 'test_*.py'
```

Playwright 테스트는 `tests/*.mjs`에 있습니다. `admin-browser.mjs`는 API 모의 응답으로 관리자 화면을 확인하며 실제 관리자 권한을 변경하지 않습니다. 기본 대상은 `http://127.0.0.1:11005`이고, `WIAVOICE_UI_ORIGIN`으로 변경할 수 있습니다. 다른 브라우저 테스트 중 일부는 별도 로그인 fixture와 실행 중인 서비스가 필요합니다.

현재 생성 큐와 업로드 정리는 단일 ASGI 프로세스를 전제로 합니다. 여러 worker나 여러 서버로 확장하려면 작업 큐와 파일 정리의 프로세스 간 동기화가 먼저 필요합니다.

## Git 관리 범위

소스, SQL, 운영 스크립트, 테스트, 의존성 목록·잠금 파일, 폰트·아이콘을 관리합니다. 환경변수·인증서·모델·생성 음성·사용자 데이터·로그·백업·`node_modules`·빌드 결과·소개 미디어는 `.gitignore`로 제외합니다.
