"""Voz: "contínua" ouve sem o nome; "tars" só com o nome; gravador que falha vira erro explicado."""
import array, math, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tars_voz as v

def tom(ms, amp):
    n = int(v.TAXA * ms / 1000)
    a = array.array("h", (int(amp * math.sin(2 * math.pi * 300 * i / v.TAXA)) for i in range(n)))
    return a.tobytes()

def gravar():
    quieto = tom(1, 0)  # zeros
    yield b"\x01\x00" * int(v.TAXA * 0.5)                # ruído de fundo mínimo
    for _ in range(3):
        yield tom(600, 6000)                               # fala
        yield b"\x01\x00" * int(v.TAXA * 0.9)              # silêncio
    time.sleep(0.3)

class Falso:
    def __init__(self, texto): self.texto = texto
    def transcrever(self, *a, **k): return self.texto
    def aquecer(self): pass

def rodar(modo, texto):
    pedidos = []
    o = v.Ouvinte(pedidos.append, "pt_BR", modo=modo, gravar=gravar, transcritor=Falso(texto),
                  transcritor_ativacao=Falso(texto), aquecer=False)
    o._rodar()
    return pedidos

assert rodar("continua", "abre o firefox") , "contínua não ouviu"
print("OK: contínua: fala sem dizer TARS vira pedido")
assert rodar("continua", "TARS, abre o firefox")[0] == "abre o firefox"
print("OK: contínua: se disser TARS, o nome é tirado")
assert rodar("ativacao", "abre o firefox") == []
print("OK: palavra TARS: sem o nome, não age")
assert rodar("ativacao", "TARS, abre o firefox")[0] == "abre o firefox"
print("OK: palavra TARS: com o nome, age")

# gravador que falha: erro explicado em vez de "parado" mudo
estados = []
o = v.Ouvinte(lambda t: None, "pt_BR", modo="continua", ao_estado=estados.append, aquecer=False)
orig, v.GRAVADORES = v.GRAVADORES, (("false", ["false"]),)
try:
    o._rodar()
finally:
    v.GRAVADORES = orig
assert any(e.startswith("erro:microfone") for e in estados), estados
print("OK: gravador que morre vira erro:", [e for e in estados if e.startswith("erro")][0][:90])
print("TUDO OK.")
