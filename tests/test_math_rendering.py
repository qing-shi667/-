from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = ROOT / "zeabur-backend" / "app.py"


def load_backend():
    spec = importlib.util.spec_from_file_location("zeabur_math_backend", BACKEND_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MathRenderingTests(unittest.TestCase):
    def test_frontend_renders_ai_latex_with_local_mathjax(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('src="assets/mathjax/tex-svg.js"', html)
        self.assertNotIn("cdn.jsdelivr", html)
        self.assertIn("function renderAssistantMath", html)
        self.assertIn("MathJax.typesetPromise([bubble])", html)

    def test_backend_requires_consistent_latex_delimiters(self):
        backend = load_backend()
        prompt = backend.build_messages("实验原理", None, [])[0]["content"]
        self.assertIn("行内公式", prompt)
        self.assertIn(r"\(", prompt)
        self.assertIn(r"\[", prompt)

    def test_mathjax_is_available_in_static_and_embedded_modes(self):
        backend = load_backend()
        normal = backend.static_response_for("/assets/mathjax/tex-svg.js", app_root=ROOT)
        self.assertIsNotNone(normal)
        normal_body, normal_type = normal
        self.assertIn("javascript", normal_type)
        self.assertGreater(len(normal_body), 100_000)

        missing_root = ROOT / "__missing_static_root__"
        embedded = backend.static_response_for(
            "/assets/mathjax/tex-svg.js", app_root=missing_root
        )
        self.assertIsNotNone(embedded)
        embedded_body, embedded_type = embedded
        self.assertEqual(embedded_type, normal_type)
        self.assertEqual(embedded_body, normal_body)


if __name__ == "__main__":
    unittest.main()
