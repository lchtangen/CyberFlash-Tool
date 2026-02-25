from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class BaseWorker(QObject):
    """Base class for all CyberFlash background workers.

    Usage pattern (moveToThread):
        thread = QThread(parent)
        worker = MyWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.start)
        thread.start()
    """

    error = Signal(str)
    finished = Signal()
