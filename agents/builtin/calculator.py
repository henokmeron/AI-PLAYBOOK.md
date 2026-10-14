"""Safe arithmetic calculator: parses with ``ast`` and evaluates a whitelist. No eval()."""
from __future__ import annotations

import ast
import decimal
from decimal import Decimal
from typing import Any

from ..tools import Tool, ToolInputError

MAX_EXPRESSION_CHARS = 300
MAX_NODES = 120
MAX_EXPONENT = 64
MAX_MAGNITUDE = Decimal("1e30")
CONTEXT = decimal.Context(prec=34, traps=[decimal.InvalidOperation, decimal.DivisionByZero, decimal.Overflow])


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ToolInputError("only numeric literals are allowed")
    return Decimal(str(value))


def _check(value: Decimal) -> Decimal:
    if not value.is_finite() or abs(value) > MAX_MAGNITUDE:
        raise ToolInputError("result is outside the supported numeric range")
    return value


def _round(value: Decimal, places: Decimal | None = None) -> Decimal:
    digits = 0 if places is None else int(places)
    if places is not None and (places != digits or not 0 <= digits <= 12):
        raise ToolInputError("round() places must be an integer from 0 to 12")
    return value.quantize(Decimal(1).scaleb(-digits), rounding=decimal.ROUND_HALF_UP, context=CONTEXT)


FUNCTIONS = {
    "abs": (1, 1, lambda args: abs(args[0])),
    "round": (1, 2, lambda args: _round(*args)),
    "min": (1, 20, lambda args: min(args)),
    "max": (1, 20, lambda args: max(args)),
    "sqrt": (1, 1, lambda args: args[0].sqrt(context=CONTEXT)),
}


def evaluate(expression: str) -> Decimal:
    if not isinstance(expression, str) or not expression.strip():
        raise ToolInputError("expression must be a non-empty string")
    if len(expression) > MAX_EXPRESSION_CHARS:
        raise ToolInputError("expression is too long")
    try:
        tree = ast.parse(expression.replace("×", "*").replace("÷", "/"), mode="eval")
    except SyntaxError:
        raise ToolInputError("expression is not valid arithmetic") from None
    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        raise ToolInputError("expression is too complex")
    try:
        return _check(_eval(tree.body))
    except (decimal.InvalidOperation, decimal.DivisionByZero, decimal.Overflow):
        raise ToolInputError("arithmetic error (for example division by zero)") from None


def _eval(node: ast.AST) -> Decimal:
    if isinstance(node, ast.Constant):
        return _to_decimal(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _eval(node.operand)
        return operand if isinstance(node.op, ast.UAdd) else -operand
    if isinstance(node, ast.BinOp):
        left, right = _eval(node.left), _eval(node.right)
        op = node.op
        if isinstance(op, ast.Add):
            return _check(CONTEXT.add(left, right))
        if isinstance(op, ast.Sub):
            return _check(CONTEXT.subtract(left, right))
        if isinstance(op, ast.Mult):
            return _check(CONTEXT.multiply(left, right))
        if isinstance(op, ast.Div):
            return _check(CONTEXT.divide(left, right))
        if isinstance(op, ast.FloorDiv):
            return _check(CONTEXT.divide_int(left, right))
        if isinstance(op, ast.Mod):
            return _check(CONTEXT.remainder(left, right))
        if isinstance(op, ast.Pow):
            if right != right.to_integral_value() or abs(right) > MAX_EXPONENT:
                raise ToolInputError(f"exponent must be an integer with magnitude <= {MAX_EXPONENT}")
            return _check(CONTEXT.power(left, right))
        raise ToolInputError("unsupported operator")
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS or node.keywords:
            raise ToolInputError("only abs, round, min, max and sqrt calls are allowed")
        low, high, fn = FUNCTIONS[node.func.id]
        if not low <= len(node.args) <= high:
            raise ToolInputError(f"{node.func.id}() received the wrong number of arguments")
        return _check(fn([_eval(arg) for arg in node.args]))
    raise ToolInputError(f"unsupported expression element: {type(node).__name__}")


def _plain(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _handler(arguments: dict[str, Any]) -> dict[str, Any]:
    value = evaluate(arguments["expression"])
    return {"expression": arguments["expression"], "result": _plain(value)}


def calculator_tool() -> Tool:
    return Tool(
        name="calculator",
        description=(
            "Exact decimal arithmetic. Supports + - * / // % ** parentheses and abs, round, "
            "min, max, sqrt. Use it for every calculation instead of mental arithmetic."
        ),
        input_schema={
            "type": "object",
            "properties": {"expression": {"type": "string", "minLength": 1, "maxLength": MAX_EXPRESSION_CHARS}},
            "required": ["expression"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"expression": {"type": "string"}, "result": {"type": "string"}},
            "required": ["expression", "result"],
            "additionalProperties": False,
        },
        handler=_handler,
        idempotent=True,
        timeout_seconds=2.0,
        tags=("compute",),
    )
