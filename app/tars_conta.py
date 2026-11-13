"""Contas por código: o modelo de 270M erra aritmética e a busca devolve lixo ("square root of 128" trazia a Wikipédia)."""
import ast
import math
import operator
import re

_PEDIDO = re.compile(r"^(please |por favor |pode |can you |could you )?(what is|what's|whats|how much is|how much|calculate|calc|compute|solve|work out|"
                     r"quanto e|quanto da|quanto vale|qual e|qual o valor de|qual|calcula|calcule|calcular|resolve|resolva|conta)?\s*(a |o |the )?")
_PALAVRAS = [
    (r"\braiz quadrada d[eao]\s*", "sqrt "), (r"\bsquare root of\s*", "sqrt "), (r"\braiz de\s*", "sqrt "), (r"\bsqrt( of)?\s*", "sqrt "),
    (r"\bmetade d[eao]\s*", "0.5*"), (r"\bhalf of\s*", "0.5*"), (r"\bdobro d[eao]\s*", "2*"), (r"\bdouble of\s*", "2*"), (r"\bdouble\s+(?=\d)", "2*"), (r"\btriplo d[eao]\s*", "3*"),
    (r"(\d)\s*(%|por cento|percent)\s*(de|do|da|of)\s*", r"\1*0.01*"),
    (r"\b(elevado a|elevado ao?|to the power of|to the)\s*", "**"), (r"\bao quadrado\b|\bsquared\b", "**2"), (r"\bao cubo\b|\bcubed\b", "**3"), (r"\^", "**"),
    (r"\b(vezes|times|multiplicado por|multiplied by)\b", "*"), (r"(?<=\d)\s*x\s*(?=\d)", "*"),
    (r"\b(dividido por|divided by|over)\b", "/"), (r"\b(mais|plus)\b", "+"), (r"\b(menos|minus)\b", "-"),
]
_OPERACOES = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Mod: operator.mod}


def _valor(no):
    if isinstance(no, ast.Constant) and type(no.value) in (int, float):
        return no.value
    if isinstance(no, ast.UnaryOp) and isinstance(no.op, (ast.USub, ast.UAdd)):
        return -_valor(no.operand) if isinstance(no.op, ast.USub) else _valor(no.operand)
    if isinstance(no, ast.BinOp) and isinstance(no.op, ast.Pow):
        base, expoente = _valor(no.left), _valor(no.right)
        if abs(expoente) > 300 or abs(base) > 1e6:     # 9**9**9 prenderia a placa
            raise ValueError
        return base ** expoente
    if isinstance(no, ast.BinOp) and type(no.op) in _OPERACOES:
        return _OPERACOES[type(no.op)](_valor(no.left), _valor(no.right))
    if isinstance(no, ast.Call) and getattr(no.func, "id", "") == "sqrt" and len(no.args) == 1:
        return math.sqrt(_valor(no.args[0]))
    raise ValueError


def _numero(valor, idioma):
    if isinstance(valor, float) and valor.is_integer() and abs(valor) < 1e15:
        valor = int(valor)
    texto = str(valor) if isinstance(valor, int) else f"{valor:.6g}" if abs(valor) >= 1e6 else f"{valor:.6f}".rstrip("0")
    return texto.replace(".", ",") if idioma == "pt" else texto


def resolver(n, idioma):
    """'2 + 2 = 4' para um pedido normalizado que é só uma conta; None para o resto."""
    texto = _PEDIDO.sub("", n.strip(" ?.!=")).strip(" ?.!=")
    for padrao, troca in _PALAVRAS:
        texto = re.sub(padrao, troca, texto)
    texto = re.sub(r"(?<=\d),(?=\d)", ".", texto)
    texto = re.sub(r"sqrt\s*(\d+(?:\.\d+)?)", r"sqrt(\1)", texto).strip()
    if not re.search(r"\d", texto) or not re.search(r"[-+*/%]|sqrt", texto) or re.fullmatch(r"[\d/.-]+", texto) and re.search(r"\d[/-]\d+[/-]\d", texto):
        return None     # sem operação, ou uma data
    if re.search(r"[^\d\s+\-*/%().sqrt]", texto):
        return None
    try:
        return _numero(_valor(ast.parse(texto, mode="eval").body), idioma)
    except (ValueError, SyntaxError, ZeroDivisionError, OverflowError, TypeError):
        return None
