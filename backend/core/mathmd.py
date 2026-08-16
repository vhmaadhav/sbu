"""Normalize the math notation LLMs emit, and render it where KaTeX cannot run.

Generated notes mix every math dialect a model has ever seen: ``$x$``, ``\\(x\\)``,
```` ```math ```` fences, bare ``\\frac{a}{b}`` dropped into a sentence, and stray
``<br>`` tags inside tables. The web reader only understands ``$…$`` / ``$$…$$``
(remark-math), and the PDF exporter understands no LaTeX at all — both surfaces
showed raw ``$``, backslashes and braces.

``normalize`` rewrites every dialect into the single ``$…$`` form, and
``to_markup`` / ``to_plain`` render that LaTeX subset for surfaces without a math
engine. Fenced and inline code is never touched: a note may legitimately show
LaTeX source.
"""
from __future__ import annotations

import re
from html import escape

__all__ = ["normalize", "to_markup", "to_plain", "MATH_SPAN"]

# ``$$…$$`` first: the alternation is ordered so display math is never read as
# two empty inline spans.
MATH_SPAN = re.compile(r"\$\$(.+?)\$\$|\$([^$\n]+?)\$", re.DOTALL)

_FENCE = re.compile(r"(?ms)^([ \t]*)```([^\n`]*)\n(.*?)^[ \t]*```[ \t]*$")
_MATH_FENCE_LANGS = {"math", "latex", "tex"}
_INLINE_CODE = re.compile(r"`[^`\n]+`")
_BREAK_TAG = re.compile(r"<br\s*/?>", re.IGNORECASE)
_PAREN_MATH = re.compile(r"\\\((.+?)\\\)", re.DOTALL)
_BRACKET_MATH = re.compile(r"\\\[(.+?)\\\]", re.DOTALL)

_SYMBOLS = {
    "alpha": "\u03b1", "beta": "\u03b2", "gamma": "\u03b3", "delta": "\u03b4",
    "epsilon": "\u03b5", "varepsilon": "\u03b5", "zeta": "\u03b6", "eta": "\u03b7",
    "theta": "\u03b8", "vartheta": "\u03d1", "iota": "\u03b9", "kappa": "\u03ba",
    "lambda": "\u03bb", "mu": "\u03bc", "nu": "\u03bd", "xi": "\u03be",
    "pi": "\u03c0", "rho": "\u03c1", "sigma": "\u03c3", "tau": "\u03c4",
    "upsilon": "\u03c5", "phi": "\u03c6", "varphi": "\u03d5", "chi": "\u03c7",
    "psi": "\u03c8", "omega": "\u03c9",
    "Gamma": "\u0393", "Delta": "\u0394", "Theta": "\u0398", "Lambda": "\u039b",
    "Xi": "\u039e", "Pi": "\u03a0", "Sigma": "\u03a3", "Upsilon": "\u03a5",
    "Phi": "\u03a6", "Psi": "\u03a8", "Omega": "\u03a9",
    "hbar": "\u210f", "ell": "\u2113", "infty": "\u221e", "partial": "\u2202",
    "nabla": "\u2207", "int": "\u222b", "iint": "\u222c", "oint": "\u222e",
    "sum": "\u2211", "prod": "\u220f", "surd": "\u221a",
    "times": "\u00d7", "div": "\u00f7", "cdot": "\u22c5", "cdots": "\u22ef",
    "ldots": "\u2026", "dots": "\u2026", "dotsc": "\u2026", "vdots": "\u22ee",
    "pm": "\u00b1", "mp": "\u2213", "le": "\u2264", "leq": "\u2264",
    "ge": "\u2265", "geq": "\u2265", "ne": "\u2260", "neq": "\u2260",
    "ll": "\u226a", "gg": "\u226b", "approx": "\u2248", "sim": "\u223c",
    "simeq": "\u2243", "equiv": "\u2261", "propto": "\u221d", "perp": "\u22a5",
    "parallel": "\u2225", "angle": "\u2220", "degree": "\u00b0",
    "to": "\u2192", "rightarrow": "\u2192", "longrightarrow": "\u27f6",
    "leftarrow": "\u2190", "longleftarrow": "\u27f5", "leftrightarrow": "\u2194",
    "Rightarrow": "\u21d2", "Leftarrow": "\u21d0", "Leftrightarrow": "\u21d4",
    "mapsto": "\u21a6", "uparrow": "\u2191", "downarrow": "\u2193",
    "in": "\u2208", "notin": "\u2209", "ni": "\u220b", "subset": "\u2282",
    "subseteq": "\u2286", "supset": "\u2283", "supseteq": "\u2287",
    "cup": "\u222a", "cap": "\u2229", "emptyset": "\u2205", "varnothing": "\u2205",
    "forall": "\u2200", "exists": "\u2203", "neg": "\u00ac", "wedge": "\u2227",
    "vee": "\u2228", "oplus": "\u2295", "otimes": "\u2297", "star": "\u22c6",
    "circ": "\u2218", "bullet": "\u2022", "prime": "\u2032", "dagger": "\u2020",
    "langle": "\u27e8", "rangle": "\u27e9", "lVert": "\u2016", "rVert": "\u2016",
    "lfloor": "\u230a", "rfloor": "\u230b", "lceil": "\u2308", "rceil": "\u2309",
    "aleph": "\u2135", "Re": "\u211c", "Im": "\u2111", "hslash": "\u210f",
}

# OCR and models write Planck's reduced constant as a Latin "h with stroke".
_SYMBOL_ALIASES = {"\u0127": "hbar"}

# Rendered as upright words, exactly as a maths textbook sets them.
_FUNCTIONS = {
    "sin", "cos", "tan", "cot", "sec", "csc", "sinh", "cosh", "tanh", "arcsin",
    "arccos", "arctan", "log", "ln", "lg", "exp", "lim", "limsup", "liminf",
    "max", "min", "sup", "inf", "det", "dim", "ker", "deg", "gcd", "arg", "mod",
    "bmod", "pmod", "Pr",
}

# Commands whose only job is styling or spacing: render the argument, drop the rest.
_TRANSPARENT = {
    "text", "textrm", "textit", "textbf", "textsf", "texttt", "mathrm", "mathit",
    "mathbf", "mathsf", "mathtt", "mathcal", "mathbb", "mathfrak", "mathop",
    "operatorname", "boldsymbol", "bm", "displaystyle", "textstyle", "scriptstyle",
    "limits", "nolimits", "!", ",", ";", ":", " ", "quad", "qquad", "space",
    "phantom", "hphantom", "vphantom", "notag", "nonumber", "mathrel", "mathbin",
}
_TAKES_ARG = {
    "text", "textrm", "textit", "textbf", "textsf", "texttt", "mathrm", "mathit",
    "mathbf", "mathsf", "mathtt", "mathcal", "mathbb", "mathfrak", "mathop",
    "operatorname", "boldsymbol", "bm", "phantom", "hphantom", "vphantom",
    "mathrel", "mathbin",
}
_SPACERS = {"!", ",", ";", ":", " ", "quad", "qquad", "space", "thinspace"}

_ESCAPED_LITERALS = {
    "{": "{", "}": "}", "$": "$", "%": "%", "&": "&", "#": "#", "_": "_",
    "|": "|", "\\": "\n",
}

_SUPERSCRIPTS = {
    "0": "\u2070", "1": "\u00b9", "2": "\u00b2", "3": "\u00b3", "4": "\u2074",
    "5": "\u2075", "6": "\u2076", "7": "\u2077", "8": "\u2078", "9": "\u2079",
    "+": "\u207a", "-": "\u207b", "=": "\u207c", "(": "\u207d", ")": "\u207e",
    "n": "\u207f", "i": "\u2071",
}
_SUBSCRIPTS = {
    "0": "\u2080", "1": "\u2081", "2": "\u2082", "3": "\u2083", "4": "\u2084",
    "5": "\u2085", "6": "\u2086", "7": "\u2087", "8": "\u2088", "9": "\u2089",
    "+": "\u208a", "-": "\u208b", "=": "\u208c", "(": "\u208d", ")": "\u208e",
    "a": "\u2090", "e": "\u2091", "h": "\u2095", "i": "\u1d62", "j": "\u2c7c",
    "k": "\u2096", "l": "\u2097", "m": "\u2098", "n": "\u2099", "o": "\u2092",
    "p": "\u209a", "r": "\u1d63", "s": "\u209b", "t": "\u209c", "u": "\u1d64",
    "v": "\u1d65", "x": "\u2093",
}

# Models routinely emit already-typeset Unicode inside a math span; KaTeX rejects
# most of it, so map it back to the command it stands for.
_UNICODE_TO_COMMAND = {
    symbol: name for name, symbol in _SYMBOLS.items()
    if len(symbol) == 1 and name not in {"Re", "Im", "in", "to", "ni", "mod"}
}
_UNICODE_TO_COMMAND.update(
    {symbol: name for symbol, name in _SYMBOL_ALIASES.items()}
)
_UNICODE_SYMBOL = re.compile(f"[{''.join(re.escape(c) for c in _UNICODE_TO_COMMAND)}]")
_UNICODE_SUPERSCRIPT = {value: key for key, value in _SUPERSCRIPTS.items()}
_UNICODE_SUBSCRIPT = {value: key for key, value in _SUBSCRIPTS.items()}
_UNICODE_SUPER_RUN = re.compile(f"[{''.join(_UNICODE_SUPERSCRIPT)}]+")
_UNICODE_SUB_RUN = re.compile(f"[{''.join(_UNICODE_SUBSCRIPT)}]+")

# Characters that may continue a bare LaTeX run once one has started.
_RUN_CHARS = set("+-*/=<>.,'|!()[]^_ ")
_RUN_AFTER_SPACE = set("\\^_+-=<>*/")

_FUNCTION_GAP = re.compile(f"({'|'.join(sorted(_FUNCTIONS, key=len, reverse=True))}) \\(")
# A single multiplied term such as ``2ma²`` needs no parentheses in ``a/b``.
_SCRIPT_CHARS = "".join(
    re.escape(c) for c in {*_SUPERSCRIPTS.values(), *_SUBSCRIPTS.values()}
)
_SIMPLE_TERM = re.compile(f"[\\w.{_SCRIPT_CHARS}]+")
# One symbol, optionally scripted: safe to leave bare even under a fraction bar.
_SINGLE_FACTOR = re.compile(f"\\w[{_SCRIPT_CHARS}]*")


# --------------------------------------------------------------------------- #
# Normalization
# --------------------------------------------------------------------------- #

def normalize(markdown: str) -> str:
    """Rewrite every math dialect in ``markdown`` as ``$…$`` / ``$$…$$``."""
    pieces: list[str] = []
    cursor = 0
    for fence in _FENCE.finditer(markdown):
        pieces.append(_normalize_prose(markdown[cursor:fence.start()]))
        pieces.append(_normalize_fence(fence))
        cursor = fence.end()
    pieces.append(_normalize_prose(markdown[cursor:]))
    return "".join(pieces)


def _normalize_fence(fence: re.Match) -> str:
    """Turn a ```` ```math ```` fence into display math; leave real code alone."""
    indent, language, body = fence.group(1), fence.group(2).strip().lower(), fence.group(3)
    if language not in _MATH_FENCE_LANGS:
        return fence.group(0)
    lines = [line for line in body.strip().split("\n") if line.strip()]
    if not lines:
        return ""
    formulas = "\n".join(f"{indent}{_clean_math(line)}" for line in lines)
    return f"{indent}$$\n{formulas}\n{indent}$$"


def _normalize_prose(text: str) -> str:
    """Normalize one run of Markdown that contains no fenced code block."""
    if not text:
        return text
    text = _BREAK_TAG.sub(" ", text)
    text = _BRACKET_MATH.sub(lambda m: f"$${m.group(1)}$$", text)
    text = _PAREN_MATH.sub(lambda m: f"${m.group(1)}$", text)
    return "".join(
        segment if is_code else _normalize_math_spans(segment)
        for segment, is_code in _split_inline_code(text)
    )


def _split_inline_code(text: str) -> list[tuple[str, bool]]:
    segments: list[tuple[str, bool]] = []
    cursor = 0
    for code in _INLINE_CODE.finditer(text):
        segments.append((text[cursor:code.start()], False))
        segments.append((code.group(0), True))
        cursor = code.end()
    segments.append((text[cursor:], False))
    return segments


def _normalize_math_spans(text: str) -> str:
    """Tidy existing math spans and promote bare LaTeX between them."""
    pieces: list[str] = []
    cursor = 0
    for span in MATH_SPAN.finditer(text):
        pieces.append(_wrap_bare_latex(text[cursor:span.start()]))
        body = _clean_math(span.group(1) if span.group(1) is not None else span.group(2))
        if body:
            pieces.append(f"$${body}$$" if span.group(1) is not None else f"${body}$")
        cursor = span.end()
    pieces.append(_wrap_bare_latex(text[cursor:]))
    return "".join(pieces)


def _clean_math(latex: str) -> str:
    """Make one math body safe for KaTeX: no stray padding, no typeset Unicode."""
    body = latex.strip()
    if not body:
        return ""
    body = _UNICODE_SUPER_RUN.sub(
        lambda m: "^{" + "".join(_UNICODE_SUPERSCRIPT[c] for c in m.group(0)) + "}", body
    )
    body = _UNICODE_SUB_RUN.sub(
        lambda m: "_{" + "".join(_UNICODE_SUBSCRIPT[c] for c in m.group(0)) + "}", body
    )
    # A command needs a separator before a letter or digit, but a space before
    # ``^``/``_`` would detach the script from the symbol it belongs to.
    source = body
    body = _UNICODE_SYMBOL.sub(
        lambda m: f"\\{_UNICODE_TO_COMMAND[m.group(0)]}"
        + (" " if m.end() < len(source) and source[m.end()].isalnum() else ""),
        source,
    )
    return re.sub(r"[ \t]{2,}", " ", body).strip()


def _wrap_bare_latex(text: str) -> str:
    """Wrap ``\\frac{a}{b}`` style runs that were written outside any ``$…$``."""
    if "\\" not in text:
        return text
    out: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char != "\\" or index + 1 >= length or not text[index + 1].isalpha():
            out.append(char)
            index += 1
            continue
        end = _latex_run_end(text, index)
        run = text[index:end].rstrip(" ,.;:")
        end = index + len(run)
        body = _clean_math(run)
        out.append(f"${body}$" if body else run)
        index = end
    return "".join(out)


def _latex_run_end(text: str, start: int) -> int:
    """Index just past the LaTeX run that begins at the backslash on ``start``."""
    index, length, depth = start, len(text), 0
    while index < length:
        char = text[index]
        if char == "\\" and index + 1 < length:
            index += 1
            if text[index].isalpha():
                while index < length and text[index].isalpha():
                    index += 1
            else:
                index += 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            if depth == 0:
                break
            depth -= 1
        elif depth == 0:
            if char == " ":
                probe = index
                while probe < length and text[probe] == " ":
                    probe += 1
                # A run only survives a space when the next token is unmistakably
                # math; otherwise the space ends the formula and prose resumes.
                if probe < length and text[probe] in _RUN_AFTER_SPACE:
                    index = probe
                    continue
                break
            if not (char.isalnum() or char in _RUN_CHARS):
                break
        index += 1
    return index


# --------------------------------------------------------------------------- #
# Rendering for surfaces without a math engine
# --------------------------------------------------------------------------- #

def to_markup(latex: str) -> str:
    """Render a LaTeX subset as ReportLab paragraph markup (escaped, with tags)."""
    return _render(latex, markup=True)


def to_plain(latex: str) -> str:
    """Render a LaTeX subset as plain Unicode text."""
    return _render(latex, markup=False)


def _render(latex: str, *, markup: bool) -> str:
    out: list[str] = []
    index, length = 0, len(latex)
    while index < length:
        char = latex[index]
        if char == "\\":
            text, index = _render_command(latex, index, markup)
            out.append(text)
            continue
        if char in "^_":
            argument, index = _read_argument(latex, index + 1)
            out.append(_render_script(argument, char == "^", markup))
            continue
        if char in "{}":
            index += 1
            continue
        if char == "&" or char == "~":
            out.append(" ")
            index += 1
            continue
        out.append(escape(char) if markup else char)
        index += 1
    rendered = re.sub(r" {2,}", " ", "".join(out)).strip()
    # ``\sin\left(x\right)`` reads as ``sin(x)``, not ``sin (x)``.
    return _FUNCTION_GAP.sub(r"\1(", rendered)


def _render_command(latex: str, index: int, markup: bool) -> tuple[str, int]:
    """Render the command starting at the backslash on ``index``."""
    index += 1
    if index >= len(latex):
        return "", index
    if not latex[index].isalpha():
        literal = _ESCAPED_LITERALS.get(latex[index], latex[index])
        rendered = ("<br/>" if markup else "\n") if literal == "\n" else (
            escape(literal) if markup else literal
        )
        return rendered, index + 1

    start = index
    while index < len(latex) and latex[index].isalpha():
        index += 1
    name = latex[start:index]
    # TeX swallows the space that terminates a control word. Letter-like
    # symbols want that — ``\pi x`` is "πx" — but a relation or operator still
    # needs breathing room, so ``\geq a`` stays "≥ a".
    separated = index < len(latex) and latex[index] == " "
    while index < len(latex) and latex[index] == " ":
        index += 1

    if name in {"frac", "dfrac", "tfrac", "cfrac"}:
        numerator, index = _read_argument(latex, index)
        denominator, index = _read_argument(latex, index)
        # A denominator of more than one term must be parenthesised or the
        # flattened fraction changes meaning: n²/(2ma²) is not n²/2·m·a².
        return (
            f"{_bracket(numerator, markup)}/{_bracket(denominator, markup, group=True)}",
            index,
        )
    if name == "sqrt":
        degree, index = _read_optional(latex, index)
        radicand, index = _read_argument(latex, index)
        root = _render_script(degree, True, markup) if degree else ""
        return f"{root}\u221a{_bracket(radicand, markup)}", index
    if name in {"left", "right", "big", "Big", "bigg", "Bigg", "middle"}:
        while index < len(latex) and latex[index] == " ":
            index += 1
        if index < len(latex) and latex[index] == "\\":
            symbol, index = _render_command(latex, index, markup)
            return symbol, index
        if index < len(latex):
            delimiter = latex[index]
            index += 1
            if delimiter == ".":
                return "", index
            return escape(delimiter) if markup else delimiter, index
        return "", index
    if name in {"begin", "end"}:
        _, index = _read_argument(latex, index)
        return ("<br/>" if markup else "\n"), index
    if name in _TRANSPARENT:
        if name in _TAKES_ARG:
            argument, index = _read_argument(latex, index)
            return _render(argument, markup=markup), index
        return " " if name in _SPACERS else "", index
    if name in _FUNCTIONS:
        return f"{name} ", index
    if name in _SYMBOLS:
        symbol = _SYMBOLS[name]
        if separated and not symbol.isalpha():
            symbol += " "
        return escape(symbol) if markup else symbol, index
    # An unknown command still reads better as its own name than as raw TeX.
    text = name + (" " if separated else "")
    return escape(text) if markup else text, index


def _read_argument(latex: str, index: int) -> tuple[str, int]:
    """Read the LaTeX argument at ``index``: a brace group, a command, or a char."""
    length = len(latex)
    while index < length and latex[index] == " ":
        index += 1
    if index >= length:
        return "", index
    if latex[index] == "{":
        depth, start = 1, index + 1
        index += 1
        while index < length and depth:
            if latex[index] == "\\":
                index += 2
                continue
            if latex[index] == "{":
                depth += 1
            elif latex[index] == "}":
                depth -= 1
            index += 1
        return latex[start:index - 1 if depth == 0 else index], index
    if latex[index] == "\\":
        start = index
        index += 1
        while index < length and latex[index].isalpha():
            index += 1
        return latex[start:index if index > start + 1 else start + 2], max(index, start + 2)
    return latex[index], index + 1


def _read_optional(latex: str, index: int) -> tuple[str, int]:
    """Read a ``[…]`` option, as in ``\\sqrt[3]{x}``."""
    length = len(latex)
    while index < length and latex[index] == " ":
        index += 1
    if index >= length or latex[index] != "[":
        return "", index
    close = latex.find("]", index)
    if close == -1:
        return "", index
    return latex[index + 1:close], close + 1


def _render_script(latex: str, superscript: bool, markup: bool) -> str:
    """Render a sub/superscript argument."""
    inner = _render(latex, markup=markup)
    if not inner:
        return ""
    if markup:
        tag = "super" if superscript else "sub"
        return f"<{tag}>{inner}</{tag}>"
    table = _SUPERSCRIPTS if superscript else _SUBSCRIPTS
    if all(char in table for char in inner):
        return "".join(table[char] for char in inner)
    return ("^" if superscript else "_") + (inner if len(inner) == 1 else f"({inner})")


def _bracket(latex: str, markup: bool, *, group: bool = False) -> str:
    """Render a fraction part or radicand, parenthesised when it is compound.

    ``group`` parenthesises anything longer than a single symbol, for positions
    where flattening would otherwise re-associate the expression.
    """
    inner = _render(latex, markup=markup)
    # Markup tags would make every term look compound, so judge the plain form.
    plain = _render(latex, markup=False) if markup else inner
    pattern = _SINGLE_FACTOR if group else _SIMPLE_TERM
    if len(plain) <= 1 or pattern.fullmatch(plain):
        return inner
    if plain.startswith("(") and plain.endswith(")"):
        return inner
    return f"({inner})"
