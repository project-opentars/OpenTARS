"""openTARS 5.1: pesquisa web pelo SearXNG (decisão do Enzo em 11/10). Módulo puro, só biblioteca padrão.

Regras (plano 5.1, "Pesquisa web integrada"):
  * Desligada por padrão. Ligar mostra o que sai: o texto da pesquisa vai para o SearXNG, que o repassa aos buscadores.
  * Com ela desligada, nada é enviado (as ferramentas nem aparecem).
  * O que vem das páginas é DADO, nunca instrução, e entra cortado (contexto pequeno).
  * Só texto: sem scripts, sem baixar arquivos. read_page não abre endereço local nem de rede interna (senão uma página
    podia fazer a IA ler o Ollama ou outro serviço do próprio PC).

A configuração fica em ~/.config/opentars/config.json ("web": {"ligada", "endereco"}).
"""

import html.parser
import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request

import tars_i18n

ENDERECO_PADRAO = "http://127.0.0.1:8888"
LIMITE_RESULTADOS = 8
LIMITE_PAGINA_BYTES = 1_000_000
LIMITE_TEXTO_PAGINA = 8000
TIMEOUT = 10
AGENTE = "openTARS/5.1 (+https://project-opentars.github.io/OpenTARS/)"


def config():
    bruto = tars_i18n.ler_config().get("web")
    bruto = bruto if isinstance(bruto, dict) else {}
    endereco = str(bruto.get("endereco") or ENDERECO_PADRAO).strip().rstrip("/")
    return {"ligada": bool(bruto.get("ligada")), "endereco": endereco}


def salvar_config(ligada, endereco=None):
    atual = config()
    tars_i18n.salvar_config(web={"ligada": bool(ligada), "endereco": (endereco or atual["endereco"]).strip().rstrip("/")})


def buscar(consulta, endereco=None, abrir=None):
    """[{'titulo', 'url', 'trecho'}] do SearXNG (formato JSON). Levanta ValueError com um motivo curto se falhar."""
    consulta = " ".join(str(consulta or "").split())[:300]
    if not consulta:
        raise ValueError("empty query")
    url = f"{(endereco or config()['endereco'])}/search?" + urllib.parse.urlencode({"q": consulta, "format": "json"})
    pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept": "application/json"})
    try:
        with (abrir or urllib.request.urlopen)(pedido, timeout=TIMEOUT) as r:
            dados = json.loads(r.read(LIMITE_PAGINA_BYTES) or b"{}")
    except urllib.error.HTTPError as e:
        raise ValueError("json format disabled in SearXNG (settings.yml: search.formats)" if e.code == 403 else f"HTTP {e.code}")
    except (OSError, ValueError) as e:
        raise ValueError(f"SearXNG not reachable: {e}")
    saida = []
    for item in (dados.get("results") or [])[:LIMITE_RESULTADOS]:
        if isinstance(item, dict) and str(item.get("url", "")).startswith(("http://", "https://")):
            saida.append({"titulo": " ".join(str(item.get("title") or "").split())[:200], "url": item["url"],
                          "trecho": " ".join(str(item.get("content") or "").split())[:400]})
    return saida


def endereco_publico(url, resolver=None):
    """True só para http(s) cujo nome resolve para endereços públicos (nada de 127.0.0.1, 192.168.x, ::1, .local...)."""
    partes = urllib.parse.urlsplit(str(url or ""))
    if partes.scheme not in ("http", "https") or not partes.hostname:
        return False
    try:
        enderecos = {info[4][0] for info in (resolver or socket.getaddrinfo)(partes.hostname, partes.port or 443)}
    except (OSError, UnicodeError):
        return False
    for e in enderecos:
        ip = ipaddress.ip_address(e.split("%")[0])
        if not ip.is_global or ip.is_multicast:
            return False
    return bool(enderecos)


class _Texto(html.parser.HTMLParser):
    _PULAR = {"script", "style", "noscript", "svg", "template", "head"}
    _BLOCO = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article", "header", "footer"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes, self._pulando = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self._PULAR:
            self._pulando += 1
        elif tag in self._BLOCO:
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if tag in self._PULAR and self._pulando:
            self._pulando -= 1

    def handle_data(self, dados):
        if not self._pulando and dados.strip():
            self.partes.append(" ".join(dados.split()) + " ")


def texto_do_html(conteudo):
    p = _Texto()
    p.feed(conteudo)
    linhas = [" ".join(l.split()) for l in "".join(p.partes).splitlines()]
    return "\n".join(l for l in linhas if l)


class _SemRedirecionarParaDentro(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not endereco_publico(newurl):
            raise ValueError("redirect to a local address blocked")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def ler_pagina(url, abrir=None, resolver=None):
    """O texto de uma página pública (cortado). Levanta ValueError com o motivo."""
    if not endereco_publico(url, resolver):
        raise ValueError("only public http(s) addresses can be read")
    pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept": "text/html, text/plain"})
    abrir = abrir or urllib.request.build_opener(_SemRedirecionarParaDentro).open
    try:
        with abrir(pedido, timeout=TIMEOUT) as r:
            tipo = (r.headers.get("Content-Type") or "").lower()
            if not tipo.startswith(("text/html", "text/plain", "application/xhtml")):
                raise ValueError(f"not a text page ({tipo or 'unknown type'})")
            corpo = r.read(LIMITE_PAGINA_BYTES).decode(r.headers.get_content_charset() or "utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raise ValueError(f"HTTP {e.code}")
    except OSError as e:
        raise ValueError(str(e))
    texto = texto_do_html(corpo) if "html" in tipo else corpo
    return texto[:LIMITE_TEXTO_PAGINA] + ("\n(... cut)" if len(texto) > LIMITE_TEXTO_PAGINA else "")


CONFIG_SEARXNG = """# openTARS: SearXNG só nesta máquina, com o formato JSON ligado (o openTARS lê os resultados por ele)
use_default_settings: true
server:
  secret_key: "{segredo}"
  limiter: false
  image_proxy: false
search:
  formats:
    - html
    - json
"""
