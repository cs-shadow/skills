from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

from scripts import validate_skills as validator


class SkillValidationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def make_skill(self, name="example-skill", fields=None, body="Follow the supplied notes."):
        directory = self.root / name
        directory.mkdir(exist_ok=True)
        if fields is None:
            fields = {"name": name, "description": "Summarize supplied meeting notes."}
        (directory / "SKILL.md").write_text(
            "---\n" + yaml.safe_dump(fields) + "---\n" + body + "\n",
            encoding="utf-8",
        )
        return directory

    def run_main(self, *arguments, collection=None):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(validator, "DEFAULT_COLLECTION", collection or self.root):
            with redirect_stdout(output), redirect_stderr(errors):
                status = validator.main(list(arguments))
        return status, output.getvalue(), errors.getvalue()

    def test_minimal_skill_and_optional_resources(self):
        directory = self.make_skill()
        (directory / "references").mkdir()
        self.assertEqual(validator.validate_skill(directory), [])

    def test_all_standard_optional_fields(self):
        directory = self.make_skill(fields={
            "name": "example-skill",
            "description": "Summarize notes when requested.",
            "license": "Proprietary",
            "compatibility": "Requires Python 3.12+.",
            "allowed-tools": "Bash(python:*)",
            "metadata": {"author": "Me", "version": "1.0"},
        })
        self.assertEqual(validator.validate_skill(directory), [])

    def test_missing_skill_file_and_non_directory_paths(self):
        directory = self.root / "empty-skill"
        directory.mkdir()
        file = self.root / "file"
        file.touch()
        for path in (directory, file, self.root / "missing"):
            with self.subTest(path=path):
                self.assertTrue(validator.validate_skill(path))

    def test_invalid_yaml_and_frontmatter_structure(self):
        contents = [
            "No frontmatter", "---\nname: example-skill", "---\n[\n---\nBody",
            "---\n- item\n---\nBody", "---\nnull\n---\nBody",
            "---\na scalar\n---\nBody", "---\n---\nBody",
            "---\n!!python/object:example {}\n---\nBody",
        ]
        directory = self.make_skill()
        for content in contents:
            with self.subTest(content=content):
                (directory / "SKILL.md").write_text(content, encoding="utf-8")
                self.assertTrue(validator.validate_skill(directory))

    def test_non_utf8_input(self):
        directory = self.make_skill()
        (directory / "SKILL.md").write_bytes(b"\xff")
        self.assertTrue(validator.validate_skill(directory))

    def test_required_fields(self):
        for fields in ({}, {"name": "example-skill"}, {"description": "Notes"}):
            with self.subTest(fields=fields):
                self.assertTrue(validator.validate_skill(self.make_skill(fields=fields)))

    def test_invalid_field_types(self):
        for field in ("name", "description", "license", "compatibility", "allowed-tools"):
            for value in (None, True, 12, [], {}):
                with self.subTest(field=field, value=value):
                    fields = {"name": "example-skill", "description": "Notes"}
                    fields[field] = value
                    self.assertTrue(validator.validate_skill(self.make_skill(fields=fields)))

    def test_metadata_requires_string_keys_and_values(self):
        for value in (None, [], "author", {1: "Me"}, {"version": 1}, {"nested": {}}):
            with self.subTest(value=value):
                fields = {"name": "example-skill", "description": "Notes", "metadata": value}
                self.assertTrue(validator.validate_skill(self.make_skill(fields=fields)))

    def test_unknown_fields(self):
        for key in ("custom", 1):
            with self.subTest(key=key):
                fields = {"name": "example-skill", "description": "Notes", key: "value"}
                self.assertTrue(validator.validate_skill(self.make_skill(fields=fields)))

    def test_invalid_name_characters_with_matching_directory(self):
        for name in (" ", "Example", "under_score", "-start", "end-", "two--hyphens",
                     "éxample", "example-skill "):
            with self.subTest(name=name):
                directory = self.make_skill(name=name)
                self.assertEqual(validator.validate_skill(directory), [
                    "name must use lowercase letters, digits, and single separating hyphens"
                ])

    def test_overlong_name_with_matching_directory(self):
        directory = self.make_skill(name="a" * 65)
        self.assertEqual(validator.validate_skill(directory), ["name must contain 1–64 characters"])

    def test_empty_name_reports_length_error(self):
        # An empty directory name is impossible; require the length error explicitly
        # so the unavoidable directory mismatch cannot make this test pass.
        directory = self.make_skill(fields={"name": "", "description": "Notes"})
        self.assertIn("name must contain 1–64 characters", validator.validate_skill(directory))

    def test_valid_name_must_match_directory(self):
        directory = self.make_skill(fields={"name": "different-directory", "description": "Notes"})
        self.assertEqual(validator.validate_skill(directory), [
            "name must match directory name 'example-skill'"
        ])

    def test_valid_name_and_text_length_boundaries(self):
        for name in ("a", "a" * 64, "notes-2"):
            with self.subTest(name=name):
                fields = {"name": name, "description": "d" * 1024, "compatibility": "c" * 500}
                self.assertEqual(validator.validate_skill(self.make_skill(name, fields)), [])

    def test_blank_or_overlong_text(self):
        for field, limit in (("description", 1024), ("compatibility", 500)):
            for value in ("", " \n\t", "a" * (limit + 1)):
                with self.subTest(field=field, value=value):
                    fields = {"name": "example-skill", "description": "Notes", field: value}
                    self.assertTrue(validator.validate_skill(self.make_skill(fields=fields)))

    def test_empty_instructions(self):
        for body in ("", " \n\t"):
            with self.subTest(body=body):
                self.assertTrue(validator.validate_skill(self.make_skill(body=body)))

    def test_crlf_and_multiline_yaml(self):
        directory = self.make_skill()
        (directory / "SKILL.md").write_bytes(
            b"---\r\nname: example-skill\r\ndescription: >\r\n  Summarize\r\n  notes.\r\n"
            b"---\r\nInstructions without a required heading.\r\n"
        )
        self.assertEqual(validator.validate_skill(directory), [])

    def test_empty_and_missing_collections(self):
        (self.root / ".gitkeep").touch()
        status, output, errors = self.run_main()
        self.assertEqual(status, 0)
        self.assertIn("empty collection", output)
        self.assertEqual(errors, "")
        status, _, errors = self.run_main(collection=self.root / "missing")
        self.assertEqual(status, 1)
        self.assertIn(str(self.root / "missing"), errors)

    def test_discovery_checks_only_immediate_directories(self):
        directory = self.make_skill()
        (directory / "assets").mkdir()
        (self.root / ".gitkeep").touch()
        status, output, errors = self.run_main()
        self.assertEqual(status, 0)
        self.assertIn("Checked 1 skill(s)", output)
        self.assertEqual(errors, "")

    def test_reports_multiple_failures_with_paths(self):
        first = self.make_skill("first", fields={})
        second = self.make_skill("second", body="")
        status, _, errors = self.run_main()
        self.assertEqual(status, 1)
        self.assertIn(str(first), errors)
        self.assertIn(str(second), errors)
        self.assertIn("missing required field: name", errors)
        self.assertIn("missing required field: description", errors)

    def test_cli_explicit_paths_and_exit_status(self):
        valid = self.make_skill()
        script = str(Path(validator.__file__).resolve())
        for paths, expected_status in (([valid.name], 0), ([valid.name, "missing"], 1)):
            with self.subTest(paths=paths):
                result = subprocess.run(
                    [sys.executable, script, *paths], cwd=self.root,
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, expected_status)
                self.assertIn(f"{valid.name}: valid", result.stdout)
                if expected_status:
                    self.assertIn("missing:", result.stderr)

    def test_cli_default_collection_is_independent_of_working_directory(self):
        # Use an isolated repository layout so this stays valid as real skills are added.
        scripts = self.root / "scripts"
        scripts.mkdir()
        script = scripts / "validate_skills.py"
        script.write_bytes(Path(validator.__file__).read_bytes())
        (self.root / "skills").mkdir()
        result = subprocess.run(
            [sys.executable, str(script)], cwd=scripts,
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("empty collection", result.stdout)

    def test_cli_accepts_current_directory_as_skill(self):
        directory = self.make_skill()
        result = subprocess.run(
            [sys.executable, str(Path(validator.__file__).resolve()), "."],
            cwd=directory, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
