"""5.2 (F6): o backend do macOS de verdade. Só roda no macOS (no CI e no Mac do amigo); fora dele, pula.
Sem as permissões de Acessibilidade e Gravação de Tela (o runner não tem), a seleção volta vazia e os títulos das
janelas são o nome do app: o teste confere só o que não depende delas."""
import plistlib
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tars_plataforma as p  # noqa: E402

if p.sistema() != "macos":
    print("test_plataforma_macos: PULADO (não é macOS)")
    sys.exit(0)

texto = "Olá, ação! 日本語 e um emoji 🚀"
p.escrever_area_de_transferencia(texto)
assert p.ler_area_de_transferencia() == texto, repr(p.ler_area_de_transferencia())
print("OK: área de transferência com acento, japonês e emoji")

pasta = Path(tempfile.mkdtemp(prefix="opentars-lixo-"))
arquivo = pasta / "apagar mesmo.txt"
arquivo.write_text("x")
p.lixeira(arquivo)
assert not arquivo.exists()
try:
    p.lixeira(pasta / "nao-existe.txt")
except OSError:
    pass
else:
    raise AssertionError("arquivo que não existe tem de dar erro")
print("OK: lixeira (NSFileManager, volta pelo Finder)")

assert p.autostart("opentars-teste-ci", "openTARS teste", [sys.executable, "-c", "print(1)"], True)
plist = p.arquivo_autostart("opentars-teste-ci")
dados = plistlib.loads(plist.read_bytes())
assert dados["Label"] == "opentars-teste-ci" and dados["RunAtLoad"] and dados["ProgramArguments"][0] == sys.executable
assert not p.autostart("opentars-teste-ci", "openTARS teste", [sys.executable], False) and not plist.exists()
print("OK: início automático pelo LaunchAgent")

p.notificar("openTARS", 'teste do CI com "aspas" e \\ barra')   # vai como argumento, não como AppleScript
inicio = time.time()
assert isinstance(p.ler_selecao(), str) and time.time() - inicio < 3
assert p.teclas_de_colar() == ("command", "v")
print("OK: notificação e seleção sem erro")

import tars_voz  # noqa: E402
assert tars_voz.comando_tocar() == ["afplay"] and "tocador" not in tars_voz.o_que_falta()
print(f"OK: voz: o tocador é o afplay; falta para a voz: {tars_voz.o_que_falta()}")

lista = p.programas()
assert any(e["id"] == "Calculator" for e in lista) and all(e["comando"][:2] == ["open", "-a"] for e in lista), lista[:5]
print(f"OK: catálogo de programas ({len(lista)} apps)")

antes = {j["id"] for j in p.janelas()}
subprocess.run(["open", "-a", "TextEdit"], check=True)
fim, nova = time.time() + 30, None
while time.time() < fim and not nova:
    time.sleep(0.5)
    nova = next((j for j in p.janelas() if j["id"] not in antes and j["classe"] in ("TextEdit", "Editor de Texto")), None)
if nova:
    x, y, largura, altura = p.area_util()
    assert largura > 0 and altura > 0
    print(f"OK: janelas: o TextEdit apareceu no Quartz ({nova['largura']}x{nova['altura']})")
else:
    print("  (o TextEdit não mostrou janela no runner: sem documento aberto ele só mostra o painel de abrir)")
subprocess.run(["osascript", "-e", 'quit app "TextEdit"'], capture_output=True)

import tars_acessibilidade as acess  # noqa: E402
motivo = acess.indisponivel()
if motivo:
    print(f"  (clique pelo nome indisponível no runner, como esperado sem a permissão: {motivo})")
else:
    janelas = acess.janelas()
    print(f"OK: AX liberada: {len(janelas)} janela(s) acessíveis")
    if janelas:
        print(f"OK: {janelas[0]['app']}: {acess.listar(janelas[0])['total']} elementos")
print("test_plataforma_macos: TUDO OK.")
