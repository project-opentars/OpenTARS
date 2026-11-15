"""14/11: atualização do app empacotado (Windows e macOS) pela Release: versao.json com a REVISAO, o instalador do sistema e
o SHA-256 do SHA256SUMS. Sem rede: as respostas do GitHub são de mentira."""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tars_atualizacao as a  # noqa: E402

SHA = "b" * 64
G = "https://github.com/project-opentars/OpenTARS/releases/download/5.3/"
RELEASE = {"tag_name": "5.3", "body": "notas", "assets": [{"name": n, "browser_download_url": G + n} for n in
           ("versao.json", "SHA256SUMS", "opentars-setup.exe", "openTARS-macos-arm64.dmg", "opentars_all.deb")]}
TEXTOS = {G + "versao.json": json.dumps({"revisao": 2026111501, "versao": "5.3"}),
          G + "SHA256SUMS": f"{SHA}  opentars-setup.exe\n{'c' * 64}  openTARS-macos-arm64.dmg\n"}
obter_json = lambda url: RELEASE  # noqa: E731
obter_texto = TEXTOS.get

r = a.procurar_pacote(2026111301, obter_json, obter_texto, arquivo="opentars-setup.exe")
assert r["arquivos"]["pacote"] == {"nome": "opentars-setup.exe", "url": G + "opentars-setup.exe", "sha256": SHA, "id": SHA}, r
assert a.procurar_pacote(2026111301, obter_json, obter_texto, arquivo="openTARS-macos-arm64.dmg")["arquivos"]["pacote"]["sha256"] == "c" * 64
assert a.procurar_pacote(2026111501, obter_json, obter_texto, arquivo="opentars-setup.exe") is None, "mesma revisão: nada"
assert a.procurar_pacote(2026111301, obter_json, obter_texto, arquivo="openTARS-macos-x86_64.dmg") is None, "sem o arquivo do sistema: nada"
sem_versao = dict(RELEASE, assets=[x for x in RELEASE["assets"] if x["name"] != "versao.json"])
assert a.procurar_pacote(1, lambda u: sem_versao, obter_texto, arquivo="opentars-setup.exe") is None, "versao.json ainda não subiu: nada"
fora = dict(RELEASE, assets=[dict(x, browser_download_url="https://exemplo.com/" + x["name"]) for x in RELEASE["assets"]])
assert a.procurar_pacote(1, lambda u: fora, lambda u: TEXTOS.get(u.replace("https://exemplo.com/", G)), arquivo="opentars-setup.exe") is None
assert a.procurar_pacote(1, lambda u: (_ for _ in ()).throw(OSError("rede")), obter_texto) is None
assert a.arquivo_do_pacote("windows") == "opentars-setup.exe" and a.arquivo_do_pacote("macos", "arm64") == "openTARS-macos-arm64.dmg"
print("OK: versão nova pela versao.json da Release, com o instalador do sistema e o SHA-256")

# o setup.exe roda solto, em silêncio, e pede para reabrir; o app sai
rodados = []
assert a.instalar_setup_windows("C:/x/opentars-setup.exe", popen=lambda argv, **k: rodados.append((argv, k))) == (True, "sair")
assert rodados[0][0][1:] == ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/REABRIR=1"] and rodados[0][1]["creationflags"] & 0x8
print("OK: no Windows o setup.exe novo roda solto e reabre o app")

# macOS: o .app novo entra no lugar do velho só depois de copiado inteiro
casa = Path(tempfile.mkdtemp())
atual = casa / "openTARS.app"
(atual / "Contents").mkdir(parents=True)
(atual / "Contents" / "velho").write_text("1")


def rodar(cmd):
    if cmd[0] == "ditto":
        Path(cmd[2], "Contents").mkdir(parents=True)
        Path(cmd[2], "Contents", "novo").write_text("2")
    return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()


assert a.instalar_dmg(casa / "x.dmg", destino=atual, rodar=rodar) == (True, "reabrir")
assert (atual / "Contents" / "novo").exists() and not (atual / "Contents" / "velho").exists()
assert not atual.with_name("openTARS.app.velho").exists() and not atual.with_name("openTARS.app.novo").exists()
falha = lambda cmd: type("R", (), {"returncode": 1, "stdout": "", "stderr": "não montou"})()  # noqa: E731
assert a.instalar_dmg(casa / "x.dmg", destino=atual, rodar=falha) == (False, "não montou") and (atual / "Contents" / "novo").exists()
print("OK: no macOS o .app novo troca o velho só depois de copiado; se o .dmg não monta, nada muda")
# quem vem da instalação por script faz o primeiro uso de novo no app empacotado; depois de feito, não pede mais
os.environ["TARS_ARQUIVO_PRIMEIRO_USO"] = str(casa / "pu.json")
import tars_primeiro_uso as pu  # noqa: E402
pu._empacotado = lambda: False
pu.marcar_concluido()
assert pu.primeiro_uso_concluido(), "fora do pacote (Linux), concluído continua concluído"
pu._empacotado = lambda: True
assert not pu.primeiro_uso_concluido(), "o primeiro uso feito antes do app empacotado não vale: faz de novo"
pu.marcar_concluido()
assert pu.primeiro_uso_concluido(), "feito no app empacotado, vale daí em diante"
print("OK: no Windows e no macOS, a atualização para o app empacotado passa pelo primeiro uso de novo, uma vez")
print("TUDO OK.")
