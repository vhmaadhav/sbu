package com.example.mobile.ui.axiom

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Inline fragments of a single markdown line. */
sealed interface MdInline {
    data class Text(val text: String) : MdInline
    data class Highlight(val text: String) : MdInline
    data class Bold(val text: String) : MdInline
    data class Italic(val text: String) : MdInline
    data class Code(val text: String) : MdInline
    data class Link(val text: String, val url: String) : MdInline
}

/** Block-level markdown structure. */
sealed interface MdBlock {
    data class Heading(val level: Int, val inlines: List<MdInline>) : MdBlock
    data class Paragraph(val inlines: List<MdInline>) : MdBlock
    data class Bullet(val marker: String, val inlines: List<MdInline>) : MdBlock
    data class Quote(val inlines: List<MdInline>) : MdBlock
    data class Code(val text: String) : MdBlock
    data object Rule : MdBlock
}

/**
 * Minimal markdown parser for LLM output: headings, bullets, numbered lists,
 * quotes, fenced/inline code, bold, italic, and links. Anything ambiguous
 * (unterminated markers, intraword underscores) stays literal text.
 */
object MarkdownParser {
    private val heading = Regex("^(#{1,6})\\s+(.*)$")
    private val bullet = Regex("^\\s*[-*+]\\s+(.*)$")
    private val ordered = Regex("^\\s*(\\d{1,3})[.)]\\s+(.*)$")
    private val rule = Regex("^\\s*(?:[-_*]\\s*){3,}$")
    private val link = Regex("\\[([^\\]]+)\\]\\(([^)\\s]*)\\)")
    private val mathFenceLanguages = setOf("math", "latex", "tex")

    // The ask endpoint emits citations as [[source: label]](target).
    private val doubleLink = Regex("\\[\\[([^\\]]+)\\]\\]\\(([^)\\s]*)\\)")

    fun parse(source: String): List<MdBlock> {
        val blocks = mutableListOf<MdBlock>()
        val lines = source.replace("\r\n", "\n").split("\n")
        var i = 0
        while (i < lines.size) {
            val trimmed = lines[i].trim()
            when {
                trimmed.isEmpty() -> Unit
                trimmed.startsWith("```") -> {
                    val language = trimmed.removePrefix("```").trim().lowercase()
                    val body = mutableListOf<String>()
                    i++
                    while (i < lines.size && !lines[i].trim().startsWith("```")) {
                        body += lines[i]
                        i++
                    }
                    // A ```math fence is a formula, not source to show verbatim.
                    if (language in mathFenceLanguages) {
                        body.filter { it.isNotBlank() }
                            .forEach { blocks += MdBlock.Paragraph(listOf(MdInline.Text(MathText.toPlain(it)))) }
                    } else {
                        blocks += MdBlock.Code(body.joinToString("\n"))
                    }
                }
                heading.matches(trimmed) -> {
                    val match = heading.matchEntire(trimmed)!!
                    blocks += MdBlock.Heading(match.groupValues[1].length, inlines(match.groupValues[2]))
                }
                rule.matches(trimmed) -> blocks += MdBlock.Rule
                trimmed.startsWith("> ") || trimmed == ">" ->
                    blocks += MdBlock.Quote(inlines(trimmed.removePrefix(">").trim()))
                bullet.matches(trimmed) ->
                    blocks += MdBlock.Bullet("•", inlines(bullet.matchEntire(trimmed)!!.groupValues[1]))
                ordered.matches(trimmed) -> {
                    val match = ordered.matchEntire(trimmed)!!
                    blocks += MdBlock.Bullet("${match.groupValues[1]}.", inlines(match.groupValues[2]))
                }
                else -> blocks += MdBlock.Paragraph(inlines(trimmed))
            }
            i++
        }
        return blocks
    }

    /** Flatten markdown to a single plain-text line (for previews). */
    fun strip(source: String): String = parse(source).joinToString(" ") { block ->
        when (block) {
            is MdBlock.Heading -> flatten(block.inlines)
            is MdBlock.Paragraph -> flatten(block.inlines)
            is MdBlock.Bullet -> "• ${flatten(block.inlines)}"
            is MdBlock.Quote -> flatten(block.inlines)
            is MdBlock.Code -> block.text.replace("\n", " ")
            MdBlock.Rule -> ""
        }
    }.replace(Regex("\\s+"), " ").trim()

    private fun flatten(inlines: List<MdInline>): String = inlines.joinToString("") {
        when (it) {
            is MdInline.Text -> it.text
            is MdInline.Highlight -> it.text
            is MdInline.Bold -> it.text
            is MdInline.Italic -> it.text
            is MdInline.Code -> it.text
            is MdInline.Link -> it.text
        }
    }

    fun inlines(source: String): List<MdInline> {
        // Formulas are typeset before any Markdown scanning: the backslashes,
        // underscores and asterisks inside `$…$` are notation, not markup.
        val text = MathText.render(source)
        val out = mutableListOf<MdInline>()
        val plain = StringBuilder()
        fun flush() {
            if (plain.isNotEmpty()) {
                out += MdInline.Text(plain.toString())
                plain.clear()
            }
        }
        var i = 0
        while (i < text.length) {
            val c = text[i]
            when {
                c == '`' -> {
                    val close = text.indexOf('`', i + 1)
                    if (close > i + 1) {
                        flush()
                        out += MdInline.Code(text.substring(i + 1, close))
                        i = close + 1
                    } else {
                        plain.append(c); i++
                    }
                }
                c == '=' && i + 1 < text.length && text[i + 1] == '=' -> {
                    val close = text.indexOf("==", i + 2)
                    if (close != -1 && text.substring(i + 2, close).isNotBlank()) {
                        flush()
                        out += MdInline.Highlight(text.substring(i + 2, close))
                        i = close + 2
                    } else {
                        plain.append(c).append(c); i += 2
                    }
                }
                c == '[' -> {
                    val match = doubleLink.matchAt(text, i) ?: link.matchAt(text, i)
                    if (match != null) {
                        flush()
                        out += MdInline.Link(match.groupValues[1], match.groupValues[2])
                        i = match.range.last + 1
                    } else {
                        plain.append(c); i++
                    }
                }
                (c == '*' || c == '_') && i + 1 < text.length && text[i + 1] == c -> {
                    val close = text.indexOf("$c$c", i + 2)
                    if (close != -1 && text.substring(i + 2, close).isNotBlank()) {
                        flush()
                        out += MdInline.Bold(text.substring(i + 2, close))
                        i = close + 2
                    } else {
                        plain.append(c).append(c); i += 2
                    }
                }
                c == '*' || c == '_' -> {
                    val close = findItalicClose(text, i, c)
                    if (close != -1) {
                        flush()
                        out += MdInline.Italic(text.substring(i + 1, close))
                        i = close + 1
                    } else {
                        plain.append(c); i++
                    }
                }
                else -> {
                    plain.append(c); i++
                }
            }
        }
        flush()
        return out
    }

    private fun findItalicClose(text: String, open: Int, marker: Char): Int {
        // Opening marker must hug the following word; '_' must also sit on a word boundary.
        if (open + 1 >= text.length || text[open + 1].isWhitespace()) return -1
        if (marker == '_' && open > 0 && text[open - 1].isLetterOrDigit()) return -1
        var j = text.indexOf(marker, open + 2)
        while (j != -1) {
            val closesWord = !text[j - 1].isWhitespace()
            val boundary = marker != '_' || j + 1 >= text.length || !text[j + 1].isLetterOrDigit()
            if (closesWord && boundary) return j
            j = text.indexOf(marker, j + 1)
        }
        return -1
    }
}

private fun annotate(inlines: List<MdInline>, colors: AxiomColors): AnnotatedString =
    buildAnnotatedString {
        inlines.forEach { inline ->
            when (inline) {
                is MdInline.Text -> append(inline.text)
                is MdInline.Highlight -> withStyle(
                    SpanStyle(fontWeight = FontWeight.Medium, background = colors.accent.copy(alpha = 0.24f))
                ) { append(inline.text) }
                // Older generated notes used bold lead terms before explicit ==highlights==
                // were introduced, so render them with the same visual emphasis.
                is MdInline.Bold -> withStyle(
                    SpanStyle(fontWeight = FontWeight.SemiBold, background = colors.accent.copy(alpha = 0.24f))
                ) { append(inline.text) }
                is MdInline.Italic -> withStyle(SpanStyle(fontStyle = FontStyle.Italic)) { append(inline.text) }
                is MdInline.Code -> withStyle(
                    SpanStyle(fontFamily = Mono, color = colors.accent, background = colors.panel2)
                ) { append(inline.text) }
                is MdInline.Link -> withStyle(SpanStyle(color = colors.accent)) { append(inline.text) }
            }
        }
    }

/** One AnnotatedString for places that need a single styled Text (flashcards, chat turns). */
fun markdownAnnotated(source: String, colors: AxiomColors): AnnotatedString =
    buildAnnotatedString {
        MarkdownParser.parse(source).forEachIndexed { index, block ->
            if (index > 0) append("\n")
            when (block) {
                is MdBlock.Heading -> withStyle(SpanStyle(fontWeight = FontWeight.SemiBold)) {
                    append(annotate(block.inlines, colors))
                }
                is MdBlock.Paragraph -> append(annotate(block.inlines, colors))
                is MdBlock.Bullet -> {
                    withStyle(SpanStyle(color = colors.accent)) { append("${block.marker} ") }
                    append(annotate(block.inlines, colors))
                }
                is MdBlock.Quote -> withStyle(SpanStyle(fontStyle = FontStyle.Italic)) {
                    append(annotate(block.inlines, colors))
                }
                is MdBlock.Code -> withStyle(SpanStyle(fontFamily = Mono)) { append(block.text) }
                MdBlock.Rule -> Unit
            }
        }
    }

/** Renders backend markdown (notes, AI answers, cards) as styled text. */
@Composable
fun MarkdownText(
    source: String,
    colors: AxiomColors,
    fontSize: TextUnit = 13.sp,
    lineHeight: TextUnit = 20.sp,
    modifier: Modifier = Modifier,
) {
    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        MarkdownParser.parse(source).forEach { block ->
            when (block) {
                is MdBlock.Heading -> Text(
                    annotate(block.inlines, colors),
                    style = TextStyle(
                        fontFamily = Sans,
                        fontSize = when (block.level) {
                            1 -> 19.sp
                            2 -> 16.sp
                            else -> 14.sp
                        },
                        fontWeight = FontWeight.SemiBold,
                        color = colors.text,
                    ),
                    modifier = Modifier.padding(top = 6.dp),
                )
                is MdBlock.Paragraph -> Text(
                    annotate(block.inlines, colors),
                    style = readingStyle(
                        TextStyle(fontFamily = Sans, fontSize = fontSize, lineHeight = lineHeight, color = colors.text)
                    ),
                )
                is MdBlock.Bullet -> Row {
                    Text(
                        block.marker,
                        style = TextStyle(fontFamily = Mono, fontSize = fontSize, lineHeight = lineHeight, color = colors.accent),
                        modifier = Modifier.padding(end = 8.dp),
                    )
                    Text(
                        annotate(block.inlines, colors),
                        style = readingStyle(
                            TextStyle(fontFamily = Sans, fontSize = fontSize, lineHeight = lineHeight, color = colors.text)
                        ),
                    )
                }
                is MdBlock.Quote -> Text(
                    annotate(block.inlines, colors),
                    style = TextStyle(
                        fontFamily = Sans, fontSize = fontSize, lineHeight = lineHeight,
                        fontStyle = FontStyle.Italic, color = colors.dim,
                    ),
                    modifier = Modifier
                        .drawBehind { drawRect(colors.accent, size = Size(2.dp.toPx(), size.height)) }
                        .padding(start = 10.dp),
                )
                is MdBlock.Code -> Text(
                    block.text,
                    style = TextStyle(fontFamily = Mono, fontSize = (fontSize.value - 1).sp, lineHeight = lineHeight, color = colors.text),
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(colors.panel2)
                        .padding(10.dp),
                )
                MdBlock.Rule -> HairlineDivider(colors.line)
            }
        }
    }
}
