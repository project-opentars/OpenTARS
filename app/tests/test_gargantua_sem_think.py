"""O Gargantua vai ao Ollama SEM o campo 'think' (com think=false o molde do .gguf força "<think></think>" e ele responde
sem ferramenta); os outros modelos continuam com think=false. Ollama de mentira: nada é executado."""
import copy
import json
from _util import carregar_tars

tars = carregar_tars()
capturados = []


class Parar(Exception):
    pass


def falso(payload, *a, **k):
    capturados.append(copy.deepcopy(payload))
    raise Parar()


tars.ollama_request = falso
tars.carregar_modelo = lambda *a, **k: True        # nunca toca o Ollama de verdade (nem descarrega nada dele)
for modelo, tem_think in (("ProjectOpenTARS/Gargantua:lite", False), ("ProjectOpenTARS/Gargantua:latest", False),
                          ("qwen3:4b", True)):
    capturados.clear()
    tars.conversa.clear()
    tars.modo_modelo, tars.modelo_manual = "MANUAL", modelo
    try:
        tars.processar_mensagem("crie a pasta Fotos em Documentos")
    except Exception:
        pass
    assert capturados, f"nada foi mandado ao Ollama para {modelo}"
    p = capturados[0]
    assert ("think" in p) == tem_think, (modelo, p.get("think", "sem o campo"))
    assert not tem_think or p["think"] is False, (modelo, p["think"])
    assert p.get("tools"), f"{modelo} foi sem ferramentas"
print("OK: o Gargantua vai sem 'think' e os outros modelos continuam com think=false")

# 17/10: o Gargantua em Qwen3.5 (família qwen35) vai com think=false: o renderer do Ollama pensa quando o campo falta
import time  # noqa: E402
tars._cache_catalogo["dados"] = {"gargantua-q35-teste": {"familia": "qwen35", "capacidades": ["tools", "vision", "thinking"]}}
tars._cache_catalogo["ts"] = time.time()
capturados.clear()
tars.conversa.clear()
tars.modo_modelo, tars.modelo_manual = "MANUAL", "gargantua-q35-teste"
try:
    tars.processar_mensagem("crie a pasta Fotos em Documentos")
except Exception:
    pass
assert capturados and capturados[0].get("think", "sem o campo") is False, capturados[:1]
print("OK: o Gargantua em Qwen3.5 vai com think=false")

# e nunca com o "/no_think" do Qwen3 colado no pedido, mesmo se o app achar que ele pensa sem pedir
tars._PENSA_MESMO_SEM_PEDIR.add("gargantua-q35-teste")
capturados.clear()
tars.conversa.clear()
try:
    tars.processar_mensagem("abre o site do Reddit")
except Exception:
    pass
assert capturados and "/no_think" not in json.dumps(capturados[0]["messages"]), capturados[0]["messages"][-1]
tars._PENSA_MESMO_SEM_PEDIR.discard("gargantua-q35-teste")
print("OK: o Qwen3.5 nunca recebe o '/no_think' do Qwen3 no pedido")
print("\nTUDO OK.")
