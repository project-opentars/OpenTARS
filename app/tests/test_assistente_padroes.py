"""5.2 (decisão do Enzo, 24/10): o assistente vem todo ligado (o modelo das ações na memória, o atalho das ações de texto,
o início com o sistema e a sugestão pelo programa em uso), uma vez só, sem desfazer o que a pessoa escolheu. Os testes e
a prova (TARS_SEM_ATALHO=1) não mexem no sistema. O atalho e o início com o sistema são de mentira aqui."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import RAIZ  # noqa: E402,F401

import tars_assistente as assistente  # noqa: E402
import tars_atalho  # noqa: E402
import tars_contexto  # noqa: E402
import tars_i18n  # noqa: E402

config = Path(os.environ["TARS_ARQUIVO_CONFIG"])
inicio = {"ligado": False}
assistente.inicia_com_sistema = lambda: inicio["ligado"]
assistente.iniciar_com_sistema = lambda v: inicio.update(ligado=bool(v)) or bool(v)
tars_atalho.registrar_acoes = lambda combinacao=None: tars_i18n.salvar_config(atalho_acoes_registrado=True) and (True, "")


def zerar(dados):
    config.write_text(json.dumps(dados))
    tars_i18n._config = None
    inicio["ligado"] = False


zerar({})
assert assistente.aplicar_padroes() == [], "com TARS_SEM_ATALHO=1 (testes, prova) nada muda"
assert not assistente.ligado() and not inicio["ligado"]
os.environ.pop("TARS_SEM_ATALHO")
ligou = assistente.aplicar_padroes(em_segundo_plano=False)
assert ligou == ["assistente", "sugestoes_programa", "atalho", "inicio"], ligou
assert assistente.ligado() and tars_contexto.ligado() and inicio["ligado"]
assert tars_i18n.ler_config().get("atalho_acoes_registrado")
print("OK: na primeira abertura liga o assistente, a sugestão, o atalho e o início com o sistema")

assistente.ligar = lambda ativo, host, modelo, sessao=None: tars_i18n.salvar_config(assistente=bool(ativo))
assistente.ligar(False, "http://x", "m")
inicio["ligado"] = False
assert assistente.aplicar_padroes(em_segundo_plano=False) == [] and not assistente.ligado() and not inicio["ligado"]
print("OK: uma vez só: o que a pessoa desligar depois continua desligado")

zerar({"assistente": False, "sugestoes_programa": False, "atalho_acoes_registrado": False})
ligou = assistente.aplicar_padroes(em_segundo_plano=False)
assert ligou == ["inicio"] and not assistente.ligado() and not tars_contexto.ligado(), ligou
print("OK: quem já tinha escolhido desligar (antes da atualização) fica como escolheu")
print("test_assistente_padroes: TUDO OK.")
