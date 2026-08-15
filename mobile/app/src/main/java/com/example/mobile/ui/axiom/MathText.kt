package com.example.mobile.ui.axiom

/**
 * Renders the LaTeX subset that generated notes contain as readable Unicode.
 *
 * Notes arrive as Markdown with maths in `$…$` spans. The web reader typesets
 * those with KaTeX and the PDF exporter renders them with ReportLab script
 * tags; on mobile the minimal parser has no maths engine, so without this a
 * reader saw raw `$\frac{n^2\pi^2}{2ma^2}$`.
 *
 * This mirrors `backend/core/mathmd.py` — same symbol tables, same flattening
 * rules — so a formula reads the same on every surface.
 */
object MathText {
    /** `$$…$$` first, so display maths is never read as two empty inline spans. */
    private val mathSpan = Regex("\\$\\$([\\s\\S]+?)\\$\\$|\\$([^$\n]+?)\\$")

    private val symbols = mapOf(
        "alpha" to "α", "beta" to "β", "gamma" to "γ", "delta" to "δ",
        "epsilon" to "ε", "varepsilon" to "ε", "zeta" to "ζ", "eta" to "η",
        "theta" to "θ", "vartheta" to "ϑ", "iota" to "ι", "kappa" to "κ",
        "lambda" to "λ", "mu" to "μ", "nu" to "ν", "xi" to "ξ", "pi" to "π",
        "rho" to "ρ", "sigma" to "σ", "tau" to "τ", "upsilon" to "υ",
        "phi" to "φ", "varphi" to "ϕ", "chi" to "χ", "psi" to "ψ", "omega" to "ω",
        "Gamma" to "Γ", "Delta" to "Δ", "Theta" to "Θ", "Lambda" to "Λ",
        "Xi" to "Ξ", "Pi" to "Π", "Sigma" to "Σ", "Upsilon" to "Υ",
        "Phi" to "Φ", "Psi" to "Ψ", "Omega" to "Ω",
        "hbar" to "ℏ", "hslash" to "ℏ", "ell" to "ℓ", "infty" to "∞",
        "partial" to "∂", "nabla" to "∇", "int" to "∫", "iint" to "∬",
        "oint" to "∮", "sum" to "∑", "prod" to "∏", "surd" to "√",
        "times" to "×", "div" to "÷", "cdot" to "⋅", "cdots" to "⋯",
        "ldots" to "…", "dots" to "…", "dotsc" to "…", "vdots" to "⋮",
        "pm" to "±", "mp" to "∓", "le" to "≤", "leq" to "≤", "ge" to "≥",
        "geq" to "≥", "ne" to "≠", "neq" to "≠", "ll" to "≪", "gg" to "≫",
        "approx" to "≈", "sim" to "∼", "simeq" to "≃", "equiv" to "≡",
        "propto" to "∝", "perp" to "⊥", "parallel" to "∥", "angle" to "∠",
        "degree" to "°", "to" to "→", "rightarrow" to "→",
        "longrightarrow" to "⟶", "leftarrow" to "←", "longleftarrow" to "⟵",
        "leftrightarrow" to "↔", "Rightarrow" to "⇒", "Leftarrow" to "⇐",
        "Leftrightarrow" to "⇔", "mapsto" to "↦", "uparrow" to "↑",
        "downarrow" to "↓", "in" to "∈", "notin" to "∉", "ni" to "∋",
        "subset" to "⊂", "subseteq" to "⊆", "supset" to "⊃", "supseteq" to "⊇",
        "cup" to "∪", "cap" to "∩", "emptyset" to "∅", "varnothing" to "∅",
        "forall" to "∀", "exists" to "∃", "neg" to "¬", "wedge" to "∧",
        "vee" to "∨", "oplus" to "⊕", "otimes" to "⊗", "star" to "⋆",
        "circ" to "∘", "bullet" to "•", "prime" to "′", "dagger" to "†",
        "langle" to "⟨", "rangle" to "⟩", "lfloor" to "⌊", "rfloor" to "⌋",
        "lceil" to "⌈", "rceil" to "⌉", "aleph" to "ℵ",
    )

    /** Set upright, exactly as a maths textbook does. */
    private val functions = setOf(
        "sin", "cos", "tan", "cot", "sec", "csc", "sinh", "cosh", "tanh",
        "arcsin", "arccos", "arctan", "log", "ln", "lg", "exp", "lim",
        "limsup", "liminf", "max", "min", "sup", "inf", "det", "dim", "ker",
        "deg", "gcd", "arg", "mod", "bmod", "pmod", "Pr",
    )

    /** Commands whose only job is styling or spacing. */
    private val takesArgument = setOf(
        "text", "textrm", "textit", "textbf", "textsf", "texttt", "mathrm",
        "mathit", "mathbf", "mathsf", "mathtt", "mathcal", "mathbb",
        "mathfrak", "mathop", "operatorname", "boldsymbol", "bm", "phantom",
        "hphantom", "vphantom", "mathrel", "mathbin",
    )
    private val spacers = setOf("quad", "qquad", "space", "thinspace")
    private val ignored = setOf(
        "displaystyle", "textstyle", "scriptstyle", "limits", "nolimits",
        "notag", "nonumber",
    )
    private val delimiterSizes = setOf("left", "right", "big", "Big", "bigg", "Bigg", "middle")

    private val superscripts = mapOf(
        '0' to '⁰', '1' to '¹', '2' to '²', '3' to '³', '4' to '⁴', '5' to '⁵',
        '6' to '⁶', '7' to '⁷', '8' to '⁸', '9' to '⁹', '+' to '⁺', '-' to '⁻',
        '=' to '⁼', '(' to '⁽', ')' to '⁾', 'n' to 'ⁿ', 'i' to 'ⁱ',
    )
    private val subscripts = mapOf(
        '0' to '₀', '1' to '₁', '2' to '₂', '3' to '₃', '4' to '₄', '5' to '₅',
        '6' to '₆', '7' to '₇', '8' to '₈', '9' to '₉', '+' to '₊', '-' to '₋',
        '=' to '₌', '(' to '₍', ')' to '₎', 'a' to 'ₐ', 'e' to 'ₑ', 'h' to 'ₕ',
        'i' to 'ᵢ', 'j' to 'ⱼ', 'k' to 'ₖ', 'l' to 'ₗ', 'm' to 'ₘ', 'n' to 'ₙ',
        'o' to 'ₒ', 'p' to 'ₚ', 'r' to 'ᵣ', 's' to 'ₛ', 't' to 'ₜ', 'u' to 'ᵤ',
        'v' to 'ᵥ', 'x' to 'ₓ',
    )
    private val scriptChars = (superscripts.values + subscripts.values).joinToString("")
    // Java's \w is ASCII-only, and a rendered term is full of Greek letters.
    private const val WORD = "\\p{L}\\p{N}_"
    private val simpleTerm = Regex("[$WORD.$scriptChars]+")
    private val singleFactor = Regex("[$WORD][$scriptChars]*")

    private val escapedLiterals = mapOf(
        '{' to "{", '}' to "}", '$' to "\$", '%' to "%", '&' to "&",
        '#' to "#", '_' to "_", '|' to "|", '\\' to "\n",
    )
    private val functionGap = Regex("(${functions.sortedByDescending { it.length }.joinToString("|")}) \\(")

    private val inlineCode = Regex("`[^`\n]+`")
    private val breakTag = Regex("<br\\s*/?>", RegexOption.IGNORE_CASE)
    private val parenMath = Regex("\\\\\\(([\\s\\S]+?)\\\\\\)")
    private val bracketMath = Regex("\\\\\\[([\\s\\S]+?)\\\\]")

    /**
     * Replace every maths span in a Markdown line with its rendered form.
     *
     * Older notes still carry `\(…\)` and `<br>`, which the backend now
     * normalizes at generation time; both are handled here so a note written
     * before that still reads correctly. Inline code is left untouched: a note
     * may legitimately show LaTeX source.
     */
    fun render(markdown: String): String {
        if (!markdown.contains('$') && !markdown.contains('\\') && !markdown.contains('<')) {
            return markdown
        }
        val prepared = breakTag.replace(markdown, " ")
            .let { bracketMath.replace(it) { match -> "$$${match.groupValues[1]}$$" } }
            .let { parenMath.replace(it) { match -> "$${match.groupValues[1]}$" } }
        val out = StringBuilder()
        var cursor = 0
        for (code in inlineCode.findAll(prepared)) {
            out.append(renderSpans(prepared.substring(cursor, code.range.first)))
            out.append(code.value)
            cursor = code.range.last + 1
        }
        out.append(renderSpans(prepared.substring(cursor)))
        return out.toString()
    }

    private fun renderSpans(markdown: String): String =
        if (!markdown.contains('$')) markdown
        else mathSpan.replace(markdown) { match ->
            toPlain(match.groupValues[1].ifEmpty { match.groupValues[2] })
        }

    /** Render a LaTeX subset as plain Unicode text. */
    fun toPlain(latex: String): String {
        val out = StringBuilder()
        var index = 0
        while (index < latex.length) {
            when (val char = latex[index]) {
                '\\' -> index = renderCommand(latex, index, out)
                '^', '_' -> {
                    val (argument, next) = readArgument(latex, index + 1)
                    out.append(renderScript(argument, char == '^'))
                    index = next
                }
                '{', '}' -> index++
                '&', '~' -> { out.append(' '); index++ }
                else -> { out.append(char); index++ }
            }
        }
        val rendered = out.toString().replace(Regex(" {2,}"), " ").trim()
        // `\sin\left(x\right)` reads as "sin(x)", not "sin (x)".
        return functionGap.replace(rendered) { "${it.groupValues[1]}(" }
    }

    /** Render the command starting at the backslash on [start]; returns the next index. */
    private fun renderCommand(latex: String, start: Int, out: StringBuilder): Int {
        var index = start + 1
        if (index >= latex.length) return index
        if (!latex[index].isLetter()) {
            val literal = escapedLiterals[latex[index]] ?: latex[index].toString()
            out.append(if (literal == "\n") "\n" else literal)
            return index + 1
        }

        val nameStart = index
        while (index < latex.length && latex[index].isLetter()) index++
        val name = latex.substring(nameStart, index)
        // TeX swallows the space that terminates a control word. Letter-like
        // symbols want that — `\pi x` is "πx" — but a relation or operator
        // still needs breathing room, so `\geq a` stays "≥ a".
        val separated = index < latex.length && latex[index] == ' '
        while (index < latex.length && latex[index] == ' ') index++

        when {
            name in setOf("frac", "dfrac", "tfrac", "cfrac") -> {
                val (numerator, afterNumerator) = readArgument(latex, index)
                val (denominator, afterDenominator) = readArgument(latex, afterNumerator)
                // A multi-factor denominator must be parenthesised or the
                // flattened fraction changes meaning: n²/(2ma²) is not n²/2·m·a².
                out.append(bracket(numerator, group = false))
                out.append('/')
                out.append(bracket(denominator, group = true))
                return afterDenominator
            }
            name == "sqrt" -> {
                val (degree, afterDegree) = readOptional(latex, index)
                val (radicand, afterRadicand) = readArgument(latex, afterDegree)
                if (degree.isNotEmpty()) out.append(renderScript(degree, superscript = true))
                out.append('√').append(bracket(radicand, group = false))
                return afterRadicand
            }
            name in delimiterSizes -> {
                if (index < latex.length && latex[index] == '\\') return renderCommand(latex, index, out)
                if (index < latex.length) {
                    if (latex[index] != '.') out.append(latex[index])
                    return index + 1
                }
                return index
            }
            name in setOf("begin", "end") -> {
                out.append('\n')
                return readArgument(latex, index).second
            }
            name in takesArgument -> {
                val (argument, next) = readArgument(latex, index)
                out.append(toPlain(argument))
                return next
            }
            name in spacers -> { out.append(' '); return index }
            name in ignored -> return index
            name in functions -> { out.append(name).append(' '); return index }
            else -> {
                val symbol = symbols[name]
                if (symbol != null) {
                    out.append(symbol)
                    if (separated && !symbol.all { it.isLetter() }) out.append(' ')
                } else {
                    // An unknown command reads better as its own name than as raw TeX.
                    out.append(name)
                    if (separated) out.append(' ')
                }
                return index
            }
        }
    }

    /** Read the argument at [start]: a brace group, a command, or a single char. */
    private fun readArgument(latex: String, start: Int): Pair<String, Int> {
        var index = start
        while (index < latex.length && latex[index] == ' ') index++
        if (index >= latex.length) return "" to index
        if (latex[index] == '{') {
            var depth = 1
            val bodyStart = ++index
            while (index < latex.length && depth > 0) {
                when {
                    latex[index] == '\\' -> { index++ }
                    latex[index] == '{' -> depth++
                    latex[index] == '}' -> depth--
                }
                index++
            }
            val bodyEnd = if (depth == 0) index - 1 else index
            return latex.substring(bodyStart, bodyEnd.coerceAtMost(latex.length)) to index
        }
        if (latex[index] == '\\') {
            val commandStart = index++
            while (index < latex.length && latex[index].isLetter()) index++
            val end = if (index > commandStart + 1) index else (commandStart + 2).coerceAtMost(latex.length)
            return latex.substring(commandStart, end) to end
        }
        return latex[index].toString() to index + 1
    }

    /** Read a `[…]` option, as in `\sqrt[3]{x}`. */
    private fun readOptional(latex: String, start: Int): Pair<String, Int> {
        var index = start
        while (index < latex.length && latex[index] == ' ') index++
        if (index >= latex.length || latex[index] != '[') return "" to index
        val close = latex.indexOf(']', index)
        if (close == -1) return "" to index
        return latex.substring(index + 1, close) to close + 1
    }

    private fun renderScript(latex: String, superscript: Boolean): String {
        val inner = toPlain(latex)
        if (inner.isEmpty()) return ""
        val table = if (superscript) superscripts else subscripts
        if (inner.all { it in table }) return inner.map { table.getValue(it) }.joinToString("")
        val marker = if (superscript) "^" else "_"
        return marker + if (inner.length == 1) inner else "($inner)"
    }

    /**
     * Render a fraction part or radicand, parenthesised when it is compound.
     * [group] parenthesises anything beyond a single scripted symbol, for
     * positions where flattening would otherwise re-associate the expression.
     */
    private fun bracket(latex: String, group: Boolean): String {
        val inner = toPlain(latex)
        val pattern = if (group) singleFactor else simpleTerm
        if (inner.length <= 1 || pattern.matches(inner)) return inner
        if (inner.startsWith("(") && inner.endsWith(")")) return inner
        return "($inner)"
    }
}
