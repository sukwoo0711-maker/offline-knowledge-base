import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


auto_grill = load("auto_grill", "auto_grill.py")
sqlite_export = load("sqlite_to_obsidian", "sqlite_to_obsidian.py")


class AutoGrillSafetyTests(unittest.TestCase):
    def test_scan_path_cannot_escape_root(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "repo"
            root.mkdir()
            with self.assertRaisesRegex(ValueError, "escapes repository root"):
                list(auto_grill.iter_text_files(root.resolve(), ["../outside"]))

    def test_output_prefix_collision_cannot_escape_root(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "repo"
            root.mkdir()
            outside = Path(folder) / "repo-other" / "report.json"
            with self.assertRaisesRegex(ValueError, "Output must stay inside repo"):
                auto_grill.scan(root, [], outside, 0, "unused")

    def test_oversize_text_is_skipped(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "large.md").write_text("x" * 20, encoding="utf-8")
            self.assertEqual(list(auto_grill.iter_text_files(root, ["large.md"], 10)), [])


class SqliteExportSafetyTests(unittest.TestCase):
    def make_db(self, root: Path) -> Path:
        db = root / "input.db"
        connection = sqlite3.connect(db)
        connection.execute('CREATE TABLE "odd""table" ("title" TEXT, "value" TEXT)')
        connection.execute(
            'INSERT INTO "odd""table" VALUES (?, ?)',
            ("A", "left|right\n<script>alert(1)</script>"),
        )
        connection.execute('INSERT INTO "odd""table" VALUES (?, ?)', ("B", "second"))
        connection.commit()
        connection.close()
        return db

    def test_quoted_identifier_and_markdown_escaping(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "export"
            stats = sqlite_export.export_db(self.make_db(root), output)
            self.assertEqual(stats['odd"table'], 2)
            note = next(path for path in output.rglob("*.md") if path.name != "INDEX.md")
            text = note.read_text(encoding="utf-8")
            self.assertIn(r"left\|right<br>&lt;script&gt;alert(1)&lt;/script&gt;", text)
            self.assertNotIn("<script>", text)
            self.assertTrue((output / sqlite_export.EXPORT_MARKER).is_file())

    def test_clean_requires_managed_directory_marker(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "unmanaged"
            output.mkdir()
            (output / "keep.txt").write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "lacks .offline-kb-export"):
                sqlite_export.export_db(self.make_db(root), output, clean=True)
            self.assertTrue((output / "keep.txt").exists())

    def test_row_limit_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaisesRegex(ValueError, "exceeds max_rows_per_table"):
                sqlite_export.export_db(self.make_db(root), root / "export", max_rows_per_table=1)

    def test_input_database_cannot_be_cleaned_as_output(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "export"
            output.mkdir()
            db = self.make_db(output)
            (output / sqlite_export.EXPORT_MARKER).write_text("managed\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must not be inside"):
                sqlite_export.export_db(db, output, clean=True)
            self.assertTrue(db.exists())

    def test_dot_table_name_stays_inside_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            db = root / "dots.db"
            connection = sqlite3.connect(db)
            connection.execute('CREATE TABLE ".." ("name" TEXT)')
            connection.execute('INSERT INTO ".." VALUES ("row")')
            connection.commit()
            connection.close()
            output = root / "export"
            sqlite_export.export_db(db, output)
            notes = list(output.rglob("*.md"))
            self.assertTrue(notes)
            self.assertTrue(all(sqlite_export.is_within(output.resolve(), note.resolve()) for note in notes))


if __name__ == "__main__":
    unittest.main()
