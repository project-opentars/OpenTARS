"""openTARS 5.0: o histórico de conversas (a lista da barra lateral).

Só biblioteca padrão. Fica em ~/.config/opentars/historico.json (permissão 0600), neste
computador e só nele. Cada conversa guarda as mensagens no mesmo formato do núcleo
(sem o prompt de sistema e sem imagens), então abrir uma conversa antiga devolve o
contexto exato à IA. TARS_ARQUIVO_HISTORICO muda o arquivo (testes)."""

import json
import os
import threading
import time
import uuid
from pathlib import Path

import tars_memoria as memoria_lib
import tars_plataforma as plataforma

LIMITE_CONVERSAS = 200
LIMITE_TITULO = 60


def arquivo_historico():
    env = os.environ.get("TARS_ARQUIVO_HISTORICO")
    if env:
        return Path(env)
    return plataforma.pastas()["config"] / "historico.json"


def _e_pedido_da_pessoa(m):
    """Mensagem 'user' escrita pela pessoa (as automáticas do núcleo começam com '[')."""
    return m.get("role") == "user" and bool((m.get("content") or "").strip()) \
        and not (m.get("content") or "").lstrip().startswith("[")


def titulo_da(mensagens):
    for m in mensagens:
        if _e_pedido_da_pessoa(m):
            texto = " ".join((m.get("content") or "").split())
            return texto if len(texto) <= LIMITE_TITULO else texto[:LIMITE_TITULO - 1].rstrip() + "…"
    return ""


def _limpar(mensagens):
    return [{k: v for k, v in m.items() if k != "images"} for m in mensagens
            if isinstance(m, dict) and m.get("role") != "system"]


LIMITE_MENSAGENS_POR_CONVERSA = 400


def _juntar_mensagens(antigas, novas):
    """A conversa em memória é podada (só as últimas ~30 mensagens), mas o histórico guarda tudo: acha onde o final
    do que já estava salvo coincide com o começo do que chegou e emenda, em vez de jogar o começo fora."""
    if not antigas or not novas:
        return novas
    for k in range(min(len(antigas), len(novas)), 0, -1):
        if antigas[-k:] == novas[:k]:
            return (antigas[:-k] + novas)[-LIMITE_MENSAGENS_POR_CONVERSA:]
    return novas


class Historico:
    def __init__(self, caminho=None, agora=None):
        self.caminho = Path(caminho) if caminho else arquivo_historico()
        self.agora = agora or time.time
        self._trava = threading.Lock()

    # -- arquivo ---------------------------------------------------------
    def _ler(self):
        try:
            dados = json.loads(self.caminho.read_text(encoding="utf-8"))
            itens = dados.get("conversas") if isinstance(dados, dict) else None
            return [c for c in (itens or []) if isinstance(c, dict) and c.get("id")]
        except OSError:
            return []
        except ValueError:
            memoria_lib.guardar_quebrado(self.caminho)     # não perde o que ainda dá pra recuperar à mão
            return []

    def _gravar(self, conversas):
        memoria_lib.gravar_texto_atomico(
            self.caminho, json.dumps({"versao": 1, "conversas": conversas}, ensure_ascii=False))

    # -- operações -------------------------------------------------------
    def nova_id(self):
        return uuid.uuid4().hex[:12]

    def salvar(self, id_, mensagens):
        """Grava (ou atualiza) a conversa. Sem nenhuma mensagem da pessoa, não grava nada."""
        mensagens = _limpar(mensagens)
        titulo = titulo_da(mensagens)
        if not titulo:
            return False
        with self._trava:
            conversas = [c for c in self._ler() if c["id"] != id_]
            anterior = next((c for c in self._ler() if c["id"] == id_), None)
            if anterior:
                mensagens = _juntar_mensagens(anterior.get("mensagens", []), mensagens)
            conversas.append({"id": id_, "titulo": (anterior or {}).get("titulo_manual") or titulo,
                              "titulo_manual": (anterior or {}).get("titulo_manual", ""),
                              "criada": (anterior or {}).get("criada", self.agora()),
                              "atualizada": self.agora(), "mensagens": mensagens})
            conversas.sort(key=lambda c: c["atualizada"])
            self._gravar(conversas[-LIMITE_CONVERSAS:])
        return True

    def listar(self, busca=""):
        """[{'id', 'titulo', 'atualizada'}] da mais recente pra mais antiga; busca nos títulos e nas mensagens."""
        chave = " ".join(str(busca or "").lower().split())
        saida = []
        for c in sorted(self._ler(), key=lambda c: c.get("atualizada", 0), reverse=True):
            if chave:
                corpo = " ".join((m.get("content") or "") for m in c.get("mensagens", []) if isinstance(m.get("content"), str))
                if chave not in c.get("titulo", "").lower() and chave not in corpo.lower():
                    continue
            saida.append({"id": c["id"], "titulo": c.get("titulo", ""), "atualizada": c.get("atualizada", 0)})
        return saida

    def abrir(self, id_):
        c = next((c for c in self._ler() if c["id"] == id_), None)
        return list(c.get("mensagens", [])) if c else None

    def renomear(self, id_, titulo):
        titulo = " ".join(str(titulo or "").split())[:LIMITE_TITULO]
        with self._trava:
            conversas = self._ler()
            for c in conversas:
                if c["id"] == id_:
                    c["titulo_manual"] = titulo
                    c["titulo"] = titulo or titulo_da(c.get("mensagens", []))
                    self._gravar(conversas)
                    return True
        return False

    def apagar(self, id_):
        with self._trava:
            conversas = self._ler()
            restantes = [c for c in conversas if c["id"] != id_]
            if len(restantes) == len(conversas):
                return False
            self._gravar(restantes)
            return True

    def apagar_tudo(self):
        with self._trava:
            n = len(self._ler())
            try:
                self.caminho.unlink()
            except OSError:
                pass
            return n

    def exportar(self, destino):
        """Copia tudo (texto puro, JSON) pra `destino`. Devolve quantas conversas."""
        conversas = self._ler()
        memoria_lib.gravar_texto_atomico(destino, json.dumps({"conversas": conversas}, ensure_ascii=False, indent=1))
        return len(conversas)


def agrupar_por_dia(itens, agora=None):
    """[(chave, [itens])] com chave em 'hoje' | 'ontem' | 'semana' | 'antes', na ordem em que aparecem."""
    import datetime as dt
    agora = dt.datetime.fromtimestamp(agora or time.time())
    inicio_hoje = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    grupos = {}
    for item in itens:
        quando = dt.datetime.fromtimestamp(item["atualizada"])
        dias = (inicio_hoje - quando.replace(hour=0, minute=0, second=0, microsecond=0)).days
        chave = "hoje" if dias <= 0 else "ontem" if dias == 1 else "semana" if dias < 7 else "antes"
        grupos.setdefault(chave, []).append(item)
    return [(k, grupos[k]) for k in ("hoje", "ontem", "semana", "antes") if k in grupos]
