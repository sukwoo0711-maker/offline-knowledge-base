# Auto-grill record

## Findings and revisions

- Repository path containment used a string-prefix comparison and scan paths could resolve outside the selected root. Both reads and writes now use resolved path ancestry checks; reports list files skipped by the size boundary.
- Text scans had no per-file bound and local-model responses were read without a limit. The scanner now skips oversized text inputs and caps response bytes.
- SQLite identifiers were interpolated with incomplete quoting. They now use escaped SQL identifiers and the database is opened read-only.
- `--clean` could recursively delete any caller-selected directory. It now requires a marker created by this exporter.
- Database size, rows per table, claim length, and rendered cell length are bounded. YAML keys/values are quoted and Markdown/HTML-active content is escaped.
- Time-sensitive model-tag wording was changed from a “current model” assertion to a compatibility default that deployments must pin and review.

## Evidence limits

The heuristic scanner identifies lexical overlap and polarity; it does not prove semantic contradiction or priority. A local LLM may improve wording but does not convert a finding into fact. SQLite export preserves selected values, not database behavior, triggers, constraints, application semantics, or complete provenance.

## Porting decisions

- `PORTING-DECISION-001`: choose approved local model tags and retention rules before enabling `AUTO_GRILL_USE_LLM=1`.
- `PORTING-DECISION-002`: tune file, database, row, pair, cell, and response limits to the destination's memory and review budget.
- `PORTING-DECISION-003`: decide whether local filenames, table names, and cell values require masking before generated Markdown or findings leave the source security zone.
- `PORTING-DECISION-004`: define the spreadsheet recalculation engine and formula evidence policy before claiming formula-derived values are current.
