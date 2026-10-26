"""Modelos recomendados conforme o hardware (26/10)."""
import _util  # noqa: F401
import tars_mais_modelos as mm

assert mm.recomendados({"vram_gb": 6, "ram_gb": 31}) == ["qwen2.5:7b", "qwen3-vl:4b", "qwen2.5-coder:7b"]
assert mm.recomendados({"vram_gb": 0, "ram_gb": 8}) == ["llama3.2:3b", "qwen3-vl:2b", "qwen2.5-coder:3b"]
assert mm.avaliar(8.3, {"vram_gb": 6, "ram_gb": 31}) == "ok" and mm.avaliar(20, {"vram_gb": 0, "ram_gb": 8}) == "pesado"
assert mm.hardware(1.0, 4)["vram_gb"] == 0.0            # vídeo integrado não conta como placa
print("ok")
