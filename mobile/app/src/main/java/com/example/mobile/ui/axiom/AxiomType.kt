package com.example.mobile.ui.axiom

import androidx.compose.runtime.Composable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import com.example.mobile.R

/**
 * OpenDyslexic (SIL OFL, see OPEN_DYSLEXIC_LICENSE.txt) — weighted letter
 * bottoms and distinct shapes for mirror-pairs like b/d and p/q.
 */
val OpenDyslexic = FontFamily(
    Font(R.font.opendyslexic_regular, FontWeight.Normal),
    Font(R.font.opendyslexic_italic, FontWeight.Normal, FontStyle.Italic),
    Font(R.font.opendyslexic_bold, FontWeight.Bold),
    Font(R.font.opendyslexic_bold_italic, FontWeight.Bold, FontStyle.Italic),
)

/**
 * Whether dyslexia-friendly reading is on. Static, so flipping it invalidates
 * the whole subtree — which is what we want, since it changes every glyph.
 */
val LocalDyslexicReading = staticCompositionLocalOf { false }

/**
 * Body/UI typeface. A composable getter rather than a constant so the
 * ~40 existing `fontFamily = Sans` call sites pick up the toggle unchanged.
 */
val Sans: FontFamily
    @Composable
    @ReadOnlyComposable
    get() = if (LocalDyslexicReading.current) OpenDyslexic else FontFamily.SansSerif

/** Never swapped: small uppercase labels and code stay clearer in mono. */
val Mono = FontFamily.Monospace

/**
 * Opens up long-form text when the reading mode is on: taller lines and wider
 * tracking, the two spacing changes that carry most of the readability
 * benefit. (Compose has no word-spacing equivalent to the web rule.)
 */
@Composable
@ReadOnlyComposable
fun readingStyle(base: TextStyle): TextStyle =
    if (!LocalDyslexicReading.current) base
    else base.copy(
        lineHeight = (base.lineHeight.value * 1.3f).sp,
        letterSpacing = 0.05.em,
    )
