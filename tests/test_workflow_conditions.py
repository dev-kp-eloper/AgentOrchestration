import logging

import pytest

from src.common.metrics import metrics
from src.orchestrator.workflow import StepStatus, WorkflowManager, WorkflowStep
from src.orchestrator.workflow_conditions import (
    ConditionValidationError,
    WorkflowCondition,
)


class TestWorkflowConditions:
    def setup_method(self):
        self.manager = WorkflowManager()
        self.executed = []

    def _handler(self):
        self.executed.append("handler")

    def test_condition_allows_handler_dispatch(self):
        workflow = self.manager.create_workflow("dispatch")
        step = WorkflowStep(
            "run",
            self._handler,
            condition=WorkflowCondition("task['status'] == 'queued'"),
        )
        workflow.add_step(step)

        assert self.manager.execute_workflow(
            workflow.id,
            {"task": {"status": "queued"}},
        )
        assert self.executed == ["handler"]
        assert step.status == StepStatus.COMPLETED

    def test_false_condition_skips_handler(self):
        workflow = self.manager.create_workflow("dispatch")
        step = WorkflowStep(
            "run",
            self._handler,
            condition=WorkflowCondition("status == 'queued'"),
        )
        workflow.add_step(step)

        assert self.manager.execute_workflow(
            workflow.id,
            {"status": "cancelled"},
        )
        assert self.executed == []
        assert step.status == StepStatus.SKIPPED

    @pytest.mark.parametrize(
        "expression",
        [
            "state.update({'status': 'running'})",
            "handler()",
            "task.status == 'queued'",
            "__import__('os')",
            "payload * 100000000 == ''",
        ],
    )
    def test_side_effectful_expression_is_rejected_when_bound(
        self,
        expression,
    ):
        with pytest.raises(ConditionValidationError, match="disallowed"):
            WorkflowCondition(expression)

    def test_rejected_definition_log_does_not_expose_expression_data(
        self,
        caplog,
    ):
        with caplog.at_level(
            logging.WARNING,
            logger="src.orchestrator.workflow_conditions",
        ):
            with pytest.raises(ConditionValidationError):
                WorkflowCondition("state.update({'private-value': True})")

        assert "Rejected workflow condition definition" in caplog.text
        assert "private-value" not in caplog.text

    def test_unsafe_context_rejection_preserves_state_and_is_audited(
        self,
        caplog,
    ):
        class StateWithSideEffect:
            evaluated = False

            def __eq__(self, other):
                self.evaluated = True
                return True

        state = StateWithSideEffect()
        workflow = self.manager.create_workflow("dispatch")
        step = WorkflowStep(
            "run",
            self._handler,
            condition=WorkflowCondition("status == 'queued'"),
        )
        workflow.add_step(step)
        previous_rejections = metrics.snapshot()["counters"].get(
            "workflow.condition.rejected",
            0,
        )

        with caplog.at_level(
            logging.WARNING,
            logger="src.orchestrator.workflow",
        ):
            assert not self.manager.execute_workflow(
                workflow.id,
                {"status": state},
            )

        assert not state.evaluated
        assert self.executed == []
        assert workflow.status == StepStatus.PENDING
        assert step.status == StepStatus.PENDING
        assert (
            metrics.snapshot()["counters"]["workflow.condition.rejected"]
            == previous_rejections + 1
        )
        assert "Rejected workflow condition before dispatch" in caplog.text
        assert "queued" not in caplog.text

    def test_legacy_workflow_execution_contract_is_unchanged(self):
        workflow = self.manager.create_workflow("legacy")
        workflow.add_step(WorkflowStep("run", self._handler))

        result = self.manager.execute_workflow(workflow.id)

        assert result is True
        assert self.executed == ["handler"]
