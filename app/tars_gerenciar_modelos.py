"""openTARS: o que a página "Gerenciar modelos" (Configurações) sabe do Ollama: listar o que está instalado (com tamanho e
detalhes) e apagar. Só biblioteca padrão, sem Qt, para testar com o Ollama de mentira.

Atualizar um modelo é baixar de novo (tars_primeiro_uso.baixar_modelo): o Ollama só traz as camadas que mudaram.
"""

import json
import os
import re
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


# 5.2 (F9.5): o Ollama não atualiza sozinho. Quem já tem o Gargantua fica com o antigo até baixar de novo; o app compara a
# camada do modelo instalado (o FROM .../sha256-... do Modelfile) com a camada "model" do manifesto publicado no ollama.com.
REGISTRO = "https://registry.ollama.ai/v2/{repositorio}/manifests/{tag}"


def camada_local(nome, host, abrir=None):
    """O digest da camada de pesos do modelo instalado, ou "" se não deu para saber."""
    pedido = urllib.request.Request(f"{host}/api/show", data=json.dumps({"model": nome}).encode(),
                                    headers={"Content-Type": "application/json"})
    with (abrir or urllib.request.urlopen)(pedido, timeout=10) as r:
        achados = re.findall(r"sha256[-:]([0-9a-f]{64})", json.loads(r.read()).get("modelfile") or "")
    return achados[0] if achados else ""


def camada_publicada(nome, abrir=None):
    """O digest da camada "model" do mesmo nome no ollama.com, ou "" se não deu para saber."""
    repositorio, _, tag = nome.partition(":")
    pedido = urllib.request.Request(REGISTRO.format(repositorio=repositorio.lower(), tag=tag or "latest"),
                                    headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"})
    with (abrir or urllib.request.urlopen)(pedido, timeout=10) as r:
        camadas = json.loads(r.read()).get("layers") or []
    return next((c["digest"].split(":")[-1] for c in camadas if str(c.get("mediaType", "")).endswith(".model")), "")


def desatualizados(host, abrir=None, abrir_registro=None):
    """Os modelos oficiais do openTARS instalados (ProjectOpenTARS/...) cuja versão publicada é outra. Sem internet ou
    sem Ollama, devolve [] (nunca avisa por engano). TARS_SEM_AVISO_VERSAO desliga, como o aviso de versão do app."""
    if os.environ.get("TARS_SEM_AVISO_VERSAO", "0") not in ("0", "", "off", "no", "nao"):
        return []
    saida = []
    try:
        nomes = [m["nome"] for m in listar(host, abrir) if m["nome"].lower().startswith("projectopentars/")]
    except Exception:  # noqa: BLE001
        return []
    for nome in nomes:
        try:
            local, publicada = camada_local(nome, host, abrir), camada_publicada(nome, abrir_registro)
        except Exception:  # noqa: BLE001  (sem internet, tag apagada do ollama.com)
            continue
        if local and publicada and local != publicada:
            saida.append(nome)
    return saida


def detalhe(m, tamanho_texto):
    """'7.6B · Q4_K_M · 4.7 GB · 2026-10-21' sem os campos que o Ollama não informou."""
    partes = [m["parametros"], m["quantizacao"], tamanho_texto(m["gb"]) if m["gb"] else "", m["data"]]
    return " · ".join(p for p in partes if p)
