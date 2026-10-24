"""5.2 (F4): ações em arquivos selecionados. Nomes sugeridos pelo modelo (de mentira aqui) viram nomes limpos e únicos;
renomear e mover nunca sobrescrevem; desfazer volta os nomes; o arquivo sem texto não ganha nome inventado; o Linux lê
os arquivos copiados no gerenciador (text/uri-list)."""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tars_acoes_arquivos as aa  # noqa: E402

pasta = Path(tempfile.mkdtemp(prefix="opentars-arquivos-"))
(pasta / "scan0001.txt").write_text("NOTA FISCAL Mercado Bom Preço 03/10/2026 total R$ 52,10")
(pasta / "scan0002.txt").write_text("NOTA FISCAL Farmácia Saúde 03/10/2026 total R$ 18,90")
(pasta / "scan0003.pdf").write_bytes(b"%PDF-1.4 sem texto")                  # PDF que é só imagem
(pasta / "nota-fiscal-farmacia-03-10-2026.txt").write_text("já existe")

assert aa.nome_limpo('"Nota fiscal — Mercado, 03/10/2026.pdf"') == "nota-fiscal-mercado-03-10-2026"
assert aa.nome_limpo("") == "" and len(aa.nome_limpo("a " * 80)) <= aa.MAXIMO_NOME

pedidos = []


def modelo_falso(acao, texto, modelo, host, pergunta=None, **_k):
    pedidos.append((acao, pergunta))
    return "Nota fiscal Mercado 03/10/2026" if "Mercado" in texto else "nota fiscal farmácia 03-10-2026.txt"


arquivos = [str(pasta / n) for n in ("scan0001.txt", "scan0002.txt", "scan0003.pdf")]
sugestoes = aa.sugerir_nomes(arquivos, "m", "h", rodar=modelo_falso)
novos = [n for _c, n in sugestoes]
assert novos == ["nota-fiscal-mercado-03-10-2026.txt", "nota-fiscal-farmacia-03-10-2026-2.txt", None], novos
assert all(a == "perguntar" and p for a, p in pedidos) and len(pedidos) == 2
print("OK: nomes limpos, sem repetir o que já existe na pasta; o PDF sem texto não ganha nome inventado")

feitos = aa.renomear(sugestoes + [(str(pasta / "scan0001.txt"), "../fora.txt")])
assert len(feitos) == 2 and (pasta / "nota-fiscal-mercado-03-10-2026.txt").exists() and not (pasta.parent / "fora.txt").exists()
assert (pasta / "nota-fiscal-farmacia-03-10-2026.txt").read_text() == "já existe"
aa.desfazer(feitos)
assert (pasta / "scan0001.txt").exists() and (pasta / "scan0002.txt").exists()
print("OK: renomear fica na mesma pasta, não sobrescreve, e desfazer volta os nomes")

destino = Path(tempfile.mkdtemp(prefix="opentars-destino-"))
(destino / "scan0002.txt").write_text("outro")
movidos, pulados = aa.mover(arquivos[:2], destino)
assert [Path(n).name for _a, n in movidos] == ["scan0001.txt"] and pulados == [arquivos[1]]
assert (destino / "scan0002.txt").read_text() == "outro"
print("OK: mover não sobrescreve um arquivo de mesmo nome no destino")

assert aa.resumir(str(pasta / "scan0003.pdf"), "m", "h", rodar=modelo_falso) == ""

# Linux: os arquivos copiados no gerenciador (text/uri-list), só os que existem
from tars_plataforma import linux  # noqa: E402
original_run, original_which = linux.subprocess.run, linux.shutil.which
uri = (destino / "scan0001.txt").as_uri()
linux.shutil.which = lambda nome: "/usr/bin/" + nome
linux.subprocess.run = lambda cmd, **k: subprocess.CompletedProcess(cmd, 0, stdout=f"{uri}\nfile:///nao/existe.txt\n", stderr="")
try:
    assert linux.arquivos_selecionados() == [str(destino / "scan0001.txt")]
finally:
    linux.subprocess.run, linux.shutil.which = original_run, original_which
print("OK: Linux: os arquivos copiados no gerenciador, só os que existem")
print("test_acoes_arquivos: TUDO OK.")
