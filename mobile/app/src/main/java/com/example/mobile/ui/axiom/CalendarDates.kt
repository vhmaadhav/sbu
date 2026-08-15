package com.example.mobile.ui.axiom

import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId

/**
 * Date helpers shared by the Calendar workspace tool and the Plan tab, so both
 * screens agree on which day a task or event belongs to.
 *
 * Everything here is deliberately total: the backend is a hackathon API and a bad
 * or missing date should leave a day unmarked, never take a screen down.
 */

/** Google events carry either a plain date or an offset date-time; map both to a local day. */
internal fun eventLocalDate(start: String, zone: ZoneId = ZoneId.systemDefault()): LocalDate? =
    runCatching {
        if (start.length > 10) OffsetDateTime.parse(start).atZoneSameInstant(zone).toLocalDate()
        else LocalDate.parse(start)
    }.getOrNull()

/** Task due dates are stored as `YYYY-MM-DD`, but tolerate a full timestamp too. */
internal fun taskDueDate(due: String?): LocalDate? {
    val trimmed = due?.trim().orEmpty()
    if (trimmed.isEmpty()) return null
    return runCatching { LocalDate.parse(trimmed.take(10)) }.getOrNull()
}

/**
 * How many things sit on each day, counting tasks and calendar events together.
 * Days with nothing scheduled are absent rather than mapped to zero.
 */
internal fun dayMarkers(
    taskDues: List<String?>,
    eventStarts: List<String>,
    zone: ZoneId = ZoneId.systemDefault(),
): Map<LocalDate, Int> {
    val counts = mutableMapOf<LocalDate, Int>()
    taskDues.mapNotNull { taskDueDate(it) }.forEach { counts[it] = (counts[it] ?: 0) + 1 }
    eventStarts.mapNotNull { eventLocalDate(it, zone) }.forEach { counts[it] = (counts[it] ?: 0) + 1 }
    return counts
}
