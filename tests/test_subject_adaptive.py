import unittest
from types import SimpleNamespace

import subject_adaptive_patch as subject_patch


class SubjectDetectionTests(unittest.TestCase):
    def test_explicit_english_overrides_math_like_words(self):
        family = subject_patch.detect_subject_family(
            "English Language",
            "The functions of language",
            "Students analyse the range and function of expressions in a persuasive text.",
        )
        self.assertEqual(family, "english")

    def test_arabic_english_label_is_detected(self):
        family = subject_patch.detect_subject_family(
            "اللغة الإنجليزية",
            "Reading comprehension",
            "main idea and supporting details",
        )
        self.assertEqual(family, "english")

    def test_explicit_science_is_not_reclassified_by_source(self):
        family = subject_patch.detect_subject_family(
            "Science",
            "Energy transfer",
            "The graph shows a function and a range of experimental values.",
        )
        self.assertEqual(family, "science")

    def test_explicit_mathematics_remains_mathematics(self):
        self.assertEqual(
            subject_patch.detect_subject_family("Mathematics", "Reading a function graph", ""),
            "math",
        )

    def test_english_fallback_contains_language_pedagogy_not_math(self):
        lesson = SimpleNamespace(
            language="en",
            subject="English Language",
            class_name="Grade 8",
            topic="Reading comprehension: main idea and inference",
            source_text="A short informational text with evidence and author's purpose.",
            source_file_name="reading.pdf",
        )
        plan = subject_patch._english_plan(lesson)
        combined = "\n".join(str(value) for value in plan.values())
        self.assertIn("textual evidence", combined.lower())
        self.assertIn("reading", plan["curriculum"].lower())
        self.assertNotRegex(combined.lower(), r"\b(?:algebra|calculus|derivative|integral|desmos|geogebra)\b")
        self.assertEqual(len(subject_patch._extract_items(plan["learning_outcomes"])), 6)
        self.assertEqual(len(subject_patch._extract_items(plan["success_criteria"])), 6)
        self.assertEqual(len(subject_patch._extract_items(plan["main"])), 4)


if __name__ == "__main__":
    unittest.main()
