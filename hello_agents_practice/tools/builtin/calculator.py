"""Safe arithmetic calculator tool."""

import ast
import math
import operator
from collections.abc import Callable, Mapping
from typing import Any

from ..base import Tool


Number = int | float
BinaryOperator = Callable[[Number, Number], Number]
UnaryOperator = Callable[[Number], Number]

BINARY_OPERATORS: dict[type[ast.operator], BinaryOperator] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
UNARY_OPERATORS: dict[type[ast.unaryop], UnaryOperator] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


class CalculatorTool(Tool):
    name = "calculator"
    description = "Evaluate one arithmetic expression using numbers and +, -, *, /, //, %, or **."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Arithmetic expression to evaluate.",
                }
            },
            "required": ["expression"],
            "additionalProperties": False,
        }

    def run(self, parameters: Mapping[str, Any]) -> str:
        raw_expression = parameters.get("expression") or parameters.get("input") or ""
        if not isinstance(raw_expression, str):
            raise TypeError("calculator expression must be a string.")
        expression = raw_expression.strip()
        if not expression:
            raise ValueError("calculator requires an expression.")
        if len(expression) > 200:
            raise ValueError("calculator expression is too long.")

        tree = ast.parse(expression, mode="eval")
        if sum(1 for _ in ast.walk(tree)) > 50:
            raise ValueError("calculator expression is too complex.")
        result = self._evaluate(tree.body)
        if isinstance(result, float) and not math.isfinite(result):
            raise ValueError("calculator result must be finite.")
        if abs(result) > 1e100:
            raise ValueError("calculator result is too large.")
        return str(result)

    def _evaluate(self, node: ast.expr) -> Number:
        if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
            return node.value

        if isinstance(node, ast.UnaryOp):
            operation = UNARY_OPERATORS.get(type(node.op))
            if operation is None:
                raise ValueError("unsupported unary operator.")
            return operation(self._evaluate(node.operand))

        if isinstance(node, ast.BinOp):
            operation = BINARY_OPERATORS.get(type(node.op))
            if operation is None:
                raise ValueError("unsupported binary operator.")
            left = self._evaluate(node.left)
            right = self._evaluate(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 10:
                raise ValueError("calculator exponent is too large.")
            return operation(left, right)

        raise ValueError("calculator accepts arithmetic expressions only.")
