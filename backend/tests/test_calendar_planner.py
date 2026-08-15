import unittest
from unittest.mock import patch

from core.calendar_planner import build_plan, priority_for


def reminder(**overrides):
    value = {
        "id": 7,
        "title": "Project presentation",
        "event_date": "2026-07-25",
        "start_time": "10:00",
        "end_time": "11:00",
        "all_day": 0,
        "filename": "schedule.png",
    }
    value.update(overrides)
    return value


def event(event_id, title, start, end, **overrides):
    value = {
        "id": event_id,
        "summary": title,
        "start": start,
        "end": end,
        "all_day": False,
        "attendees": [],
        "recurring_event_id": None,
        "agent_movable": None,
    }
    value.update(overrides)
    return value


class CalendarPlannerTests(unittest.TestCase):
    def test_priority_applies_to_all_event_categories(self):
        self.assertGreater(priority_for("Doctor appointment"), priority_for("Gym workout"))
        self.assertGreater(priority_for("Client meeting"), priority_for("Reading"))

    @patch("core.calendar_planner.GOOGLE_CALENDAR_TIMEZONE", "Asia/Kolkata")
    def test_flexible_solo_conflict_moves_to_next_open_slot(self):
        plan = build_plan(reminder(), [
            event(
                "focus", "Focus work",
                "2026-07-25T10:00:00+05:30", "2026-07-25T11:00:00+05:30",
            ),
            event(
                "lunch", "Lunch",
                "2026-07-25T11:00:00+05:30", "2026-07-25T12:00:00+05:30",
            ),
        ])

        self.assertEqual(len(plan["moves"]), 1)
        self.assertEqual(plan["moves"][0]["event_id"], "focus")
        self.assertEqual(plan["moves"][0]["new_start"], "2026-07-25T12:00:00+05:30")
        self.assertFalse(plan["needs_confirmation"])
        self.assertEqual(plan["blocked"], [])

    @patch("core.calendar_planner.GOOGLE_CALENDAR_TIMEZONE", "Asia/Kolkata")
    def test_attendee_conflict_is_never_silently_moved(self):
        plan = build_plan(reminder(), [
            event(
                "team", "Team sync",
                "2026-07-25T10:00:00+05:30", "2026-07-25T11:00:00+05:30",
                attendees=[{"email": "friend@example.com"}],
            ),
        ])

        self.assertEqual(plan["moves"], [])
        self.assertEqual(plan["blocked"][0]["event_id"], "team")
        self.assertTrue(plan["needs_confirmation"])

    @patch("core.calendar_planner.GOOGLE_CALENDAR_TIMEZONE", "Asia/Kolkata")
    def test_lower_priority_new_event_asks_before_displacing_important_work(self):
        plan = build_plan(
            reminder(title="Workout"),
            [event(
                "meeting", "Project meeting",
                "2026-07-25T10:00:00+05:30", "2026-07-25T11:00:00+05:30",
            )],
        )

        self.assertEqual(plan["moves"], [])
        self.assertIn("higher priority", plan["blocked"][0]["reason"])

    @patch("core.calendar_planner.GOOGLE_CALENDAR_TIMEZONE", "Asia/Kolkata")
    def test_all_day_capture_does_not_displace_timed_events(self):
        plan = build_plan(
            reminder(start_time=None, end_time=None, all_day=1),
            [event(
                "class", "Class",
                "2026-07-25T10:00:00+05:30", "2026-07-25T11:00:00+05:30",
            )],
        )

        self.assertEqual(plan["moves"], [])
        self.assertEqual(plan["blocked"], [])


if __name__ == "__main__":
    unittest.main()
