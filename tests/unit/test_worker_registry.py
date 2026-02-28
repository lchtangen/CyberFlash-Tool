"""tests/unit/test_worker_registry.py — Unit tests for WorkerRegistry."""

from __future__ import annotations

import pytest

from cyberflash.services.worker_registry import WorkerRegistrationError, WorkerRegistry
from cyberflash.workers.base_worker import BaseWorker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _DummyWorker(BaseWorker):
    def start(self) -> None:
        pass


class _OtherWorker(BaseWorker):
    def start(self) -> None:
        pass


@pytest.fixture(autouse=True)
def reset_registry() -> None:
    """Fresh singleton for every test."""
    WorkerRegistry.reset()
    yield
    WorkerRegistry.reset()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestWorkRegistrySingleton:
    def test_instance_is_singleton(self) -> None:
        a = WorkerRegistry.instance()
        b = WorkerRegistry.instance()
        assert a is b

    def test_reset_creates_new_instance(self) -> None:
        a = WorkerRegistry.instance()
        WorkerRegistry.reset()
        b = WorkerRegistry.instance()
        assert a is not b


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------


class TestWorkerRegistryRegister:
    def test_register_valid_worker(self) -> None:
        reg = WorkerRegistry.instance()
        reg.register("plugin.dummy", _DummyWorker)
        assert reg.is_registered("plugin.dummy")

    def test_register_requires_namespace(self) -> None:
        reg = WorkerRegistry.instance()
        with pytest.raises(WorkerRegistrationError, match="namespaced"):
            reg.register("nodotname", _DummyWorker)

    def test_register_rejects_non_baseworker(self) -> None:
        reg = WorkerRegistry.instance()

        class NotAWorker:
            pass

        with pytest.raises(WorkerRegistrationError, match="BaseWorker"):
            reg.register("plugin.bad", NotAWorker)  # type: ignore[arg-type]

    def test_register_same_class_twice_is_idempotent(self) -> None:
        reg = WorkerRegistry.instance()
        reg.register("plugin.idem", _DummyWorker)
        reg.register("plugin.idem", _DummyWorker)  # no error
        assert reg.count() == 1

    def test_register_different_class_same_name_raises(self) -> None:
        reg = WorkerRegistry.instance()
        reg.register("plugin.clash", _DummyWorker)
        with pytest.raises(WorkerRegistrationError, match="already registered"):
            reg.register("plugin.clash", _OtherWorker)

    def test_register_stores_metadata(self) -> None:
        reg = WorkerRegistry.instance()
        reg.register(
            "plugin.meta",
            _DummyWorker,
            description="A worker",
            author="Alice",
            version="2.0.0",
        )
        meta = reg.get_metadata("plugin.meta")
        assert meta["author"] == "Alice"
        assert meta["version"] == "2.0.0"


# ---------------------------------------------------------------------------
# unregister / count
# ---------------------------------------------------------------------------


class TestWorkerRegistryUnregister:
    def test_unregister_existing(self) -> None:
        reg = WorkerRegistry.instance()
        reg.register("plugin.del", _DummyWorker)
        assert reg.unregister("plugin.del") is True
        assert not reg.is_registered("plugin.del")

    def test_unregister_nonexistent_returns_false(self) -> None:
        reg = WorkerRegistry.instance()
        assert reg.unregister("plugin.ghost") is False

    def test_count(self) -> None:
        reg = WorkerRegistry.instance()
        reg.register("plugin.a", _DummyWorker)
        reg.register("plugin.b", _OtherWorker)
        assert reg.count() == 2


# ---------------------------------------------------------------------------
# create / get_class
# ---------------------------------------------------------------------------


class TestWorkerRegistryCreate:
    def test_create_returns_instance(self) -> None:
        reg = WorkerRegistry.instance()
        reg.register("plugin.create", _DummyWorker)
        worker = reg.create("plugin.create")
        assert isinstance(worker, _DummyWorker)

    def test_create_unknown_raises(self) -> None:
        reg = WorkerRegistry.instance()
        with pytest.raises(KeyError):
            reg.create("plugin.unknown")

    def test_get_class_known(self) -> None:
        reg = WorkerRegistry.instance()
        reg.register("plugin.gc", _DummyWorker)
        assert reg.get_class("plugin.gc") is _DummyWorker

    def test_get_class_unknown_returns_none(self) -> None:
        reg = WorkerRegistry.instance()
        assert reg.get_class("plugin.nope") is None

    def test_list_names(self) -> None:
        reg = WorkerRegistry.instance()
        reg.register("plugin.x", _DummyWorker)
        reg.register("plugin.y", _OtherWorker)
        names = reg.list_names()
        assert "plugin.x" in names
        assert "plugin.y" in names
