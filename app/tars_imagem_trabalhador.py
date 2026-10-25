"""Roda com o Python do venv do Bonsai Image (não com o do openTARS): carrega o modelo uma vez e gera uma imagem por linha
JSON recebida na entrada ({"prompt", "lado", "semente", "saida"}), respondendo uma linha JSON ({"ok", "erro"}). Usa as
funções do próprio scripts/generate.py deles para achar as pastas do modelo. Sem rede, sem porta aberta."""
import json
import os
import secrets
import sys
from pathlib import Path

# as bibliotecas imprimem na saída padrão (até pelo C): a resposta vai por uma cópia dela, e o resto vai para o stderr
_RESPOSTAS = os.fdopen(os.dup(1), "w")
os.dup2(2, 1)
sys.stdout = sys.stderr
DEMO = Path(sys.argv[1])
sys.path.insert(0, str(DEMO / "scripts"))
import generate as g  # noqa: E402  (o script deles; ajusta os caches do Triton ao ser importado)


def carregar():
    modelo = g.default_model()
    if sys.platform == "darwin":
        from backend.pipeline import FluxPipeline, PipelineConfig
        return FluxPipeline(PipelineConfig(backend=g.MODELS[modelo][0], baked_model_path=str(g.require_model_dir(modelo)),
                                           te_4bit=True, evict_text_encoder=True))
    from backend_gpu.pipeline_gpu import GpuPipeline
    raiz = g.require_model_dir(modelo)
    texto = g._find_subdir(raiz, "text_encoder")
    pipe = GpuPipeline(backend=g.MODELS[modelo][0],
                       ternary_transformer_path=str(g._resolve_gemlite_transformer_dir("ternary")),
                       binary_transformer_path=str(g._resolve_gemlite_transformer_dir("binary")),
                       text_encoder_path=str(texto), vae_path=str(g._find_subdir(raiz, "vae")),
                       tokenizer_path=str(texto / "tokenizer"))
    pipe.prewarm()
    _vae_so_para_decodificar(pipe)
    return pipe


def _vae_so_para_decodificar(pipe):
    """Placa de 6 GB com o desktop usando ~700 MB (25/10): faltavam ~25 MB para codificar o texto. O VAE só é usado no fim
    (decodificar); fica no processador até lá e volta para a placa só no decode. shortcut: mexe num atributo interno deles
    (`_vae`); se a versão mudar e ele sumir, segue sem isto."""
    import torch
    vae = getattr(pipe, "_vae", None)
    if vae is None or not torch.cuda.is_available():
        return
    vae.to("cpu")
    torch.cuda.empty_cache()
    decodificar = vae.decode

    def decode(latentes, *a, **k):
        vae.to("cuda")
        try:
            return decodificar(latentes.to("cuda"), *a, **k)
        finally:
            vae.to("cpu")
            torch.cuda.empty_cache()
    vae.decode = decode


pipeline = None
for linha in sys.stdin:
    try:
        pedido = json.loads(linha)
        pipeline = pipeline or carregar()
        png = pipeline.generate_png(prompt=pedido["prompt"], seed=pedido.get("semente") or secrets.randbits(31), steps=4,
                                    height=int(pedido["lado"]), width=int(pedido["lado"]))
        Path(pedido["saida"]).write_bytes(png)
        resposta = {"ok": True}
    except Exception as e:  # noqa: BLE001  (falta de memória na placa, modelo faltando: volta como texto)
        resposta = {"ok": False, "erro": f"{type(e).__name__}: {e}"[:300]}
    _RESPOSTAS.write(json.dumps(resposta) + "\n")
    _RESPOSTAS.flush()
