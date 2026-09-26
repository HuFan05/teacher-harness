"""Skill-asset checks for cs-ai-coach.

The terminology validator must accept the shipped glossary and fail closed on
a damaged copy; the version-coupling manifest must list exactly the shipped
files; and every closed vocabulary and fixed sentence these documents quote
must still match the Teacher harness that implements the practice mode.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = SKILL_ROOT / "scripts" / "validate_terminology.py"
TEACHER_TH = SKILL_ROOT.parent / "teacher" / "scripts" / "th"
IGNORED_PARTS = {"__pycache__"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}
CJK = re.compile(r"[\u4e00-\u9fff]")


def run_validator(root: Path) -> tuple[int, dict]:
    completed = subprocess.run(
        [sys.executable, "-B", str(VALIDATOR), "--skill-root", str(root), "--json"],
        capture_output=True, text=True, check=False, timeout=60,
    )
    return completed.returncode, json.loads(completed.stdout)


def shipped_files() -> set[str]:
    return {
        path.relative_to(SKILL_ROOT).as_posix()
        for path in SKILL_ROOT.rglob("*")
        if path.is_file()
        and not IGNORED_PARTS.intersection(path.relative_to(SKILL_ROOT).parts)
        and path.suffix not in IGNORED_SUFFIXES
        and path.name != ".DS_Store"
    }


def literal_assignments(path: Path) -> dict[str, object]:
    """Read module-level literal constants without importing the module."""

    values: dict[str, object] = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                values[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                continue
    return values


def rendered_literals(path: Path) -> list[str]:
    """Chinese string literals of a module, without docstrings or regex patterns."""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)
    }
    literals = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str) or id(node) in docstrings:
            continue
        value = node.value.strip()
        if CJK.search(value) and "|" not in value and 8 <= len(value) <= 200:
            literals.append(value)
    return literals


def documents() -> dict[str, str]:
    paths = [SKILL_ROOT / "SKILL.md", *sorted((SKILL_ROOT / "references").glob("*.md"))]
    return {path.relative_to(SKILL_ROOT).as_posix(): path.read_text(encoding="utf-8") for path in paths}


class TerminologyValidatorTests(unittest.TestCase):
    def test_shipped_terminology_is_valid(self) -> None:
        code, result = run_validator(SKILL_ROOT)
        self.assertEqual(code, 0, result)
        self.assertEqual(result, {"ok": True, "code": "terminology_valid", "term_count": 2})

    def test_an_incomplete_definition_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "cs-ai-coach"
            (root / "references").mkdir(parents=True)
            shutil.copy2(SKILL_ROOT / "SKILL.md", root / "SKILL.md")
            shutil.copy2(SKILL_ROOT / "references" / "terminology-registry.json",
                         root / "references" / "terminology-registry.json")
            glossary = (SKILL_ROOT / "references" / "terminology.md").read_text(encoding="utf-8")
            (root / "references" / "terminology.md").write_text(
                glossary.replace("### 机器绑定", "### 其他", 1), encoding="utf-8")
            code, result = run_validator(root)
        self.assertEqual(code, 1)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "terminology_definition_incomplete")

    def test_a_foreign_skill_identity_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "cs-ai-coach"
            shutil.copytree(SKILL_ROOT / "references", root / "references")
            shutil.copy2(SKILL_ROOT / "SKILL.md", root / "SKILL.md")
            registry_path = root / "references" / "terminology-registry.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            registry["skill_id"] = "personal:another-skill"
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            code, result = run_validator(root)
        self.assertEqual(code, 1)
        self.assertEqual(result["code"], "terminology_skill_identity_mismatch")


class SkillMetadataTests(unittest.TestCase):
    def test_frontmatter_names_this_skill(self) -> None:
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^name: cs-ai-coach$")
        self.assertRegex(text, r"(?m)^version: v1\.0\.0$")

    def test_manifest_lists_exactly_the_shipped_files(self) -> None:
        manifest = json.loads((SKILL_ROOT / "references" / "version-coupling-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["skill_name"], "cs-ai-coach")
        self.assertEqual(manifest["historical_generations"], [])
        recorded = [component["path"] for component in manifest["components"]]
        self.assertEqual(len(recorded), len(set(recorded)))
        self.assertEqual(set(recorded), shipped_files())
        for entry in manifest["entrypoints"]:
            self.assertTrue((SKILL_ROOT / entry["path"]).is_file(), entry["path"])
            self.assertEqual(entry["generation"], manifest["current_generation"])

    def test_observer_catalog_belongs_to_this_skill(self) -> None:
        catalog = json.loads((SKILL_ROOT / "references" / "observer-phases.json").read_text(encoding="utf-8"))
        dictionary = (SKILL_ROOT / "references" / "observer-data-dictionary.md").read_text(encoding="utf-8")
        self.assertEqual(catalog["catalog_version"], "cs-ai-coach/v1")
        for phase in catalog["workflow_phases"] + catalog["script_phases"]:
            self.assertIn(f"`{phase}`", dictionary)
        for phase in catalog["script_phases"]:
            self.assertTrue(phase.startswith("cs-ai-coach.script."), phase)


@unittest.skipUnless((TEACHER_TH / "coach.py").is_file(), "the sibling teacher Skill is not installed")
class HarnessAgreementTests(unittest.TestCase):
    """The documents describe the implemented practice mode, not an intention."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.constants = literal_assignments(TEACHER_TH / "constants.py")
        cls.coach = literal_assignments(TEACHER_TH / "coach.py")
        cls.documents = documents()
        cls.corpus = "\n".join(cls.documents.values())

    def test_closed_vocabularies_are_documented(self) -> None:
        vocabularies = {name: self.constants[name] for name in (
            "COACH_ADMISSIONS", "COACH_EPISTEMIC", "COACH_DECISIONS", "COACH_FIRST_ERRORS",
            "COACH_ROLES", "COACH_STATES", "COACH_COMPLETION")}
        for name in ("INCUBATION_KINDS", "QUESTION_CODES", "SCOPES", "REVIEW_KEYS", "GUARD_KEYS",
                     "ADMIT_KEYS", "AUDIT_KEYS", "INCUBATE_KEYS"):
            vocabularies[name] = self.coach[name]
        vocabularies["PROGRESS_TEXT"] = tuple(self.coach["PROGRESS_TEXT"])
        for name, values in vocabularies.items():
            for value in values:
                self.assertIn(f"`{value}`", self.corpus, f"{name}: {value}")

    def test_the_first_error_table_matches_the_renderer(self) -> None:
        policy = self.documents["references/training-policy.md"]
        rows = dict(re.findall(r"(?m)^\| `([A-Z_]+)` \| ([^|]+?) \|$", policy))
        self.assertEqual(set(rows), set(self.constants["COACH_FIRST_ERRORS"]))
        for code, label in self.coach["ERROR_TEXT"].items():
            self.assertEqual(rows[code], label, code)

    def test_fixed_sentences_are_quoted_verbatim(self) -> None:
        sentences = [self.coach["SAFE_COACH_FAILURE"]]
        for table in ("TEXT", "DECISION_TEXT", "PROGRESS_TEXT", "COMPLETION_TEXT", "OBLIGATION_TEXT",
                      "QUESTION_TEMPLATES"):
            sentences.extend(self.coach[table].values())
        for sentence in sentences:
            self.assertIn(sentence, self.corpus)

    def test_every_rendered_literal_is_documented(self) -> None:
        """Inline refusals and render lines, not only the tables, are quoted."""

        sources = {"th/coach.py": None, "teacher.py": "练习", "server/app.py": "练习", "th/teach.py": "练习"}
        for relative, marker in sources.items():
            path = TEACHER_TH.parent / relative
            for literal in rendered_literals(path):
                if marker is None or marker in literal:
                    self.assertIn(literal, self.corpus, f"{relative}: {literal}")


if __name__ == "__main__":
    unittest.main()
