package com.example.mobile

import com.example.mobile.ui.axiom.dayMarkers
import com.example.mobile.ui.axiom.eventLocalDate
import com.example.mobile.ui.axiom.taskDueDate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.LocalDate
import java.time.ZoneId

class CalendarDatesTest {

    private val utc = ZoneId.of("UTC")

    @Test
    fun allDayEventKeepsItsPlainDate() {
        assertEquals(LocalDate.of(2026, 7, 24), eventLocalDate("2026-07-24", utc))
    }

    @Test
    fun timedEventIsConvertedIntoTheTargetZone() {
        // 23:30 on the 24th at UTC-4 is already the 25th in UTC.
        assertEquals(LocalDate.of(2026, 7, 25), eventLocalDate("2026-07-24T23:30:00-04:00", utc))
    }

    @Test
    fun unparseableEventStartIsNull() {
        assertNull(eventLocalDate("", utc))
        assertNull(eventLocalDate("sometime next week", utc))
    }

    @Test
    fun taskDueAcceptsAPlainDate() {
        assertEquals(LocalDate.of(2026, 7, 24), taskDueDate("2026-07-24"))
    }

    @Test
    fun taskDueAcceptsATimestampAndKeepsTheDatePart() {
        assertEquals(LocalDate.of(2026, 7, 24), taskDueDate("2026-07-24T09:00:00+05:30"))
    }

    @Test
    fun taskDueToleratesMissingAndJunkValues() {
        assertNull(taskDueDate(null))
        assertNull(taskDueDate(""))
        assertNull(taskDueDate("   "))
        assertNull(taskDueDate("tomorrow"))
    }

    @Test
    fun markersCountTasksAndEventsOnTheSameDay() {
        val markers = dayMarkers(
            taskDues = listOf("2026-07-24", "2026-07-24", "2026-07-26", null, "junk"),
            eventStarts = listOf("2026-07-24", "2026-07-25"),
            zone = utc,
        )
        assertEquals(3, markers[LocalDate.of(2026, 7, 24)])
        assertEquals(1, markers[LocalDate.of(2026, 7, 25)])
        assertEquals(1, markers[LocalDate.of(2026, 7, 26)])
        assertNull(markers[LocalDate.of(2026, 7, 27)])
    }

    @Test
    fun markersAreEmptyWhenNothingIsScheduled() {
        assertEquals(emptyMap<LocalDate, Int>(), dayMarkers(emptyList(), emptyList(), utc))
    }
}
