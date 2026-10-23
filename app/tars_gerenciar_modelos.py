"""openTARS: o que a página "Gerenciar modelos" (Configurações) sabe do Ollama: listar o que está instalado (com tamanho e
detalhes) e apagar. Só biblioteca padrão, sem Qt, para testar com o Ollama de mentira.

Atualizar um modelo é baixar de novo (tars_primeiro_uso.baixar_modelo): o Ollama só traz as camadas que mudaram.
"""

import json
import urllib.error
import urllib.request

import tars_primeiro_uso as pu


def _tamanho_gb(m):
    return float(m.get("size") or 0) / 1e9


def listar(host, abrir=None):
    """Os modelos instalados, do maior para o menor: [{nome, gb, parametros, quantizacao, familia, data, nuvem, oficial}].
    Levanta OSError se o Ollama não responder."""
    pedido = urllib.request.Request(f"{host}/api/tags")
    with (abrir or urllib.request.urlopen)(pedido, timeout=6) as r:
        dados = json.loads(r.read())
    saida = []
    for m in dados.get("models", []):
        nome = str(m.get("name") or m.get("model") or "")
        if not nome:
            continue
        d = m.get("details") or {}
        saida.append({
            "nome": nome,
            "gb": _tamanho_gb(m),
            "parametros": str(d.get("parameter_size") or ""),
            "quantizacao": str(d.get("quantization_level") or ""),
            "familia": str(d.get("family") or ""),
            "data": str(m.get("modified_at") or "")[:10],
            "nuvem": pu.e_modelo_de_nuvem(nome) or bool(m.get("remote_host")),
            "oficial": "gargantua" in nome.lower().split("/")[-1],
        })
    return sorted(saida, key=lambda x: (-x["gb"], x["nome"]))


def total_gb(modelos):
    return sum(m["gb"] for m in modelos)


def apagar(nome, host, abrir=None):
    """Apaga `nome` do Ollama (DELETE /api/delete). Devolve (ok, erro). Os modelos que outros modelos compartilham
    continuam: o Ollama só remove as camadas que mais ninguém usa."""
    corpo = json.dumps({"model": nome, "name": nome}).encode()      # "name" para os Ollama mais antigos
    pedido = urllib.request.Request(f"{host}/api/delete", data=corpo, method="DELETE",
                                    headers={"Content-Type": "application/json"})
    try:
        with (abrir or urllib.request.urlopen)(pedido, timeout=30):
            return True, ""
    except urllib.error.HTTPError as e:
        try:
            detalhe = json.loads(e.read()).get("error", "")
        except Exception:  # noqa: BLE001
            detalhe = ""
        return False, detalhe or f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def detalhe(m, tamanho_texto):
    """'7.6B · Q4_K_M · 4.7 GB · 2026-10-21' sem os campos que o Ollama não informou."""
    partes = [m["parametros"], m["quantizacao"], tamanho_texto(m["gb"]) if m["gb"] else "", m["data"]]
    return " · ".join(p for p in partes if p)
