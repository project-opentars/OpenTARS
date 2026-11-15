"""A pesquisa da loja de modelos (filtro local; desde 14/11 a busca e a escolha do arquivo no Hugging Face), sem rede."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tars_mais_modelos as mm

itens = [i for _, g in mm.GRUPOS for i in g]
assert any(i[0].endswith("Gargantua-Pro:pro") for i in itens)
assert [i[0] for i in mm.filtrar(itens, "gargantua pro")] == ["ProjectOpenTARS/Gargantua-Pro:pro"]
assert all("vision" in i[3] for i in mm.filtrar(itens, "vision"))
assert mm.filtrar(itens, "zzzz") == [] and len(mm.filtrar(itens, "")) == len(itens)

import json  # noqa: E402
BUSCA = [{"id": "unsloth/gemma-4-E2B-it-GGUF", "downloads": 9, "likes": 1}, {"id": "semdono"}]
r = mm.buscar_hf("gemma 4", http=lambda url: json.dumps(BUSCA) if "filter=gguf" in url and "search=gemma%204" in url else "[]")
assert r == [{"repo": "unsloth/gemma-4-E2B-it-GGUF", "downloads": 9, "likes": 1}], r

lfs = lambda n, t, h="a": {"type": "file", "path": n, "size": t, "lfs": {"oid": h * 64, "size": t}}  # noqa: E731
ARVORE = [lfs("g-Q8_0.gguf", 8), lfs("g-Q4_K_M.gguf", 4, "b"), lfs("mmproj-F16.gguf", 1, "c"), {"type": "file", "path": "README.md"}]
INFO = {"gguf": {"chat_template": "{% if tools %}{{ tools }}{% endif %}", "architecture": "gemma4"}}
http = lambda url: json.dumps(ARVORE if url.endswith("/tree/main") else INFO)  # noqa: E731
nome, ficha, gb, caps = mm.resolver_hf("unsloth/gemma-4-E2B-it-GGUF", http=http)
assert nome == "hf.co/unsloth/gemma-4-E2B-it-GGUF:Q4_K_M" and ficha["gguf"] == ["g-Q4_K_M.gguf", "b" * 64, 4]
assert ficha["mmproj"] == ["mmproj-F16.gguf", "c" * 64, 1] and caps == ("vision", "tools") and ficha["family"] == "gemma4"
for ruim in ("a/b/c", "../x", "sem-barra"):
    try:
        mm.resolver_hf(ruim, http=http)
        raise AssertionError(ruim)
    except ValueError:
        pass
print("TUDO OK.")
