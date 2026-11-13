"""11/11: a pesquisa da loja de modelos (filtro local e biblioteca do Ollama), sem rede."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tars_mais_modelos as mm

itens = [i for _, g in mm.GRUPOS for i in g]
assert any(i[0].endswith("Gargantua-Pro:pro") for i in itens)
assert [i[0] for i in mm.filtrar(itens, "gargantua pro")] == ["ProjectOpenTARS/Gargantua-Pro:pro"]
assert all("vision" in i[3] for i in mm.filtrar(itens, "vision"))
assert mm.filtrar(itens, "zzzz") == [] and len(mm.filtrar(itens, "")) == len(itens)

PAGINA = '''<ul><li  class="border-t-[0.5px] border-line first:border-t-0">
<a href="/library/gemma4" class="x"><h2 title="gemma4"><span >gemma4</span></h2><span>4w</span>
<span class="a">vision</span><span class="a">tools</span><span class="a">audio</span><span class="a">cloud</span>
<p class="mt-1 line-clamp-2">Gemma 4 models are designed for agents.</p>
<span>29M</span><span>51 tags</span><span>e2b</span><span>e4b</span><span>12b</span></a></li>
<li  class="border-t-[0.5px] border-line"><a href="/library/tinyllama"><span>tinyllama</span>
<p class="x">A tiny one.</p><span>1.1b</span></a></li></ul>'''
r = mm.buscar_biblioteca("gemma", http=lambda url: PAGINA)
assert [x["nome"] for x in r] == ["gemma4", "tinyllama"], r
assert r[0]["capacidades"] == ("vision", "tools") and r[0]["tamanhos"] == ("e2b", "e4b", "12b"), r[0]
assert r[0]["descricao"].startswith("Gemma 4") and r[1]["tamanhos"] == ("1.1b",)

TAGS = '<a href="/library/gemma4:e2b" class="x"><span>gemma4:e2b</span></a><span>862c9e801351</span> • 4.6GB - 7.5GB • 128K'
assert mm.tamanho_da_tag("gemma4:e2b", http=lambda url: TAGS) == 4.6
assert mm.tamanho_da_tag("gemma4:zzz", http=lambda url: TAGS) is None
print("TUDO OK.")
