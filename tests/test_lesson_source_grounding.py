import ast
import re
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "lesson_source_grounding_patch.py"
UPLOAD_PATH = ROOT / "lesson_upload_relevance_patch.py"
SOURCE_TEXT = SOURCE_PATH.read_text(encoding="utf-8")
SOURCE_TREE = ast.parse(SOURCE_TEXT)


def load_selected_functions():
    wanted_functions = {
        "_clean",
        "_tokens",
        "_split_blocks",
        "select_relevant_source",
        "_distinctive_terms",
        "_ground_local",
    }
    wanted_assignments = {"_STOPWORDS", "SOURCE_MAX_CHARS", "EXTRACT_MAX_CHARS"}
    body = []
    for node in SOURCE_TREE.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = []
            if isinstance(node, ast.Assign):
                targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
            elif isinstance(node.target, ast.Name):
                targets = [node.target.id]
            if any(name in wanted_assignments for name in targets):
                body.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in wanted_functions:
            body.append(node)
    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "re": re,
        "Counter": Counter,
        "Any": object,
    }
    exec(compile(module, str(SOURCE_PATH), "exec"), namespace)
    return namespace


FUNCTIONS = load_selected_functions()


class LessonSourceGroundingTests(unittest.TestCase):
    def test_files_are_valid_python(self):
        ast.parse(SOURCE_TEXT)
        ast.parse(UPLOAD_PATH.read_text(encoding="utf-8"))

    def test_relevant_context_prefers_lesson_topic(self):
        source = """
        Unit 1: General introduction
        This section explains classroom routines and assessment dates.

        Lesson: Main Idea and Supporting Details
        Readers identify the central idea, select supporting details, and cite text evidence.
        A strong response explains how each detail supports the main idea.

        Lesson: Grammar Review
        Students revise verb forms and punctuation.
        """
        selected = FUNCTIONS["select_relevant_source"](
            source,
            "Main Idea and Supporting Details",
            "English Language",
            "Use text evidence",
            max_chars=900,
        )
        self.assertIn("central idea", selected)
        self.assertIn("text evidence", selected)

    def test_local_fallback_carries_uploaded_source_vocabulary(self):
        lesson = SimpleNamespace(language="en")
        fallback = {
            "keywords": "reading",
            "strategies": "Use guided reading.",
            "curriculum": "Subject: English Language",
        }
        result = FUNCTIONS["_ground_local"](
            fallback,
            "Readers identify the central idea and cite supporting textual evidence.",
            lesson,
        )
        combined = " ".join(str(value).lower() for value in result.values())
        self.assertIn("central", combined)
        self.assertIn("evidence", combined)
        self.assertEqual(result["_mode"], "source_grounded_local_fallback")

    def test_source_and_word_cache_versions_changed(self):
        self.assertIn("source-grounded-v5", SOURCE_TEXT)
        self.assertIn("lesson-docx-source-grounded-v5", SOURCE_TEXT)

    def test_full_pdf_topic_search_is_enabled(self):
        upload_source = UPLOAD_PATH.read_text(encoding="utf-8")
        self.assertIn("LESSON_PDF_SEARCH_PAGES", upload_source)
        self.assertIn("_extract_pdf_for_topic", upload_source)
        self.assertIn("page_index - 1", upload_source)
        self.assertIn("page_index + 1", upload_source)


if __name__ == "__main__":
    unittest.main()
