"""tests/unit/test_event_bus.py — Unit tests for EventBus."""

from __future__ import annotations

import pytest

from cyberflash.services.event_bus import EventBus


@pytest.fixture(autouse=True)
def reset_event_bus() -> None:
    """Ensure a fresh EventBus singleton for every test."""
    EventBus.reset()
    yield
    EventBus.reset()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestEventBusSingleton:
    def test_instance_is_singleton(self, qapp: object) -> None:
        a = EventBus.instance()
        b = EventBus.instance()
        assert a is b

    def test_reset_creates_new_instance(self, qapp: object) -> None:
        a = EventBus.instance()
        EventBus.reset()
        b = EventBus.instance()
        assert a is not b


# ---------------------------------------------------------------------------
# subscribe / publish / unsubscribe
# ---------------------------------------------------------------------------


class TestEventBusPubSub:
    def test_subscribe_and_publish(self, qapp: object) -> None:
        received: list[dict] = []

        def handler(**kwargs: object) -> None:
            received.append(dict(kwargs))

        bus = EventBus.instance()
        bus.subscribe("test.event", handler)
        count = bus.publish("test.event", value=42)
        assert count == 1
        assert received == [{"value": 42}]

    def test_publish_case_insensitive(self, qapp: object) -> None:
        received: list[str] = []

        def handler(**kwargs: object) -> None:
            received.append("called")

        bus = EventBus.instance()
        bus.subscribe("Device.Connected", handler)
        bus.publish("device.connected")
        assert received == ["called"]

    def test_unsubscribe_removes_handler(self, qapp: object) -> None:
        received: list[int] = []

        def handler(**kwargs: object) -> None:
            received.append(1)

        bus = EventBus.instance()
        bus.subscribe("ev.x", handler)
        bus.unsubscribe("ev.x", handler)
        bus.publish("ev.x")
        assert received == []

    def test_unsubscribe_returns_false_if_not_found(self, qapp: object) -> None:
        def handler(**kwargs: object) -> None:
            pass

        bus = EventBus.instance()
        assert bus.unsubscribe("nonexistent.topic", handler) is False

    def test_publish_no_handlers_returns_zero(self, qapp: object) -> None:
        bus = EventBus.instance()
        assert bus.publish("empty.topic") == 0

    def test_multiple_subscribers(self, qapp: object) -> None:
        calls: list[str] = []

        def h1(**kwargs: object) -> None:
            calls.append("h1")

        def h2(**kwargs: object) -> None:
            calls.append("h2")

        bus = EventBus.instance()
        bus.subscribe("multi", h1)
        bus.subscribe("multi", h2)
        count = bus.publish("multi")
        assert count == 2
        assert "h1" in calls
        assert "h2" in calls

    def test_no_duplicate_subscription(self, qapp: object) -> None:
        calls: list[int] = []

        def handler(**kwargs: object) -> None:
            calls.append(1)

        bus = EventBus.instance()
        bus.subscribe("dup", handler)
        bus.subscribe("dup", handler)  # should be a no-op
        bus.publish("dup")
        assert len(calls) == 1

    def test_dead_weak_ref_pruned(self, qapp: object) -> None:
        """Dead weak-refs are pruned on publish."""

        def make_handler() -> object:
            def h(**kwargs: object) -> None:
                pass

            return h

        handler = make_handler()
        bus = EventBus.instance()
        bus.subscribe("prune.test", handler)
        del handler  # let it go
        # After deletion, publish should not crash and returns 0
        result = bus.publish("prune.test")
        assert result == 0


# ---------------------------------------------------------------------------
# subscriber_count / topic_count / clear
# ---------------------------------------------------------------------------


class TestEventBusIntrospection:
    def test_subscriber_count_initial_zero(self, qapp: object) -> None:
        bus = EventBus.instance()
        assert bus.subscriber_count("anything") == 0

    def test_subscriber_count_after_subscribe(self, qapp: object) -> None:
        def h(**kwargs: object) -> None:
            pass

        bus = EventBus.instance()
        bus.subscribe("count.me", h)
        assert bus.subscriber_count("count.me") == 1

    def test_topic_count(self, qapp: object) -> None:
        def h(**kwargs: object) -> None:
            pass

        bus = EventBus.instance()
        bus.subscribe("topic.a", h)
        bus.subscribe("topic.b", h)
        assert bus.topic_count() >= 2

    def test_clear_topic(self, qapp: object) -> None:
        def h(**kwargs: object) -> None:
            pass

        bus = EventBus.instance()
        bus.subscribe("clear.me", h)
        bus.clear_topic("clear.me")
        assert bus.subscriber_count("clear.me") == 0

    def test_clear_all(self, qapp: object) -> None:
        def h(**kwargs: object) -> None:
            pass

        bus = EventBus.instance()
        bus.subscribe("clear.a", h)
        bus.subscribe("clear.b", h)
        bus.clear_all()
        assert bus.topic_count() == 0


# ---------------------------------------------------------------------------
# Qt signal
# ---------------------------------------------------------------------------


class TestEventBusSignal:
    def test_event_published_signal(self, qapp: object) -> None:
        from PySide6.QtTest import QSignalSpy

        def h(**kwargs: object) -> None:
            pass

        bus = EventBus.instance()
        spy = QSignalSpy(bus.event_published)
        bus.subscribe("signal.test", h)
        bus.publish("signal.test", foo="bar")
        assert len(spy) >= 1
