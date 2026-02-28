"""event_bus.py — Application-wide inter-component event bus (Phase 12).

Provides a lightweight publish/subscribe system so plugins (and core
modules) can communicate without direct imports.  The bus is a singleton
QObject; subscriptions are weak-reference safe.

Usage::

    bus = EventBus.instance()
    bus.subscribe("device.connected", on_device_connected, sender=self)
    bus.publish("device.connected", serial="ABC123", model="Pixel 7")
    bus.unsubscribe("device.connected", on_device_connected)
"""

from __future__ import annotations

import logging
import weakref
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

# Type alias
_Handler = Callable[..., None]


class EventBus(QObject):
    """Singleton application event bus.

    Events are grouped under *topic* strings (e.g. ``"device.connected"``).
    Handlers receive arbitrary keyword arguments published with the event.

    Signals:
        event_published(str): emitted with the *topic* whenever any event fires.
    """

    event_published = Signal(str)

    _instance: EventBus | None = None

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._handlers: dict[str, list[weakref.ref[_Handler] | _Handler]] = {}

    @classmethod
    def instance(cls) -> EventBus:
        """Return (or create) the application-wide singleton."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Destroy the singleton (useful in tests)."""
        if cls._instance is not None:
            cls._instance._handlers.clear()
            cls._instance = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def subscribe(self, topic: str, handler: _Handler) -> None:
        """Register *handler* to be called when *topic* is published."""
        topic = topic.lower()
        if topic not in self._handlers:
            self._handlers[topic] = []
        # Avoid duplicate registrations
        for existing in self._handlers[topic]:
            cb = existing() if isinstance(existing, weakref.ref) else existing
            if cb is handler:
                return
        try:
            ref: weakref.ref[_Handler] | _Handler = weakref.ref(handler)  # type: ignore[assignment]
        except TypeError:
            # Built-in or lambda — can't weak-ref; store directly
            ref = handler
        self._handlers[topic].append(ref)
        logger.debug("EventBus: subscribed %r to '%s'", handler, topic)

    def unsubscribe(self, topic: str, handler: _Handler) -> bool:
        """Remove *handler* from *topic*. Returns ``True`` if found."""
        topic = topic.lower()
        before = len(self._handlers.get(topic, []))
        self._handlers[topic] = [
            ref for ref in self._handlers.get(topic, [])
            if (ref() if isinstance(ref, weakref.ref) else ref) is not handler
        ]
        removed = before - len(self._handlers.get(topic, []))
        return removed > 0

    def publish(self, topic: str, **kwargs: Any) -> int:
        """Publish an event to *topic*, passing *kwargs* to all handlers.

        Returns the number of handlers called.  Dead weak-references are
        silently pruned.
        """
        topic = topic.lower()
        handlers = self._handlers.get(topic, [])
        alive: list[weakref.ref[_Handler] | _Handler] = []
        called = 0
        for ref in handlers:
            cb = ref() if isinstance(ref, weakref.ref) else ref
            if cb is None:
                continue  # dead weak-ref — prune
            alive.append(ref)
            try:
                cb(**kwargs)
                called += 1
            except Exception as exc:
                logger.warning(
                    "EventBus handler %r for '%s' raised: %s", cb, topic, exc
                )
        self._handlers[topic] = alive
        if called or alive:
            self.event_published.emit(topic)
        return called

    def topic_count(self) -> int:
        """Return number of registered topics."""
        return len(self._handlers)

    def subscriber_count(self, topic: str) -> int:
        """Return the number of live subscribers for *topic*."""
        topic = topic.lower()
        return sum(
            1 for ref in self._handlers.get(topic, [])
            if (ref() if isinstance(ref, weakref.ref) else ref) is not None
        )

    def clear_topic(self, topic: str) -> None:
        """Remove all handlers for *topic*."""
        topic = topic.lower()
        self._handlers.pop(topic, None)

    def clear_all(self) -> None:
        """Remove all subscriptions."""
        self._handlers.clear()
