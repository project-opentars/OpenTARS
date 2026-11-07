"""5.3 (F4): o que o assistente resolve sem o modelo (tars_atalhos). Memória de verdade, comandos de verdade numa casa temporária,
busca desligada (a pergunta sobre o mundo volta para o modelo)."""
import os
import subprocess
import sys
import tempfile

casa = tempfile.mkdtemp(prefix="opentars-atalhos-")
os.environ["HOME"] = casa
os.environ["TARS_ARQUIVO_CONFIG"] = os.path.join(casa, "config.json")
os.environ["TARS_ARQUIVO_AGENDA"] = os.path.join(casa, "agenda.json")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tars_atalhos  # noqa: E402
import tars_i18n  # noqa: E402
import tars_memoria  # noqa: E402
import tars_plataforma  # noqa: E402

tars_i18n.salvar_config(web={"ligada": False, "endereco": "http://127.0.0.1:9"})
os.makedirs(os.path.join(casa, "Documents"))
with open(os.path.join(casa, "Documents", "relatorio-2026.txt"), "w") as f:
    f.write("".join(f"linha {i}\n" for i in range(7)))
os.makedirs(os.path.join(casa, "logs"))
with open(os.path.join(casa, "logs", "app.log"), "w") as f:
    f.write("ERROR a\nINFO b\nERROR c\n")


class Core:
    memoria = tars_memoria.Memoria(os.path.join(casa, "memoria.json"))
    rodados = []

    def executar_ferramenta(self, nome, argumentos):
        assert nome == "execute_terminal"
        self.rodados.append(argumentos["command"])
        r = subprocess.run(["bash", "-c", argumentos["command"]], capture_output=True, text=True, cwd=casa)
        return {"sucesso": r.returncode == 0, "codigo": r.returncode, "stdout": r.stdout, "stderr": r.stderr}


core = Core()
r = tars_atalhos.resolver


assert "MB" in r("quanta memória ram está livre?", core) and "disponíveis" in r("quanta memória ram está livre?", core)
assert "GB" in r("is my disk almost full?", core)
assert r("dá pra baixar um arquivo de 2 GB?", core).startswith(("Sim", "Não"))
print("OK: estado do PC com avaliação e capacidade, pela memória disponível")

assert "Anotado" in r("guarda que o roteador fica na sala", core) and core.memoria.listar() == ["o roteador fica na sala"]
assert "roteador" in r("o que você sabe sobre mim?", core)
assert "Esquecido" in r("esquece o roteador", core) and core.memoria.listar() == []
print("OK: lembrar, ver e esquecer pela memória do app")

if tars_plataforma.sistema() == "linux":
    assert "7 linhas" in r("quantas linhas tem o relatorio?", core), core.rodados[-1:]
    assert "2 vezes" in r("quantas vezes ERROR aparece em logs/app.log?", core)
    resposta = r("cria a pasta backup e copia Documents/relatorio-2026.txt para ela", core)
    assert os.path.exists(os.path.join(casa, "backup", "relatorio-2026.txt")), (resposta, core.rodados[-2:])
    print("OK: operações com o nome ligado ao disco, resposta em palavras e vários passos")

import tars_rotinas  # noqa: E402
assert "te lembro de tomar água" in r("me lembra de tomar água daqui a 30 minutos", core)
assert "Timer de 5 minutos" in r("põe um timer de 5 minutos", core)
assert "Quando te lembro" in r("me lembra de comprar pão", core)
rotinas = tars_rotinas.Agenda().listar()
assert len(rotinas) == 2 and all(x["ativa"] and x["quando"]["tipo"] == "uma_vez" for x in rotinas), rotinas
assert r("Lembrete: tomar água", core) == "⏰ Lembrete: tomar água"
assert r("tell me a fun fact about honey", core) is None
print("OK: lembrete e timer viram rotina de verdade na agenda; na hora, o aviso sai sem o modelo")

assert r("quem escreveu Grande Sertão: Veredas?", core) is None, "busca desligada: a pergunta vai para o modelo"
assert r("me conta uma piada", core) is None and r("abre o firefox", core) is None
print("OK: o que não é de regra segue para o modelo")
print("TUDO OK.")
