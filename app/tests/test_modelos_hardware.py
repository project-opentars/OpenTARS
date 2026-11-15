"""Modelos recomendados conforme o hardware (26/10)."""
import _util  # noqa: F401
import tars_mais_modelos as mm

# 14/11: a loja é o Hugging Face
assert mm.recomendados({"vram_gb": 6, "ram_gb": 31}) == ["hf.co/unsloth/gemma-4-E2B-it-GGUF:Q4_K_M", "hf.co/Qwen/Qwen3-VL-4B-Instruct-GGUF:Q4_K_M",
                                                       "hf.co/bartowski/Qwen2.5-Coder-7B-Instruct-GGUF:Q4_K_M"]
assert mm.recomendados({"vram_gb": 0, "ram_gb": 8}) == ["hf.co/bartowski/Llama-3.2-3B-Instruct-GGUF:Q4_K_M"]
assert mm.avaliar(8.3, {"vram_gb": 6, "ram_gb": 31}) == "ok" and mm.avaliar(20, {"vram_gb": 0, "ram_gb": 8}) == "pesado"
assert mm.hardware(1.0, 4)["vram_gb"] == 0.0            # vídeo integrado não conta como placa
print("ok")
