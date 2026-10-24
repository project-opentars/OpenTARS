"""5.2 (F4, contexto do programa em uso): uma sugestão pelo programa ativo, como no mock-up aprovado em 20/10 ("Você está
escrevendo um e-mail. Quer que eu revise a ortografia?"). Só o nome do programa e o título da janela, lidos na hora e
nunca gravados nem enviados; desligado por padrão (Configurações > Assistente). O histórico da tela estilo Recall fica fora,
por privacidade. Sem Qt."""
import unicodedata

import tars_i18n

# (sugestão, o programa ou o site no título, o que no título diz que é a janela de escrever)
REGRAS = (
    ("email", ("thunderbird", "outlook", "geary", "evolution", "mailspring", "mail", "correio", "gmail", "proton"),
     ("escrever", "nova mensagem", "new message", "compose", "write", "responder", "reply", "rascunho", "draft", "re:",
      "fwd:", "encaminhar", "forward")),
)


def _normal(texto):
    return unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()


def programa(classe):
    """O nome do programa na classe da janela ("Thunderbird thunderbird", "Mail", "Notepad notepad")."""
    partes = str(classe or "").split()
    return (partes[-1] if partes else "").lower()


def sugestao(titulo, classe):
    """A sugestão para esta janela ("email") ou None."""
    titulo_n, classe_n = _normal(titulo), _normal(classe)
    for nome, programas, janelas in REGRAS:
        if any(p in classe_n or p in titulo_n for p in programas) and any(j in titulo_n for j in janelas):
            return nome
    return None


def ligado():
    return bool(tars_i18n.ler_config().get("sugestoes_programa"))


def ligar(valor):
    tars_i18n.salvar_config(sugestoes_programa=bool(valor))


def silenciado(nome_programa):
    return nome_programa in (tars_i18n.ler_config().get("sugestoes_silenciadas") or [])


def silenciar(nome_programa):
    lista = list(tars_i18n.ler_config().get("sugestoes_silenciadas") or [])
    if nome_programa and nome_programa not in lista:
        tars_i18n.salvar_config(sugestoes_silenciadas=lista + [nome_programa])
