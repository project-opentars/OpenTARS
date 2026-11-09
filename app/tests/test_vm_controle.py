"""5.3 (F7, passo 2): o controle da VM de fora (tars_vm_controle) contra um QMP de mentira: nenhum QEMU é ligado. O mesmo código foi
conferido com uma VM de verdade em 08/11 (clicou no ícone do terminal, digitou um comando com $((6*7)) e ele rodou)."""
import json
import os
import socket
import sys
import tempfile
import threading
from pathlib import Path

if sys.platform == "win32":
    print("PULADO: socket unix")
    sys.exit(0)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tars_vm as vm  # noqa: E402
import tars_vm_controle as ctl  # noqa: E402
from PIL import Image  # noqa: E402

pasta = Path(tempfile.mkdtemp(prefix="vmq-"))
caminho = pasta / "q.sock"
recebidos = []


def servidor():
    s = socket.socket(socket.AF_UNIX)
    s.bind(str(caminho))
    s.listen(1)
    c, _ = s.accept()
    f = c.makefile("rwb")
    f.write(json.dumps({"QMP": {"version": {}, "capabilities": []}}).encode() + b"\n"); f.flush()
    for linha in f:
        cmd = json.loads(linha)
        recebidos.append(cmd)
        if cmd["execute"] == "input-send-event":
            f.write(json.dumps({"event": "INPUT_BUSY", "data": {}}).encode() + b"\n")         # um evento no meio: não é a resposta
        if cmd["execute"] == "screendump":
            Image.new("RGB", (1024, 768)).save(cmd["arguments"]["filename"])
        if cmd["execute"] == "falha":
            f.write(json.dumps({"error": {"class": "GenericError", "desc": "deu ruim"}}).encode() + b"\n")
        else:
            f.write(json.dumps({"return": {}}).encode() + b"\n")
        f.flush()
        if cmd["execute"] == "quit":
            break


threading.Thread(target=servidor, daemon=True).start()
c = ctl.ControleVM(caminho).conectar()
assert recebidos[0]["execute"] == "qmp_capabilities"

# tela: PNG e o tamanho vem do arquivo
destino = c.tela(pasta / "t" / "1.png")
assert destino.exists() and c.tela_tam == (1024, 768) and recebidos[-1] == {"execute": "screendump", "arguments": {"filename": str(destino), "format": "png"}}
print("OK: tela: screendump em PNG e o tamanho da tela vem do arquivo")

# mouse: pixel -> eixo 0..32767; clique = mover, apertar, soltar; duplo clique; fora da tela fica na borda
recebidos.clear()
c.clicar(1023, 767)
ev = [e for r in recebidos for e in r["arguments"]["events"]]
assert ev[0] == {"type": "abs", "data": {"axis": "x", "value": 32767}} and ev[1] == {"type": "abs", "data": {"axis": "y", "value": 32767}}
assert [e["data"]["down"] for e in ev if e["type"] == "btn"] == [True, False] and ev[2]["data"]["button"] == "left"
recebidos.clear()
c.clicar(0, 0, botao="direito", duplo=True)
ev = [e for r in recebidos for e in r["arguments"]["events"]]
assert ev[0]["data"]["value"] == 0 and [e["data"]["down"] for e in ev if e["type"] == "btn"] == [True, False, True, False] and ev[2]["data"]["button"] == "right"
recebidos.clear()
c.clicar(-50, 5000)
ev = [e for r in recebidos for e in r["arguments"]["events"]]
assert ev[0]["data"]["value"] == 0 and ev[1]["data"]["value"] == 32767, "fora da tela vira a borda"
recebidos.clear()
c.rolar(2); c.rolar(-1)
botoes = [e["data"]["button"] for r in recebidos for e in r["arguments"]["events"] if e["data"]["down"]]
assert botoes == ["wheel-down", "wheel-down", "wheel-up"]
print("OK: mouse: pixel vira eixo absoluto, clique e duplo clique (esquerdo e direito), borda da tela, rolagem")

# teclado: letras, maiúsculas com shift, símbolos, o que não existe é devolvido
recebidos.clear()
ignorados = c.digitar("Ab1 $\né😀", pausa=0)
teclas = [(e["data"]["key"]["data"], e["data"]["down"]) for r in recebidos for e in r["arguments"]["events"]]
assert teclas[:6] == [("shift", True), ("a", True), ("a", False), ("shift", False), ("b", True), ("b", False)] or \
    teclas[:8] == [("shift", True), ("a", True), ("a", False), ("shift", False), ("b", True), ("b", False), ("1", True), ("1", False)], teclas[:8]
nomes = [t[0] for t in teclas if t[1]]
assert nomes == ["shift", "a", "b", "1", "spc", "shift", "4", "ret"], nomes            # "$" é shift+4; "\n" é ret; é e o emoji não saem
assert ignorados == ["é", "😀"], ignorados
assert ctl.qcode_do_caractere("é") is None and ctl.qcode_do_caractere("|") == ("backslash", True) and ctl.qcode_do_caractere("(") == ("9", True)
recebidos.clear()
c.atalho("ctrl+alt+T")
teclas = [(e["data"]["key"]["data"], e["data"]["down"]) for r in recebidos for e in r["arguments"]["events"]]
assert teclas == [("ctrl", True), ("alt", True), ("t", True), ("t", False), ("alt", False), ("ctrl", False)], teclas
print("OK: teclado: letras, maiúsculas (shift), símbolos, enter; o que não existe (é, emoji) é devolvido; atalhos")

# erro do QEMU vira exceção, e encerrar fecha
try:
    c.comando("falha")
    raise AssertionError("tinha de levantar")
except RuntimeError as e:
    assert "deu ruim" in str(e)
c.encerrar()
assert recebidos[-1]["execute"] == "quit" and c._sock is None
print("OK: erro do QEMU vira exceção; encerrar manda quit e fecha o canal")

# a linha do qemu: o canal é um socket unix (sem porta de rede), tablet e teclado virtio (sem USB), e continua sem pasta do PC
argv = vm.argumentos_qemu("o.qcow2", internet=False, ollama=11435, controle="/tmp/vmx/q.sock")
texto = " ".join(argv)
assert "-qmp unix:/tmp/vmx/q.sock,server=on,wait=off" in texto and "virtio-tablet-pci" in texto and "virtio-keyboard-pci" in texto
assert argv[argv.index("-qmp") + 1].startswith("unix:"), "o canal de controle é socket unix, nunca tcp"
for proibido in ("-usb", "usb-", "virtfs", "fsdev", "vnc", "spice", "-monitor", "hostfwd"):
    assert proibido not in texto, proibido
assert "-qmp" not in " ".join(vm.argumentos_qemu("o.qcow2")), "sem pedir, nada de canal de controle"
print("OK: qemu com controle: socket unix sem porta de rede, tablet e teclado virtio (sem USB), sem pasta do PC")
print("TUDO OK.")
