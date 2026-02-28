"""worker_registry.py — Plugin worker registration (Phase 12).

Allows plugins to register custom :class:`~cyberflash.workers.base_worker.BaseWorker`
subclasses by name so the workflow builder and CLI can launch them by name
without direct imports.

Usage::

    registry = WorkerRegistry.instance()
    registry.register("my_plugin.my_worker", MyWorker)

    # Workflow builder or CLI launches a worker by name:
    worker = registry.create("my_plugin.my_worker", serial="ABC123")
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Worker class type — BaseWorker subclass constructor
_WorkerClass = type  # type: ignore[type-arg]


class WorkerRegistrationError(Exception):
    """Raised when registration fails due to a naming conflict or invalid class."""


class WorkerRegistry:
    """Singleton registry mapping names to :class:`BaseWorker` subclasses.

    Thread-safety: registry mutations happen only at plugin-load time
    (main thread), so no locking is required.
    """

    _instance: WorkerRegistry | None = None

    def __init__(self) -> None:
        self._registry: dict[str, _WorkerClass] = {}
        self._metadata: dict[str, dict[str, str]] = {}

    @classmethod
    def instance(cls) -> WorkerRegistry:
        """Return (or create) the application singleton."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Destroy the singleton (test helper)."""
        cls._instance = None

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        worker_class: _WorkerClass,
        description: str = "",
        author: str = "",
        version: str = "1.0.0",
    ) -> None:
        """Register *worker_class* under *name*.

        Raises :class:`WorkerRegistrationError` on naming conflicts unless
        the class is identical.
        """
        if not name or "." not in name:
            raise WorkerRegistrationError(
                f"Worker name must be namespaced (e.g. 'plugin.MyWorker'), got: {name!r}"
            )

        existing = self._registry.get(name)
        if existing is not None and existing is not worker_class:
            raise WorkerRegistrationError(
                f"Worker name '{name}' is already registered by a different class. "
                f"Use a unique namespace."
            )

        from cyberflash.workers.base_worker import BaseWorker

        if not (isinstance(worker_class, type) and issubclass(worker_class, BaseWorker)):
            raise WorkerRegistrationError(
                f"'{name}': worker_class must be a BaseWorker subclass, "
                f"got {worker_class!r}"
            )

        self._registry[name] = worker_class
        self._metadata[name] = {
            "description": description,
            "author": author,
            "version": version,
        }
        logger.info("WorkerRegistry: registered '%s'", name)

    def unregister(self, name: str) -> bool:
        """Remove a registered worker. Returns ``False`` if not found."""
        if name not in self._registry:
            return False
        del self._registry[name]
        self._metadata.pop(name, None)
        logger.info("WorkerRegistry: unregistered '%s'", name)
        return True

    # ------------------------------------------------------------------
    # Lookup & instantiation
    # ------------------------------------------------------------------

    def get_class(self, name: str) -> _WorkerClass | None:
        """Return the registered class for *name*, or ``None``."""
        return self._registry.get(name)

    def create(self, name: str, **kwargs: Any) -> object:
        """Instantiate the registered worker for *name*, passing *kwargs*.

        Raises :class:`KeyError` if *name* is not registered.
        """
        cls_ = self._registry.get(name)
        if cls_ is None:
            raise KeyError(f"No worker registered under name '{name}'")
        return cls_(**kwargs)

    def list_names(self) -> list[str]:
        """Return all registered worker names."""
        return sorted(self._registry.keys())

    def get_metadata(self, name: str) -> dict[str, str]:
        """Return metadata dict for *name* (empty dict if not found)."""
        return dict(self._metadata.get(name, {}))

    def is_registered(self, name: str) -> bool:
        """Return ``True`` if *name* is registered."""
        return name in self._registry

    def count(self) -> int:
        """Return number of registered workers."""
        return len(self._registry)
