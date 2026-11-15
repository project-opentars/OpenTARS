"""openTARS: a lista da página "Mais modelos" (Configurações). Só dados e contas simples, sem Qt, para testar à parte.

14/11/2026 (decisão do Enzo): a loja é o Hugging Face e tudo roda no motor llama.cpp; o Ollama saiu. Duas fontes:
- a lista curada abaixo (os Gargantua e GGUF de quem publica modelos conhecidos: unsloth, ggml-org, bartowski, Qwen, Mistral),
  com o arquivo e o SHA-256 fixos;
- a pesquisa livre (buscar_hf + resolver_hf), marcada na tela como "comunidade": o SHA-256 vem da API do Hugging Face.
Os modelos de imagem (FLUX, Z-Image) saíram junto com o Ollama: o llama.cpp não gera imagem. As fotos continuam (tars_imagem).
"""

# (id do grupo, ((nome no app, nome mostrado, tamanho do download em GB, o que sabe fazer), ...))
GRUPOS = (
    # 25/10 (decisão do Enzo): os modelos do openTARS no topo, o Lite primeiro e destacado (é o que fica em segundo plano)
    ("opentars", (
        ("ProjectOpenTARS/Gargantua-2.5:lite", "Gargantua Lite Gen 3", 4.4, ("vision", "tools")),
        ("ProjectOpenTARS/Gargantua-2.5:latest", "Gargantua 2.5", 6.3, ("vision", "tools")),
        ("ProjectOpenTARS/Gargantua-Pro:pro", "Gargantua Pro Gen 1", 7.6, ("vision", "tools")),
        ("ProjectOpenTARS/Gargantua-Code-Gen2:code", "Gargantua Code Gen 2", 4.7, ("tools",)),
    )),
    ("geral", (
        ('hf.co/unsloth/Qwen3.5-0.8B-GGUF:Q4_K_M', 'Qwen3.5 · 0.8B', 0.74, ('vision', 'tools', 'thinking')),
        ('hf.co/ggml-org/SmolLM3-3B-GGUF:Q4_K_M', 'SmolLM3 · 3B', 1.92, ('tools', 'thinking')),
        ('hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M', 'Qwen3.5 · 2B', 1.95, ('vision', 'tools', 'thinking')),
        ('hf.co/bartowski/Llama-3.2-3B-Instruct-GGUF:Q4_K_M', 'Llama 3.2 · 3B', 2.02, ('tools',)),
        ('hf.co/unsloth/Phi-4-mini-instruct-GGUF:Q4_K_M', 'Phi-4 mini · 3.8B', 2.49, ('tools',)),
        ('hf.co/mistralai/Ministral-3-3B-Instruct-2512-GGUF:Q4_K_M', 'Ministral 3 · 3B', 2.99, ('vision', 'tools')),
        ('hf.co/unsloth/Qwen3.5-4B-GGUF:Q4_K_M', 'Qwen3.5 · 4B', 3.42, ('vision', 'tools', 'thinking')),
        ('hf.co/unsloth/gemma-4-E2B-it-GGUF:Q4_K_M', 'Gemma 4 · E2B', 4.09, ('vision', 'tools', 'thinking')),
        ('hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_M', 'DeepSeek-R1 0528 · 8B', 5.03, ('tools',)),
        ('hf.co/unsloth/gemma-4-E4B-it-GGUF:Q4_K_M', 'Gemma 4 · E4B', 5.97, ('vision', 'tools', 'thinking')),
        ('hf.co/mistralai/Ministral-3-8B-Instruct-2512-GGUF:Q4_K_M', 'Ministral 3 · 8B', 6.06, ('vision', 'tools')),
        ('hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M', 'Qwen3.5 · 9B', 6.6, ('vision', 'tools', 'thinking')),
        ('hf.co/unsloth/gemma-4-12b-it-GGUF:Q4_K_M', 'Gemma 4 · 12B', 7.3, ('vision', 'tools', 'thinking')),
        ('hf.co/mistralai/Ministral-3-14B-Instruct-2512-GGUF:Q4_K_M', 'Ministral 3 · 14B', 9.12, ('vision', 'tools')),
        ('hf.co/ggml-org/gpt-oss-20b-GGUF:MXFP4', 'gpt-oss · 20B', 12.11, ('tools', 'thinking')),
        ('hf.co/unsloth/gemma-4-26B-A4B-it-GGUF:Q4_K_M', 'Gemma 4 · 26B A4B', 18.14, ('vision', 'tools', 'thinking')),
    )),
    ("visao", (
        ('hf.co/Qwen/Qwen3-VL-4B-Instruct-GGUF:Q4_K_M', 'Qwen3-VL · 4B', 3.33, ('vision', 'tools')),
        ('hf.co/ggml-org/gemma-3-4b-it-GGUF:Q4_K_M', 'Gemma 3 · 4B', 3.34, ('vision',)),
        ('hf.co/Qwen/Qwen3-VL-8B-Instruct-GGUF:Q4_K_M', 'Qwen3-VL · 8B', 6.19, ('vision', 'tools')),
    )),
    ("codigo", (
        ('hf.co/bartowski/Qwen2.5-Coder-7B-Instruct-GGUF:Q4_K_M', 'Qwen2.5-Coder · 7B', 4.68, ('tools',)),
        ('hf.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q4_K_M', 'Qwen3-Coder · 30B A3B', 18.56, ('tools', 'thinking')),
    )),
)

CAPACIDADES = ("vision", "tools", "thinking", "image", "text")
DESTAQUE = "ProjectOpenTARS/Gargantua-2.5:lite"

# A ficha de cada modelo curado para o motor (arquivo, SHA-256 e tamanho conferidos na API do Hugging Face em 14/11/2026).
# O SHA-256 é fixo: se o repositório trocar o arquivo, o download falha na conferência em vez de instalar outra coisa.
FICHAS = {
 "hf.co/unsloth/Qwen3.5-0.8B-GGUF:Q4_K_M": {
  "repo": "unsloth/Qwen3.5-0.8B-GGUF",
  "gguf": [
   "Qwen3.5-0.8B-Q4_K_M.gguf",
   "bd258782e35f7f458f8aced1adc053e6e92e89bc735ba3be89d38a06121dc517",
   532517120
  ],
  "mmproj": [
   "mmproj-BF16.gguf",
   "d312c4d02fd46eea7a16e4f3bbb58840e6222209322ca1e33ca03247ad8935d6",
   207346528
  ],
  "capabilities": [
   "completion",
   "tools",
   "thinking",
   "vision"
  ],
  "family": "qwen35",
  "quantization_level": "Q4_K_M"
 },
 "hf.co/unsloth/Qwen3.5-2B-GGUF:Q4_K_M": {
  "repo": "unsloth/Qwen3.5-2B-GGUF",
  "gguf": [
   "Qwen3.5-2B-Q4_K_M.gguf",
   "aaf42c8b7c3cab2bf3d69c355048d4a0ee9973d48f16c731c0520ee914699223",
   1280835840
  ],
  "mmproj": [
   "mmproj-BF16.gguf",
   "f17196c0d8fc756bc65be60075bd4a359917eee8a438505639511727c585d3c2",
   671372992
  ],
  "capabilities": [
   "completion",
   "tools",
   "thinking",
   "vision"
  ],
  "family": "qwen35",
  "quantization_level": "Q4_K_M"
 },
 "hf.co/unsloth/Qwen3.5-4B-GGUF:Q4_K_M": {
  "repo": "unsloth/Qwen3.5-4B-GGUF",
  "gguf": [
   "Qwen3.5-4B-Q4_K_M.gguf",
   "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4",
   2740937888
  ],
  "mmproj": [
   "mmproj-BF16.gguf",
   "302b92d565080b9cc0281186979ae75a7429ec23d14f6f7607a035539b21f3a6",
   675569344
  ],
  "capabilities": [
   "completion",
   "tools",
   "thinking",
   "vision"
  ],
  "family": "qwen35",
  "quantization_level": "Q4_K_M"
 },
 "hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M": {
  "repo": "unsloth/Qwen3.5-9B-GGUF",
  "gguf": [
   "Qwen3.5-9B-Q4_K_M.gguf",
   "03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8",
   5680522464
  ],
  "mmproj": [
   "mmproj-BF16.gguf",
   "853698ce7aa6c7ba732478bad280240969ddf7b0fcbf93900046f63903a83383",
   921705024
  ],
  "capabilities": [
   "completion",
   "tools",
   "thinking",
   "vision"
  ],
  "family": "qwen35",
  "quantization_level": "Q4_K_M"
 },
 "hf.co/unsloth/gemma-4-E2B-it-GGUF:Q4_K_M": {
  "repo": "unsloth/gemma-4-E2B-it-GGUF",
  "gguf": [
   "gemma-4-E2B-it-Q4_K_M.gguf",
   "740185b21d22ceb83a11c3aa62ad5842ef32c70f6096d756bbee85a1e4ec34b8",
   3106738272
  ],
  "mmproj": [
   "mmproj-BF16.gguf",
   "a402f10fb5780bf91d03a10cd89061139f522bee2e679b1291bbfdcd71d9547d",
   986833728
  ],
  "capabilities": [
   "completion",
   "tools",
   "thinking",
   "vision"
  ],
  "family": "gemma4",
  "quantization_level": "Q4_K_M"
 },
 "hf.co/unsloth/gemma-4-E4B-it-GGUF:Q4_K_M": {
  "repo": "unsloth/gemma-4-E4B-it-GGUF",
  "gguf": [
   "gemma-4-E4B-it-Q4_K_M.gguf",
   "85a896a047553e842f25297ee5b031d64ff30147d9c4af17b1e4b394cd1fab87",
   4977171584
  ],
  "mmproj": [
   "mmproj-BF16.gguf",
   "ee01cba03fd9c71ea2ea722225d24a84f72e7197714367e550ef705ef8851bc6",
   991552320
  ],
  "capabilities": [
   "completion",
   "tools",
   "thinking",
   "vision"
  ],
  "family": "gemma4",
  "quantization_level": "Q4_K_M"
 },
 "hf.co/unsloth/gemma-4-12b-it-GGUF:Q4_K_M": {
  "repo": "unsloth/gemma-4-12b-it-GGUF",
  "gguf": [
   "gemma-4-12b-it-Q4_K_M.gguf",
   "0a270ec9fe6b34f4a0d33992b6135117b484ebc4766ab76b51d4ae8c457e4c42",
   7121861440
  ],
  "mmproj": [
   "mmproj-BF16.gguf",
   "2e269f906eb15169ee9ce880ea649bd6d42d4964c21f8ede10d0d0efc738bcbb",
   175115840
  ],
  "capabilities": [
   "completion",
   "tools",
   "thinking",
   "vision"
  ],
  "family": "gemma4",
  "quantization_level": "Q4_K_M"
 },
 "hf.co/unsloth/gemma-4-26B-A4B-it-GGUF:Q4_K_M": {
  "repo": "unsloth/gemma-4-26B-A4B-it-GGUF",
  "gguf": [
   "gemma-4-26B-A4B-it-UD-Q4_K_M.gguf",
   "f2c28b3dc4776931ac6f879e11f203dec637ea0f14267a86ec8f6165f63f293f",
   16947541728
  ],
  "mmproj": [
   "mmproj-BF16.gguf",
   "41926ed5f1403cf5add23b0684992805ea6f97253096132e769e65646b8cef9d",
   1194828256
  ],
  "capabilities": [
   "completion",
   "tools",
   "thinking",
   "vision"
  ],
  "family": "gemma4",
  "quantization_level": "Q4_K_M"
 },
 "hf.co/bartowski/Llama-3.2-3B-Instruct-GGUF:Q4_K_M": {
  "repo": "bartowski/Llama-3.2-3B-Instruct-GGUF",
  "gguf": [
   "Llama-3.2-3B-Instruct-Q4_K_M.gguf",
   "6c1a2b41161032677be168d354123594c0e6e67d2b9227c84f296ad037c728ff",
   2019377696
  ],
  "mmproj": None,
  "capabilities": [
   "completion",
   "tools"
  ],
  "family": "llama",
  "quantization_level": "Q4_K_M"
 },
 "hf.co/mistralai/Ministral-3-3B-Instruct-2512-GGUF:Q4_K_M": {
  "repo": "mistralai/Ministral-3-3B-Instruct-2512-GGUF",
  "gguf": [
   "Ministral-3-3B-Instruct-2512-Q4_K_M.gguf",
   "9ed150d4367e68df0ac8e1540f6ddc65b42d0ee26378329d1ecbca60f93fc5f8",
   2147023008
  ],
  "mmproj": [
   "Ministral-3-3B-Instruct-2512-BF16-mmproj.gguf",
   "70ca26e41ecea9da997e2887462ad68b848fbf64da011ff4107bbe7353519ee0",
   841501856
  ],
  "capabilities": [
   "completion",
   "tools",
   "vision"
  ],
  "family": "mistral3",
  "quantization_level": "Q4_K_M"
 },
 "hf.co/mistralai/Ministral-3-8B-Instruct-2512-GGUF:Q4_K_M": {
  "repo": "mistralai/Ministral-3-8B-Instruct-2512-GGUF",
  "gguf": [
   "Ministral-3-8B-Instruct-2512-Q4_K_M.gguf",
   "33e7a72cf5e6e2cfc2f2847075acc013d68bba023e35310cef86b5cf8fdca761",
   5198911904
  ],
  "mmproj": [
   "Ministral-3-8B-Instruct-2512-BF16-mmproj.gguf",
   "e799380f596d152ff4026a72d409ecc89c96cd437676804bc3f2ab3bd6b486ec",
   858283168
  ],
  "capabilities": [
   "completion",
   "tools",
   "vision"
  ],
  "family": "mistral3",
  "quantization_level": "Q4_K_M"
 },
 "hf.co/mistralai/Ministral-3-14B-Instruct-2512-GGUF:Q4_K_M": {
  "repo": "mistralai/Ministral-3-14B-Instruct-2512-GGUF",
  "gguf": [
   "Ministral-3-14B-Instruct-2512-Q4_K_M.gguf",
   "824e0f3373e69b84f2cae46fdcb9bd1ebc6ab3bfc7acc125d818b7b8178cc613",
   8239593024
  ],
  "mmproj": [
   "Ministral-3-14B-Instruct-2512-BF16-mmproj.gguf",
   "ab7616148b7081030fd38e410c9213ce8346a8b0588291c8ca279058e78cfae7",
   879258784
  ],
  "capabilities": [
   "completion",
   "tools",
   "vision"
  ],
  "family": "mistral3",
  "quantization_level": "Q4_K_M"
 },
 "hf.co/unsloth/Phi-4-mini-instruct-GGUF:Q4_K_M": {
  "repo": "unsloth/Phi-4-mini-instruct-GGUF",
  "gguf": [
   "Phi-4-mini-instruct-Q4_K_M.gguf",
   "88c00229914083cd112853aab84ed51b87bdf6b9ce42f532d8c85c7c63b1730a",
   2491874272
  ],
  "mmproj": None,
  "capabilities": [
   "completion",
   "tools"
  ],
  "family": "phi3",
  "quantization_level": "Q4_K_M"
 },
 "hf.co/ggml-org/SmolLM3-3B-GGUF:Q4_K_M": {
  "repo": "ggml-org/SmolLM3-3B-GGUF",
  "gguf": [
   "SmolLM3-Q4_K_M.gguf",
   "8334b850b7bd46238c16b0c550df2138f0889bf433809008cc17a8b05761863e",
   1915305312
  ],
  "mmproj": None,
  "capabilities": [
   "completion",
   "tools",
   "thinking"
  ],
  "family": "smollm3",
  "quantization_level": "Q4_K_M"
 },
 "hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_M": {
  "repo": "unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF",
  "gguf": [
   "DeepSeek-R1-0528-Qwen3-8B-Q4_K_M.gguf",
   "a86349a4180c4e6bb43f874c29c404fa2be3f90b15509bd6d86f697dba724ec1",
   5027785216
  ],
  "mmproj": None,
  "capabilities": [
   "completion",
   "tools"
  ],
  "family": "qwen3",
  "quantization_level": "Q4_K_M"
 },
 "hf.co/ggml-org/gpt-oss-20b-GGUF:MXFP4": {
  "repo": "ggml-org/gpt-oss-20b-GGUF",
  "gguf": [
   "gpt-oss-20b-MXFP4.gguf",
   "27cd6c432c7672cb812a92f611cf3ba7bbc35928262bb1e1253ff4ee6ae35901",
   12109566624
  ],
  "mmproj": None,
  "capabilities": [
   "completion",
   "tools",
   "thinking"
  ],
  "family": "gpt-oss",
  "quantization_level": "MXFP4"
 },
 "hf.co/ggml-org/gemma-3-4b-it-GGUF:Q4_K_M": {
  "repo": "ggml-org/gemma-3-4b-it-GGUF",
  "gguf": [
   "gemma-3-4b-it-Q4_K_M.gguf",
   "882e8d2db44dc554fb0ea5077cb7e4bc49e7342a1f0da57901c0802ea21a0863",
   2489757856
  ],
  "mmproj": [
   "mmproj-model-f16.gguf",
   "8c0fb064b019a6972856aaae2c7e4792858af3ca4561be2dbf649123ba6c40cb",
   851251104
  ],
  "capabilities": [
   "completion",
   "vision"
  ],
  "family": "gemma3",
  "quantization_level": "Q4_K_M"
 },
 "hf.co/Qwen/Qwen3-VL-4B-Instruct-GGUF:Q4_K_M": {
  "repo": "Qwen/Qwen3-VL-4B-Instruct-GGUF",
  "gguf": [
   "Qwen3VL-4B-Instruct-Q4_K_M.gguf",
   "66358cb18bb6b3b1b6675aa412c7a88ef01d228f481184d13668e5201c730a0a",
   2497281664
  ],
  "mmproj": [
   "mmproj-Qwen3VL-4B-Instruct-F16.gguf",
   "256f3a43bd4205ffef48d6b92715e1e70b5b0e9aef06522584967513a9985331",
   836180256
  ],
  "capabilities": [
   "completion",
   "tools",
   "vision"
  ],
  "family": "qwen3vl",
  "quantization_level": "Q4_K_M"
 },
 "hf.co/Qwen/Qwen3-VL-8B-Instruct-GGUF:Q4_K_M": {
  "repo": "Qwen/Qwen3-VL-8B-Instruct-GGUF",
  "gguf": [
   "Qwen3VL-8B-Instruct-Q4_K_M.gguf",
   "67d1659bfe71b89d50b45a4ad1a9e5b997e5bb16ce5da66a6a6167abd569e9e2",
   5027784800
  ],
  "mmproj": [
   "mmproj-Qwen3VL-8B-Instruct-F16.gguf",
   "ca524100ebf825c9a870db1c580d03879e0da0ab2541697e2458e64891cf9d38",
   1159029824
  ],
  "capabilities": [
   "completion",
   "tools",
   "vision"
  ],
  "family": "qwen3vl",
  "quantization_level": "Q4_K_M"
 },
 "hf.co/bartowski/Qwen2.5-Coder-7B-Instruct-GGUF:Q4_K_M": {
  "repo": "bartowski/Qwen2.5-Coder-7B-Instruct-GGUF",
  "gguf": [
   "Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf",
   "1664fccab734674a50763490a8c6931b70e3f2f8ec10031b54806d30e5f956b6",
   4683074336
  ],
  "mmproj": None,
  "capabilities": [
   "completion",
   "tools"
  ],
  "family": "qwen2",
  "quantization_level": "Q4_K_M"
 },
 "hf.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q4_K_M": {
  "repo": "unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF",
  "gguf": [
   "Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf",
   "fadc3e5f8d42bf7e894a785b05082e47daee4df26680389817e2093056f088ad",
   18556689568
  ],
  "mmproj": None,
  "capabilities": [
   "completion",
   "tools",
   "thinking"
  ],
  "family": "qwen3moe",
  "quantization_level": "Q4_K_M"
 }
}


def _norma(tag):
    tag = tag.strip().lower()
    return tag if ":" in tag else tag + ":latest"


def instalado(tag, instalados):
    """O modelo `tag` já está entre os `instalados` (lista de nomes do /api/tags)?"""
    return _norma(tag) in {_norma(n) for n in instalados}


def tamanho_texto(gb):
    if not gb:
        return "?"                        # resultado da pesquisa na biblioteca: o tamanho só se sabe ao clicar
    return f"{round(gb * 1000)} MB" if gb < 1 else f"{gb:.1f} GB"


def espaco_necessario(gb):
    """O download mais 10% e 1 GB de folga."""
    return gb * 1.1 + 1.0


def cabe(gb, livre_gb):
    """Cabe no disco? Sem saber o espaço livre (None), deixa tentar: o download avisa se faltar."""
    return livre_gb is None or livre_gb >= espaco_necessario(gb)


# 26/10 (pedido do Enzo): os modelos que combinam com o computador
GRUPOS_RECOMENDADOS = ("geral", "visao", "codigo")      # um recomendado por grupo


def hardware(vram_gb=None, ram_gb=None):
    """{'vram_gb': placa dedicada (0 se não há), 'ram_gb': memória}. Sem argumentos, lê o computador."""
    if vram_gb is None:
        try:
            import tars_primeiro_uso as pu
            vram_gb = pu._vram_mb() / 1024
        except Exception:  # noqa: BLE001
            vram_gb = 0.0
    if ram_gb is None:
        try:
            import psutil
            ram_gb = psutil.virtual_memory().total / 2 ** 30
        except Exception:  # noqa: BLE001
            ram_gb = 8.0
    return {"vram_gb": vram_gb if vram_gb >= 2.0 else 0.0, "ram_gb": ram_gb}      # menos de 2 GB é vídeo integrado


def avaliar(gb, hw):
    """'otimo' (cabe na placa com folga, ou é pequeno o bastante para o processador), 'ok' (roda, mais devagar) ou 'pesado'.
    O tamanho do download aproxima a memória usada (já vem quantizado)."""
    if hw["vram_gb"]:
        if gb <= hw["vram_gb"] * 0.8:
            return "otimo"
    elif gb <= min(hw["ram_gb"] * 0.3, 5.0):
        return "otimo"
    return "ok" if gb <= hw["ram_gb"] * 0.5 else "pesado"


def recomendados(hw):
    """Em cada grupo, o maior modelo 'otimo', preferindo os que usam ferramentas e, no empate, os sem raciocínio longo."""
    achados = []
    for grupo, itens in GRUPOS:
        cabem = [i for i in itens if grupo in GRUPOS_RECOMENDADOS and avaliar(i[2], hw) == "otimo"]
        if cabem:
            achados.append(max(cabem, key=lambda i: ("tools" in i[3], i[2], "thinking" not in i[3]))[0])
    return achados


# ---------------------------------------------------------------- 11/11: pesquisa na loja

def filtrar(itens, consulta):
    """Os itens (tag, nome, gb, capacidades) em que todas as palavras da consulta aparecem no nome, na tag ou nas capacidades."""
    palavras = str(consulta or "").lower().split()
    return [i for i in itens if all(p in " ".join((i[0].split("/")[-1], i[1], *i[3])).lower() for p in palavras)]   # sem o dono: "pro" não casa com ProjectOpenTARS


def _http(url, tempo=10):
    import urllib.request
    pedido = urllib.request.Request(url, headers={"User-Agent": "openTARS"})
    with urllib.request.urlopen(pedido, timeout=tempo) as r:
        return r.read(4_000_000).decode("utf-8", "replace")


# ---------------------------------------------------------------- 14/11: a loja é o Hugging Face (o Ollama saiu)
# Busca pela API pública (sem conta, só GET). Um repositório vira um modelo instalável escolhendo o GGUF Q4_K_M (ou o mais
# próximo) e, se houver, o projetor de visão (mmproj). O SHA-256 vem do próprio Hugging Face (campo lfs.oid da árvore) e o
# motor confere o arquivo baixado contra ele.
_HF_API = "https://huggingface.co/api/models"
QUANTS = ("Q4_K_M", "Q4_K_S", "IQ4_XS", "Q4_0", "MXFP4", "Q5_K_M", "Q4_1", "Q5_K_S", "Q6_K", "Q8_0", "BF16", "F16")


def _quant_do(arquivo):
    import re
    m = re.search(r"(?i)(IQ\d_[A-Z]+|Q\d_K_[SML]|Q\d_K|Q\d_\d|MXFP4|BF16|F16|F32)", arquivo)
    return m.group(1).upper() if m else ""


def escolher_arquivos(arvore):
    """Da árvore de um repositório GGUF: ((arquivo, sha256, tamanho) do modelo, idem do mmproj ou None), ou None se não há GGUF
    de um arquivo só (modelos divididos em partes ficam de fora)."""
    ggufs = [a for a in arvore if isinstance(a, dict) and a.get("type") == "file" and str(a.get("path", "")).endswith(".gguf")
             and "/" not in a["path"] and isinstance(a.get("lfs"), dict) and len(str(a["lfs"].get("oid", ""))) == 64]
    projetores = [a for a in ggufs if "mmproj" in a["path"].lower()]
    modelos = [a for a in ggufs if a not in projetores and "-of-0" not in a["path"]]
    if not modelos:
        return None

    def posicao(a):
        q = _quant_do(a["path"])
        return (QUANTS.index(q) if q in QUANTS else len(QUANTS), int(a["lfs"].get("size") or a.get("size") or 0))
    modelo = min(modelos, key=posicao)
    projetor = min(projetores, key=lambda a: next((i for i, q in enumerate(("F16", "BF16", "Q8_0", "F32")) if q in a["path"].upper()), 9)) if projetores else None
    trio = lambda a: (a["path"], str(a["lfs"]["oid"]).lower(), int(a["lfs"].get("size") or a.get("size") or 0))
    return trio(modelo), (trio(projetor) if projetor else None)


def capacidades_do_modelo(info, projetor):
    """('vision'?, 'tools'?, 'thinking'?) pelo modelo de conversa (chat template) que o próprio GGUF traz."""
    modelo = str(((info or {}).get("gguf") or {}).get("chat_template") or "")
    caps = []
    if projetor:
        caps.append("vision")
    if "tools" in modelo or "tool_call" in modelo:
        caps.append("tools")
    if "<think>" in modelo or "enable_thinking" in modelo or "reasoning" in modelo:
        caps.append("thinking")
    return tuple(caps)


def resolver_hf(repo, http=_http):
    """O que instalar de um repositório do HF: (nome no app, ficha para o motor, GB, capacidades). Levanta ValueError se o
    repositório não tem um GGUF de um arquivo só. Falha de rede levanta a exceção do `http`."""
    import json
    import re
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", str(repo)):
        raise ValueError(f"invalid repository: {repo}")
    escolha = escolher_arquivos(json.loads(http(f"{_HF_API}/{repo}/tree/main")))
    if not escolha:
        raise ValueError(f"no single-file GGUF in {repo}")
    modelo, projetor = escolha
    try:
        info = json.loads(http(f"{_HF_API}/{repo}?expand[]=gguf"))
    except Exception:  # noqa: BLE001  (sem a ficha do GGUF, só não sabemos as capacidades)
        info = {}
    caps = capacidades_do_modelo(info, projetor)
    quant = _quant_do(modelo[0]) or "GGUF"
    ficha = {"repo": repo, "gguf": list(modelo), "mmproj": list(projetor) if projetor else None,
             "capabilities": ["completion"] + [c for c in caps if c != "vision"] + (["vision"] if projetor else []),
             "family": str(((info.get("gguf") or {}).get("architecture")) or "gguf"), "quantization_level": quant}
    gb = round((modelo[2] + (projetor[2] if projetor else 0)) / 1e9, 2)
    return f"hf.co/{repo}:{quant}", ficha, gb, caps


def buscar_hf(consulta, http=_http, limite=20):
    """Procura repositórios GGUF no Hugging Face, os mais baixados primeiro: [{repo, downloads, likes}]."""
    import json
    from urllib.parse import quote
    dados = json.loads(http(f"{_HF_API}?search={quote(str(consulta).strip())}&filter=gguf&sort=downloads&direction=-1&limit={int(limite)}"))
    return [{"repo": m["id"], "downloads": int(m.get("downloads") or 0), "likes": int(m.get("likes") or 0)}
            for m in dados if isinstance(m, dict) and "/" in str(m.get("id", ""))]
