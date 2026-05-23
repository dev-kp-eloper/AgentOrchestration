import asyncio

import pytest

from src.agent.executor import AgentExecutor


class TestAgentExecutorContext:
    def test_nested_execution_restores_parent_context(self):
        executor = AgentExecutor()
        observed = []

        async def inner(agent_id, task):
            observed.append(executor.current_context()["agent_id"])
            return "inner"

        async def outer(agent_id, task):
            before = executor.current_context().copy()
            await executor.execute("inner-agent", {}, inner)
            after = executor.current_context().copy()
            assert before == after
            observed.append(after["agent_id"])
            return "outer"

        outer_id = asyncio.run(executor.execute("outer-agent", {}, outer))

        assert observed == ["inner-agent", "outer-agent"]
        assert executor.get_result(outer_id)["status"] == "completed"
        assert executor.current_context()["agent_id"] is None

    def test_failed_nested_execution_restores_parent_context(self):
        executor = AgentExecutor()

        async def inner(agent_id, task):
            raise RuntimeError("failed")

        async def outer(agent_id, task):
            before = executor.current_context().copy()
            inner_id = await executor.execute("inner-agent", {}, inner)
            assert executor.get_result(inner_id)["status"] == "failed"
            assert executor.current_context() == before

        asyncio.run(executor.execute("outer-agent", {}, outer))
        assert executor.current_context()["execution_id"] is None

    def test_cancellation_records_outcome_and_restores_context(self):
        executor = AgentExecutor()
        started = asyncio.Event()

        async def handler(agent_id, task):
            started.set()
            await asyncio.Event().wait()

        async def run():
            execution = asyncio.create_task(
                executor.execute("cancelled-agent", {"id": "task"}, handler)
            )
            await started.wait()
            execution_id = next(iter(executor._active_tasks))
            assert executor.cancel(execution_id)
            with pytest.raises(asyncio.CancelledError):
                await execution
            return execution_id

        execution_id = asyncio.run(run())

        assert executor.get_result(execution_id)["status"] == "cancelled"
        assert executor.current_context()["agent_id"] is None
        assert executor._active_tasks == {}
