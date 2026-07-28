import logging
import ast
import operator
import numpy as np
import scipy
from .base_tool import BaseTool

logger = logging.getLogger("alana.agent.tool.calculator")

class SafeMathEvaluator:
    """Avaliador matemático seguro usando Abstract Syntax Tree."""
    
    ALLOWED_OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
        ast.Mod: operator.mod
    }

    ALLOWED_FUNCTIONS = {
        'sqrt': np.sqrt,
        'log': np.log10,
        'ln': np.log,
        'sin': np.sin,
        'cos': np.cos,
        'tan': np.tan,
        'arcsin': np.arcsin,
        'arccos': np.arccos,
        'arctan': np.arctan
    }

    ALLOWED_CONSTANTS = {
        'pi': np.pi,
        'e': np.e
    }

    def evaluate(self, expr: str):
        try:
            # Substitui prefixos np. ou scipy. para simplificar a validação AST
            expr = expr.replace('np.', '').replace('scipy.', '')
            tree = ast.parse(expr, mode='eval')
            return self._eval_node(tree.body)
        except Exception as e:
            raise ValueError(f"Fórmula inválida ou não suportada: {e}")

    def _eval_node(self, node):
        if isinstance(node, ast.Constant):
            # Para Python 3.8+
            if isinstance(node.value, (int, float, complex)):
                return node.value
            raise ValueError("Apenas valores numéricos são permitidos.")
        elif isinstance(node, ast.Num):
            # Fallback para Python antigo
            return node.n
        elif isinstance(node, ast.BinOp):
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            op = type(node.op)
            if op in self.ALLOWED_OPERATORS:
                return self.ALLOWED_OPERATORS[op](left, right)
            raise ValueError(f"Operador binário não suportado: {op}")
        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand)
            op = type(node.op)
            if op in self.ALLOWED_OPERATORS:
                return self.ALLOWED_OPERATORS[op](operand)
            raise ValueError(f"Operador unário não suportado: {op}")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
                if func_name in self.ALLOWED_FUNCTIONS:
                    args = [self._eval_node(arg) for arg in node.args]
                    return self.ALLOWED_FUNCTIONS[func_name](*args)
                raise ValueError(f"Função não autorizada: {func_name}")
            raise ValueError("Chamada de função inválida (apenas funções matemáticas diretas).")
        elif isinstance(node, ast.Name):
            if node.id in self.ALLOWED_CONSTANTS:
                return self.ALLOWED_CONSTANTS[node.id]
            raise ValueError(f"Variável ou constante desconhecida: {node.id}")
        else:
            raise ValueError(f"Estrutura não suportada: {type(node).__name__}")


class EngineeringCalculatorTool(BaseTool):
    name = "calculate"
    description = "Executa cálculos matemáticos e de engenharia complexos de forma segura. Use para validar impedâncias, frequências, dissipação ou fórmulas técnicas. Argumento: 'expression' (ex: 'sqrt(10**2 + 5**2)')"
    
    def __init__(self):
        self.evaluator = SafeMathEvaluator()
        
    async def execute(self, expression: str = None, **kwargs) -> str:
        expr = expression or kwargs.get("expression")
        
        if not expr:
            return "[ERRO DE CÁLCULO]: Nenhuma expressão fornecida. DICA: Use o argumento 'expression', ex: {'expression': '2 + 2'}"
            
        try:
            logger.info(f"🧮 Alana calculando com AST Seguro: {expr}")
            result = self.evaluator.evaluate(expr)
            return f"[CÁLCULO EXECUTADO]\nEXPRESSÃO: {expr}\nRESULTADO: {result}"
        except Exception as e:
            logger.error(f"Erro no cálculo: {e}")
            return f"[ERRO DE SEGURANÇA/CÁLCULO]: '{str(e)}'. DICA: A calculadora roda em modo estrito (AST). Use apenas funções matemáticas (sin, cos, sqrt) e constantes (pi, e) numéricas válidas."
