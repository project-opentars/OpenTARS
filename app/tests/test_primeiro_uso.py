"""5.0 Tesseract: a lógica do primeiro uso (tars_primeiro_uso.py), sem janela,
contra um Ollama de mentira."""

import os
import stat
import sys
import tempfile

from _util import RAIZ  # coloca a raiz no sys.path e fixa o idioma de teste

import fake_ollama
import tars_i18n
import tars_primeiro_uso as pu

pasta = tempfile.mkdtemp(prefix="opentars-pu-")
os.environ["TARS_ARQUIVO_PRIMEIRO_USO"] = os.path.join(pasta, "primeiro_uso.json")
os.environ["TARS_ARQUIVO_NUVEM"] = os.path.join(pasta, "nuvem.json")

# --- host -------------------------------------------------------------
assert pu.normalizar_host("") == "http://127.0.0.1:11434"
assert pu.normalizar_host("0.0.0.0") == "http://127.0.0.1:11434"
assert pu.normalizar_host("meupc:5000") == "http://meupc:5000"
assert pu.normalizar_host("https://x.org/") == "https://x.org:11434"

# --- achar o Ollama ---------------------------------------------------
servidor, url = fake_ollama.subir(modelos=["qwen3:4b", "ProjectOpenTARS/Gargantua:latest"])
r = pu.achar_ollama(candidatos=[url], tem_comando=False)
assert r == {"instalado": True, "responde": True, "host": url, "versao": "0.99.1"}, r
fora = pu.achar_ollama(candidatos=["http://127.0.0.1:9"], tem_comando=False)   # porta fechada
assert fora["instalado"] is False and fora["responde"] is False and fora["versao"] is None, fora
parado = pu.achar_ollama(candidatos=["http://127.0.0.1:9"], tem_comando=True)  # comando existe, servidor parado
assert parado["instalado"] is True and parado["responde"] is False, parado

# --- modelos ----------------------------------------------------------
modelos = pu.modelos_instalados(url)
assert modelos == ["qwen3:4b", "ProjectOpenTARS/Gargantua:latest"], modelos
assert pu.tem_gargantua(modelos) and not pu.tem_gargantua(["qwen3:4b"])
assert pu.tem_gargantua(["projectopentars/gargantua:1.2"]), "maiúsculas e tag não contam"
assert pu.nome_do_gargantua(modelos) == "ProjectOpenTARS/Gargantua:latest"
assert pu.nome_do_gargantua(["qwen3:4b"]) == pu.MODELO_GARGANTUA
assert pu.modelos_instalados("http://127.0.0.1:9") == []

# --- instalar / iniciar (sem rodar nada de verdade) --------------------
cmd = pu.comando_instalar_ollama()
assert cmd[-1].endswith("| sh") and "ollama.com/install.sh" in cmd[-1]


class _R:
    def __init__(self, codigo, saida="", erro=""):
        self.returncode, self.stdout, self.stderr = codigo, saida, erro


assert pu.instalar_ollama(rodar=lambda c: _R(0)) == (True, "")
ok, msg = pu.instalar_ollama(rodar=lambda c: _R(1, erro="sem rede"))
assert not ok and "sem rede" in msg
ok, msg = pu.instalar_ollama(rodar=lambda c: (_ for _ in ()).throw(OSError("boom")))
assert not ok and "boom" in msg
assert pu.iniciar_ollama(procurar=lambda: True) == (True, "")

# --- baixar o Gargantua -----------------------------------------------
vistos = []
ok, erro = pu.baixar_modelo("ProjectOpenTARS/Gargantua", url, ao_progredir=lambda p: vistos.append((p.feito, p.total)))
assert ok and erro == "", (ok, erro)
assert vistos[-1] == (1500, 1500), vistos[-1]
assert [f for f, _ in vistos] == sorted(f for f, _ in vistos), "o progresso só avança"
corpo = [c for m, p, c in servidor.pedidos if p == "/api/pull"][-1]
assert corpo["model"] == "ProjectOpenTARS/Gargantua" and corpo["stream"] is True

p = pu.Progresso()
assert p.fracao == 0 and p.segundos_restantes() is None
p.atualizar({"digest": "a", "total": 100, "completed": 25})
p.atualizar({"digest": "b", "total": 100, "completed": 75})
assert (p.feito, p.total, p.fracao) == (100, 200, 0.5)

s2, u2 = fake_ollama.subir(erro_no_download="pull model manifest: file does not exist")
ok, erro = pu.baixar_modelo("x", u2)
assert not ok and "does not exist" in erro, erro
ok, erro = pu.baixar_modelo("x", "http://127.0.0.1:9")
assert not ok and erro, "Ollama fora do ar vira erro, não exceção"

s3, u3 = fake_ollama.subir(atraso=0.05)
contador = {"n": 0}


def _cancelar():
    contador["n"] += 1
    return contador["n"] > 2


ok, erro = pu.baixar_modelo("x", u3, cancelado=_cancelar)
assert not ok and erro == "cancelado", (ok, erro)

# --- teste rápido -----------------------------------------------------
ok, texto, seg = pu.testar_gargantua(url, "ProjectOpenTARS/Gargantua")
assert ok and texto == "4" and seg >= 0, (ok, texto)
corpo = [c for m, p_, c in servidor.pedidos if p_ == "/api/chat"][-1]
assert corpo["model"] == "ProjectOpenTARS/Gargantua" and corpo["stream"] is False and corpo["think"] is False
s4, u4 = fake_ollama.subir(erro_no_chat="model not found")
ok, texto, _ = pu.testar_gargantua(u4, "x")
assert not ok and texto, (ok, texto)
s5, u5 = fake_ollama.subir(resposta="")
ok, texto, _ = pu.testar_gargantua(u5, "x")
assert not ok and texto == "resposta vazia"

# --- nuvem ------------------------------------------------------------
assert pu.carregar_nuvem() == {"ativa": False, "provedor": "", "endereco": "", "chave": ""}
pu.salvar_nuvem(True, "groq", "https://api.groq.com/openai/v1/", " segredo ")
n = pu.carregar_nuvem()
assert n == {"ativa": True, "provedor": "groq", "endereco": "https://api.groq.com/openai/v1", "chave": "segredo"}, n
modo = stat.S_IMODE(os.stat(pu.arquivo_nuvem()).st_mode)
assert modo == 0o600, oct(modo)
pu.salvar_nuvem(False)
n = pu.carregar_nuvem()
assert n["ativa"] is False and n["chave"] == "segredo", "desligar não apaga a chave"
assert not any(f.endswith(".tmp") for f in os.listdir(pasta))

servidor_n, url_n = fake_ollama.subir(chave="boa")
assert pu.testar_nuvem(url_n, "boa") == (True, "ok")
assert pu.testar_nuvem(url_n, "ruim") == (False, "chave")
assert pu.testar_nuvem(url_n + "/nada", "boa")[0] is False
assert pu.testar_nuvem("sem-esquema", "x") == (False, "endereço")
assert pu.testar_nuvem("http://127.0.0.1:9", "x") == (False, "rede")
for _, texto in (pu.testar_nuvem(url_n, "SEGREDO-DA-CHAVE"),):
    assert "SEGREDO-DA-CHAVE" not in texto

assert pu.provedor("ollama")["nome"] == "Ollama Cloud" and pu.provedor("ollama")["a_confirmar"]
assert pu.provedor("inexistente")["id"] == "outro"
assert [p["id"] for p in pu.PROVEDORES][:1] == ["ollama"], "o Ollama Cloud vem primeiro"

# --- estado do assistente --------------------------------------------
assert pu.primeiro_uso_concluido() is False
pu.marcar_concluido()
assert pu.primeiro_uso_concluido() is True
pu.marcar_concluido(False)
assert pu.primeiro_uso_concluido() is False

# --- textos ------------------------------------------------------------
t = tars_i18n.t
assert pu.formatar_tempo(None, t) == "calculando…"
assert pu.formatar_tempo(20, t) == "menos de 1 minuto"
assert pu.formatar_tempo(75, t) == "cerca de 1 minuto"
assert pu.formatar_tempo(185, t) == "uns 3 minutos"
for chave in tars_i18n.chaves("pu."):
    assert tars_i18n.t(chave) != chave, chave

pt = tars_i18n.ler_config  # só pra garantir que o módulo carregou
import json
for idioma in ("pt_BR", "en"):
    d = json.load(open(os.path.join(RAIZ, "idiomas", f"{idioma}.json"), encoding="utf-8"))
    chaves_pu = {k for k in d if k.startswith("pu.")}
    assert chaves_pu, idioma
    d_pt = json.load(open(os.path.join(RAIZ, "idiomas", "pt_BR.json"), encoding="utf-8"))
    assert chaves_pu == {k for k in d_pt if k.startswith("pu.")}, f"{idioma}: chaves 'pu.' diferentes do português"

print("test_primeiro_uso: OK")
