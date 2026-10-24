"""5.2: o clique pelo nome no Windows (UI Automation) e no macOS (AX) passa pela mesma lógica do AT-SPI. Aqui o backend é
de mentira (uma calculadora em árvore); o de verdade roda no CI do Windows (test_plataforma_windows) e no Mac."""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tars_acessibilidade as acess  # noqa: E402


class No:
    def __init__(self, papel, nome="", filhos=(), valor=None, ativo=True):
        self.papel, self.nome, self.filhos, self.valor, self.ativo, self.clicado = papel, nome, list(filhos), valor, ativo, 0


visor = No("label", "0")
sete = No("push-button", "Seven")
campo = No("entry", "Search", valor="")
janela = No("frame", "Calculator", [No("panel", "", [visor, sete, No("push-button", "Plus"), campo,
                                                      No("push-button", "Memory", ativo=False)])])


def acionar(no):
    no.clicado += 1
    visor.nome = "7"
    return True


falso = types.SimpleNamespace(
    erro=lambda: None,
    janelas=lambda: [{"no": janela, "app": "CalculatorApp", "pid": 50, "titulo": "Calculator", "ativa": True}],
    papel=lambda no: no.papel, nome=lambda no: no.nome, descricao=lambda no: "",
    estados=lambda no: {"showing", "visible"} | ({"sensitive", "enabled"} if no.ativo else set()),
    filhos=lambda no: no.filhos, texto=lambda no: no.valor or "", acionar=acionar,
    retangulo=lambda no: (10, 20, 30, 40), escrever=lambda no, v: setattr(no, "valor", v) or True, focar=lambda no: None)

original = acess._nativo
acess._nativo = falso
acess._atspi.update(modulo=None, erro=None, tentou=False)
try:
    assert acess.indisponivel() is None
    alvo = acess.achar_janela(termos=["calculator"])
    assert alvo and alvo["pid"] == 50, alvo
    lista = acess.listar(alvo)
    assert lista["elementos"]["button"] == ["Seven", "Plus", "Memory (disabled)"], lista
    assert lista["elementos"]["text field"] == ["Search"] and "0" in lista["textos"], lista
    r = acess.clicar(alvo, "seven")
    assert r["sucesso"] and sete.clicado == 1 and r["elemento"] == "button 'Seven'" and "7" in r["textos"], r
    assert acess.localizar(alvo, "Plus") == ("button 'Plus'", (10, 20, 30, 40))
    r = acess.preencher(alvo, "search", "olá")
    assert r["sucesso"] and campo.valor == "olá", r
    assert acess.coordenadas_confiaveis(alvo) and acess.ativar() is False
    print("OK: listar, clicar pelo nome, localizar e preencher com o backend nativo (nomes de papel do AT-SPI)")

    acess._atspi.update(modulo=None, erro=None, tentou=False)
    falso.erro = lambda: "macOS has not allowed openTARS in Accessibility yet"
    assert "Accessibility" in acess.indisponivel() and acess.janelas() == []
    print("OK: sem a permissão, a acessibilidade fica indisponível com o motivo (a IA volta para o print)")
finally:
    acess._nativo = original
    acess._atspi.update(modulo=None, erro=None, tentou=False)
print("test_acessibilidade_outros_sistemas: TUDO OK.")
