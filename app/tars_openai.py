"""openTARS 3.0: servidores compatíveis com a API da OpenAI.

vLLM, LM Studio, llama.cpp (llama-server), LocalAI, Jan... todos falam
/v1/models e /v1/chat/completions. Com o endereço configurado
(opentars --servidor http://localhost:1234/v1), os modelos desse servidor
entram no catálogo como "api:<nome>" e o openTARS conversa com eles, com
ferramentas, igual faz com o Ollama.

Aqui fica só o que é da API: converter a conversa (formato do Ollama, que
o resto do openTARS usa) pro formato OpenAI, ler o streaming (SSE) e
converter as chamadas de ferramenta de volta. Sem estado global."""

import json
import re

PREFIXO = "api:"


def eh_modelo_api(tag):
    return isinstance(tag, str) and tag.startswith(PREFIXO)


def nome_no_servidor(tag):
    return tag[len(PREFIXO):] if eh_modelo_api(tag) else tag


def normalizar_url(url):
    """'localhost:1234' -> 'http://localhost:1234/v1'; mantém /v1 se já tiver."""
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    if not re.match(r"^https?://", url):
        # sem http(s):// escrito: servidor da própria máquina/rede local usa http; qualquer outro, https
        # (a chave de API não pode ir em texto puro pela internet só porque faltou digitar o "https://")
        local = re.match(r"^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|\[::1\]|[^/]*\.local)", url, re.I)
        url = ("http://" if local else "https://") + url
    if not re.search(r"/v\d+[a-z]*(/openai)?$", url):
        url += "/v1"
    return url


# ------------------------------------------------------------
# Conversa: Ollama -> OpenAI
# ------------------------------------------------------------

def _conteudo_com_imagens(texto, imagens):
    partes = [{"type": "text", "text": texto or ""}]
    for b64 in imagens or ():
        partes.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
    return partes


def para_openai(mensagens):
    """Mensagens no formato do Ollama -> formato OpenAI.

    Diferenças: a chamada de ferramenta da OpenAI tem 'id' e argumentos em
    TEXTO JSON; o resultado ('tool') aponta pro id. O Ollama não usa ids:
    os resultados vêm na ordem das chamadas, então os ids são dados aqui,
    em ordem. Imagens viram partes 'image_url'."""
    saida = []
    pendentes = []  # ids de chamadas ainda sem resultado, na ordem
    n = 0
    for m in mensagens:
        papel = m.get("role")
        conteudo = m.get("content") or ""
        if papel == "assistant" and m.get("tool_calls"):
            chamadas = []
            for ch in m["tool_calls"]:
                funcao = ch.get("function", {}) or {}
                argumentos = funcao.get("arguments", {})
                if not isinstance(argumentos, str):
                    argumentos = json.dumps(argumentos or {}, ensure_ascii=False)
                n += 1
                ident = ch.get("id") or f"call_{n}"
                pendentes.append(ident)
                chamadas.append({"id": ident, "type": "function",
                                 "function": {"name": funcao.get("name", ""), "arguments": argumentos}})
            saida.append({"role": "assistant", "content": conteudo or None, "tool_calls": chamadas})
        elif papel == "tool":
            if pendentes:
                saida.append({"role": "tool", "tool_call_id": pendentes.pop(0), "content": conteudo})
            else:  # resultado órfão (conversa antiga cortada): vira texto
                saida.append({"role": "user", "content": f"[tool result] {conteudo}"})
        elif papel in ("system", "user", "assistant"):
            while pendentes:     # chamada sem resultado: os servidores OpenAI recusam (400); fecha com um resultado vazio
                saida.append({"role": "tool", "tool_call_id": pendentes.pop(0), "content": "(no result)"})
            if m.get("images"):
                saida.append({"role": papel, "content": _conteudo_com_imagens(conteudo, m["images"])})
            else:
                saida.append({"role": papel, "content": conteudo})
    return saida


def corpo_chat(modelo, mensagens, tools=None, stream=True, temperatura=None, formato=None):
    corpo = {"model": nome_no_servidor(modelo), "messages": para_openai(mensagens), "stream": stream}
    if tools:
        corpo["tools"] = tools  # o formato do openTARS já é o da OpenAI
    if temperatura is not None:
        corpo["temperature"] = temperatura
    if formato:
        corpo["response_format"] = {"type": "json_schema",
                                    "json_schema": {"name": "resposta", "schema": formato, "strict": True}}
    return corpo


# ------------------------------------------------------------
# Streaming (SSE) -> eventos
# ------------------------------------------------------------

def _argumentos(texto):
    if isinstance(texto, dict):
        return texto
    try:
        valor = json.loads(texto or "{}")
        return valor if isinstance(valor, dict) else {}
    except ValueError:
        achado = re.search(r"\{.*\}", texto or "", re.S)
        if achado:
            try:
                return json.loads(achado.group(0))
            except ValueError:
                pass
        return {}


class LeitorStream:
    """Junta os pedaços do streaming. alimentar(linha) devolve os eventos
    novos: [('pensamento', txt) | ('resposta', txt) | ('erro', txt) | ('fim', motivo)].
    Depois do fim, .chamadas tem as chamadas de ferramenta no formato do Ollama."""

    def __init__(self):
        self._chamadas = {}   # índice -> {"name", "arguments" (texto)}
        self.conteudo = []
        self.pensamento = []
        self.terminou = False
        self.motivo = None

    def alimentar(self, linha):
        if isinstance(linha, bytes):
            linha = linha.decode("utf-8", "replace")
        linha = (linha or "").strip()
        if not linha or linha.startswith(":") or not linha.startswith("data:"):
            return []
        dados = linha[5:].strip()
        if dados == "[DONE]":
            self.terminou = True
            return [("fim", self.motivo)]
        try:
            pedaco = json.loads(dados)
        except ValueError:
            return []
        if not isinstance(pedaco, dict):
            return []
        if pedaco.get("error"):
            erro = pedaco["error"]
            return [("erro", erro.get("message") if isinstance(erro, dict) else str(erro))]
        eventos = []
        for escolha in pedaco.get("choices") or []:
            if not isinstance(escolha, dict):
                continue
            delta = escolha.get("delta") or escolha.get("message") or {}
            raciocinio = delta.get("reasoning_content") or delta.get("reasoning")
            if raciocinio:
                self.pensamento.append(raciocinio)
                eventos.append(("pensamento", raciocinio))
            if delta.get("content"):
                self.conteudo.append(delta["content"])
                eventos.append(("resposta", delta["content"]))
            for ch in delta.get("tool_calls") or []:
                i = ch.get("index", len(self._chamadas))
                atual = self._chamadas.setdefault(i, {"name": "", "arguments": ""})
                funcao = ch.get("function") or {}
                if funcao.get("name"):
                    atual["name"] += funcao["name"]
                if funcao.get("arguments"):
                    args = funcao["arguments"]
                    atual["arguments"] += args if isinstance(args, str) else json.dumps(args)
            if escolha.get("finish_reason"):
                self.motivo = escolha["finish_reason"]
        return eventos

    @property
    def chamadas(self):
        return [{"function": {"name": c["name"], "arguments": _argumentos(c["arguments"])}}
                for _, c in sorted(self._chamadas.items()) if c["name"]]


def resposta_unica(dados):
    """Texto de uma resposta não-streaming."""
    try:
        mensagem = dados["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return None
    return (mensagem.get("content") or "").strip()


# ------------------------------------------------------------
# Modelos do servidor
# ------------------------------------------------------------
_RE_VISAO = re.compile(r"(^|[-_/.])(vl|vision|llava|pixtral|moondream|minicpm-v|gemma-?3|gemma-?4|qwen2\.5-?omni)",
                       re.I)


def ler_modelos(dados):
    """/v1/models -> lista de ids (sem os de embedding)."""
    ids = []
    for item in (dados or {}).get("data") or []:
        ident = item.get("id") if isinstance(item, dict) else None
        if ident and not re.search(r"embed|bge-|minilm|rerank", ident, re.I):
            ids.append(ident)
    return ids


def capacidades_pelo_nome(ident):
    caps = {"tools"}
    if _RE_VISAO.search(ident):
        caps.add("vision")
    if re.search(r"qwen3|deepseek-r1|qwq|reason|think", ident, re.I):
        caps.add("thinking")
    return caps
