"""Tests for zcoder.async.lifecycle - async lifecycle controller."""

import asyncio

import pytest

from zcoder.app.shutdown import ShutdownManager
from zcoder.lifecycle.lifecycle import LifecycleController


class TestLifecycleController:
    """Tests for LifecycleController."""

    def test_create(self):
        ctrl = LifecycleController("test-op")
        assert ctrl.name == "test-op"
        assert ctrl.is_cancelled is False
        assert ctrl.is_completed is False
        assert ctrl.aborted is False

    def test_start(self):
        ctrl = LifecycleController("op")
        ctrl.start()
        assert ctrl._started is True

    def test_start_twice_raises(self):
        ctrl = LifecycleController("op")
        ctrl.start()
        with pytest.raises(RuntimeError, match="already started"):
            ctrl.start()

    def test_start_after_complete_raises(self):
        ctrl = LifecycleController("op")
        ctrl.start()
        ctrl.complete()
        with pytest.raises(RuntimeError, match="already started"):
            ctrl.start()

    def test_cancel(self):
        ctrl = LifecycleController("op")
        ctrl.start()
        ctrl.cancel()
        assert ctrl.is_cancelled is True
        assert ctrl.aborted is True
        assert ctrl.cancel_event.is_set()

    def test_cancel_idempotent(self):
        ctrl = LifecycleController("op")
        ctrl.start()
        ctrl.cancel()
        ctrl.cancel()  # Should not raise
        assert ctrl.is_cancelled is True

    def test_complete(self):
        ctrl = LifecycleController("op")
        ctrl.start()
        ctrl.complete()
        assert ctrl.is_completed is True

    def test_complete_after_cancel_noop(self):
        ctrl = LifecycleController("op")
        ctrl.start()
        ctrl.cancel()
        ctrl.complete()  # Should not override cancelled
        assert ctrl.is_cancelled is True
        assert ctrl.is_completed is False

    def test_check_cancelled(self):
        ctrl = LifecycleController("op")
        ctrl.start()
        ctrl.check_cancelled()  # Should not raise
        ctrl.cancel()
        with pytest.raises(asyncio.CancelledError):
            ctrl.check_cancelled()

    def test_register_cleanup(self):
        ctrl = LifecycleController("op")
        cleanup_called = False

        def cleanup():
            nonlocal cleanup_called
            cleanup_called = True

        ctrl.register_cleanup(cleanup)
        ctrl.close()
        assert cleanup_called is True

    def test_register_cleanup_runs_on_cancel(self):
        ctrl = LifecycleController("op")
        cleanup_called = False

        def cleanup():
            nonlocal cleanup_called
            cleanup_called = True

        ctrl.register_cleanup(cleanup)
        ctrl.cancel()
        ctrl.close()
        assert cleanup_called is True

    @pytest.mark.asyncio
    async def test_wait_completes(self):
        ctrl = LifecycleController("op")
        ctrl.start()
        ctrl.complete()
        await ctrl.wait()  # Should not raise

    @pytest.mark.asyncio
    async def test_wait_cancelled_raises(self):
        ctrl = LifecycleController("op")
        ctrl.start()
        ctrl.cancel()
        with pytest.raises(asyncio.CancelledError):
            await ctrl.wait()

    @pytest.mark.asyncio
    async def test_register_task_cancelled_on_shutdown(self):
        ctrl = LifecycleController("op")
        ctrl.start()

        async def long_running():
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                raise

        task = asyncio.create_task(long_running())
        ctrl.register_task(task)
        ctrl.cancel()

        # Wait for the task to be cancelled (with timeout)
        done, pending = await asyncio.wait({task}, timeout=1.0)
        assert task in done, "Task was not cancelled within timeout"

    def test_abort_signal_delegates(self):
        ctrl = LifecycleController("op")
        assert ctrl.abort_signal.aborted is False
        ctrl.abort_signal.abort()
        assert ctrl.aborted is True


class TestShutdownManager:
    """Tests for ShutdownManager."""

    def test_register_controller(self):
        mgr = ShutdownManager()
        ctrl = LifecycleController("op")
        mgr.register_controller(ctrl)
        assert ctrl in mgr._controllers

    def test_shutdown_cancels_controllers(self):
        mgr = ShutdownManager()
        ctrl = LifecycleController("op")
        ctrl.start()
        mgr.register_controller(ctrl)

        asyncio.run(mgr.shutdown())
        assert ctrl.is_cancelled is True
        assert mgr.is_shutting_down() is True

    def test_shutdown_idempotent(self):
        mgr = ShutdownManager()
        ctrl = LifecycleController("op")
        ctrl.start()
        mgr.register_controller(ctrl)

        asyncio.run(mgr.shutdown())
        asyncio.run(mgr.shutdown())  # Should not raise

    def test_register_shutdown_callback(self):
        mgr = ShutdownManager()
        callback_called = False

        def callback():
            nonlocal callback_called
            callback_called = True

        mgr.register_shutdown_callback(callback)
        asyncio.run(mgr.shutdown())
        assert callback_called is True

    def test_global_shutdown_manager_is_shared(self):
        from zcoder.app.shutdown import shutdown_manager as mgr1
        from zcoder.app.shutdown import shutdown_manager as mgr2

        assert mgr1 is mgr2

    @pytest.mark.asyncio
    async def test_shutdown_waits_for_tasks(self):
        mgr = ShutdownManager()
        ctrl = LifecycleController("op")
        ctrl.start()

        async def cancellable_task():
            try:
                await ctrl.wait()
            except asyncio.CancelledError:
                pass  # Expected cancellation during test

        task = asyncio.create_task(cancellable_task())
        ctrl.register_task(task)
        mgr.register_controller(ctrl)

        await asyncio.sleep(0.05)  # Let task start waiting
        await mgr.shutdown()

        # Task should be done (cancelled)
        assert task.done()
