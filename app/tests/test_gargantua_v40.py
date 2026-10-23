"""4.0 Endurance: o Gargantua, a IA oficial (ProjectOpenTARS/Gargantua).

- o formato que o openTARS manda pro Gargantua é IDÊNTICO ao do treino
  (gargantua/gargantua.py): prompt curto, todas as ferramentas (28) curtas, sem raciocínio;
- no AUTO ele vai pra frente da fila nas ações e buscas (e só nelas);
- se o AUTO trocar de modelo no meio do pedido, o formato troca junto;
- as pastas do usuário entram no contexto do sistema."""

import os
import sys
import tempfile
from pathlib import Path

from _util import carregar_tars

tars = carregar_tars()
RAIZ = Path(__file__).resolve().parent.parent

# 1. Nomes
for nome in ("gargantua", "gargantua:1.0", "ProjectOpenTARS/Gargantua", "ProjectOpenTARS/Gargantua:latest",
             "registry.ollama.ai/projectopentars/gargantua:1.0", "enzo/gargantua"):
    assert tars.eh_gargantua(nome), nome
for nome in ("qwen3:4b", "api:gargantua-fake/qwen", "", None, "llama3-gargantuan-helper:1b/x"):
    assert not tars.eh_gargantua(nome), nome
assert tars.MODELO_GARGANTUA == "ProjectOpenTARS/Gargantua-2"
print("OK: 'gargantua', 'ProjectOpenTARS/Gargantua:latest'... são o Gargantua; qwen3 não")

# 2. Pastas do usuário no contexto
casa = Path(tempfile.mkdtemp())
(casa / ".config").mkdir()
(casa / ".config" / "user-dirs.dirs").write_text(
    'XDG_DESKTOP_DIR="$HOME/Área de Trabalho"\nXDG_DOWNLOAD_DIR="$HOME/Downloads"\nXDG_DOCUMENTS_DIR="$HOME/Documentos"\n',
    encoding="utf-8")
pastas = tars.pastas_do_usuario(casa)
assert pastas == {"Desktop": f"{casa}/Área de Trabalho", "Documents": f"{casa}/Documentos",
                  "Downloads": f"{casa}/Downloads"}, pastas
assert tars.pastas_do_usuario(Path(tempfile.mkdtemp())) == {}
tars._contexto_sistema_cache.clear()
original = tars.pastas_do_usuario
tars.pastas_do_usuario = lambda casa=None: pastas
ctx = tars.contexto_sistema()
assert ctx.rstrip().endswith(f"- User folders: Desktop = {casa}/Área de Trabalho; Documents = {casa}/Documentos; "
                             f"Downloads = {casa}/Downloads"), ctx
print("OK: o contexto diz as pastas do usuário (Desktop = .../Área de Trabalho)")

# 3. Formato idêntico ao do treino: sempre contra o retrato do contrato (tests/contrato_gargantua.json, que vai junto no
# repositório público) e, onde o kit existe (o PC do Enzo), contra o próprio kit
import json  # noqa: E402

contrato = json.loads((Path(__file__).with_name("contrato_gargantua.json")).read_text(encoding="utf-8"))
assert contrato["sistema"] == tars.SISTEMA_GARGANTUA and contrato["descricoes_curtas"] == tars.DESCRICOES_CURTAS
assert contrato["ferramentas"] == tars.ferramentas_gargantua()
assert len(tars.ferramentas_gargantua()) == 19
if (RAIZ / "gargantua" / "gargantua.py").exists():
    sys.path.insert(0, str(RAIZ / "gargantua"))
    import gargantua as kit  # noqa: E402

    kit._contar_pastas_no_contexto(tars)  # o kit não pode duplicar a linha na 4.0
    assert tars.contexto_sistema().count("User folders") == 1
    assert kit.SISTEMA_GARGANTUA == tars.SISTEMA_GARGANTUA and kit.DESCRICOES_CURTAS == tars.DESCRICOES_CURTAS
    assert kit.sistema_gargantua(tars) == tars.sistema_gargantua()
    assert kit.ferramentas_compactas(kit.todas_as_ferramentas(tars)) == tars.ferramentas_gargantua()
else:
    print("(kit não está ao lado: comparei só com o retrato do contrato)")
assert not tars.pensar_do_modelo("ProjectOpenTARS/Gargantua:latest", "codigo", "x")
os.environ["TARS_PENSAR"] = "sempre"
assert not tars.pensar_do_modelo("gargantua", "geral", "x") and tars.pensar_do_modelo("qwen3:8b", "acao", "x")
del os.environ["TARS_PENSAR"]
assert tars.prompt_do_modelo("gargantua").startswith("You are Gargantua,")
assert not tars.prompt_do_modelo("qwen3:8b").startswith("You are Gargantua,")
print("OK: prompt e as 19 ferramentas iguaizinhos aos do treino; sem raciocínio nem com TARS_PENSAR=sempre")

# 4. Fila do AUTO


def m(tag, p, caps, v, fam="qwen3"):
    return {"tag": tag, "familia": fam, "parametros_b": p, "vram_estimado_gb": v, "capacidades": set(caps),
            "capacidades_conhecidas": True, "categoria": tars._categorizar_modelo(tag, set(caps), p, fam)}


catalogo = {x["tag"]: x for x in [
    m("qwen3:1.7b", 1.7, {"tools", "thinking"}, 1.6),
    m("qwen3:8b", 8.2, {"tools", "thinking"}, 5.5),
    m("ProjectOpenTARS/Gargantua:latest", 4.0, {"tools", "completion"}, 3.0),
    m("qwen2.5-coder:7b", 7.6, {"tools"}, 5.2, "qwen2"),
]}
tars.detectar_gpu = lambda forcar=False: {"vram_total_gb": 6.0, "vram_livre_gb": 5.0}
for tarefa in ("acao", "busca", "acao_complexa"):
    assert tars.construir_cadeia_fallback(tarefa, catalogo)[0] == "ProjectOpenTARS/Gargantua:latest", tarefa
assert tars.construir_cadeia_fallback("codigo", catalogo)[0] == "qwen2.5-coder:7b"
assert tars.construir_cadeia_fallback("geral", catalogo)[0] == "qwen3:8b"
assert tars.construir_cadeia_fallback("tecnico", catalogo)[0] == "qwen3:8b"
os.environ["TARS_SEM_GARGANTUA"] = "1"
assert tars.construir_cadeia_fallback("acao", catalogo)[0] != "ProjectOpenTARS/Gargantua:latest"
del os.environ["TARS_SEM_GARGANTUA"]
# se não roda bem nesta máquina, ele não passa na frente de quem roda
pesado = dict(catalogo, **{"ProjectOpenTARS/Gargantua:latest": m("ProjectOpenTARS/Gargantua:latest", 4.0,
                                                                   {"tools"}, 40.0)})
assert tars.construir_cadeia_fallback("acao", pesado)[0] != "ProjectOpenTARS/Gargantua:latest"
# o oficial ganha de um treinado em casa
catalogo["gargantua:latest"] = m("gargantua:latest", 4.0, {"tools"}, 3.0)
assert tars.construir_cadeia_fallback("acao", catalogo)[:2] == ["ProjectOpenTARS/Gargantua:latest", "gargantua:latest"]
assert tars.gargantua_instalado(catalogo) == "ProjectOpenTARS/Gargantua:latest"
assert tars.gargantua_instalado({"qwen3:8b": {}}) is None
print("OK: AUTO usa o Gargantua primeiro em ação/busca; código, técnico e conversa seguem a fila; "
      "TARS_SEM_GARGANTUA=1 desliga")

# 5. Pedido de verdade: formato certo, e troca no meio do caminho
tars.catalogar_modelos = lambda forcar=False: catalogo
tars.carregar_modelo = lambda mod, silencioso=False: True
tars.modo_modelo = "AUTO"
tars._DISPATCH_FERRAMENTAS["open_application"] = lambda a: {"sucesso": True, "mensagem": "SUCCESS: opened"}
vistos = []


def turno(modelo, msgs, tools, pensar=True, **kw):
    vistos.append((modelo, msgs[0]["content"][:40], len(tools), pensar,
                   next(t for t in tools if t["function"]["name"] == "open_application")["function"]["description"]))
    if tars.eh_gargantua(modelo):
        return {"content": "Desculpe, não consigo abrir aplicativos.", "tool_calls": []}, None
    if not any(x["role"] == "tool" for x in msgs[-3:]):
        return {"content": "", "tool_calls": [{"function": {"name": "open_application",
                                                            "arguments": {"app": "firefox"}}}]}, None
    return {"content": "Abri o Firefox.", "tool_calls": []}, None


tars._executar_turno_streaming = turno
resposta = tars.perguntar_modelo("ProjectOpenTARS/Gargantua:latest", "abra o firefox", tarefa="acao")
assert resposta == "Abri o Firefox.", resposta
garg = [v for v in vistos if tars.eh_gargantua(v[0])]
outros = [v for v in vistos if not tars.eh_gargantua(v[0])]
assert garg and all(v[1].startswith("You are Gargantua,") and v[2] == 19 and v[3] is False
                    and v[4] == tars.DESCRICOES_CURTAS["open_application"] for v in garg), garg
assert outros and all(not v[1].startswith("You are Gargantua,")
                      and v[4] != tars.DESCRICOES_CURTAS["open_application"] for v in outros), outros
print("OK: o Gargantua recebe o formato curto; o AUTO passa pra outro modelo e o formato normal volta")

# 6. /modelo gargantua e --version
import contextlib  # noqa: E402
import io  # noqa: E402

catalogo.pop("gargantua:latest")
tars.listar_modelos_instalados = lambda forcar=False: list(catalogo)
tars.ollama_online = lambda: True
tars.carregar_modelo_em_segundo_plano = lambda *a, **k: None
tars.interpretar_comando_modelo("/modelo gargantua")
assert tars.modo_modelo == "MANUAL" and tars.modelo_manual == "ProjectOpenTARS/Gargantua:latest", tars.modelo_manual
saida = io.StringIO()
sys.argv = ["opentars", "--version"]
with contextlib.redirect_stdout(saida):
    tars.main()
assert f"openTARS {tars.VERSAO} ({tars.VERSAO_EXIBIDA})" in saida.getvalue() and "Gargantua 1.2 (ProjectOpenTARS/Gargantua:latest)" \
    in saida.getvalue(), saida.getvalue()
tars.catalogar_modelos = lambda forcar=False: {}
saida = io.StringIO()
with contextlib.redirect_stdout(saida):
    tars.main()
assert "ollama pull ProjectOpenTARS/Gargantua" in saida.getvalue(), saida.getvalue()
print("OK: '/modelo gargantua' acha o oficial; --version mostra o Gargantua (ou como baixar)")

# 7. 5.2: fora do Linux vai o prompt neutro dos dados da 5.2 (só a palavra "Linux" sai); no Linux, byte a byte o do treino
neutro = tars.SISTEMA_GARGANTUA.replace("controls this Linux computer", "controls this computer")
assert neutro != tars.SISTEMA_GARGANTUA and tars.sistema_gargantua().startswith(tars.SISTEMA_GARGANTUA)
original = tars.plataforma.sistema
tars.plataforma.sistema = lambda: "windows"
try:
    assert tars.sistema_gargantua().startswith(neutro), tars.sistema_gargantua()[:120]
finally:
    tars.plataforma.sistema = original
print("OK: no Linux o prompt do treino; no Windows e no macOS o prompt neutro")

print("\nTUDO OK.")
