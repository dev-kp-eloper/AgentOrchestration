import asyncio
import pytest

from src.sdk.decorators import task

class TestTaskDecorator:
    def test_async_task_handler(self):
        @task()
        async def async_handler():
            return "async-ok"

        result = asyncio.run(async_handler())

        assert result == "async-ok"

    def test_sync_task_handler(self):
        @task()
        def sync_handler():
            return "sync-ok"

        result = asyncio.run(sync_handler())

        assert result == "sync-ok"

    def test_sync_handler_timeout(self):
        @task(timeout=1)
        def slow_handler():
            import time
            time.sleep(2)
            return "done"

        with pytest.raises(TimeoutError):
            asyncio.run(slow_handler())

    def test_async_handler_timeout(self):
        @task(timeout=1)
        async def slow_async():
            await asyncio.sleep(2)
            return "done"

        with pytest.raises(TimeoutError):
            asyncio.run(slow_async())

    def test_sync_exception_propagation(self):
        @task()
        def failing():
            raise ValueError("sync failure")

        with pytest.raises(ValueError):
            asyncio.run(failing())

    def test_async_exception_propagation(self):
        @task()
        async def failing():
            raise RuntimeError("async failure")

        with pytest.raises(RuntimeError):
            asyncio.run(failing())

    def test_metadata_attributes(self):
        @task(timeout=10)
        def handler():
            return "ok"

        assert handler._task_timeout == 10
        assert handler._task_async is False
