"""Medição (não entra no run_all, usa os modelos de voz de verdade): quanto o Whisper acerta em português e em inglês, e quanto
tempo leva para falar e para ouvir. NÃO rodada em 08/11/2026 (o treino ocupava o computador): é a ferramenta para rodar depois.

Dois jeitos:
  python3 tests/medir_voz.py --sintetizar [pt_BR|en|os dois]     o Kokoro fala frases de pedido e o Whisper as escreve de volta
                                                                  (limite: voz sintética limpa, sem ruído de sala nem sotaque:
                                                                  acerto real, com gente falando, é menor)
  python3 tests/medir_voz.py PASTA [--idioma pt_BR]              PASTA com pares frase.wav (16 kHz, mono, 16 bits) e frase.txt
                                                                  (o que foi dito): gravações de gente de verdade, o que vale
Mostra o acerto por palavra (1 - WER), o tempo de cada transcrição e, no modo --sintetizar, o tempo para sair a primeira fala."""
import os
import re
import sys
import tempfile
import time
import unicodedata
import wave
from pathlib import Path

os.environ.setdefault("TARS_TESTE_OLLAMA_REAL", "1")
from _util import carregar_tars  # noqa: E402

FRASES = {
    "pt_BR": ["abre o navegador e entra no github", "que horas são agora", "cria uma pasta chamada relatórios na minha pasta pessoal",
              "me lembra de ligar para a Ana amanhã às nove horas", "quanto espaço livre tem no disco", "pesquisa a previsão do tempo para sábado",
              "move todos os pdfs da pasta downloads para documentos", "o que eu tenho na agenda amanhã", "cria uma nota comprar pão e leite",
              "aumenta o volume", "resume esse texto em duas frases", "qual é a capital da Austrália"],
    "en": ["open the browser and go to github", "what time is it now", "create a folder called reports in my home folder",
           "remind me to call Anna tomorrow at nine", "how much free space is left on the disk", "search the weather forecast for saturday",
           "move all the pdfs from downloads to documents", "what do I have on my calendar tomorrow", "create a note buy bread and milk",
           "turn the volume up", "summarize this text in two sentences", "what is the capital of Australia"],
}


def palavras(texto):
    sem = "".join(c for c in unicodedata.normalize("NFKD", texto.lower()) if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", sem)


def erro_de_palavras(referencia, ouvido):
    """Distância de edição entre as palavras (WER): erros / palavras da referência."""
    r, o = palavras(referencia), palavras(ouvido)
    anterior = list(range(len(o) + 1))
    for i, pr in enumerate(r, 1):
        atual = [i]
        for j, po in enumerate(o, 1):
            atual.append(min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (pr != po)))
        anterior = atual
    return anterior[-1] / max(1, len(r))


def ler_wav(caminho):
    with wave.open(str(caminho)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16000, 1, 2), f"{caminho}: use 16 kHz, mono, 16 bits"
        return w.readframes(w.getnframes())


def main():
    tars = carregar_tars()
    voz = tars.voz_lib
    argumentos = sys.argv[1:]
    idiomas = ["pt_BR", "en"]
    if "--idioma" in argumentos:
        idiomas = [argumentos[argumentos.index("--idioma") + 1]]
    pares = {i: [] for i in idiomas}           # (referência, áudio)
    primeira_fala = {}
    if "--sintetizar" in argumentos or not [a for a in argumentos if not a.startswith("--") and a not in idiomas]:
        falador = voz.Falador()
        pasta = Path(tempfile.mkdtemp(prefix="opentars-medir-voz-"))
        for idioma in idiomas:
            for k, frase in enumerate(FRASES[idioma]):
                destino = pasta / f"{idioma}-{k}.wav"
                inicio = time.monotonic()
                falador._sintetizar(voz.preparar_para_fala(frase, idioma), idioma, str(destino))
                primeira_fala.setdefault(idioma, []).append(time.monotonic() - inicio)
                if destino.exists():
                    pares[idioma].append((frase, ler_wav(destino)))
    else:
        pasta = Path([a for a in argumentos if not a.startswith("--") and a not in idiomas][0])
        for wav in sorted(pasta.glob("*.wav")):
            txt = wav.with_suffix(".txt")
            if txt.exists():
                pares[idiomas[0]].append((txt.read_text(encoding="utf-8").strip(), ler_wav(wav)))
    transcritor = voz.Transcritor()
    for idioma, itens in pares.items():
        if not itens:
            print(f"{idioma}: nada para medir")
            continue
        voz.configurar(idioma=idioma)
        transcritor.aquecer()
        erros, tempos = [], []
        for referencia, audio in itens:
            inicio = time.monotonic()
            ouvido = transcritor.transcrever(audio, idioma)
            tempos.append(time.monotonic() - inicio)
            erros.append(erro_de_palavras(referencia, ouvido))
            marca = "ok " if erros[-1] == 0 else "ERR"
            print(f"  {marca} [{erros[-1]:.2f}] disse: {referencia!r}  ouviu: {ouvido!r}")
        n = len(itens)
        print(f"{idioma}: acerto por palavra {100 * (1 - sum(erros) / n):.1f}% em {n} frases; frases perfeitas {sum(e == 0 for e in erros)}/{n}; "
              f"transcrição mediana {sorted(tempos)[n // 2]:.2f} s ({transcritor.tamanho})"
              + (f"; sintetizar mediana {sorted(primeira_fala[idioma])[len(primeira_fala[idioma]) // 2]:.2f} s" if idioma in primeira_fala else ""))


if __name__ == "__main__":
    if "--teste-wer" in sys.argv:        # confere só a conta do erro, sem modelo
        assert erro_de_palavras("abre o navegador", "abre o navegador") == 0
        assert abs(erro_de_palavras("abre o navegador", "abre navegador") - 1 / 3) < 1e-9
        assert erro_de_palavras("Que horas são?", "que horas sao") == 0, "acento e pontuação não contam"
        print("OK: a conta do erro por palavra")
    else:
        main()
