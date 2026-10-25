"""5.2: pesquisar dentro de outros sites (Spotify, Amazon, Wikipedia...) e a identidade do Gargantua pelo contexto do pedido
(o prompt e as 19 ferramentas do treino não mudam)."""
from _util import carregar_tars

t = carregar_tars()
abertos = []
t._abrir_no_navegador = abertos.append
n = t.normalizar
assert t._sites_citados_na_busca(n("pesquisa lofi no Spotify")) == ["spotify"]
assert t._sites_citados_na_busca(n("search for a mouse on amazon")) == ["amazon"]
assert t._sites_citados_na_busca(n("pesquisa gatos no google")) == [] and t._sites_citados_na_busca(n("abra o spotify")) == []
for pergunta in ("Quem criou você?", "quem é você?", "who made you", "Qual é o seu nome?", "quem é o fundador do openTARS"):
    assert t._PERGUNTA_DE_IDENTIDADE.search(n(pergunta)), pergunta
assert not t._PERGUNTA_DE_IDENTIDADE.search(n("abra o chrome"))
ctx = t._contexto_do_pedido("quem criou você?", "conversa", False)
assert "Gargantua" in ctx and "Enzo" in ctx and "founder of openTARS" in ctx, ctx
ctx = t._contexto_do_pedido("pesquisa lofi no spotify", "busca", False)
assert 'service="spotify"' in ctx, ctx
for consulta, servico, esperado in (("lofi", "spotify", "https://open.spotify.com/search/lofi"),
                                    ("fisica", "wiki", "https://wikipedia.org/w/index.php?search=fisica"),
                                    ("pizza", "tripadvisor", "https://www.google.com/search?q=pizza+tripadvisor")):
    r = t.pesquisar_web(consulta, servico)
    assert r["url"] == esperado and abertos[-1] == esperado, (r["url"], esperado)
assert t._resolver_busca("pesquisar lofi no spotify")
print("test_busca_outros_sites_e_identidade: TUDO OK.")
