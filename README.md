# Offline Knowledge Base

오프라인·제한망 환경으로 이식하기 위한 중립형 지식 자산 도구 모음입니다. 승인된 문서와 스프레드시트를 로컬 전용 지식 베이스로 변환하고, 문서 규칙 간 충돌을 검출해 review queue로 남깁니다.

이 저장소는 특정 제품, 고객, 사양서, 게임 데이터, 영상 실험 결과를 포함하지 않습니다. 실제 원본 문서와 생성 산출물은 Git에 넣지 않고, 사내 보안 정책에 맞는 별도 저장 위치에서 관리하는 것을 전제로 합니다.

## 목적

- 사내 문서, 스프레드시트, SQLite 데이터베이스를 검색 가능한 지식 자산으로 변환
- 생성된 Markdown, vector DB, 검색 인덱스, 실행 로그를 Git 밖에서 관리
- 규칙 문서 간 중복, 충돌, 누락 가능성을 자동으로 찾아 review queue로 남김
- local LLM 또는 규칙 기반 검사를 사용할 수 있게 하되, 자동 수정은 하지 않음

## 구성

```text
.
├── auto_grill.py              # 중립 지식 일관성 검사기
├── self_heal.py               # auto_grill 호환 CLI
├── sqlite_to_obsidian.py      # SQLite -> Markdown 변환 도구
├── docs/
│   ├── ai-agent-trends-2026.md
│   ├── build-plan.md
│   ├── self-healing-knowledge-research.md
│   └── small-local-llm-value-guide.md
├── skills/
│   ├── excel-asset/
│   └── self-heal/
└── requirements.txt
```

## 기본 사용

문서 일관성 검사:

```powershell
python .\auto_grill.py scan --paths docs skills --output build\self_heal\findings.json
```

local LLM 판정을 켜려면 Ollama 실행 후:

```powershell
$env:AUTO_GRILL_USE_LLM = "1"
$env:AUTO_GRILL_MODEL = "<internally-approved-model-tag>"
python .\auto_grill.py scan
```

> 내장 모델명은 호환성 기본값일 뿐 최신성·적합성을 보장하지 않습니다. 재현 가능한 환경에서는 내부 승인·고정된 태그를 명시하십시오. 로컬 LLM을 켜면 문서 발췌가 loopback Ollama 서비스로 전달되며, 결과 보고서에도 원문 발췌와 파일명이 포함됩니다.

SQLite를 Markdown으로 내보내기:

```powershell
python .\sqlite_to_obsidian.py .\data\input.db .\build\markdown-export --clean
```

첫 내보내기는 `--clean` 없이 실행해 관리 디렉터리 표식을 만듭니다. 이후 `--clean`은 이 표식이 있는 출력 폴더에서만 동작합니다. 데이터베이스·행·셀·문서 파일에는 기본 자원 상한이 있으며 CLI 옵션으로 조정할 수 있습니다.

## 운영 원칙

- `data/`, `build/`, `exports/`, vector DB, 검색 인덱스, 로그는 Git에 넣지 않는다.
- 원본 문서는 사내 승인된 위치에 보관하고, repo에는 변환 코드와 중립 문서만 둔다.
- Self-healing 결과는 자동 수정이 아니라 review finding으로 처리한다.
- 수정이 필요하면 사람이 근거를 확인한 뒤 PR 또는 변경 요청으로 반영한다.
- 외부망 패키지는 사내 mirror 또는 wheelhouse를 통해 반입한다.

## 제거된 항목

이 저장소에서 다음 유형은 제거 대상입니다.

- 개인 테스트 데이터
- 샘플 Excel/DB/JSON 결과물
- vector DB, 검색 엔진 데이터 디렉터리
- 게임/영상/외부 튜토리얼 기반 실험 산출물
- 특정 사내 환경 경로가 하드코딩된 데모 스크립트

## 보안 메모

민감정보 마스킹은 별도 전처리 단계로 넣는 것을 권장합니다. 제한망에서는 Microsoft Presidio 같은 도구도 사내 패키지 반입 절차를 거쳐 로컬 전용으로 구성해야 합니다.
