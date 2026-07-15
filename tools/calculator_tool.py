import ast
import math
import operator

from .base_tool import BaseTool


class CalculatorTool(BaseTool):
    def __init__(self, config: dict):
        self.safe_operators = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.Pow: operator.pow,
            ast.USub: operator.neg,
            ast.UAdd: operator.pos,
            ast.Mod: operator.mod,
        }
        self.safe_names = {"abs": abs, "round": round, "sqrt": math.sqrt, "pi": math.pi}

    @property
    def name(self):
        return "calculate"

    @property
    def description(self):
        return "Evaluate a bounded arithmetic expression"

    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        }

    def _eval(self, node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.Name) and node.id in self.safe_names:
            return self.safe_names[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in self.safe_operators:
            return self.safe_operators[type(node.op)](self._eval(node.left), self._eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in self.safe_operators:
            return self.safe_operators[type(node.op)](self._eval(node.operand))
        if isinstance(node, ast.Call) and not node.keywords:
            function = self._eval(node.func)
            if not callable(function):
                raise ValueError("Unsupported function")
            return function(*[self._eval(arg) for arg in node.args])
        raise ValueError(f"Unsupported expression node: {type(node).__name__}")

    def execute(self, expression: str):
        try:
            if len(expression) > 500:
                raise ValueError("Expression is too long")
            return {"success": True, "result": self._eval(ast.parse(expression, mode="eval").body)}
        except (SyntaxError, TypeError, ValueError, ZeroDivisionError) as exc:
            return {"success": False, "error": str(exc)}
