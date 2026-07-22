"""Export a SQLite database to neutral Markdown notes.

This script is intentionally schema-agnostic. It skips SQLite internal tables
and writes generated Markdown to a caller-provided directory. Generated output
should stay out of Git unless it is deliberately curated.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sqlite3
import urllib.parse
from pathlib import Path
from typing import Any


INTERNAL_TABLE_PREFIX = "sqlite_"
EXPORT_MARKER = ".offline-kb-export"
DEFAULT_MAX_DB_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_ROWS_PER_TABLE = 100_000
DEFAULT_MAX_CELL_CHARS = 10_000
WINDOWS_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", *{f"COM{i}" for i in range(1, 10)},
                          *{f"LPT{i}" for i in range(1, 10)}}


def safe_filename(value: Any, fallback: str = "row") -> str:
    text = str(value if value is not None else fallback)
    text = re.sub(r'[\\/:*?"<>|&#;\[\]\n\r\t]', " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    text = (text or fallback).strip(" .") or "item"
    text = text[:80]
    if text.upper() in WINDOWS_RESERVED_NAMES:
        text += "_"
    return text


def quote_yaml(value: Any) -> str:
    text = html.escape(str(value).replace("\r", " ").replace("\n", " "), quote=False)
    return json.dumps(text[:200], ensure_ascii=False)


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def markdown_cell(value: Any, max_chars: int) -> str:
    text = html.escape(str(value)[:max_chars], quote=False)
    return (text.replace("\\", "\\\\").replace("|", "\\|")
            .replace("[", "\\[").replace("]", "\\]")
            .replace("\r", "").replace("\n", "<br>"))


def is_within(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def list_user_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    return [row[0] for row in rows if not row[0].startswith(INTERNAL_TABLE_PREFIX)]


def choose_name_column(columns: list[str]) -> str:
    preferred = ("name", "title", "id", "key", "code")
    lowered = {col.lower(): col for col in columns}
    for candidate in preferred:
        if candidate in lowered:
            return lowered[candidate]
    return columns[0]


def render_row(
    table: str, columns: list[str], row: sqlite3.Row, name_column: str, max_cell_chars: int
) -> str:
    row_dict = {col: row[col] for col in columns}
    title = markdown_cell(row_dict.get(name_column) or "Untitled", 200).replace("<br>", " ")
    lines = ["---", f"type: {quote_yaml(table)}"]
    for col, value in row_dict.items():
        if value is not None and str(value).strip():
            lines.append(f"{quote_yaml(col)}: {quote_yaml(value)}")
    lines.extend(["---", "", f"# {title}", "", "| Field | Value |", "|---|---|"])
    for col, value in row_dict.items():
        if value is not None and str(value).strip():
            clean = markdown_cell(value, max_cell_chars)
            lines.append(f"| {markdown_cell(col, 200)} | {clean} |")
    lines.append("")
    return "\n".join(lines)


def export_db(
    db_path: Path,
    output_dir: Path,
    clean: bool = False,
    max_db_bytes: int = DEFAULT_MAX_DB_BYTES,
    max_rows_per_table: int = DEFAULT_MAX_ROWS_PER_TABLE,
    max_cell_chars: int = DEFAULT_MAX_CELL_CHARS,
) -> dict[str, int]:
    if not db_path.exists():
        raise FileNotFoundError(db_path)
    if min(max_db_bytes, max_rows_per_table, max_cell_chars) < 1:
        raise ValueError("resource limits must be positive integers")
    if db_path.stat().st_size > max_db_bytes:
        raise ValueError(f"Database exceeds max_db_bytes ({max_db_bytes})")
    db_path = db_path.resolve()
    output_dir = output_dir.resolve()
    if output_dir == Path(output_dir.anchor) or output_dir == Path.home().resolve():
        raise ValueError("Output must be a dedicated subdirectory, not a filesystem or home root")
    if is_within(output_dir, db_path):
        raise ValueError("Input database must not be inside the managed output directory")
    if output_dir.exists() and not (output_dir / EXPORT_MARKER).is_file() and any(output_dir.iterdir()):
        raise ValueError(f"Output directory is non-empty and lacks {EXPORT_MARKER}")
    if clean and output_dir.exists():
        if not (output_dir / EXPORT_MARKER).is_file():
            raise ValueError(f"Refusing --clean without {EXPORT_MARKER} marker in output directory")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / EXPORT_MARKER).write_text("managed export directory\n", encoding="utf-8")

    conn = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    stats: dict[str, int] = {}
    table_directories: dict[str, str] = {}
    try:
        for table_index, table in enumerate(list_user_tables(conn), 1):
            columns = [row[1] for row in conn.execute(f"PRAGMA table_info({quote_identifier(table)})").fetchall()]
            if not columns:
                continue
            name_column = choose_name_column(columns)
            table_name = f"{table_index:04d}_{safe_filename(table, 'table')}"
            table_dir = (output_dir / table_name).resolve()
            if not is_within(output_dir, table_dir):
                raise ValueError(f"Unsafe table output path for {table!r}")
            table_dir.mkdir(parents=True, exist_ok=True)
            count = 0
            query = f"SELECT * FROM {quote_identifier(table)} LIMIT ?"
            for row in conn.execute(query, (max_rows_per_table + 1,)):
                if count >= max_rows_per_table:
                    raise ValueError(f"Table {table!r} exceeds max_rows_per_table ({max_rows_per_table})")
                base_name = safe_filename(row[name_column], f"{table}_{count + 1}")
                target = table_dir / f"{base_name}.md"
                suffix = 2
                while target.exists():
                    target = table_dir / f"{base_name}_{suffix}.md"
                    suffix += 1
                target.write_text(
                    render_row(table, columns, row, name_column, max_cell_chars), encoding="utf-8"
                )
                count += 1
            stats[table] = count
            table_directories[table] = table_name
    finally:
        conn.close()

    index = ["# Export Index", ""]
    for table, count in stats.items():
        table_name = table_directories[table]
        link_target = urllib.parse.quote(table_name, safe="")
        index.append(f"- [{markdown_cell(table, 200)}](./{link_target}/) - {count} rows")
    (output_dir / "INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Export SQLite tables to Markdown notes.")
    parser.add_argument("db", type=Path, help="SQLite database path.")
    parser.add_argument("output", type=Path, help="Output directory.")
    parser.add_argument("--clean", action="store_true", help="Delete output directory before export.")
    parser.add_argument("--max-db-bytes", type=int, default=DEFAULT_MAX_DB_BYTES)
    parser.add_argument("--max-rows-per-table", type=int, default=DEFAULT_MAX_ROWS_PER_TABLE)
    parser.add_argument("--max-cell-chars", type=int, default=DEFAULT_MAX_CELL_CHARS)
    args = parser.parse_args()
    stats = export_db(
        args.db, args.output, args.clean, args.max_db_bytes,
        args.max_rows_per_table, args.max_cell_chars,
    )
    print(f"exported {sum(stats.values())} rows from {len(stats)} tables to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
