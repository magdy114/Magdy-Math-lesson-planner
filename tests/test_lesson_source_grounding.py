import unittest
from types import SimpleNamespace

import lesson_source_grounding_patch as source_patch


class LessonSourceGroundingTests(unittest.TestCase):
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
        selected = source_patch.select_relevant_source(
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
        result = source_patch._ground_local(
            fallback,
            "Readers identify the central idea and cite supporting textual evidence.",
            lesson,
        )
        combined = " ".join(str(value).lower() for value in result.values())
        self.assertIn("central", combined)
        self.assertIn("evidence", combined)
        self.assertEqual(result["_mode"], "source_grounded_local_fallback")

    def test_source_cache_version_is_new(self):
        self.assertIn("source-grounded", source_patch.SOURCE_CACHE_VERSION)


if __name__ == "__main__":
    unittest.main()
