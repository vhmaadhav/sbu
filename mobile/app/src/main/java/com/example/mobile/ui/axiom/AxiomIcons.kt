package com.example.mobile.ui.axiom

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathBuilder
import androidx.compose.ui.graphics.vector.path
import androidx.compose.ui.unit.dp

// Stroked 24x24 icons matching the design's SVG tab glyphs. Stroke color is
// Color.White so tab tinting can recolor them via BlendMode/tint.
private fun icon(name: String, block: ImageVector.Builder.() -> Unit): ImageVector =
    ImageVector.Builder(
        name = name,
        defaultWidth = 23.dp,
        defaultHeight = 23.dp,
        viewportWidth = 24f,
        viewportHeight = 24f,
    ).apply(block).build()

private fun ImageVector.Builder.stroked(pathBuilder: PathBuilder.() -> Unit) {
    path(
        stroke = SolidColor(Color.White),
        strokeLineWidth = 1.5f,
        strokeLineCap = StrokeCap.Round,
        strokeLineJoin = StrokeJoin.Round,
        pathBuilder = pathBuilder,
    )
}

private fun PathBuilder.rect(x: Float, y: Float, w: Float, h: Float) {
    moveTo(x, y)
    horizontalLineToRelative(w)
    verticalLineToRelative(h)
    horizontalLineToRelative(-w)
    close()
}

private fun PathBuilder.roundRect(x: Float, y: Float, w: Float, h: Float, r: Float) {
    moveTo(x + r, y)
    horizontalLineTo(x + w - r)
    arcTo(r, r, 0f, isMoreThanHalf = false, isPositiveArc = true, x1 = x + w, y1 = y + r)
    verticalLineTo(y + h - r)
    arcTo(r, r, 0f, isMoreThanHalf = false, isPositiveArc = true, x1 = x + w - r, y1 = y + h)
    horizontalLineTo(x + r)
    arcTo(r, r, 0f, isMoreThanHalf = false, isPositiveArc = true, x1 = x, y1 = y + h - r)
    verticalLineTo(y + r)
    arcTo(r, r, 0f, isMoreThanHalf = false, isPositiveArc = true, x1 = x + r, y1 = y)
    close()
}

val IconHome: ImageVector = icon("Home") {
    stroked {
        rect(3.5f, 3.5f, 7f, 7f)
        rect(13.5f, 3.5f, 7f, 7f)
        rect(3.5f, 13.5f, 7f, 7f)
        rect(13.5f, 13.5f, 7f, 7f)
    }
}

val IconNotes: ImageVector = icon("Notes") {
    stroked {
        moveTo(12f, 5.5f)
        curveTo(10.5f, 4.3f, 8.3f, 4f, 6f, 4f)
        horizontalLineTo(3.5f)
        verticalLineToRelative(14f)
        horizontalLineTo(6f)
        curveToRelative(2.3f, 0f, 4.5f, 0.3f, 6f, 1.5f)
    }
    stroked {
        moveTo(12f, 5.5f)
        curveTo(13.5f, 4.3f, 15.7f, 4f, 18f, 4f)
        horizontalLineTo(20.5f)
        verticalLineToRelative(14f)
        horizontalLineTo(18f)
        curveToRelative(-2.3f, 0f, -4.5f, 0.3f, -6f, 1.5f)
        close()
    }
    stroked {
        moveTo(12f, 5.5f)
        verticalLineToRelative(14f)
    }
}

val IconCards: ImageVector = icon("Cards") {
    stroked { roundRect(6.5f, 7f, 13f, 13f, 1.5f) }
    stroked {
        moveTo(4.5f, 16f)
        verticalLineTo(6f)
        arcToRelative(1.5f, 1.5f, 0f, isMoreThanHalf = false, isPositiveArc = true, dx1 = 1.5f, dy1 = -1.5f)
        horizontalLineToRelative(9f)
    }
}

val IconPlan: ImageVector = icon("Plan") {
    stroked { roundRect(3.5f, 5f, 17f, 15.5f, 1.5f) }
    stroked {
        moveTo(3.5f, 9.5f)
        horizontalLineToRelative(17f)
        moveTo(8f, 3.5f)
        verticalLineToRelative(3f)
        moveTo(16f, 3.5f)
        verticalLineToRelative(3f)
    }
    stroked {
        moveTo(7f, 13f)
        horizontalLineToRelative(3f)
        moveTo(7f, 16.5f)
        horizontalLineToRelative(3f)
        moveTo(14f, 13f)
        horizontalLineToRelative(3f)
        moveTo(14f, 16.5f)
        horizontalLineToRelative(3f)
    }
}

val IconAll: ImageVector = icon("All features") {
    stroked {
        rect(3.5f, 3.5f, 4f, 4f)
        rect(10f, 3.5f, 4f, 4f)
        rect(16.5f, 3.5f, 4f, 4f)
        rect(3.5f, 10f, 4f, 4f)
        rect(10f, 10f, 4f, 4f)
        rect(16.5f, 10f, 4f, 4f)
        rect(3.5f, 16.5f, 4f, 4f)
        rect(10f, 16.5f, 4f, 4f)
        rect(16.5f, 16.5f, 4f, 4f)
    }
}
