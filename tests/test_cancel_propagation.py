"""Tests for cancellation propagation — avoid child retry after parent cancel (#3695)."""

import pytest
from src.orchestrator.workflow import (
    Workflow,
    WorkflowCancelledError,
    WorkflowManager,
    WorkflowStep,
    StepStatus,
)


def ok_handler():
    return "done"


def failing_handler():
    raise RuntimeError("transient failure")


def cancel_handler():
    raise WorkflowCancelledError("handler detected cancellation")


class TestCancelWorkflow:
    """cancel_workflow() must propagate CANCELLED to the workflow and all pending steps."""

    def test_cancel_returns_true_for_existing_workflow(self):
        mgr = WorkflowManager()
        wf = mgr.create_workflow("wf")
        assert mgr.cancel_workflow(wf.id) is True

    def test_cancel_returns_false_for_unknown_workflow(self):
        mgr = WorkflowManager()
        assert mgr.cancel_workflow("nonexistent") is False

    def test_cancel_sets_workflow_status(self):
        mgr = WorkflowManager()
        wf = mgr.create_workflow("wf")
        mgr.cancel_workflow(wf.id)
        assert wf.status == StepStatus.CANCELLED

    def test_cancel_propagates_to_pending_steps(self):
        mgr = WorkflowManager()
        wf = mgr.create_workflow("wf")
        step = WorkflowStep("s1", ok_handler)
        wf.add_step(step)
        mgr.cancel_workflow(wf.id)
        assert step.status == StepStatus.CANCELLED

    def test_cancel_does_not_regress_completed_step(self):
        mgr = WorkflowManager()
        wf = mgr.create_workflow("wf")
        step = WorkflowStep("s1", ok_handler)
        step.status = StepStatus.COMPLETED
        wf.add_step(step)
        mgr.cancel_workflow(wf.id)
        assert step.status == StepStatus.COMPLETED  # already done — must not be overwritten

    def test_cancel_is_idempotent(self):
        mgr = WorkflowManager()
        wf = mgr.create_workflow("wf")
        assert mgr.cancel_workflow(wf.id) is True
        assert mgr.cancel_workflow(wf.id) is True  # second call must not raise


class TestExecuteWorkflowCancellationGuard:
    """execute_workflow() must refuse to run (or retry) when parent is cancelled."""

    def test_pre_cancelled_workflow_is_not_executed(self):
        mgr = WorkflowManager()
        wf = mgr.create_workflow("wf")
        executed = []
        wf.add_step(WorkflowStep("s1", lambda: executed.append(1) or "ok"))
        mgr.cancel_workflow(wf.id)
        result = mgr.execute_workflow(wf.id)
        assert result is False
        assert executed == []  # handler must never be called

    def test_pre_cancelled_step_is_skipped(self):
        mgr = WorkflowManager()
        wf = mgr.create_workflow("wf")
        step = WorkflowStep("s1", ok_handler)
        wf.add_step(step)
        mgr.cancel_workflow(wf.id)
        mgr.execute_workflow(wf.id)
        assert step.status == StepStatus.CANCELLED

    def test_mid_run_cancellation_stops_remaining_steps(self):
        """Cancellation during step-2 must prevent step-3 from executing."""
        mgr = WorkflowManager()
        wf = mgr.create_workflow("wf")
        ran = []

        def step1():
            ran.append(1)
            return "ok"

        def step2():
            ran.append(2)
            # Simulate external cancel arriving mid-execution
            mgr.cancel_workflow(wf.id)
            return "ok"

        def step3():
            ran.append(3)
            return "ok"

        wf.add_step(WorkflowStep("s1", step1))
        wf.add_step(WorkflowStep("s2", step2))
        wf.add_step(WorkflowStep("s3", step3))

        result = mgr.execute_workflow(wf.id)
        assert result is False
        assert 3 not in ran  # step-3 must never run after parent cancel

    def test_retry_is_suppressed_after_parent_cancel(self):
        """After a cancel, the retry loop must NOT keep attempting the failing step."""
        mgr = WorkflowManager()
        wf = mgr.create_workflow("wf")
        attempts = []

        def flaky():
            attempts.append(1)
            mgr.cancel_workflow(wf.id)
            raise RuntimeError("fail")

        step = WorkflowStep("s1", flaky, retries=5)
        wf.add_step(step)
        mgr.execute_workflow(wf.id)

        # Must have been attempted exactly once — not 6 times
        assert len(attempts) == 1
        assert step.status == StepStatus.CANCELLED

    def test_workflow_cancelled_error_propagates_cancellation(self):
        """WorkflowCancelledError raised by a handler must cancel the whole workflow."""
        mgr = WorkflowManager()
        wf = mgr.create_workflow("wf")
        step = WorkflowStep("s1", cancel_handler)
        wf.add_step(step)
        result = mgr.execute_workflow(wf.id)
        assert result is False
        assert step.status == StepStatus.CANCELLED
        assert wf.status == StepStatus.CANCELLED

    def test_normal_execution_completes_when_not_cancelled(self):
        mgr = WorkflowManager()
        wf = mgr.create_workflow("wf")
        wf.add_step(WorkflowStep("s1", ok_handler))
        wf.add_step(WorkflowStep("s2", ok_handler))
        assert mgr.execute_workflow(wf.id) is True
        assert wf.status == StepStatus.COMPLETED

    def test_step_retries_work_before_any_cancel(self):
        """Retries must still work normally when no cancellation occurs."""
        mgr = WorkflowManager()
        wf = mgr.create_workflow("wf")
        call_count = [0]

        def flaky_then_ok():
            call_count[0] += 1
            if call_count[0] < 3:
                raise RuntimeError("not yet")
            return "ok"

        step = WorkflowStep("s1", flaky_then_ok, retries=5)
        wf.add_step(step)
        assert mgr.execute_workflow(wf.id) is True
        assert call_count[0] == 3
        assert step.status == StepStatus.COMPLETED
