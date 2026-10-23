"""5.1: Probes (tars_probes.py) sem Ollama e sem tela. Contrato igual ao do kit; o código manda no plano (só leitura,
pastas sensíveis fora, tetos); rodar só pergunta ao modelo quando há o que ver e só aceita arquivos que leu; nasce
desligado; teto de avisos por dia; mover (nível 2) só se a pessoa ligou; lixeira (nível 3) só com aprovação, e sem
resposta em 30 minutos fica negado; o serviço é instância única."""
import datetime as dt
import importlib.util
import json
import os
import tempfile
import threading
import time
from pathlib import Path

CASA = Path(tempfile.mkdtemp(prefix="opentars-probes-"))
os.environ["HOME"] = str(CASA)
os.environ["XDG_CONFIG_HOME"] = str(CASA / ".config")
os.environ["TARS_ARQUIVO_PROBES"] = str(CASA / ".config" / "opentars" / "probes.json")

from _util import RAIZ  # noqa: E402

import tars_probes as tp  # noqa: E402

# 1) o contrato do Lite é o do kit, byte a byte
kit = Path(RAIZ).parent / "kit" / "gargantua.py"
if kit.is_file():
    spec = importlib.util.spec_from_file_location("kit_probes", kit)
    k = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(k)
    assert tp.SISTEMA_PROBE_PLANO == k.SISTEMA_PROBE_PLANO and tp.FERRAMENTAS_PROBE == k.FERRAMENTAS_PROBE
    print("OK: SISTEMA_PROBE_PLANO e as ferramentas são os do kit")
else:
    print("(kit fora da árvore: contrato não conferido aqui)")

# 2) ler o JSON com folga; validar sem folga
assert tp.ler_json('```json\n{"name": "x", "tools": ["list_folder"]}\n```') == {"name": "x", "tools": ["list_folder"]}
assert tp.ler_json("blá {quebrado {\"a\": 1} fim") == {"a": 1} and tp.ler_json("nada") is None
assert tp.validar_plano({"refuse": "não apago arquivos"}) == (None, "recusa:não apago arquivos")
assert tp.validar_plano({"watch": ["~/.ssh"], "tools": ["read_file"]})[1] == "proibido:~/.ssh"
assert tp.validar_plano({"watch": ["~/Documentos/github-recovery-codes.txt"], "tools": ["read_file"]})[1].startswith("proibido")
assert tp.validar_plano({"name": "x"})[1] == "ferramentas"
plano, erro = tp.validar_plano({"name": "Instaladores nos Downloads, um nome bem comprido demais", "watch": "~/Downloads",
                                "tools": ["list_folder", "delete_file", "list_folder"], "check": {"every_minutes": 1},
                                "alert": {"max_per_day": 99}, "look_for": "um .deb"})
assert erro is None and plano["tools"] == ["list_folder"] and plano["watch"] == ["~/Downloads"], plano
assert plano["check"] == {"every_minutes": 5} and plano["alert"]["max_per_day"] == 24 and len(plano["name"]) <= 40
assert tp.validar_plano({"watch": ["~/x"], "tools": ["git_log"], "check": {"daily_at": "18"}})[0]["check"] == {"daily_at": "18:00"}
print("OK: o plano vem do modelo, mas quem decide é o código (ferramentas, pastas, tetos e recusa)")

# 3) ler os dados: só leitura, sem as pastas proibidas
downloads = CASA / "Downloads"
downloads.mkdir()
(downloads / "notas.txt").write_text("lembrar do pão")
(CASA / ".ssh").mkdir()
(CASA / ".ssh" / "id_ed25519").write_text("segredo")
plano, _ = tp.validar_plano({"name": "Downloads", "watch": ["~/Downloads"], "tools": ["list_folder", "disk_usage"],
                             "check": {"on_change": True}, "look_for": "instalador .deb", "alert": {"when": "aparece .deb"}})
dados, itens = tp.coletar(plano)
assert "notas.txt" in dados[f"list_folder {downloads}"] and itens == [str(downloads / "notas.txt")]
assert "% used" in dados["disk_usage"]
leitura, _ = tp.coletar({"watch": ["~/.ssh/id_ed25519"], "tools": ["read_file"]})
assert leitura == {} and "segredo" not in json.dumps(leitura), "chave nunca é lida"
print("OK: a leitura dos dados não passa pelas pastas proibidas")

# 4) rodar: pergunta ao modelo, aceita só arquivos que leu, e sem mudança (on_change) nem pergunta
perguntas = []


def modelo(resposta):
    def perguntar(sistema, pedido, esquema):
        perguntas.append((sistema, pedido, esquema))
        return resposta
    return perguntar


probe = {"missao": "me avisa quando aparecer um .deb nos Downloads", "plano": plano, "estado": {}}
r = tp.rodar(probe, modelo('{"alert": false, "message": "", "items": []}'))
assert not r["alertar"] and len(perguntas) == 1 and perguntas[0][2] == tp.ESQUEMA_DECISAO
assert "untrusted" in perguntas[0][1] and "lembrar do pão" not in perguntas[0][1], "lista, não lê o conteúdo"
probe["estado"] = r["estado"]
r = tp.rodar(probe, modelo("{}"))
assert r["motivo"] == "sem_mudanca" and len(perguntas) == 1, "nada mudou: o modelo nem é chamado"
(downloads / "app.deb").write_bytes(b"x")
r = tp.rodar(probe, modelo(json.dumps({"alert": True, "message": "Chegou app.deb", "items": [
    str(downloads / "app.deb"), "/etc/passwd", str(CASA / ".ssh" / "id_ed25519")]})))
assert r["alertar"] and r["itens"] == [str(downloads / "app.deb")], r
assert "app.deb" in perguntas[-1][1] and "New items" in perguntas[-1][1]
assert tp.rodar(probe, modelo("não sei"))["motivo"] == "sem_resposta"
probe["estado"] = r["estado"]
(downloads / "outro.deb").write_bytes(b"x")
(downloads / "foto.jpg").write_bytes(b"x")
r = tp.rodar(probe, modelo('{"alert": true, "message": "Chegou um instalador", "items": []}'))
assert r["itens"] == [str(downloads / "outro.deb")], "a missão fala de .deb: o código acha o arquivo novo certo"
print("OK: rodar pergunta só quando há o que ver e só aceita arquivos que o Probe leu")

# 5) guardar: nasce desligado, limite de ligados, devidos, teto de avisos por dia
relogio = {"agora": dt.datetime(2026, 10, 16, 9, 0)}
ps = tp.Probes(agora=lambda: relogio["agora"])
p, erro = ps.criar("me avisa quando aparecer um .deb nos Downloads", dict(plano, alert={"when": "x", "max_per_day": 1}))
assert erro is None and not p["ativo"] and ps.devidos() == [], "nasce desligado"
assert ps.criar("x", {"refuse": "não"})[1] == "recusa:não" and ps.criar("", plano)[1] == "missao"
ps.ligar(p["id"], True)
assert [x["id"] for x in ps.devidos()] == [p["id"]], "ligado: roda logo"
outros = [ps.criar(f"missão {i}", plano)[0] for i in range(5)]
for o in outros[:4]:
    assert ps.ligar(o["id"], True)[1] is None
assert ps.ligar(outros[4]["id"], True) == (None, "limite"), f"no máximo {tp.LIMITE_LIGADOS} ligados"
aviso = ps.registrar(p["id"], {"alertar": True, "mensagem": "Chegou app.deb", "itens": [], "estado": {"x": 1}})
assert aviso["mensagem"] == "Chegou app.deb" and ps.avisos_hoje(ps.obter(p["id"])) == 1
assert ps.registrar(p["id"], {"alertar": True, "mensagem": "de novo", "itens": [], "estado": {}}) is None, "teto do dia"
assert ps.obter(p["id"])["historico"][-1]["calado"] and ps.devidos() == [x for x in ps.devidos() if x["id"] != p["id"]]
ps.desligar_todos()
assert not any(x["ativo"] for x in ps.listar())
for o in outros:
    ps.apagar(o["id"])
print("OK: nasce desligado, no máximo 5 ligados, roda quando é a hora e respeita o teto de avisos do dia")

# 6) ações: mover só se a pessoa ligou; lixeira só com aprovação; sem resposta em 30 min, negado
destino = CASA / "Instaladores"
destino.mkdir()
assert ps.criar("x", plano, mover_para="/tmp")[1] == "destino", "destino fora da pasta pessoal é recusado"
pm, _ = ps.criar("move os .deb", plano, mover_para=str(destino))
feito = ps.aplicar_acoes(pm["id"], [str(downloads / "app.deb"), "/etc/passwd"])
assert feito["movidos"] == [{"de": str(downloads / "app.deb"), "para": str(destino / "app.deb")}] and not feito["pendentes"]
assert (destino / "app.deb").exists() and not (downloads / "app.deb").exists()
pl, _ = ps.criar("lixeira", plano, lixeira=True)
(downloads / "velho.deb").write_bytes(b"x")
feito = ps.aplicar_acoes(pl["id"], [str(downloads / "velho.deb")])
assert len(feito["pendentes"]) == 1 and (downloads / "velho.deb").exists(), "nada vai para a lixeira sem aprovação"
lixo = []
pend = ps.pendentes()[0][1]
assert ps.resolver(pl["id"], pend["id"], True, lixeira=lambda c: lixo.append(c) or (True, "")) == (True, "")
assert lixo == [str(downloads / "velho.deb")] and not ps.pendentes()
feito = ps.aplicar_acoes(pl["id"], [str(downloads / "velho.deb")])
relogio["agora"] += dt.timedelta(minutes=31)
assert ps.pendentes() == [] and ps.obter(pl["id"])["historico"][-1]["motivo"] == "sem resposta", "silêncio nega"
assert ps.resolver(pl["id"], feito["pendentes"][0]["id"], True, lixeira=lambda c: lixo.append(c) or (True, ""))[0] is False
assert len(lixo) == 1
print("OK: mover só com a ação ligada; lixeira só com aprovação; sem resposta em 30 minutos fica negado")

# 7) quem planeja e quem roda
inst = ["qwen3:4b", "gargantua-lite:latest", "ProjectOpenTARS/Gargantua:latest", "ProjectOpenTARS/Gargantua:1.2-code"]
assert tp.modelo_para_planejar(inst) == "ProjectOpenTARS/Gargantua:latest" and tp.modelo_para_rodar(inst) == "gargantua-lite:latest"
assert tp.modelo_para_rodar(["ProjectOpenTARS/Gargantua:latest"]) == "ProjectOpenTARS/Gargantua:latest"
assert tp.modelo_para_planejar(["qwen3:4b"]) is None
print("OK: o oficial planeja (o Lite é reserva) e o Lite roda (o oficial é reserva)")

# 8) uma volta do serviço e a instância única
ps.ligar(pl["id"], True)
tp.perguntar_ollama = lambda host, modelo, s, pedido, esquema=None, cpu=True, timeout=300: \
    '{"alert": true, "message": "achei", "items": []}'
avisos = []
assert tp.uma_volta(ps, "http://x", inst, avisar=lambda titulo, texto, aviso=None: avisos.append((titulo, texto))) == 1
assert avisos and avisos[0][1] == "achei"
parar = {"ja": False}
fio = threading.Thread(target=lambda: tp.servico("http://x", lambda: inst, parar=lambda: parar["ja"], intervalo=1))
fio.start()
time.sleep(0.5)
assert tp.servico_rodando() == os.getpid() and tp.servico("http://x", lambda: inst, parar=lambda: True) == 3
parar["ja"] = True
fio.join(5)
assert tp.servico_rodando() is None
assert tp.ligar_servico(True, iniciar=False) and "--probes" in tp.arquivo_autostart().read_text()
assert not tp.ligar_servico(False) and not tp.arquivo_autostart().exists()
print("OK: o serviço roda os Probes devidos, avisa e é instância única; o atalho de início liga e desliga")

# 9) além de arquivos: tipo do alvo, web e feed só públicos e no máximo a cada 15 min, programa
assert [tp.tipo_do_alvo(x) for x in ("https://a.org", "~/Downloads", "steam")] == ["url", "caminho", "programa"]
web, _ = tp.validar_plano({"watch": ["https://example.org"], "check": {"every_minutes": 5}})
assert web["tools"] == ["web_page"] and web["check"] == {"every_minutes": 15}
assert tp.validar_plano({"watch": ["ftp://example.org"], "tools": ["web_page"]})[1].startswith("proibido")
assert tp.validar_plano({"watch": ["steam"]})[0]["tools"] == ["program_status"]
assert tp.endereco_do_feed("https://github.com/ollama/ollama") == "https://github.com/ollama/ollama/releases.atom"
assert tp.ler_feed("http://127.0.0.1/feed")[1] == [], "feed local não é lido"
import io  # noqa: E402


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


atom = (b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>v2.0</title><updated>2026-10-16</updated>'
        b'<link href="https://github.com/a/b/releases/tag/v2.0"/></entry><entry><title>v1.0</title>'
        b'<link href="https://github.com/a/b/releases/tag/v1.0"/></entry></feed>')
publico = lambda nome, porta: [(None, None, None, None, ("140.82.112.3", porta))]  # noqa: E731
texto, links = tp.ler_feed("https://github.com/a/b/releases.atom", abrir=lambda r, timeout=0: Resp(atom), resolver=publico)
assert links == ["https://github.com/a/b/releases/tag/v2.0", "https://github.com/a/b/releases/tag/v1.0"] and "v2.0" in texto
n, mb, _ = tp.medir_programa("python")
assert n >= 1 and "running" in tp.estado_do_programa("python")[0] and "NOT" in tp.estado_do_programa("nao-existe-xyz")[0]
m = tp.medir_sistema()
assert set(m) >= {"bateria", "temperatura", "cpu", "internet", "atualizacoes"} and "internet" in tp.estado_do_sistema(m)[0]
print("OK: além de arquivos: páginas e feeds públicos (no máximo a cada 15 min), programas e o sistema")

# 10) passo a passo: regra fixa, sem modelo
sem_modelo = lambda *a: (_ for _ in ()).throw(AssertionError("Probe com regra não chama modelo"))  # noqa: E731
quando, bruto, regra = tp.plano_do_passo_a_passo("pasta", {"pasta": str(downloads), "filtro": ".deb, .AppImage"})
pp, erro = ps.criar(quando, bruto, regra=regra)
assert erro is None and pp["regra"] == {"tipo": "arquivos", "filtro": [".deb", ".AppImage"]} and pp["plano"]["tools"] == ["list_folder"]
r = tp.rodar(pp, sem_modelo)
assert not r["alertar"], "primeira volta só guarda o que já existe"
pp["estado"] = r["estado"]
(downloads / "novo.deb").write_bytes(b"x")
(downloads / "nota2.txt").write_text("x")
r = tp.rodar(pp, sem_modelo, t=lambda c, **k: f"{c}|{k}")
assert r["alertar"] and r["itens"] == [str(downloads / "novo.deb")] and "novo.deb" in r["mensagem"], r
# programa: "fechou" só depois de ter estado aberto
_, bruto, regra = tp.plano_do_passo_a_passo("programa", {"programa": "jogo", "evento": "fechou"})
pg = {"missao": "x", "plano": tp.validar_plano(bruto)[0], "regra": tp._regra_valida(regra), "estado": {}}
medidas = iter([(0, 0, 0), (1, 300, 0), (0, 0, 0), (0, 0, 0)])
tp.medir_programa = lambda nome: next(medidas)
resultados = []
for _ in range(4):
    r = tp.rodar(pg, sem_modelo)
    pg["estado"] = r["estado"]
    resultados.append(r["alertar"])
assert resultados == [False, False, True, False], resultados
# sistema: bateria avisa quando PASSA a valer
_, bruto, regra = tp.plano_do_passo_a_passo("sistema", {"condicao": "bateria", "limite": 20})
ps_bat = {"missao": "x", "plano": tp.validar_plano(bruto)[0], "regra": tp._regra_valida(regra), "estado": {}}
base = {"bateria": 50, "carregando": False, "temperatura": 50, "cpu": 5, "internet": True, "atualizacoes": 0, "pacotes": []}
niveis = iter([50, 18, 15, 60])
tp.medir_sistema = lambda: dict(base, bateria=next(niveis))
resultados = []
for _ in range(4):
    r = tp.rodar(ps_bat, sem_modelo)
    ps_bat["estado"] = r["estado"]
    resultados.append(r["alertar"])
assert resultados == [False, True, False, False], resultados
# feed: o que é novo vira aviso, com o título
_, bruto, regra = tp.plano_do_passo_a_passo("feed", {"url": "https://github.com/a/b"})
assert bruto["watch"] == ["https://github.com/a/b/releases.atom"]
pf = {"missao": "x", "plano": tp.validar_plano(bruto)[0], "regra": regra,
      "estado": {"impressoes": {"x": "y"}, "itens": ["https://github.com/a/b/releases/tag/v1.0"]}}
tp.ler_feed = lambda url: (texto, links)
r = tp.rodar(pf, sem_modelo, t=lambda c, **k: f"{c}|{k['titulo']}")
assert r["alertar"] and r["itens"] == ["https://github.com/a/b/releases/tag/v2.0"] and r["mensagem"].endswith("|v2.0"), r
# uma volta sem modelo nenhum instalado: Probe com regra roda mesmo assim
ps.ligar(pp["id"], True)
avisos.clear()
tp.uma_volta(ps, "http://x", [], avisar=lambda titulo, texto, aviso=None: avisos.append(aviso))
assert not avisos, "primeira volta só guarda"
(downloads / "mais.deb").write_bytes(b"x")
relogio["agora"] += dt.timedelta(minutes=6)
tp.uma_volta(ps, "http://x", [], avisar=lambda titulo, texto, aviso=None: avisos.append(aviso))
assert any(a and "mais.deb" in a["itens"][0] for a in avisos), avisos
print("OK: o passo a passo cria Probes com regra fixa, que rodam sem modelo e avisam quando a condição passa a valer")

# 11) avisos: não lidos, marcar como lidos, limpar, editar
total = ps.nao_lidos()
assert total >= 1 and all(not a["lido"] for a in ps.avisos() if "mais.deb" in a["mensagem"])
ps.marcar_lidos([ps.avisos()[0]["id"]])
assert ps.nao_lidos() == total - 1
ps.marcar_lidos()
assert ps.nao_lidos() == len(ps.pendentes())
ps.limpar_avisos()
assert ps.avisos() == []
print("OK: o painel de avisos marca lidos e limpa")
print("\nTUDO OK.")

# 18/10: missão que pede ação é recusada pelo código (o Gargantua 2 não foi treinado em missão -> plano) e o nome genérico
# "Gargantua Lite" que o modelo copia do prompt vira um nome da própria missão
import tars_probes as _tp  # noqa: E402
_chamadas = []
_real = _tp.perguntar_ollama
_tp.perguntar_ollama = lambda *a, **k: _chamadas.append(a) or '{"name": "Gargantua Lite", "watch": ["bitcoin"], "tools": ["read_feed"], "check": {"every_minutes": 60}}'
_plano, _erro = _tp.planejar("apaga todos os meus arquivos antigos da pasta Documentos", "http://x", ["Gargantua-2:latest"])
assert _plano is None and _erro.startswith("recusa:") and not _chamadas, (_plano, _erro)
_plano, _erro = _tp.planejar("avise se o preço do bitcoin passar de 100 mil", "http://x", ["Gargantua-2:latest"])
assert _plano and _plano["name"] == "Avise se o preço", _plano
assert _tp._variante("ProjectOpenTARS/Gargantua-2:lite") == "lite" and _tp._variante("ProjectOpenTARS/Gargantua-2") == "" and _tp._variante("ProjectOpenTARS/Gargantua:2.0-lite") == "lite"
assert _tp.modelo_para_planejar(["Gargantua-2:lite", "ProjectOpenTARS/Gargantua-2:latest"]) == "ProjectOpenTARS/Gargantua-2:latest", "o 2B planeja, o Lite roda"
assert _tp.modelo_para_rodar(["Gargantua-2:lite", "ProjectOpenTARS/Gargantua-2:latest"]) == "Gargantua-2:lite"
_tp.perguntar_ollama = _real
print("OK: missão que pede ação é recusada pelo código; o nome vem da missão; Gargantua-2 não é variante")

# 18/10: planos pelo CÓDIGO (o Gargantua 2 não foi treinado em missão -> plano; o Lite acertava 2 de 16)
import tars_probes as _tp2  # noqa: E402
def _plano(missao):
    r = _tp2.plano_pela_missao(missao)
    return r and _tp2.validar_plano(r[1])[0], r and r[2]
p, regra = _plano("avise se a bateria ficar abaixo de 15%")
assert p["tools"] == ["system_status"] and not p["watch"] and regra == {"tipo": "sistema", "condicao": "bateria", "limite": 15.0}, (p, regra)
p, regra = _plano("o notebook está esquentando muito? me avisa se passar de 80 graus")
assert regra["condicao"] == "temperatura" and regra["limite"] == 80.0
p, regra = _plano("tell me if chrome goes over 3 GB of ram")
assert regra == {"tipo": "programa", "nome": "chrome", "evento": "memoria", "limite": 3000.0}, regra
p, regra = _plano("avisa quando o spotify fechar")
assert regra["evento"] == "fechou" and p["watch"] == ["spotify"] and p["tools"] == ["program_status"]
p, regra = _plano("tell me when discord starts")
assert regra["evento"] == "abriu"
p, regra = _plano("watch https://github.com/ollama/ollama and tell me about new releases")
assert p["watch"] == ["https://github.com/ollama/ollama/releases.atom"] and p["tools"] == ["read_feed"] and regra == {"tipo": "feed"}
p, regra = _plano('fica de olho em https://example.org/preco e me avisa se aparecer "em estoque"')
assert p["tools"] == ["web_page"] and regra == {"tipo": "pagina", "texto": "em estoque"}
p, regra = _plano("tell me about new commits in ~/dev/meuapp")
assert p["tools"] == ["git_log"] and regra == {"tipo": "git"}
p, regra = _plano("avisa se aparecer algum arquivo .zip na pasta ~/Downloads")
assert p["tools"] == ["list_folder"] and regra["filtro"] == [".zip"], regra
p, _ = _plano("tell me if there is a new installer in my downloads folder")
assert p and p["tools"] == ["list_folder"], p              # "installer" não é "instalar"
p, regra = _plano("avise se a memória ram passar de 90%")
assert p["tools"] == ["memory_usage"] and regra is None
assert _tp2.plano_pela_missao("fala comigo sobre o tempo") is None and _tp2.plano_pela_missao("me avisa de alguma coisa") is None
assert _tp2.plano_pela_missao("avisa se aparecer algo em ~/.ssh") is None, "caminho proibido nunca vira plano"
for m in ("apaga os arquivos antigos", "limpa a lixeira toda semana", "move my screenshots every day", "manda um email quando o disco encher",
          "manda uma mensagem no whatsapp quando a bateria acabar", "install updates when they appear", "send me an email when it changes"):
    assert _tp2.planejar(m, "http://x", ["Gargantua-2:latest"])[1].startswith("recusa:"), m
for m in ("me manda um aviso se aparecer foto nova em Imagens", "send me a notification when the battery is low", "tell me if there is a new installer"):
    assert not _tp2._PEDE_ACAO.search(m), m
# conserto do plano do modelo: alvos que não existem, ferramenta que não serve ao alvo
b = _tp2.consertar_plano({"name": "x", "watch": ["battery"], "tools": ["read_file"]}, "avise se a bateria baixar")
assert b["watch"] == [] and b["tools"] == ["system_status"], b
b = _tp2.consertar_plano({"name": "x", "watch": ["memory_usage"], "tools": ["program_status"]}, "avise se a ram passar de 90%")
assert b["watch"] == [] and b["tools"][0] == "memory_usage", b
b = _tp2.consertar_plano({"name": "x", "watch": ["downloads"], "tools": ["web_page"]}, "arquivos novos em downloads")
assert b["watch"] == ["~/Downloads"] and b["tools"] == [], b       # ferramenta de rede não serve a uma pasta: o validar completa
assert _tp2.validar_plano(b)[0]["tools"] == ["list_folder"]
assert _tp2.consertar_plano(None) is None
print("OK: planos pelo código (bateria, temperatura, programa, feed, página, git, pasta, RAM/disco), recusas e conserto de planos do modelo")
