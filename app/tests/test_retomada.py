"""18/10: "use the built-in tool" depois de um pedido (captura do Enzo). O Lite abriu o "app" google (= Google Chrome) e disse
que tinha pesquisado. Três travas de código, nenhuma de treino:
  1. a frase que só manda fazer o pedido anterior é reconhecida: a tarefa, o modelo e a IA usam o pedido anterior;
  2. search_web diz ao modelo que ele NÃO leu os resultados (não pode afirmar o que eles dizem);
  3. open_application com nome de site (google, youtube...) abre o site, a não ser que exista um programa com esse nome."""
from _util import carregar_tars

tars = carregar_tars()
n = tars.normalizar

for s in ["use the built-in tool", "use the search engine", "usa a ferramenta", "use o buscador", "faz de verdade",
          "faça isso de verdade", "do it", "actually do it", "try again", "tenta de novo", "de novo", "ok, use your tools",
          "pesquisa de verdade", "search it online", "use the tool please", "mas usa a ferramenta", "do it for real"]:
    assert tars.escolha.eh_retomada(n(s)), s
for s in ["use the search engine to tell me the current president of the usa", "abre a calculadora", "faz uma pasta Fotos",
          "use firefox to open github", "what tool do you use?", "but i need to wash the car", "try the new restaurant", ""]:
    assert not tars.escolha.eh_retomada(n(s)), s
print("OK: reconhece 'use a ferramenta', 'faz de verdade', 'try again'... e não confunde com pedidos de verdade")

conversa = [{"role": "system", "content": "x"},
            {"role": "user", "content": "use the search engine to tell me the current president of the usa"},
            {"role": "user", "content": "[Context from openTARS, not a new request] Open windows right now: 'Brave'."},
            {"role": "assistant", "content": "The current president of the USA is ..."}]
assert tars._ultimo_pedido_real(conversa) == "use the search engine to tell me the current president of the usa"
ctx = tars._contexto_do_pedido("use the built-in tool", None, False, retoma="use the search engine to tell me X")
assert ctx and 'previous request: "use the search engine to tell me X"' in ctx and "only what the tool results confirm" in ctx
assert tars._contexto_do_pedido("oi", None, False) is None
print("OK: a IA recebe o pedido anterior junto com 'use a ferramenta'")

abertos = []
tars._abrir_no_navegador = lambda url: abertos.append(url)
r = tars.pesquisar_web("current president of the usa", "google")
assert r["sucesso"] and "NOT read the results" in r["mensagem"] and "own knowledge" in r["mensagem"], r
print("OK: search_web avisa que os resultados só foram abertos, não lidos")

tars.desktop_entries = lambda: [{"nome": "Google Chrome", "outros_nomes": [], "exec": "google-chrome", "arquivo": "/x/google-chrome.desktop"},
                                {"nome": "Spotify", "outros_nomes": [], "exec": "spotify", "arquivo": "/x/spotify.desktop"}]
real_which = tars.shutil.which
tars.shutil.which = lambda nome: None
r = tars.abrir_aplicativo("google")
assert r["sucesso"] and "is a website, not an installed application" in r["mensagem"] and abertos[-1].startswith("https://"), (r, abertos)
assert "google" in abertos[-1]
assert tars._app_com_nome_exato("spotify") and not tars._app_com_nome_exato("google")
tars.shutil.which = real_which
print("OK: open_application('google') abre o site, não o Google Chrome; um programa com o nome exato continua app")
print("\nTUDO OK.")

# 4) a resposta de memória depois de uma busca não lida ganha o aviso do app (o 2B diz "abri no navegador": sem aviso)
assert not tars._RE_FALA_DO_NAVEGADOR.search(n("The current president of the USA is Joe Biden."))
for frase in ("O resultado da busca foi aberto no navegador.", "The results are open in your browser.",
              "Abri a pesquisa, confira na tela."):
    assert tars._RE_FALA_DO_NAVEGADOR.search(n(frase)), frase
assert tars.t("msg.busca_nao_lida")
print("OK: resposta de memória depois de uma busca não lida é sinalizada pelo app")

# 5) 18/10 (decisão do Enzo): com o SearXNG ligado, "pesquisa X" só consulta o SearXNG e responde; nada abre no PC, a não
# ser que a pessoa peça para abrir, ou que seja um site com busca própria (YouTube). Desligada: abre, como antes.
tars.web_lib.config = lambda: {"ligada": True, "endereco": "http://x"}
tars.web_lib.buscar = lambda q: [{"titulo": "President of the United States", "url": "https://en.wikipedia.org/wiki/P", "trecho": "The current president is X."}]
for pedido, servico in (("pesquisa quem é o presidente dos eua", "google"), ("search latest bonsai model releases using searxng", "searxng"),
                        ("procura isso", None), ("what's the price of bitcoin", "bing")):
    abertos.clear()
    tars._pedido_atual["texto"] = pedido
    r = tars.pesquisar_web("x", servico)
    assert r["sucesso"] and r["leu_resultados"] and not abertos, (pedido, r, abertos)
    assert "Nothing was opened" in r["mensagem"] and "wikipedia.org" in r["mensagem"], r["mensagem"]
for pedido in ("pesquisa o presidente e abre no navegador", "search it and open the results in the browser",
               "mostra no google o preço do dólar", "open google results for bonsai"):
    abertos.clear()
    tars._pedido_atual["texto"] = pedido
    r = tars.pesquisar_web("x", "google")
    assert r["leu_resultados"] and abertos and "also opened" in r["mensagem"], (pedido, r)
abertos.clear()
tars._pedido_atual["texto"] = "procura lofi no youtube"
r = tars.pesquisar_web("lofi", "youtube")
assert abertos and "youtube.com" in abertos[-1] and not r.get("leu_resultados"), "YouTube: abre a página do YouTube"
def _quebrado(q):
    raise ValueError("SearXNG not reachable")
tars.web_lib.buscar = _quebrado
abertos.clear()
tars._pedido_atual["texto"] = "pesquisa o tempo amanhã"
r = tars.pesquisar_web("tempo amanhã", None)
assert not r["sucesso"] and not abertos and "Nothing was opened" in r["mensagem"], "SearXNG fora do ar: avisa, não abre"
tars.web_lib.config = lambda: {"ligada": False, "endereco": "http://x"}
abertos.clear()
r = tars.pesquisar_web("x", None)
assert r["sucesso"] and abertos and "NOT read" in r["mensagem"], "pesquisa desligada: abre no navegador, como antes"
assert not tars.pediu_para_abrir("pesquisa quem ganhou o jogo") and tars.pediu_para_abrir("abre o google com isso")
print("OK: com o SearXNG ligado, pesquisar não abre nada (só se pedir ou no YouTube); desligado, abre como antes")

# 6) 18/10: o Gargantua 2 recém-exportado (fora do catálogo em cache) recebe think=false mesmo assim; sem isso o Qwen3.5 pensava
# e a resposta vinha vazia (a visão do Lite novo parecia errar 40 de 40)
enviados = []
class _R:
    status_code = 200
    def json(self): return {"message": {"content": "ok"}}
tars._SESSION.post = lambda url, json=None, timeout=None: enviados.append(json) or _R()
tars._cache_catalogo["dados"] = {}
tars._chat_unico("Gargantua-2:qualquer-tag-nova", "oi")
tars._chat_unico("qwen3:4b", "oi")
assert enviados[0].get("think") is False and "think" not in enviados[1], enviados
print("OK: modelo Gargantua-2 fora do catálogo em cache também recebe think=false")

# 7) 18/10: lembrete de idioma só para pedido em inglês; nota quando a resposta diz que abriu algo e nada abriu
for f in ("what is the capital of sweden", "search latest bonsai model releases using searxng", "open the calculator", "tell me a joke",
          "who painted the mona lisa", "yeah search latest bonsai model releases using searxng"):
    assert tars.escolha.pedido_em_ingles(n(f)), f
for f in ("qual a capital da suécia", "pesquisa quem ganhou a copa", "abre a calculadora", "open", "oi", "calculadora", "google",
          "abre o spotify", "como faço arroz"):
    assert not tars.escolha.pedido_em_ingles(n(f)), f
assert "answer in English" in tars._contexto_do_pedido("what is the capital of sweden", None, False)
assert tars._contexto_do_pedido("qual a capital da suécia", None, False) is None
for frase in ("O resultado da busca foi aberto no navegador.", "I opened the results in your browser.", "Encontrado no Google: ...",
              "Abri a pesquisa na tela.", "The search results are open in the browser."):
    assert tars._RE_DIZ_QUE_ABRIU.search(n(frase)), frase
for frase in ("O presidente é X, segundo a Wikipedia.", "Bitcoin is at $81 thousand according to TradingView.", "A capital é Estocolmo."):
    assert not tars._RE_DIZ_QUE_ABRIU.search(n(frase)), frase
assert tars.t("msg.busca_nada_aberto")
print("OK: lembrete de idioma só para inglês; nota quando a resposta diz que abriu o navegador e nada abriu")
