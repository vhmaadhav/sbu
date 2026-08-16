// Normalize the math notation generated notes contain into the single dialect
// remark-math understands: `$…$` for inline, `$$…$$` for display.
//
// Models mix every dialect they have seen — `\(x\)`, ```math fences, and bare
// `\frac{a}{b}` dropped straight into a sentence — and none of those reach
// KaTeX, so the reader saw raw backslashes and braces. This mirrors the
// backend's `core/mathmd.py`, which normalizes at generation time; the port
// exists because notes written before that landed are still in the database.
//
// Fenced and inline code is never touched: a note may legitimately show LaTeX
// source.

// `$$…$$` is matched first so display math is never read as two empty spans.
export const MATH_SPAN = /\$\$([\s\S]+?)\$\$|\$([^$\n]+?)\$/g;

const FENCE = /^([ \t]*)```([^\n`]*)\n([\s\S]*?)^[ \t]*```[ \t]*$/gm;
const MATH_FENCE_LANGS = new Set(["math", "latex", "tex"]);
const INLINE_CODE = /`[^`\n]+`/g;
const BREAK_TAG = /<br\s*\/?>/gi;
const PAREN_MATH = /\\\(([\s\S]+?)\\\)/g;
const BRACKET_MATH = /\\\[([\s\S]+?)\\\]/g;

// Already-typeset Unicode inside a math span: KaTeX rejects most of it, so map
// it back to the command it stands for.
const UNICODE_TO_COMMAND: Record<string, string> = {
  "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon",
  "ζ": "zeta", "η": "eta", "θ": "theta", "ι": "iota", "κ": "kappa",
  "λ": "lambda", "μ": "mu", "ν": "nu", "ξ": "xi", "π": "pi", "ρ": "rho",
  "σ": "sigma", "τ": "tau", "υ": "upsilon", "φ": "phi", "χ": "chi",
  "ψ": "psi", "ω": "omega", "Γ": "Gamma", "Δ": "Delta", "Θ": "Theta",
  "Λ": "Lambda", "Ξ": "Xi", "Π": "Pi", "Σ": "Sigma", "Υ": "Upsilon",
  "Φ": "Phi", "Ψ": "Psi", "Ω": "Omega",
  "ℏ": "hbar", "ħ": "hbar", "ℓ": "ell", "∞": "infty", "∂": "partial",
  "∇": "nabla", "∫": "int", "∬": "iint", "∮": "oint", "∑": "sum",
  "∏": "prod", "√": "surd", "×": "times", "÷": "div", "⋅": "cdot",
  "⋯": "cdots", "…": "ldots", "±": "pm", "∓": "mp", "≤": "le", "≥": "ge",
  "≠": "ne", "≪": "ll", "≫": "gg", "≈": "approx", "∼": "sim", "≃": "simeq",
  "≡": "equiv", "∝": "propto", "⊥": "perp", "∥": "parallel", "∠": "angle",
  "→": "rightarrow", "⟶": "longrightarrow", "←": "leftarrow",
  "↔": "leftrightarrow", "⇒": "Rightarrow", "⇐": "Leftarrow",
  "⇔": "Leftrightarrow", "↦": "mapsto", "↑": "uparrow", "↓": "downarrow",
  "∈": "in", "∉": "notin", "⊂": "subset", "⊆": "subseteq", "⊃": "supset",
  "⊇": "supseteq", "∪": "cup", "∩": "cap", "∅": "emptyset", "∀": "forall",
  "∃": "exists", "¬": "neg", "∧": "wedge", "∨": "vee", "⊕": "oplus",
  "⊗": "otimes", "∘": "circ", "′": "prime", "⟨": "langle", "⟩": "rangle",
};
const UNICODE_SYMBOL = new RegExp(`[${Object.keys(UNICODE_TO_COMMAND).join("")}]`, "g");

const SUPERSCRIPTS: Record<string, string> = {
  "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6",
  "⁷": "7", "⁸": "8", "⁹": "9", "⁺": "+", "⁻": "-", "⁼": "=", "⁽": "(",
  "⁾": ")", "ⁿ": "n", "ⁱ": "i",
};
const SUBSCRIPTS: Record<string, string> = {
  "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4", "₅": "5", "₆": "6",
  "₇": "7", "₈": "8", "₉": "9", "₊": "+", "₋": "-", "₌": "=", "₍": "(",
  "₎": ")", "ₐ": "a", "ₑ": "e", "ₕ": "h", "ᵢ": "i", "ⱼ": "j", "ₖ": "k",
  "ₗ": "l", "ₘ": "m", "ₙ": "n", "ₒ": "o", "ₚ": "p", "ᵣ": "r", "ₛ": "s",
  "ₜ": "t", "ᵤ": "u", "ᵥ": "v", "ₓ": "x",
};
const SUPER_RUN = new RegExp(`[${Object.keys(SUPERSCRIPTS).join("")}]+`, "g");
const SUB_RUN = new RegExp(`[${Object.keys(SUBSCRIPTS).join("")}]+`, "g");

// Characters that may continue a bare LaTeX run once one has started.
const RUN_CHARS = new Set("+-*/=<>.,'|!()[]^_ ");
const RUN_AFTER_SPACE = new Set("\\^_+-=<>*/");

const isAlpha = (char: string) => char >= "a" && char <= "z" || char >= "A" && char <= "Z";
const isAlnum = (char: string) => isAlpha(char) || (char >= "0" && char <= "9");

/** Rewrite every math dialect in `markdown` as `$…$` / `$$…$$`. */
export function normalizeMath(markdown: string): string {
  const pieces: string[] = [];
  let cursor = 0;
  FENCE.lastIndex = 0;
  for (let fence = FENCE.exec(markdown); fence; fence = FENCE.exec(markdown)) {
    pieces.push(normalizeProse(markdown.slice(cursor, fence.index)));
    pieces.push(normalizeFence(fence[1], fence[2], fence[3], fence[0]));
    cursor = fence.index + fence[0].length;
  }
  pieces.push(normalizeProse(markdown.slice(cursor)));
  return pieces.join("");
}

/** Turn a ```math fence into display math; leave real code alone. */
function normalizeFence(indent: string, info: string, body: string, whole: string): string {
  if (!MATH_FENCE_LANGS.has(info.trim().toLowerCase())) return whole;
  const lines = body.trim().split("\n").filter((line) => line.trim());
  if (!lines.length) return "";
  const formulas = lines.map((line) => `${indent}${cleanMath(line)}`).join("\n");
  return `${indent}$$\n${formulas}\n${indent}$$`;
}

/** Normalize one run of Markdown that contains no fenced code block. */
function normalizeProse(text: string): string {
  if (!text) return text;
  const converted = text
    .replace(BREAK_TAG, " ")
    .replace(BRACKET_MATH, (_all, body: string) => `$$${body}$$`)
    .replace(PAREN_MATH, (_all, body: string) => `$${body}$`);
  return splitInlineCode(converted)
    .map(([segment, isCode]) => (isCode ? segment : normalizeMathSpans(segment)))
    .join("");
}

function splitInlineCode(text: string): [string, boolean][] {
  const segments: [string, boolean][] = [];
  let cursor = 0;
  INLINE_CODE.lastIndex = 0;
  for (let code = INLINE_CODE.exec(text); code; code = INLINE_CODE.exec(text)) {
    segments.push([text.slice(cursor, code.index), false]);
    segments.push([code[0], true]);
    cursor = code.index + code[0].length;
  }
  segments.push([text.slice(cursor), false]);
  return segments;
}

/** Tidy existing math spans and promote bare LaTeX between them. */
function normalizeMathSpans(text: string): string {
  const pieces: string[] = [];
  let cursor = 0;
  MATH_SPAN.lastIndex = 0;
  for (let span = MATH_SPAN.exec(text); span; span = MATH_SPAN.exec(text)) {
    pieces.push(wrapBareLatex(text.slice(cursor, span.index)));
    const display = span[1] !== undefined;
    const body = cleanMath(display ? span[1] : span[2]);
    if (body) pieces.push(display ? `$$${body}$$` : `$${body}$`);
    cursor = span.index + span[0].length;
  }
  pieces.push(wrapBareLatex(text.slice(cursor)));
  return pieces.join("");
}

/** Make one math body safe for KaTeX: no stray padding, no typeset Unicode. */
function cleanMath(latex: string): string {
  const trimmed = latex.trim();
  if (!trimmed) return "";
  const scripted = trimmed
    .replace(SUPER_RUN, (run) => `^{${[...run].map((c) => SUPERSCRIPTS[c]).join("")}}`)
    .replace(SUB_RUN, (run) => `_{${[...run].map((c) => SUBSCRIPTS[c]).join("")}}`);
  // A command needs a separator before a letter or digit, but a space before
  // `^`/`_` would detach the script from the symbol it belongs to.
  const expanded = scripted.replace(UNICODE_SYMBOL, (symbol, offset: number) => {
    const next = scripted[offset + symbol.length] ?? "";
    return `\\${UNICODE_TO_COMMAND[symbol]}${isAlnum(next) ? " " : ""}`;
  });
  return expanded.replace(/[ \t]{2,}/g, " ").trim();
}

/** Wrap `\frac{a}{b}` style runs that were written outside any `$…$`. */
function wrapBareLatex(text: string): string {
  if (!text.includes("\\")) return text;
  const out: string[] = [];
  let index = 0;
  while (index < text.length) {
    const char = text[index];
    if (char !== "\\" || !isAlpha(text[index + 1] ?? "")) {
      out.push(char);
      index += 1;
      continue;
    }
    const run = text.slice(index, latexRunEnd(text, index)).replace(/[ ,.;:]+$/, "");
    const body = cleanMath(run);
    out.push(body ? `$${body}$` : run);
    index += run.length;
  }
  return out.join("");
}

/** Index just past the LaTeX run that begins at the backslash on `start`. */
function latexRunEnd(text: string, start: number): number {
  let index = start;
  let depth = 0;
  while (index < text.length) {
    const char = text[index];
    if (char === "\\" && index + 1 < text.length) {
      index += 1;
      if (isAlpha(text[index])) {
        while (index < text.length && isAlpha(text[index])) index += 1;
      } else {
        index += 1;
      }
      continue;
    }
    if (char === "{") {
      depth += 1;
    } else if (char === "}") {
      if (depth === 0) break;
      depth -= 1;
    } else if (depth === 0) {
      if (char === " ") {
        let probe = index;
        while (probe < text.length && text[probe] === " ") probe += 1;
        // A run only survives a space when the next token is unmistakably
        // math; otherwise the space ends the formula and prose resumes.
        if (probe < text.length && RUN_AFTER_SPACE.has(text[probe])) {
          index = probe;
          continue;
        }
        break;
      }
      if (!isAlnum(char) && !RUN_CHARS.has(char)) break;
    }
    index += 1;
  }
  return index;
}
