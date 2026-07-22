---
name: self-heal
description: Check internal documentation for possible contradictions, duplicates, and missing condition boundaries. Use for "self-healing knowledge", "knowledge consistency", "open query", or "rule conflict" requests. The workflow creates findings for human review and does not edit source documents automatically.
---

# Self-Healing Knowledge

Use this skill when a repository needs a neutral consistency review of its documentation or knowledge assets.

## Principles

- Scan only the current repository unless the user explicitly provides another path.
- Keep every scan path and report path inside the selected repository root; reject resolved symlink escapes.
- Do not scan user-global home folders by default.
- Do not modify source documents automatically.
- Preserve file and line references for every finding.
- Write generated reports under an ignored directory such as `build/self_heal/`.
- Treat local LLM output as advisory, not authoritative.
- Treat the Ollama option as local data disclosure: enable it only when the loopback service and selected model are approved for the documents. Pin the model tag in reproducible environments.
- Keep file-size and pair-count limits enabled for untrusted repositories.

## Default Command

```powershell
python .\auto_grill.py scan --paths docs skills --output build\self_heal\findings.json
```

Optional local LLM judge:

```powershell
$env:AUTO_GRILL_USE_LLM = "1"
$env:AUTO_GRILL_MODEL = "qwen2.5-coder:7b"   # low-RAM default; override with a current coder tag (e.g. qwen3-coder:30b) on capable hardware
python .\auto_grill.py scan
```

## Review Flow

1. Extract rule-like claims from Markdown or text files.
2. Pair related claims using keyword overlap.
3. Classify each pair as possible conflict, duplicate, condition boundary, or needs review.
4. Save findings with file and line references.
5. Ask the document owner to approve any correction.

## Do Not

- Do not commit generated findings unless explicitly requested.
- Do not apply LLM-generated corrections directly.
- Do not include raw sensitive documents in prompts or logs.
- Findings contain source excerpts and filenames; protect the report at the same classification as its inputs even when the model is disabled.
