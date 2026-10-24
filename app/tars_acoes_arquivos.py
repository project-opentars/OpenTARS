"""5.2 (F4, ações em arquivos): o que o painel faz com os arquivos selecionados no gerenciador de arquivos. Resumir e
sugerir nomes usam o contrato das ações de texto (tars_acoes_texto: o texto do arquivo é dado, nunca instrução); renomear,
mover e mandar para a lixeira são código, sempre depois de a pessoa ver a prévia e confirmar. Nada sobrescreve um arquivo
que já existe. Sem Qt."""
import re
import shutil
import unicodedata
from pathlib import Path

import tars_acoes_texto as acoes
import tars_busca_arquivos as busca
import tars_plataforma as plataforma

PERGUNTA_NOME = {
    "pt_BR": "Que nome curto de arquivo descreve este documento? Use de 2 a 6 palavras e inclua a data se o texto tiver uma. "
             "Responda só com o nome, sem extensão.",
    "en": "What short file name describes this document? Use 2 to 6 words and include the date if the text has one. "
          "Answer with only the name, without extension.",
}
MAXIMO_NOME = 60


def ler(caminho):
    """O texto de dentro do arquivo (o mesmo leitor da busca: txt, md, csv, docx, odt, pdf com texto)."""
    return busca.texto_do_arquivo(Path(caminho), limite=acoes.LIMITE_TEXTO)


def nome_limpo(resposta):
    """'Nota fiscal — Mercado, 03/10/2026.pdf' -> 'nota-fiscal-mercado-03-10-2026': sem acento, minúsculo, com hífens."""
    texto = acoes.limpar(str(resposta or "").splitlines()[0] if str(resposta or "").strip() else "")
    texto = re.sub(r"\.[a-z0-9]{2,4}$", "", texto.strip(), flags=re.I)
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    palavras, nome = re.sub(r"[^a-z0-9]+", "-", texto).strip("-").split("-"), ""
    for p in palavras:                     # corta numa palavra inteira, nunca no meio ("...-rua-d")
        if len(nome) + len(p) + 1 > MAXIMO_NOME:
            break
        nome = f"{nome}-{p}" if nome else p
    return nome or palavras[0][:MAXIMO_NOME]


def sugerir_nomes(arquivos, modelo, host, rodar=None, idioma="pt_BR"):
    """[(caminho, novo_nome_com_extensao | None)]: None quando o arquivo não tem texto legível (PDF que é imagem, por
    exemplo). Os nomes não se repetem nem batem com um arquivo que já existe na pasta."""
    rodar = rodar or acoes.rodar
    saida, usados = [], set()
    for caminho in map(Path, arquivos):
        texto = ler(caminho)
        if not texto.strip():
            saida.append((str(caminho), None))
            continue
        pergunta = PERGUNTA_NOME[idioma if idioma in PERGUNTA_NOME else "en"]
        base = nome_limpo(rodar("perguntar", texto, modelo, host, pergunta=pergunta)) or caminho.stem
        novo, n = base + caminho.suffix.lower(), 2
        while novo in usados or (caminho.with_name(novo).exists() and caminho.with_name(novo) != caminho):
            novo, n = f"{base}-{n}{caminho.suffix.lower()}", n + 1
        usados.add(novo)
        saida.append((str(caminho), novo))
    return saida


def renomear(pares):
    """Aplica [(caminho, novo_nome)] na mesma pasta; pula o que viraria por cima de outro arquivo. Devolve os feitos
    [(antigo, novo)], para desfazer."""
    feitos = []
    for caminho, novo in pares:
        origem = Path(caminho)
        if not novo or not origem.exists():
            continue
        destino = origem.with_name(Path(novo).name)          # só o nome: nunca para outra pasta
        if destino == origem or destino.exists():
            continue
        origem.rename(destino)
        feitos.append((str(origem), str(destino)))
    return feitos


def desfazer(feitos):
    for antigo, novo in reversed(feitos):
        if Path(novo).exists() and not Path(antigo).exists():
            Path(novo).rename(antigo)


def mover(arquivos, pasta):
    """Move para a pasta escolhida, sem sobrescrever. Devolve (movidos [(antigo, novo)], pulados [caminho])."""
    pasta = Path(pasta)
    movidos, pulados = [], []
    for caminho in map(Path, arquivos):
        destino = pasta / caminho.name
        if not caminho.exists() or destino.exists():
            pulados.append(str(caminho))
            continue
        shutil.move(str(caminho), str(destino))
        movidos.append((str(caminho), str(destino)))
    return movidos, pulados


def para_lixeira(arquivos):
    """Lixeira, nunca apagar de vez (dá para recuperar). Devolve (enviados, erros)."""
    enviados, erros = [], []
    for caminho in arquivos:
        try:
            plataforma.lixeira(caminho)
            enviados.append(caminho)
        except OSError as e:
            erros.append(f"{Path(caminho).name}: {e}")
    return enviados, erros


def resumir(caminho, modelo, host, rodar=None, ao_pedaco=None):
    """O resumo do texto do arquivo, ou "" se não houver texto legível."""
    texto = ler(caminho)
    return (rodar or acoes.rodar)("resumir", texto, modelo, host, ao_pedaco=ao_pedaco) if texto.strip() else ""
