package com.example.mobile

import com.example.mobile.ui.axiom.MdBlock
import com.example.mobile.ui.axiom.MdInline
import com.example.mobile.ui.axiom.MarkdownParser
import org.junit.Assert.assertEquals
import org.junit.Test

class MarkdownParserTest {
    @Test
    fun parsesImportantTermHighlights() {
        val blocks = MarkdownParser.parse("Apply ==Ohm's law==. ==Current remains constant in a series circuit.==")

        assertEquals(
            listOf(
                MdBlock.Paragraph(
                    listOf(
                        MdInline.Text("Apply "),
                        MdInline.Highlight("Ohm's law"),
                        MdInline.Text(". "),
                        MdInline.Highlight("Current remains constant in a series circuit."),
                    )
                )
            ),
            blocks,
        )
        assertEquals(
            "Apply Ohm's law. Current remains constant in a series circuit.",
            MarkdownParser.strip("Apply ==Ohm's law==. ==Current remains constant in a series circuit.=="),
        )
    }


    @Test
    fun headingLosesHashes() {
        val blocks = MarkdownParser.parse("## Photosynthesis")
        assertEquals(listOf(MdBlock.Heading(2, listOf(MdInline.Text("Photosynthesis")))), blocks)
    }

    @Test
    fun boldAndItalicBecomeSpans() {
        val blocks = MarkdownParser.parse("The **mitochondria** is *important*.")
        assertEquals(
            listOf(
                MdBlock.Paragraph(
                    listOf(
                        MdInline.Text("The "),
                        MdInline.Bold("mitochondria"),
                        MdInline.Text(" is "),
                        MdInline.Italic("important"),
                        MdInline.Text("."),
                    )
                )
            ),
            blocks,
        )
    }

    @Test
    fun bulletsKeepTextOnly() {
        val blocks = MarkdownParser.parse("- first\n* second\n1. third")
        assertEquals(
            listOf(
                MdBlock.Bullet("•", listOf(MdInline.Text("first"))),
                MdBlock.Bullet("•", listOf(MdInline.Text("second"))),
                MdBlock.Bullet("1.", listOf(MdInline.Text("third"))),
            ),
            blocks,
        )
    }

    @Test
    fun linkShowsTextNotUrl() {
        val blocks = MarkdownParser.parse("See [source: notes p. 3](/notes?note=7) here")
        assertEquals(
            listOf(
                MdBlock.Paragraph(
                    listOf(
                        MdInline.Text("See "),
                        MdInline.Link("source: notes p. 3", "/notes?note=7"),
                        MdInline.Text(" here"),
                    )
                )
            ),
            blocks,
        )
    }

    @Test
    fun doubleBracketCitationShowsLabel() {
        val blocks = MarkdownParser.parse("Answer [[source: physics.pdf p. 2]](/notes?note=4).")
        assertEquals(
            listOf(
                MdBlock.Paragraph(
                    listOf(
                        MdInline.Text("Answer "),
                        MdInline.Link("source: physics.pdf p. 2", "/notes?note=4"),
                        MdInline.Text("."),
                    )
                )
            ),
            blocks,
        )
    }

    @Test
    fun inlineCodeAndFences() {
        val blocks = MarkdownParser.parse("Use `sqrt`\n```\nx = 1\ny = 2\n```")
        assertEquals(
            listOf(
                MdBlock.Paragraph(listOf(MdInline.Text("Use "), MdInline.Code("sqrt"))),
                MdBlock.Code("x = 1\ny = 2"),
            ),
            blocks,
        )
    }

    @Test
    fun horizontalRuleAndQuote() {
        val blocks = MarkdownParser.parse("---\n> keep in mind")
        assertEquals(
            listOf(
                MdBlock.Rule,
                MdBlock.Quote(listOf(MdInline.Text("keep in mind"))),
            ),
            blocks,
        )
    }

    @Test
    fun unterminatedMarkersStayLiteral() {
        val blocks = MarkdownParser.parse("2 * 3 = 6 and a_b")
        assertEquals(
            listOf(MdBlock.Paragraph(listOf(MdInline.Text("2 * 3 = 6 and a_b")))),
            blocks,
        )
    }

    @Test
    fun stripFlattensToPlainText() {
        val plain = MarkdownParser.strip("## Title\n- **bold** point\nSee [here](/x)")
        assertEquals("Title • bold point See here", plain)
    }
}
