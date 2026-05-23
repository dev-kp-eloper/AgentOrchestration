"""Side-effect-free conditions for workflow dispatch decisions."""

import ast
import logging
from types import MappingProxyType
from typing import Any, Dict, Set

logger = logging.getLogger(__name__)


class ConditionValidationError(ValueError):
    """Raised when a condition definition is not side-effect free."""


class ConditionEvaluationError(ValueError):
    """Raised when runtime values cannot be safely bound to a condition."""


class WorkflowCondition:
    """A boolean condition evaluated against immutable primitive values."""

    _ALLOWED_NODES = (
        ast.Expression,
        ast.BoolOp,
        ast.UnaryOp,
        ast.Compare,
        ast.Name,
        ast.Load,
        ast.Constant,
        ast.List,
        ast.Tuple,
        ast.Set,
        ast.Dict,
        ast.Subscript,
        ast.Slice,
        ast.And,
        ast.Or,
        ast.Not,
        ast.UAdd,
        ast.USub,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        ast.In,
        ast.NotIn,
        ast.Is,
        ast.IsNot,
    )

    def __init__(self, expression: str):
        if not isinstance(expression, str) or not expression.strip():
            logger.warning(
                "Rejected workflow condition definition: "
                "reason=empty expression"
            )
            raise ConditionValidationError(
                "condition must be a non-empty expression"
            )

        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            logger.warning(
                "Rejected workflow condition definition: reason=invalid syntax"
            )
            raise ConditionValidationError(
                "condition expression has invalid syntax"
            ) from exc

        for node in ast.walk(tree):
            if not isinstance(node, self._ALLOWED_NODES):
                reason = f"disallowed {type(node).__name__}"
                logger.warning(
                    "Rejected workflow condition definition: reason=%s",
                    reason,
                )
                raise ConditionValidationError(
                    f"condition expression contains {reason}"
                )

        self.expression = expression
        self._names = {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        }
        self._code = compile(tree, "<workflow-condition>", "eval")

    def evaluate(self, context: Dict[str, Any]) -> bool:
        bindings = self._snapshot_bindings(context)
        try:
            result = eval(self._code, {"__builtins__": {}}, bindings)
        except Exception as exc:
            raise ConditionEvaluationError(
                "condition could not be evaluated safely"
            ) from exc

        if not isinstance(result, bool):
            raise ConditionEvaluationError(
                "condition must evaluate to a boolean value"
            )
        return result

    def _snapshot_bindings(self, context: Dict[str, Any]) -> Dict[str, Any]:
        if type(context) is not dict:
            raise ConditionEvaluationError(
                "condition context must be a dictionary"
            )

        missing = self._names - context.keys()
        if missing:
            raise ConditionEvaluationError(
                "condition context is missing required values"
            )

        return {
            name: self._freeze(context[name], set()) for name in self._names
        }

    def _freeze(self, value: Any, active: Set[int]) -> Any:
        if value is None or type(value) in (bool, int, float, str):
            return value

        if type(value) in (list, tuple, set, frozenset, dict):
            identity = id(value)
            if identity in active:
                raise ConditionEvaluationError(
                    "condition context contains a cycle"
                )
            active.add(identity)
            try:
                if type(value) is dict:
                    frozen = {
                        self._freeze(key, active): self._freeze(item, active)
                        for key, item in value.items()
                    }
                    return MappingProxyType(frozen)
                frozen_items = [self._freeze(item, active) for item in value]
                if type(value) is list or type(value) is tuple:
                    return tuple(frozen_items)
                return frozenset(frozen_items)
            finally:
                active.remove(identity)

        raise ConditionEvaluationError(
            "condition context contains an unsupported value"
        )
