"""5.0 Tesseract: atualizar com um clique, só com SHA-256 conferido."""

import hashlib
import json
import os
import stat
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from _util import RAIZ  # noqa: F401

import tars_atualizacao as at

os.environ.pop("TARS_SEM_AVISO_VERSAO", None)   # o _util liga; aqui precisamos dele desligado

assert at.numeros_da_versao("v5.0.1") == (5, 0, 1) and at.numeros_da_versao("5.0") < at.numeros_da_versao("5.0.1")
assert at.numeros_da_versao("5.10") > at.numeros_da_versao("5.9") and at.numeros_da_versao("lixo") == ()
assert at.host_permitido("https://github.com/x/y") and at.host_permitido("https://objects.githubusercontent.com/a")
assert not at.host_permitido("http://github.com/x") and not at.host_permitido("https://evil.example.com/a")
assert not at.host_permitido("https://github.com.evil.example/a") and not at.host_permitido("file:///etc/passwd")
h = "a" * 64
assert at.ler_somas(f"{h}  opentars.AppImage\n{'b' * 64} *opentars.deb\nlixo\n") == {"opentars.AppImage": h, "opentars.deb": "b" * 64}

conteudo = os.urandom(200_000)
soma = hashlib.sha256(conteudo).hexdigest()


class Servidor(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        corpo = {"/arq.AppImage": conteudo, "/ruim.AppImage": conteudo + b"x",
                 "/SHA256SUMS": f"{soma}  arq.AppImage\n{soma}  ruim.AppImage\n".encode()}.get(self.path)
        if corpo is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        for i in range(0, len(corpo), 20000):
            self.wfile.write(corpo[i:i + 20000])


http = HTTPServer(("127.0.0.1", 0), Servidor)
threading.Thread(target=http.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{http.server_port}"
livre = ("127.0.0.1",)
pasta = Path(tempfile.mkdtemp(prefix="opentars-at-"))

release = {"tag_name": "v5.0.1", "body": "notas", "assets": [
    {"name": "SHA256SUMS", "browser_download_url": base + "/SHA256SUMS"},
    {"name": "arq.AppImage", "browser_download_url": base + "/arq.AppImage"},
    {"name": "sem-soma.deb", "browser_download_url": base + "/x.deb"}]}
obter_texto = lambda url: __import__("requests").get(url).text  # noqa: E731

os.environ["TARS_SEM_AVISO_VERSAO"] = "1"      # desliga a busca inteira (repositório E Release), como o README promete
assert at.procurar_atualizacao("5.0", obter_json=lambda u: release, obter_texto=obter_texto, extras=livre) is None
chamadas = []
assert at.procurar_atualizacao("5.0", obter_json=lambda u: chamadas.append(u) or None) is None and not chamadas, "nenhuma consulta com a variável ligada"
del os.environ["TARS_SEM_AVISO_VERSAO"]
nova = at.procurar_atualizacao("5.0", obter_json=lambda u: release, obter_texto=obter_texto, extras=livre)
assert nova["versao"] == "5.0.1" and list(nova["arquivos"]) == ["appimage"], nova   # o .deb sem soma é ignorado
assert nova["arquivos"]["appimage"]["sha256"] == soma
assert at.procurar_atualizacao("5.0.1", obter_json=lambda u: release, obter_texto=obter_texto, extras=livre) is None, "mesma versão"
assert at.procurar_atualizacao("5.1", obter_json=lambda u: release, obter_texto=obter_texto, extras=livre) is None, "versão local maior"
sem_somas = dict(release, assets=release["assets"][1:])
assert at.procurar_atualizacao("5.0", obter_json=lambda u: sem_somas, obter_texto=obter_texto, extras=livre) is None, "sem SHA256SUMS não instala"
assert at.procurar_atualizacao("5.0", obter_json=lambda u: None) is None
assert at.procurar_atualizacao("5.0", obter_json=lambda u: release, obter_texto=obter_texto) is None, "fora do GitHub: recusa"

# baixar com hash certo
vistos = []
ok, motivo = at.baixar_verificado(base + "/arq.AppImage", pasta / "arq.AppImage", soma, ao_progredir=lambda f, t: vistos.append((f, t)), extras=livre)
assert ok and (pasta / "arq.AppImage").read_bytes() == conteudo and vistos[-1][0] == len(conteudo)
assert [f for f, _ in vistos] == sorted(f for f, _ in vistos)
# hash errado: nada fica
ok, motivo = at.baixar_verificado(base + "/ruim.AppImage", pasta / "ruim.AppImage", soma, extras=livre)
assert not ok and motivo == "hash" and not (pasta / "ruim.AppImage").exists() and not list(pasta.glob("*.parte"))
# cancelar
n = {"i": 0}
ok, motivo = at.baixar_verificado(base + "/arq.AppImage", pasta / "c.AppImage", soma, cancelado=lambda: n.__setitem__("i", n["i"] + 1) or n["i"] > 2, extras=livre)
assert not ok and motivo == "cancelado" and not list(pasta.glob("c.*"))
# host fora da lista, rede fora do ar
assert at.baixar_verificado("https://evil.example.com/a", pasta / "e", soma)[1] == "endereço"
assert at.baixar_verificado("http://127.0.0.1:9/x", pasta / "e", soma, extras=livre)[1] == "rede"
assert at.baixar_verificado(base + "/nao-existe", pasta / "e", soma, extras=livre)[1] == "rede"

# instalar: AppImage troca o arquivo que está rodando
atual = pasta / "openTARS.AppImage"
atual.write_bytes(b"velho")
assert at.instalar_arquivo(pasta / "arq.AppImage", appimage_atual=str(atual)) == (True, "reabrir")
assert atual.read_bytes() == conteudo and stat.S_IMODE(atual.stat().st_mode) == 0o755
assert at.instalar_arquivo(pasta / "arq.AppImage", appimage_atual=None)[0] is False or os.environ.get("APPIMAGE")


class R:
    def __init__(self, c, e=""):
        self.returncode, self.stdout, self.stderr = c, "", e


(pasta / "x.deb").write_bytes(b"deb")
comandos = []
assert at.instalar_arquivo(pasta / "x.deb", rodar=lambda c: comandos.append(c) or R(0)) == (True, "reabrir")
assert comandos[0][:2] == ["pkexec", "apt-get"] and comandos[0][-1].endswith("x.deb")
assert "--reinstall" in comandos[0]   # mesma versão "5.0": sem ele o apt não instala nada e diz que deu certo
# com hash: o hash é conferido DENTRO do passo de root (cópia só do root), não no arquivo da pasta da pessoa
comandos.clear()
at.instalar_arquivo(pasta / "x.deb", rodar=lambda c: comandos.append(c) or R(0), sha256="a" * 64)
assert comandos[0][:3] == ["pkexec", "sh", "-c"] and "sha256sum -c" in comandos[0][3] and comandos[0][-3:] == [str(pasta / "x.deb"), "sha256", "a" * 64]
assert "--reinstall" in comandos[0][3] and "cmp -s" in comandos[0][3]   # instala de novo e confere que o arquivo mudou
comandos.clear()
at.instalar_arquivo(pasta / "x.deb", rodar=lambda c: comandos.append(c) or R(0), git_sha="b" * 40)
assert comandos[0][-2:] == ["git", "b" * 40]
ok, msg = at.instalar_arquivo(pasta / "x.deb", rodar=lambda c: R(100, "dpkg: erro"))
assert not ok and "erro" in msg
assert at.instalar_arquivo(pasta / "arq.txt")[0] is False
http.shutdown()
print("test_atualizacao_clique: OK")

# --- detecção automática pelo último arquivo enviado (tag 'update', sem SHA256SUMS, mesma versão) ---
H1, H2 = "a" * 64, "b" * 64
def _rel(tag="update", nome="v5.0", enviado="2026-10-06T22:10:00Z", digest="sha256:" + H1, com_somas=False):
    ativos = [{"name": "opentars_all.deb", "created_at": enviado, "digest": digest,
               "browser_download_url": "https://github.com/x/y/releases/download/t/opentars_all.deb"}]
    if com_somas:
        ativos.append({"name": "SHA256SUMS", "browser_download_url": "https://github.com/x/y/releases/download/t/SHA256SUMS"})
    return {"tag_name": tag, "name": nome, "body": "update", "assets": ativos}
_epoch = at._epoch("2026-10-06T22:10:00Z")
antes, depois = _epoch - 3600, _epoch + 3600
# pacote montado ANTES do upload e hash diferente do instalado: oferece, só com o .deb enviado
r = at.procurar_atualizacao("5.0", obter_json=lambda u: _rel(), compilado=antes, ultima="")
assert r and r["versao"] == "5.0" and r["arquivos"]["deb"]["sha256"] == H1, r
# pacote montado DEPOIS do upload: em dia
assert at.procurar_atualizacao("5.0", obter_json=lambda u: _rel(), compilado=depois, ultima="") is None
# já instalado por aqui (mesmo hash): em dia
assert at.procurar_atualizacao("5.0", obter_json=lambda u: _rel(), compilado=antes, ultima=H1) is None
# o dono envia outro arquivo (hash novo, mais recente): oferece de novo
assert at.procurar_atualizacao("5.0", obter_json=lambda u: _rel(enviado="2026-10-07T10:00:00Z", digest="sha256:" + H2),
                               compilado=depois, ultima=H1)["arquivos"]["deb"]["sha256"] == H2
# SHA256SUMS, se existir, tem prioridade sobre o digest
assert at.procurar_atualizacao("5.0", obter_json=lambda u: _rel(com_somas=True), obter_texto=lambda u: f"{H2}  opentars_all.deb\n",
                               compilado=antes, ultima="")["arquivos"]["deb"]["sha256"] == H2
# sem hash nenhum (nem digest nem SHA256SUMS): não instala
assert at.procurar_atualizacao("5.0", obter_json=lambda u: _rel(digest=""), compilado=antes, ultima="") is None
# número de versão maior vale mesmo sem data; menor que o local: nada; rascunho: nada
assert at.procurar_atualizacao("5.0", obter_json=lambda u: _rel(tag="v5.1", enviado="2020-01-01T00:00:00Z"), compilado=depois, ultima="")["versao"] == "5.1"
assert at.procurar_atualizacao("5.2", obter_json=lambda u: _rel(), compilado=antes, ultima="") is None
d = _rel(); d["draft"] = True
assert at.procurar_atualizacao("5.0", obter_json=lambda u: d, compilado=antes, ultima="") is None
# marcar_instalada guarda o hash
os.environ["TARS_ARQUIVO_ATUALIZACAO"] = str(pasta / "atu.json")
at.marcar_instalada(H1)
assert at.procurar_atualizacao("5.0", obter_json=lambda u: _rel(), compilado=antes) is None
print("detecção automática: OK")

# --- upload direto no repositório ('Add files via upload'): sem Release, sem tag, sem nada ---
dados = os.urandom(50_000)
blob = hashlib.sha1(b"blob %d\0" % len(dados) + dados).hexdigest()
def _repo(u):
    if "/commits" in u:
        return [{"commit": {"committer": {"date": "2026-10-06T22:10:00Z"}}}]
    return [{"type": "file", "name": "README.md", "sha": "1" * 40, "download_url": "https://raw.githubusercontent.com/x/y/main/README.md"},
            {"type": "file", "name": "opentars_all.deb", "sha": blob, "download_url": "https://raw.githubusercontent.com/x/y/main/opentars_all.deb"}]
r = at.procurar_atualizacao("5.0", obter_json=_repo, compilado=antes, ultima="")
assert r and r["arquivos"]["deb"]["nome"] == "opentars_all.deb" and r["arquivos"]["deb"]["id"] == blob, r
assert at.procurar_atualizacao("5.0", obter_json=_repo, compilado=depois, ultima="") is None, "pacote mais novo que o upload"
assert at.procurar_atualizacao("5.0", obter_json=_repo, compilado=antes, ultima=blob) is None, "já instalado"
# novo upload (outro conteúdo) depois de instalar: oferece de novo
def _repo2(u):
    if "/commits" in u:
        return [{"commit": {"committer": {"date": "2026-10-07T09:00:00Z"}}}]
    return [{"type": "file", "name": "opentars_all.deb", "sha": "c" * 40, "download_url": "https://raw.githubusercontent.com/x/y/main/opentars_all.deb"}]
assert at.procurar_atualizacao("5.0", obter_json=_repo2, compilado=depois, ultima=blob)["arquivos"]["deb"]["id"] == "c" * 40
# baixa sem SHA256SUMS conferindo o SHA-1 git; arquivo adulterado é recusado
_abrir = lambda cont: (lambda u: (iter([cont[i:i + 9000] for i in range(0, len(cont), 9000)]), len(cont), True))  # noqa: E731
ok, _m = at.baixar_verificado("https://raw.githubusercontent.com/x/y/main/a.deb", pasta / "a.deb", "", abrir=_abrir(dados), git_sha=blob)
assert ok and (pasta / "a.deb").read_bytes() == dados
ok, m = at.baixar_verificado("https://raw.githubusercontent.com/x/y/main/b.deb", pasta / "b.deb", "", abrir=_abrir(dados + b"x"), git_sha=blob)
assert not ok and m == "hash" and not (pasta / "b.deb").exists()
ok, m = at.baixar_verificado("https://raw.githubusercontent.com/x/y/main/c.deb", pasta / "c.deb", "", abrir=_abrir(dados))
assert not ok and m == "hash", "sem nenhuma conferência não instala"
print("upload no repositório: OK")
# .deb dentro de uma pasta do repositório (não na raiz)
def _repo3(u):
    if "/commits" in u:
        return [{"commit": {"committer": {"date": "2026-10-06T22:10:00Z"}}}]
    if "/git/trees" in u:
        return {"tree": [{"type": "blob", "path": "dist/opentars_all.deb", "sha": blob}]}
    return [{"type": "file", "name": "README.md", "sha": "1" * 40, "download_url": "https://raw.githubusercontent.com/x/y/main/README.md"}]
r = at.procurar_atualizacao("5.0", obter_json=_repo3, compilado=antes, ultima="")
assert r["arquivos"]["deb"]["nome"] == "opentars_all.deb" and r["arquivos"]["deb"]["url"].endswith("/HEAD/dist/opentars_all.deb"), r
print("deb em subpasta: OK")
