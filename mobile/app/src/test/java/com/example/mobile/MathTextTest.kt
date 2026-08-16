package com.example.mobile

import com.example.mobile.ui.axiom.MathText
import com.example.mobile.ui.axiom.MdBlock
import com.example.mobile.ui.axiom.MdInline
import com.example.mobile.ui.axiom.MarkdownParser
import org.junit.Assert.assertEquals
import org.junit.Test

class MathTextTest {

    @Test
    fun rendersScriptsSymbolsAndFractions() {
        assertEquals("Eₙ = (n² π² ℏ²)/(2ma²)", MathText.toPlain("E_n = \\frac{n^2 \\pi^2 \\hbar^2}{2ma^2}"))
    }

    @Test
    fun rendersRootsAndFunctions() {
        assertEquals(
            "ψₙ = √(2/a) sin(nπx/a)",
            MathText.toPlain("\\psi_n = \\sqrt{\\frac{2}{a}} \\sin\\left(\\frac{n\\pi x}{a}\\right)"),
        )
    }

    @Test
    fun keepsFractionMeaning() {
        assertEquals("a/b", MathText.toPlain("\\frac{a}{b}"))
        assertEquals("(a+b)/(c+d)", MathText.toPlain("\\frac{a+b}{c+d}"))
    }

    @Test
    fun unknownCommandFallsBackToItsName() {
        assertEquals("widetildex", MathText.toPlain("\\widetilde{x}"))
    }

    @Test
    fun renderReplacesEveryDelimiterDialect() {
        assertEquals("Energy Eₙ obeys Eₙ = n² exactly.", MathText.render("Energy \\(E_n\\) obeys \$E_n = n^2\$ exactly."))
    }

    @Test
    fun renderLeavesInlineCodeAlone() {
        val source = "Write `\\frac{a}{b}` to divide."
        assertEquals(source, MathText.render(source))
    }

    @Test
    fun renderDropsBreakTags() {
        assertEquals("a b c", MathText.render("a<br>b<br />c"))
    }

    @Test
    fun parserTypesetsMathInsteadOfShowingLatex() {
        val blocks = MarkdownParser.parse("The energy is \$E_n = n^2\$.")
        assertEquals(listOf(MdBlock.Paragraph(listOf(MdInline.Text("The energy is Eₙ = n².")))), blocks)
    }

    @Test
    fun parserTypesetsMathFencesInsteadOfShowingCode() {
        val blocks = MarkdownParser.parse("```math\nE_n = \\frac{n^2}{2}\n```")
        assertEquals(listOf(MdBlock.Paragraph(listOf(MdInline.Text("Eₙ = n²/2")))), blocks)
    }

    @Test
    fun parserStillShowsRealCodeVerbatim() {
        val blocks = MarkdownParser.parse("```python\nx = a_b * c\n```")
        assertEquals(listOf(MdBlock.Code("x = a_b * c")), blocks)
    }
}
