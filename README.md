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
$env:AUTO_GRILL_MODEL = "qwen2.5-coder:7b"   # 저사양 기본값. 고사양은 qwen3-coder:30b 등으로 교체
python .\auto_grill.py scan
```

> 모델 태그는 환경에 맞는 최신 코더 모델로 교체할 수 있습니다. Qwen3-Coder는 7B 태그가 없으므로(30b/480b만 존재) 기본값은 동작이 검증된 qwen2.5-coder:7b로 둡니다.

SQLite를 Markdown으로 내보내기:

```powershell
python .\sqlite_to_obsidian.py .\data\input.db .\build\markdown-export --clean
```

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
