package com.example.mobile.ui.axiom

import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.lerp

@Immutable
data class AxiomColors(
    val bg: Color,
    val panel: Color,
    val panel2: Color,
    val line: Color,
    val line2: Color,
    val text: Color,
    val dim: Color,
    val faint: Color,
    val glow2: Color,
    val accent: Color,
)

val AxiomDark = AxiomColors(
    bg = Color(0xFF070B11),
    panel = Color(0x990C121B),
    panel2 = Color(0xB8121B29),
    line = Color(0x298CAFD7),
    line2 = Color(0x4D8CAFD7),
    text = Color(0xFFDCE7F3),
    dim = Color(0xFF677C93),
    faint = Color(0xFF3D4D60),
    glow2 = Color(0x2E78BEFF),
    accent = Color(0xFFFDA4AF),
)

val AxiomLight = AxiomColors(
    bg = Color(0xFFEEF2F7),
    panel = Color(0x9EFFFFFF),
    panel2 = Color(0xBDE9EEF5),
    line = Color(0x261E3C5F),
    line2 = Color(0x4D1E3C5F),
    text = Color(0xFF17222F),
    dim = Color(0xFF5B6C7F),
    faint = Color(0xFF9FB0C2),
    glow2 = Color(0x295A96E6),
    accent = Color(0xFFE8798A),
)

fun lerp(a: AxiomColors, b: AxiomColors, t: Float): AxiomColors = AxiomColors(
    bg = lerp(a.bg, b.bg, t),
    panel = lerp(a.panel, b.panel, t),
    panel2 = lerp(a.panel2, b.panel2, t),
    line = lerp(a.line, b.line, t),
    line2 = lerp(a.line2, b.line2, t),
    text = lerp(a.text, b.text, t),
    dim = lerp(a.dim, b.dim, t),
    faint = lerp(a.faint, b.faint, t),
    glow2 = lerp(a.glow2, b.glow2, t),
    accent = lerp(a.accent, b.accent, t),
)

val LocalAxiomColors = staticCompositionLocalOf { AxiomDark }
