"""5.1: os modos Lite, Base e Pro (tars_modos.py) e os ajustes avançados do Pro no núcleo: temperatura, contexto,
instruções extras e ferramenta desligada (bloqueada na execução, a lista do Gargantua não muda). Sem Ollama."""
import json
import os
import tempfile

pasta = tempfile.mkdtemp(prefix="opentars-modos-")
os.environ["TARS_ARQUIVO_CONFIG"] = os.path.join(pasta, "config.json")
os.environ["TARS_ARQUIVO_PRIMEIRO_USO"] = os.path.join(pasta, "primeiro_uso.json")

from _util import carregar_tars  # noqa: E402

tars = carregar_tars()
modos = tars.modos

# 1) padrão: instalação nova = Base; quem já tinha feito o primeiro uso (veio da 5.0) = Pro
assert modos.modo_atual() == "base"
tars.primeiro_uso.marcar_concluido()
assert modos.modo_atual() == "pro"
modos.definir_modo("lite")
assert modos.modo_atual() == "lite" and json.load(open(os.environ["TARS_ARQUIVO_CONFIG"]))["modo"] == "lite"
try:
    modos.definir_modo("turbo")
    raise AssertionError("modo inválido devia ser recusado")
except ValueError:
    pass
print("OK: padrão Base na instalação nova, Pro ao vir da 5.0, e a escolha fica gravada")

# 2) o que cada modo mostra: Lite ⊂ Base ⊂ Pro; o Lite nunca mostra nada avançado; o Pro nunca perde nada
lite, base, pro = (modos.RECURSOS[m] for m in modos.MODOS)
assert lite < base < pro
for r in ("historico", "seletor_modelo", "cfg.memoria", "cfg.rotinas", "cfg.probes", "cfg.nuvem", "cfg.avancado",
          "cfg.diagnostico"):
    assert not modos.mostra(r, "lite"), r
for r in ("cfg.avancado", "cfg.diagnostico"):
    assert not modos.mostra(r, "base") and modos.mostra(r, "pro"), r
print("OK: Lite ⊂ Base ⊂ Pro, e só o Pro tem ajustes avançados e diagnóstico")

# 3) ajustes avançados: limpos ao gravar e só valem no Pro
modos.salvar_avancado(temperatura=3, contexto=5000, instrucoes="  responda em tópicos  ",
                      ferramentas_desligadas=["execute_terminal", 7, ""])
gravado = modos.avancado_gravado()
assert gravado == {"temperatura": 1.5, "contexto": None, "instrucoes": "responda em tópicos",
                   "ferramentas_desligadas": ["execute_terminal"]}, gravado
assert modos.avancado()["temperatura"] is None, "no Lite nada avançado vale"
assert tars.temperatura_conversa() == tars.TEMPERATURA_CONVERSA
modos.definir_modo("pro")
modos.salvar_avancado(temperatura=0.7, contexto=32768)
assert tars.temperatura_conversa() == 0.7 and tars.contexto_ia() == 32768
assert "responda em tópicos" in tars._memoria_para_prompt()
assert "responda em tópicos" in tars.sistema_gargantua() and "responda em tópicos" in tars.montar_system_prompt()
print("OK: temperatura, contexto e instruções extras valem no Pro (e só nele)")

# 4) ferramenta desligada: a lista do Gargantua continua a do treino, e a execução recusa
nomes = [f["function"]["name"] for f in tars.ferramentas_gargantua()]
assert "execute_terminal" in nomes and len(nomes) == 19, nomes
rodou = []
tars._DISPATCH_FERRAMENTAS["execute_terminal"] = lambda a: rodou.append(a) or {"sucesso": True, "mensagem": "ok"}
r = tars.executar_ferramenta("execute_terminal", {"command": "ls"})
assert not r["sucesso"] and "turned the tool" in r["mensagem"] and not rodou, r
modos.definir_modo("base")                  # fora do Pro, nada fica desligado
r = tars.executar_ferramenta("execute_terminal", {"command": "ls"})
assert r["sucesso"] and rodou, r
print("OK: ferramenta desligada é recusada na execução só no Pro; a lista do Gargantua não muda")
print("\nTUDO OK.")
