import unittest
from datetime import datetime, timedelta, timezone

from pet.context import ContextFetcher

NOW = datetime(2026, 7, 25, 9, 0, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class FakeClient:
    """Routes by path substring so tests only describe what they care about."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(url)
        for fragment, response in self.routes.items():
            if fragment in url:
                if isinstance(response, Exception):
                    raise response
                return response
        return FakeResponse({}, status_code=404)


def fetcher(routes, clock=None):
    return ContextFetcher(
        base_url="http://test",
        client=FakeClient(routes),
        clock=clock or (lambda: 0.0),
        now=lambda: NOW,
    )


class SnapshotTests(unittest.TestCase):
    def test_assembles_tasks_gaps_and_calendar(self):
        due = (NOW + timedelta(days=2)).date().isoformat()
        start = (NOW + timedelta(days=4)).isoformat()
        target = fetcher({
            "/api/tasks": FakeResponse([
                {"label": "Finish DBMS sheet", "due": due, "done": 0},
                {"label": "Old thing", "due": None, "done": 1},
                {"label": "Read chapter 4", "due": None, "done": 0},
            ]),
            "/api/learn/gaps": FakeResponse({
                "gaps": [
                    {"name": "Normalization"},
                    {"name": "Indexing"},
                    {"name": "Transactions"},
                    {"name": "Sharding"},
                ]
            }),
            "/api/calendar/google/events": FakeResponse([
                {"summary": "DBMS exam", "start": start}
            ]),
        })

        snapshot = target.snapshot()

        self.assertEqual(snapshot.open_task_count, 2)
        self.assertEqual(
            snapshot.weakest_concepts, ("Normalization", "Indexing", "Transactions")
        )
        self.assertIn("Finish DBMS sheet", snapshot.next_deadline)
        self.assertIn("2 days", snapshot.next_deadline)

    def test_calendar_event_wins_when_it_is_sooner_than_any_task(self):
        target = fetcher({
            "/api/tasks": FakeResponse([
                {"label": "Sheet", "due": (NOW + timedelta(days=6)).date().isoformat(), "done": 0}
            ]),
            "/api/learn/gaps": FakeResponse({"gaps": []}),
            "/api/calendar/google/events": FakeResponse([
                {"summary": "OS quiz", "start": (NOW + timedelta(days=1)).isoformat()}
            ]),
        })

        self.assertIn("OS quiz", target.snapshot().next_deadline)

    def test_past_due_dates_are_ignored(self):
        target = fetcher({
            "/api/tasks": FakeResponse([
                {"label": "Overdue", "due": (NOW - timedelta(days=3)).date().isoformat(), "done": 0}
            ]),
            "/api/learn/gaps": FakeResponse({"gaps": []}),
            "/api/calendar/google/events": FakeResponse([]),
        })

        self.assertIsNone(target.snapshot().next_deadline)


class DegradationTests(unittest.TestCase):
    def test_one_failing_endpoint_does_not_lose_the_others(self):
        target = fetcher({
            "/api/tasks": FakeResponse([{"label": "Sheet", "due": None, "done": 0}]),
            "/api/learn/gaps": FakeResponse(None, status_code=400),
            "/api/calendar/google/events": FakeResponse(None, status_code=401),
        })

        snapshot = target.snapshot()

        self.assertEqual(snapshot.open_task_count, 1)
        self.assertEqual(snapshot.weakest_concepts, ())
        self.assertIsNone(snapshot.next_deadline)

    def test_backend_entirely_down_yields_an_empty_snapshot(self):
        target = fetcher({
            "/api": ConnectionError("refused"),
        })

        snapshot = target.snapshot()

        self.assertEqual(snapshot.open_task_count, 0)
        self.assertEqual(snapshot.weakest_concepts, ())
        self.assertIsNone(snapshot.next_deadline)

    def test_malformed_payloads_do_not_raise(self):
        target = fetcher({
            "/api/tasks": FakeResponse({"unexpected": "shape"}),
            "/api/learn/gaps": FakeResponse([1, 2, 3]),
            "/api/calendar/google/events": FakeResponse("nope"),
        })

        self.assertEqual(target.snapshot().open_task_count, 0)


class CacheTests(unittest.TestCase):
    def test_repeat_calls_inside_the_interval_do_not_refetch(self):
        client = FakeClient({
            "/api/tasks": FakeResponse([]),
            "/api/learn/gaps": FakeResponse({"gaps": []}),
            "/api/calendar/google/events": FakeResponse([]),
        })
        target = ContextFetcher(
            base_url="http://test", client=client, clock=lambda: 0.0, now=lambda: NOW
        )

        target.snapshot()
        target.snapshot()

        self.assertEqual(len(client.calls), 3)

    def test_snapshot_refetches_once_the_interval_has_passed(self):
        client = FakeClient({
            "/api/tasks": FakeResponse([]),
            "/api/learn/gaps": FakeResponse({"gaps": []}),
            "/api/calendar/google/events": FakeResponse([]),
        })
        ticks = iter([0.0, 1000.0])
        target = ContextFetcher(
            base_url="http://test",
            client=client,
            clock=lambda: next(ticks),
            now=lambda: NOW,
        )

        target.snapshot()
        target.snapshot()

        self.assertEqual(len(client.calls), 6)


if __name__ == "__main__":
    unittest.main()
