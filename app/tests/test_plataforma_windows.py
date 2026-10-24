"""5.2 (F5): o backend do Windows de verdade. Só roda no Windows (no CI e no notebook); fora dele, pula."""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tars_plataforma as p  # noqa: E402

if p.sistema() != "windows":
    print("test_plataforma_windows: PULADO (não é Windows)")
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
print("OK: lixeira (SHFileOperation com desfazer)")

assert p.autostart("opentars-teste-ci", "openTARS teste", [sys.executable, "-c", "print(1)"], True)
lnk = p.arquivo_autostart("opentars-teste-ci")
assert lnk.exists() and lnk.suffix == ".lnk", lnk
assert not p.autostart("opentars-teste-ci", "openTARS teste", [sys.executable], False) and not lnk.exists()
print("OK: início automático pelo atalho na pasta Inicializar")

p.notificar("openTARS", "teste do CI")   # não espera; só não pode levantar erro
inicio = time.time()
selecao = p.ler_selecao()                # no runner não há o que copiar: volta vazio, rápido e sem erro
assert isinstance(selecao, str) and time.time() - inicio < 3
assert p.teclas_de_colar() == ("ctrl", "v")
print("OK: notificação e seleção sem erro")

import tars_voz  # noqa: E402
assert tars_voz.comando_tocar()[-1] == "--tocar" and "gravador" not in tars_voz.o_que_falta()
print(f"OK: voz: o tocador é o winsound (--tocar); falta para a voz: {tars_voz.o_que_falta()}")

# janelas e programas: abre o Bloco de Notas, acha a janela, foca, move e fecha
import subprocess  # noqa: E402
lista = p.programas()
assert any(e["comando"] == ["notepad.exe"] for e in lista) and all(e["nome"] and e["comando"] for e in lista), lista[:5]
print(f"OK: catálogo de programas ({len(lista)}: Menu Iniciar e os do Windows)")
antes = {j["id"] for j in p.janelas()}
proc = subprocess.Popen(["notepad.exe"])
fim, nova = time.time() + 20, None
while time.time() < fim and not nova:
    time.sleep(0.3)
    nova = next((j for j in p.janelas() if j["id"] not in antes and "notepad" in j["classe"].lower()), None)
assert nova, [(j["titulo"], j["classe"]) for j in p.janelas()]
try:
    p.focar_janela(nova["id"])
except OSError as e:
    print(f"  (o runner não deixou focar: {e})")
p.mover_janela(nova["id"], 50, 60, 500, 400)
movida = next(j for j in p.janelas() if j["id"] == nova["id"])
assert (movida["x"], movida["y"], movida["largura"], movida["altura"]) == (50, 60, 500, 400), movida
x, y, largura, altura = p.area_util()
assert largura > 0 and altura > 0
p.fechar_janela(nova["id"])
fim = time.time() + 10
while time.time() < fim and any(j["id"] == nova["id"] for j in p.janelas()):
    time.sleep(0.2)
assert not any(j["id"] == nova["id"] for j in p.janelas()), "o Bloco de Notas não fechou"
print(f"OK: janelas: '{nova['titulo']}' ({nova['classe']}) achada, movida e fechada")

# clique pelo nome (UI Automation): só onde o pacote uiautomation está (o Python instalado pelo instalar.ps1)
import tars_acessibilidade as acess  # noqa: E402
if acess.indisponivel():
    print(f"  (sem UI Automation neste Python: {acess.indisponivel()})")
else:
    subprocess.Popen(["notepad.exe"])
    fim, alvo = time.time() + 20, None
    while time.time() < fim and not alvo:
        time.sleep(0.5)
        alvo = acess.achar_janela(termos=["notepad", "bloco de notas"])
    try:
        assert alvo, [(j["app"], j["titulo"]) for j in acess.janelas()]
        lista = acess.listar(alvo)
        assert lista["total"] > 0, lista
        print(f"OK: UI Automation: '{alvo['titulo']}' tem {lista['total']} elementos: {sorted(lista['elementos'])}")
        r = acess.preencher(alvo, "", "escrito pelo openTARS")
        assert r["achou"] and (r["sucesso"] or r.get("precisa_digitar")), r
        print(f"OK: preencher pelo nome: {r}")
        menu = next((n for n in ("File", "Arquivo") if acess.localizar(alvo, n)), None)
        if menu:
            r = acess.clicar(alvo, menu)
            assert r["achou"], r
            print(f"OK: clicar pelo nome: {r.get('elemento')} (sucesso={r['sucesso']})")
        else:
            print(f"  (sem menu File/Arquivo nesta versão do Bloco de Notas: {acess.parecidos(alvo, 'file')})")
    finally:
        subprocess.run(["taskkill", "/F", "/IM", "notepad.exe"], capture_output=True)
print("test_plataforma_windows: TUDO OK.")
