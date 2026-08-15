import unittest

from core import mathmd


class NormalizeTests(unittest.TestCase):
    def test_converts_paren_and_bracket_delimiters(self):
        self.assertEqual(
            mathmd.normalize(r"Energy \(E_n\) obeys \[E_n = n^2\] exactly."),
            "Energy $E_n$ obeys $$E_n = n^2$$ exactly.",
        )

    def test_converts_math_fence_to_display_math(self):
        self.assertEqual(
            mathmd.normalize("```math\nE_n = \\frac{n^2}{2}\n```"),
            "$$\nE_n = \\frac{n^2}{2}\n$$",
        )

    def test_leaves_real_code_fences_alone(self):
        source = "```python\nx = a_b * c\n```"
        self.assertEqual(mathmd.normalize(source), source)

    def test_leaves_inline_code_alone(self):
        source = "Write `\\frac{a}{b}` to divide."
        self.assertEqual(mathmd.normalize(source), source)

    def test_wraps_bare_latex_without_swallowing_prose(self):
        self.assertEqual(
            mathmd.normalize(r"E = \frac{\pi^2}{2m a^2} (for n=1) and so on"),
            r"E = $\frac{\pi^2}{2m a^2}$ (for n=1) and so on",
        )

    def test_trims_padding_inside_math_spans(self):
        self.assertEqual(mathmd.normalize("$ n = 4 $ states"), "$n = 4$ states")

    def test_rewrites_typeset_unicode_as_commands(self):
        self.assertEqual(
            mathmd.normalize("$E₀ = π²ħ²$"),
            r"$E_{0} = \pi^{2}\hbar^{2}$",
        )

    def test_drops_break_tags(self):
        self.assertEqual(mathmd.normalize("a<br>b<br />c"), "a b c")


class RenderTests(unittest.TestCase):
    def test_plain_renders_scripts_symbols_and_fractions(self):
        self.assertEqual(
            mathmd.to_plain(r"E_n = \frac{n^2 \pi^2 \hbar^2}{2ma^2}"),
            "Eₙ = (n² π² ℏ²)/(2ma²)",
        )

    def test_plain_renders_roots_and_functions(self):
        self.assertEqual(
            mathmd.to_plain(r"\psi_n = \sqrt{\frac{2}{a}} \sin\left(\frac{n\pi x}{a}\right)"),
            "ψₙ = √(2/a) sin(nπx/a)",
        )

    def test_markup_uses_reportlab_script_tags(self):
        self.assertEqual(mathmd.to_markup("E_n = n^2"), "E<sub>n</sub> = n<super>2</super>")

    def test_markup_escapes_text(self):
        self.assertEqual(mathmd.to_markup(r"a < b \& c"), "a &lt; b &amp; c")

    def test_unknown_command_falls_back_to_its_name(self):
        self.assertEqual(mathmd.to_plain(r"\widetilde{x}"), "widetildex")

    def test_bracketing_keeps_fraction_meaning(self):
        self.assertEqual(mathmd.to_plain(r"\frac{a}{b}"), "a/b")
        self.assertEqual(mathmd.to_plain(r"\frac{a+b}{c+d}"), "(a+b)/(c+d)")


if __name__ == "__main__":
    unittest.main()
