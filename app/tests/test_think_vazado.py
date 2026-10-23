"""4.0: raciocínio que vaza no texto da resposta (print real: o Gargantua
escreveu o raciocínio em inglês como resposta, com um "</think>" solto no
fim, e o turno seguinte começou com "</think>").

O FiltroPensamento separa de novo: o raciocínio vai como pensamento (cinza
na janela), a resposta fica limpa, nenhuma tag aparece e o histórico guarda
só a resposta."""

import json
import os
import sys

from _util import carregar_tars

tars = carregar_tars()
F = tars.FiltroPensamento


def rodar(pedacos):
    f = F()
    eventos = []
    for p in pedacos:
        eventos += f.alimentar(p)
    eventos += f.terminar()
    return f, eventos


def textos(eventos, tipo):
    return "".join(t for k, t in eventos if k == tipo)


def picar(texto, n=7):
    return [texto[i:i + n] for i in range(0, len(texto), n)]


# 1. O caso do print: raciocínio sem <think>, "</think>" no fim, depois a resposta
bruto = ('Okay, the user said "abre o claude". Let me figure out what they mean.\n\nSo, I should call '
         'open_application.\n</think>\n\nAbri o Claude.')
f, ev = rodar(picar(bruto))
assert f.conteudo == "Abri o Claude.", f.conteudo
assert "Let me figure out" in f.texto_pensado and "think>" not in f.texto_pensado
assert "think>" not in json.dumps(ev) and "Let me" not in textos(ev, "resposta"), ev
assert "Let me figure out" in textos(ev, "pensamento") and textos(ev, "resposta") == "Abri o Claude.", ev
print("OK: raciocínio sem <think> e com '</think>' no fim vira pensamento; a resposta fica limpa")

# 2. Turno que começa com um "</think>" solto
f, ev = rodar(picar("</think>\n\nThe application \"Claude\" has been opened."))
assert f.conteudo == 'The application "Claude" has been opened.' and not f.texto_pensado, (f.conteudo, ev)
assert "think" not in json.dumps(ev)
print("OK: '</think>' solto no começo some")

# 3. <think> ... </think> normal dentro do texto (tags picadas em pedaços de 3)
f, ev = rodar(picar("<think>\npreciso abrir o app\n</think>\n\nPronto, abri.", 3))
assert f.conteudo == "Pronto, abri." and f.texto_pensado == "preciso abrir o app", (f.conteudo, f.texto_pensado)
assert "think>" not in json.dumps(ev) and "<" not in json.dumps(ev), ev
print("OK: <think>...</think> com as tags picadas entre pedaços vira pensamento")

# 4. Resposta normal: passa igual, sem atraso de tag
for resp in ("Oi! Tudo certo por aqui.", "12 x 8 = 96", "Abri a calculadora e fiz a conta: 96.",
             "Okay, abri o Firefox pra você."[:0] or "Claro! Abri o Firefox."):
    f, ev = rodar(picar(resp))
    assert f.conteudo == resp and not f.texto_pensado and textos(ev, "resposta") == resp, (resp, ev)
print("OK: resposta comum passa igual")

# 5. Começa como 'Okay, ...' mas era a resposta (nunca fechou): vira resposta no fim
resp = "Okay, I opened the calculator for you and the result is 96."
f, ev = rodar(picar(resp))
assert f.conteudo == resp and not f.texto_pensado, (f.conteudo, f.texto_pensado)
assert textos(ev, "resposta") == resp
print("OK: 'Okay, ...' que nunca fecha era a resposta mesmo")

# 6. Pareceu resposta, mas veio '</think>': o que foi mostrado vira pensamento (era_pensamento)
bruto = "Preciso ver quais apps existem. Vou chamar a ferramenta certa pra isso agora.\n</think>\nAbri."
f, ev = rodar(picar(bruto))
assert f.conteudo == "Abri." and "Preciso ver" in f.texto_pensado, (f.conteudo, f.texto_pensado)
assert any(k == "era_pensamento" for k, _ in ev), ev
print("OK: texto mostrado como resposta que termina em '</think>' é repintado como pensamento")

# 7. De ponta a ponta no turno de streaming (Ollama falso): eventos e retorno


class Resposta:
    def __init__(self, pedacos):
        self.linhas = [json.dumps({"message": {"content": p}, "done": False}).encode() for p in pedacos]
        self.linhas.append(json.dumps({"message": {"content": ""}, "done": True}).encode())

    def iter_lines(self):
        return iter(self.linhas)

    def close(self):
        pass


eventos = []
tars.emitir = lambda tipo, **dados: eventos.append((tipo, dados))
bruto = 'Okay, the user wants the calculator. I will call open_application.\n</think>\n\nAbri a calculadora.'
tars._chamar_ollama_stream = lambda payload: (Resposta(picar(bruto, 5)), None)
resultado, erro = tars._executar_turno_streaming("ProjectOpenTARS/gargantua:1.0", [{"role": "user", "content": "x"}],
                                                 None, pensar=False)
assert not erro and resultado["content"] == "Abri a calculadora." and "I will call" in resultado["thinking"], resultado
assert "think>" not in json.dumps(eventos), eventos
assert [e for e in eventos if e[0] == "pensamento"] and eventos[-1][0] == "fim_stream"
assert "".join(d["texto"] for k, d in eventos if k == "resposta") == "Abri a calculadora."
print("OK: no turno de verdade, a tela recebe pensamento + resposta limpa, e o histórico guarda só a resposta")

# 8. Janela: 'resposta_era_pensamento' repinta de cinza (só com tkinter e display)
try:
    import tkinter as tk
    sys.modules["tars"] = tars
    import tars_gui
    raiz = tk.Tk()
except Exception as e:
    print(f"PULADO (janela): {e}")
else:
    area = tars_gui.AreaConversa.__new__(tars_gui.AreaConversa)
    texto = tk.Text(raiz)
    for nome in ("rotulo_ia", "pensamento", "pensamento_rotulo"):
        texto.tag_configure(nome)
    area.t, area.ultimo_estilo, area.blocos, area.fontes = texto, None, [], None
    area.escrever(tars_gui.formatar_evento("resposta", {"texto": "Let me think about it", "inicio": True}))
    area.virar_pensamento()
    conteudo = texto.get("1.0", "end-1c")
    assert "openTARS" not in conteudo and "Let me think about it" in conteudo, conteudo
    inicio = texto.search("Let me", "1.0")
    assert "pensamento" in texto.tag_names(inicio), texto.tag_names(inicio)
    raiz.destroy()
    print("OK: na janela, a 'resposta' que era raciocínio vira texto cinza de pensamento")

print("\nTUDO OK.")
