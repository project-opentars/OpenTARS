"""openTARS: a lista da página "Mais modelos" (Configurações). Só dados e contas simples, sem Qt, para testar à parte.

Nomes e tamanhos conferidos nas páginas do ollama.com em 21/10/2026 (só entra o que a página mostra com um tamanho único; gemma4 e
qwen3.5 ficaram de fora porque a página dá uma faixa de tamanhos). Só entram o Bonsai 2 oficial (Prism ML), os modelos de
imagem do namespace x/ (experimental, do Ollama) e a biblioteca principal. Versões da comunidade ficam de fora de propósito (origem desconhecida e algumas "sem filtro").
Se um tamanho mudar lá, é aqui que se corrige.
"""

# (id do grupo, ((tag no Ollama, nome mostrado, tamanho do download em GB, o que sabe fazer), ...))
GRUPOS = (
    ("bonsai", (
        ("bonsai-2:2b", "Bonsai 2 · 2B", 0.911, ("vision", "tools", "thinking")),
        ("bonsai-2:4b", "Bonsai 2 · 4B", 1.6, ("vision", "tools", "thinking")),
        ("bonsai-2:9b", "Bonsai 2 · 9B", 3.2, ("vision", "tools", "thinking")),
        ("bonsai-2:27b", "Bonsai 2 · 27B", 8.3, ("vision", "tools", "thinking")),
    )),
    # A biblioteca oficial do Ollama só tem estas duas famílias de imagem (namespace x/, experimental); o que muda
    # entre as linhas é o tamanho e a precisão dos pesos (fp4 é o padrão, fp8 e bf16 pesam mais).
    ("imagem", (
        ("x/flux2-klein:4b", "FLUX.2 klein · 4B", 5.7, ("image",)),
        ("x/flux2-klein:4b-fp8", "FLUX.2 klein · 4B fp8", 9.5, ("image",)),
        ("x/flux2-klein:4b-bf16", "FLUX.2 klein · 4B bf16", 16.0, ("image",)),
        ("x/flux2-klein:9b", "FLUX.2 klein · 9B", 12.0, ("image",)),
        ("x/flux2-klein:9b-fp8", "FLUX.2 klein · 9B fp8", 20.0, ("image",)),
        ("x/flux2-klein:9b-bf16", "FLUX.2 klein · 9B bf16", 35.0, ("image",)),
        ("x/z-image-turbo", "Z-Image Turbo · 6B", 13.0, ("image",)),
        ("x/z-image-turbo:bf16", "Z-Image Turbo · 6B bf16", 33.0, ("image",)),
    )),
    ("geral", (
        ("tinyllama:1.1b", "TinyLlama · 1.1B", 0.638, ("text",)),
        ("qwen2.5:0.5b", "Qwen2.5 · 0.5B", 0.398, ("tools",)),
        ("qwen3:0.6b", "Qwen3 · 0.6B", 0.523, ("tools", "thinking")),
        ("gemma3:1b", "Gemma 3 · 1B", 0.806, ("text",)),
        ("qwen2.5:1.5b", "Qwen2.5 · 1.5B", 0.986, ("tools",)),
        ("deepseek-r1:1.5b", "DeepSeek-R1 · 1.5B", 1.1, ("tools", "thinking")),
        ("qwen3:1.7b", "Qwen3 · 1.7B", 1.4, ("tools", "thinking")),
        ("gemma2:2b", "Gemma 2 · 2B", 1.6, ("text",)),
        ("qwen2.5:3b", "Qwen2.5 · 3B", 1.9, ("tools",)),
        ("llama3.2:3b", "Llama 3.2 · 3B", 2.0, ("tools",)),
        ("phi3:3.8b", "Phi-3 · 3.8B", 2.2, ("text",)),
        ("qwen3:4b", "Qwen3 · 4B", 2.5, ("tools", "thinking")),
        ("mistral:7b", "Mistral · 7B", 4.4, ("tools",)),
        ("qwen2.5:7b", "Qwen2.5 · 7B", 4.7, ("tools",)),
        ("deepseek-r1:7b", "DeepSeek-R1 · 7B", 4.7, ("tools", "thinking")),
        ("llama3.1:8b", "Llama 3.1 · 8B", 4.9, ("tools",)),
        ("qwen3:8b", "Qwen3 · 8B", 5.2, ("tools", "thinking")),
        ("deepseek-r1:8b", "DeepSeek-R1 · 8B", 5.2, ("tools", "thinking")),
        ("gemma2:9b", "Gemma 2 · 9B", 5.4, ("text",)),
        ("mistral-nemo:12b", "Mistral Nemo · 12B", 7.1, ("tools",)),
        ("phi3:14b", "Phi-3 medium · 14B", 7.9, ("text",)),
        ("qwen2.5:14b", "Qwen2.5 · 14B", 9.0, ("tools",)),
        ("deepseek-r1:14b", "DeepSeek-R1 · 14B", 9.0, ("tools", "thinking")),
        ("phi4:14b", "Phi-4 · 14B", 9.1, ("text",)),
        ("qwen3:14b", "Qwen3 · 14B", 9.3, ("tools", "thinking")),
    )),
    ("visao", (
        ("qwen3-vl:2b", "Qwen3-VL · 2B", 1.9, ("vision", "tools", "thinking")),
        ("qwen3-vl:4b", "Qwen3-VL · 4B", 3.3, ("vision", "tools", "thinking")),
        ("gemma3:4b", "Gemma 3 · 4B", 3.4, ("vision",)),
        ("llava:7b", "LLaVA · 7B", 4.7, ("vision",)),
        ("qwen3-vl:8b", "Qwen3-VL · 8B", 6.2, ("vision", "tools", "thinking")),
        ("llava:13b", "LLaVA · 13B", 8.0, ("vision",)),
        ("gemma3:12b", "Gemma 3 · 12B", 8.2, ("vision",)),
    )),
    ("codigo", (
        ("qwen2.5-coder:1.5b", "Qwen2.5-Coder · 1.5B", 0.986, ("tools",)),
        ("qwen2.5-coder:3b", "Qwen2.5-Coder · 3B", 1.9, ("tools",)),
        ("qwen2.5-coder:7b", "Qwen2.5-Coder · 7B", 4.7, ("tools",)),
        ("qwen2.5-coder:14b", "Qwen2.5-Coder · 14B", 9.0, ("tools",)),
        ("qwen2.5-coder:32b", "Qwen2.5-Coder · 32B", 20.0, ("tools",)),
        ("qwen3-coder:30b", "Qwen3-Coder · 30B", 19.0, ("tools",)),
    )),
    # Pedem uma placa de vídeo grande ou muita memória (a RTX 3050 de 6 GB do Enzo não os roda bem).
    ("grandes", (
        ("gpt-oss:20b", "gpt-oss · 20B", 14.0, ("tools", "thinking")),
        ("gemma2:27b", "Gemma 2 · 27B", 16.0, ("text",)),
        ("gemma3:27b", "Gemma 3 · 27B", 17.0, ("vision",)),
        ("qwen3:30b", "Qwen3 · 30B", 19.0, ("tools", "thinking")),
        ("qwen3:32b", "Qwen3 · 32B", 20.0, ("tools", "thinking")),
        ("qwen2.5:32b", "Qwen2.5 · 32B", 20.0, ("tools",)),
        ("deepseek-r1:32b", "DeepSeek-R1 · 32B", 20.0, ("tools", "thinking")),
        ("llava:34b", "LLaVA · 34B", 20.0, ("vision",)),
    )),
)

CAPACIDADES = ("vision", "tools", "thinking", "image", "text")

# Etiquetas que o Ollama mostra com outro nome quando o modelo foi baixado sem a tag (o mesmo arquivo).
_APELIDOS = {
    "bonsai-2:9b": "bonsai-2:latest",
    "gemma3:4b": "gemma3:latest",
    "gemma2:9b": "gemma2:latest",
    "llama3.2:3b": "llama3.2:latest",
    "llama3.1:8b": "llama3.1:latest",
    "qwen3:8b": "qwen3:latest",
    "qwen3-vl:8b": "qwen3-vl:latest",
    "qwen3-coder:30b": "qwen3-coder:latest",
    "qwen2.5:7b": "qwen2.5:latest",
    "qwen2.5-coder:7b": "qwen2.5-coder:latest",
    "deepseek-r1:8b": "deepseek-r1:latest",
    "mistral:7b": "mistral:latest",
    "mistral-nemo:12b": "mistral-nemo:latest",
    "llava:7b": "llava:latest",
    "phi3:3.8b": "phi3:latest",
    "phi4:14b": "phi4:latest",
    "gpt-oss:20b": "gpt-oss:latest",
    "tinyllama:1.1b": "tinyllama:latest",
    "x/flux2-klein:4b": "x/flux2-klein:latest",
    "x/z-image-turbo": "x/z-image-turbo:latest",
}


def todas_as_tags():
    return [item[0] for _, itens in GRUPOS for item in itens]


def _norma(tag):
    tag = tag.strip().lower()
    return tag if ":" in tag else tag + ":latest"


def instalado(tag, instalados):
    """O modelo `tag` já está entre os `instalados` (lista de nomes do /api/tags)?"""
    nomes = {_norma(n) for n in instalados}
    return _norma(tag) in nomes or _norma(_APELIDOS.get(tag, tag)) in nomes


def tamanho_texto(gb):
    return f"{round(gb * 1000)} MB" if gb < 1 else f"{gb:.1f} GB"


def espaco_necessario(gb):
    """O download mais 10% e 1 GB de folga (o Ollama descompacta e guarda camadas por cima)."""
    return gb * 1.1 + 1.0


def cabe(gb, livre_gb):
    """Cabe no disco? Sem saber o espaço livre (None), deixa tentar: o Ollama avisa se faltar."""
    return livre_gb is None or livre_gb >= espaco_necessario(gb)
