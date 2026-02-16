"""Executor utilities for background task management."""

from __future__ import annotations

import logging
import queue
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

log = logging.getLogger(__name__)


def create_daemon_threadpool_executor(
    max_workers: int, thread_name_prefix: str = ""
) -> ThreadPoolExecutor:
    """
    Create a standard ThreadPoolExecutor whose worker threads are daemon.

    ThreadPoolExecutor worker threads are created with daemon=None, so they inherit
    the daemon status of the thread that creates them. This helper creates the executor
    from a short-lived daemon thread and forces worker creation so the workers become
    daemon threads (suitable for expendable background work like prefetching/previews).

    NOTE: For critical tasks (saving/deleting), prefer a normal non-daemon executor.
    """
    if max_workers < 1:
        raise ValueError("max_workers must be >= 1")

    executor_container: dict[str, ThreadPoolExecutor] = {}
    error_container: list[BaseException] = []

    def creator() -> None:
        try:
            executor = ThreadPoolExecutor(
                max_workers=max_workers, thread_name_prefix=thread_name_prefix
            )
            executor_container["executor"] = executor

            # Pre-spawn workers so they inherit daemon status from this daemon creator thread.
            futs = [executor.submit(lambda: None) for _ in range(max_workers)]
            for f in futs:
                f.result()
        except BaseException as e:
            error_container.append(e)

    t = threading.Thread(target=creator, name=f"{thread_name_prefix}_Creator", daemon=True)
    t.start()
    t.join()

    if error_container:
        raise error_container[0]

    executor = executor_container.get("executor")
    if executor is None:
        raise RuntimeError("Failed to create daemon ThreadPoolExecutor")

    return executor


def create_priority_executor(
    max_workers: int, thread_name_prefix: str = "", maxsize: int = 0
) -> "PriorityExecutor":
    """
    Create a PriorityExecutor (daemon-threaded by default).

    Useful for thumbnail loading where visible items take precedence.
    """
    return PriorityExecutor(
        max_workers=max_workers,
        thread_name_prefix=thread_name_prefix,
        maxsize=maxsize,
    )


class PriorityExecutor:
    """A thread pool executor that uses a priority queue for task scheduling.

    Tasks are processed in order of:
      1) priority (lower number = higher priority)
      2) -seq (higher seq = more recent = more negative = higher priority among same priority)

    Workers are daemon threads.
    """

    def __init__(self, max_workers: int, thread_name_prefix: str = "", maxsize: int = 0):
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")

        self._max_workers = max_workers
        self._thread_name_prefix = thread_name_prefix
        self._queue: queue.PriorityQueue[
            tuple[int, int, Callable[..., Any], tuple[Any, ...], dict[str, Any], Future]
        ] = queue.PriorityQueue(maxsize=maxsize)
        self._workers: list[threading.Thread] = []
        self._stop_event = threading.Event()

        # Monotonic counter for stable LIFO ordering within same priority.
        self._count = 0
        self._count_lock = threading.Lock()

        for i in range(max_workers):
            t = threading.Thread(
                target=self._worker_loop,
                name=f"{thread_name_prefix}_{i}",
                daemon=True,
            )
            t.start()
            self._workers.append(t)

    def _worker_loop(self) -> None:
        # Drain behavior:
        # - If stop_event is set, workers will exit only after the queue becomes empty,
        #   unless queued items are explicitly cancelled via shutdown(cancel_futures=True).
        while True:
            if self._stop_event.is_set() and self._queue.empty():
                break

            try:
                item = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            priority, neg_seq, fn, args, kwargs, fut = item
            try:
                if fut.set_running_or_notify_cancel():
                    try:
                        fut.set_result(fn(*args, **kwargs))
                    except BaseException as e:
                        fut.set_exception(e)
            except BaseException as e:
                # If we blow up here, make sure the future doesn't get stranded.
                try:
                    fut.set_exception(e)
                except Exception:
                    pass
                log.error("Error in PriorityExecutor worker: %s", e)
            finally:
                # Always mark item done so join/drain semantics work.
                try:
                    self._queue.task_done()
                except Exception:
                    pass

    def submit(self, fn: Callable[..., Any], *args: Any, priority: int = 1, **kwargs: Any) -> Future:
        """Submit a task to the priority queue.

        Args:
            fn: Function to execute
            priority: Lower number means higher priority
            *args, **kwargs: Passed to fn

        Returns:
            Future object for the task.
        """
        if self._stop_event.is_set():
            raise RuntimeError("Executor shutdown")

        fut: Future = Future()

        with self._count_lock:
            self._count += 1
            seq = self._count

        try:
            self._queue.put((priority, -seq, fn, args, kwargs, fut), block=False)
        except queue.Full:
            fut.set_exception(RuntimeError("PriorityQueue full"))
        return fut

    def shutdown(self, wait: bool = True, cancel_futures: bool = False) -> None:
        """Shutdown the executor.

        If cancel_futures is True, queued (not-yet-started) tasks are cancelled immediately.
        If cancel_futures is False, workers will drain the queue before exiting.
        """
        self._stop_event.set()

        if cancel_futures:
            # Cancel queued work so workers can exit once queue empties.
            while True:
                try:
                    _priority, _neg_seq, _fn, _args, _kwargs, fut = self._queue.get_nowait()
                except queue.Empty:
                    break
                try:
                    fut.cancel()
                finally:
                    try:
                        self._queue.task_done()
                    except Exception:
                        pass

        if wait:
            for t in self._workers:
                try:
                    t.join(timeout=1.0)
                except Exception:
                    pass
