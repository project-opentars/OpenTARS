"""5.3 (F4+++): e-mail no assistente, DESLIGADO por padrão: só vale depois de a pessoa pôr a conta em Configurações > Assistente.

- A senha vai para o cofre do sistema (Secret Service no Linux, Gerenciador de Credenciais no Windows, Chaveiro no macOS) pelo pacote
  `keyring`, e NUNCA para o config.json nem para o log. Sem o `keyring`, o e-mail fica desligado (não guarda senha em texto).
- Ler é só leitura: a caixa é aberta em modo somente leitura e os cabeçalhos vêm com PEEK, então nada vira "lido". "Meus e-mails de hoje"
  lista quem escreveu e o assunto; "ler o último e-mail de X" mostra o começo do texto. O texto do e-mail é dado: nunca vira ordem.
- Enviar SEMPRE pergunta antes, com o destinatário, o assunto e o texto na tela; um destinatário por vez; sem lista nem cópia.
- Gmail e Outlook pessoal exigem senha de app (ou já não aceitam senha); contas com login por navegador (OAuth) não funcionam aqui.
Nada disso foi usado com um servidor de verdade (os testes usam servidores falsos).
"""
import datetime as dt
import email
import email.header
import email.message
import email.utils
import imaplib
import re
import smtplib
import ssl
import unicodedata

import tars_i18n

SERVICO = "openTARS-email"
LIMITE_LISTA = 12
LIMITE_TEXTO = 1200
LIMITE_BAIXAR = 200_000          # bytes do começo da mensagem (anexos grandes não vêm inteiros)
TEMPO_REDE = 15
MESES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]       # o IMAP só entende estes
SERVIDORES = {    # domínio -> (imap, smtp)
    "gmail.com": ("imap.gmail.com", "smtp.gmail.com"), "googlemail.com": ("imap.gmail.com", "smtp.gmail.com"),
    "outlook.com": ("outlook.office365.com", "smtp-mail.outlook.com"), "hotmail.com": ("outlook.office365.com", "smtp-mail.outlook.com"),
    "live.com": ("outlook.office365.com", "smtp-mail.outlook.com"), "icloud.com": ("imap.mail.me.com", "smtp.mail.me.com"),
    "me.com": ("imap.mail.me.com", "smtp.mail.me.com"), "yahoo.com": ("imap.mail.yahoo.com", "smtp.mail.yahoo.com"),
    "yahoo.com.br": ("imap.mail.yahoo.com", "smtp.mail.yahoo.com"), "uol.com.br": ("imap.uol.com.br", "smtps.uol.com.br"),
    "proton.me": ("127.0.0.1", "127.0.0.1"),        # o Proton só fala IMAP pelo programa Bridge, que a pessoa instala e ajusta
}

TEXTOS = {
    "pt": {"desligado": "O e-mail está desligado. Ligue em Configurações > Assistente.", "sem_senha": "Não achei a senha da conta no cofre do sistema. Digite de novo em Configurações > Assistente.",
           "erro": "Não consegui falar com o servidor de e-mail ({erro}).", "nada_hoje": "Nenhum e-mail novo hoje.", "hoje": "Hoje chegaram {n} e-mails:",
           "hoje_um": "Hoje chegou 1 e-mail:", "mais": "… e mais {n}.", "nao_achei": "Não achei e-mail de {quem}.", "de": "De {de}, {data}\nAssunto: {assunto}\n\n{texto}",
           "sem_texto": "(sem texto)", "pedir": "Mandar este e-mail?\nPara: {para}\nAssunto: {assunto}\n\n{texto}", "negado": "Tudo bem, não enviei.",
           "enviado": "E-mail enviado para {para}.", "sem_corpo": "Diga o que escrever: envia um e-mail para ana@exemplo.com dizendo que chego às 9h.",
           "so_um": "Mando um e-mail por vez, para um destinatário.", "sem_assunto": "(sem assunto)"},
    "en": {"desligado": "Email is off. Turn it on in Settings > Assistant.", "sem_senha": "I couldn't find the account password in the system keychain. Type it again in Settings > Assistant.",
           "erro": "I couldn't reach the mail server ({erro}).", "nada_hoje": "No new email today.", "hoje": "{n} emails came in today:",
           "hoje_um": "1 email came in today:", "mais": "… and {n} more.", "nao_achei": "I found no email from {quem}.", "de": "From {de}, {data}\nSubject: {assunto}\n\n{texto}",
           "sem_texto": "(no text)", "pedir": "Send this email?\nTo: {para}\nSubject: {assunto}\n\n{texto}", "negado": "Okay, I didn't send it.",
           "enviado": "Email sent to {para}.", "sem_corpo": "Tell me what to write: send an email to ana@example.com saying I arrive at 9.",
           "so_um": "I send one email at a time, to one recipient.", "sem_assunto": "(no subject)"},
}


def _t(chave, idioma, **kw):
    s = TEXTOS["pt" if idioma == "pt" else "en"][chave]
    return s.format(**kw) if kw else s


def normalizar(texto):
    return unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()


# ---------------------------------------------------------------- conta e senha
class SemCofre(RuntimeError):
    """O pacote keyring não está instalado ou o sistema não tem cofre de senhas."""


def _cofre():
    try:
        import keyring
        from keyring.backends import fail
    except ImportError as e:
        raise SemCofre("keyring não instalado") from e
    if isinstance(keyring.get_keyring(), fail.Keyring):
        raise SemCofre("este sistema não tem cofre de senhas")
    return keyring


def guardar_senha(usuario, senha):
    _cofre().set_password(SERVICO, usuario, senha)


def ler_senha(usuario):
    try:
        return _cofre().get_password(SERVICO, usuario)
    except SemCofre:
        return None


def apagar_senha(usuario):
    try:
        _cofre().delete_password(SERVICO, usuario)
    except Exception:  # noqa: BLE001  (já não existia)
        pass


def conta():
    """{usuario, imap, imap_porta, smtp, smtp_porta} escolhida pela pessoa, ou None (desligado, o padrão)."""
    c = tars_i18n.ler_config().get("email")
    return c if isinstance(c, dict) and c.get("usuario") and c.get("imap") and c.get("smtp") else None


def servidores_do_dominio(endereco):
    """(imap, smtp) provável para o endereço, ou ('', '') se não conheço o provedor."""
    return SERVIDORES.get(endereco.rsplit("@", 1)[-1].lower(), ("", ""))


def salvar_conta(usuario, senha, imap="", smtp="", imap_porta=993, smtp_porta=465):
    """Guarda a conta no config e a senha no cofre. Levanta SemCofre se não há cofre (aí nada é guardado). Vazio desliga."""
    if not usuario:
        antiga = conta()
        tars_i18n.salvar_config(email={})
        if antiga:
            apagar_senha(antiga["usuario"])
        return
    padrao_imap, padrao_smtp = servidores_do_dominio(usuario)
    if senha:
        guardar_senha(usuario, senha)         # primeiro o cofre: se falhar, a conta não fica pela metade
    tars_i18n.salvar_config(email={"usuario": usuario, "imap": imap or padrao_imap, "smtp": smtp or padrao_smtp,
                                   "imap_porta": int(imap_porta), "smtp_porta": int(smtp_porta)})


# ---------------------------------------------------------------- IMAP: ler
def _decodificar(valor):
    try:
        return str(email.header.make_header(email.header.decode_header(valor or ""))).strip()
    except Exception:  # noqa: BLE001  (cabeçalho torto: o texto cru serve)
        return str(valor or "").strip()


def _abrir_imap(c, senha):
    if not senha:
        raise SemCofre("sem senha")
    # sem ssl_context o imaplib usa ssl._create_stdlib_context(), que não confere o certificado (revisão de 13/11)
    caixa = imaplib.IMAP4_SSL(c["imap"], int(c.get("imap_porta") or 993), timeout=TEMPO_REDE, ssl_context=ssl.create_default_context())
    caixa.login(c["usuario"], senha)
    caixa.select("INBOX", readonly=True)             # só leitura: nada vira "lido", nada é apagado
    return caixa


def _cabecalhos(caixa, numeros):
    saida = []
    for n in numeros:
        tipo, dados = caixa.fetch(n, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
        if tipo != "OK" or not dados or not isinstance(dados[0], tuple):
            continue
        msg = email.message_from_bytes(dados[0][1])
        nome, endereco = email.utils.parseaddr(_decodificar(msg.get("From")))
        saida.append({"de": nome or endereco, "endereco": endereco, "assunto": _decodificar(msg.get("Subject")), "data": msg.get("Date", "")})
    return saida


def de_hoje(agora=None, c=None, senha=None):
    """Os e-mails que chegaram hoje (do mais novo para o mais velho), só cabeçalhos."""
    c, agora = c or conta(), agora or dt.datetime.now()
    caixa = _abrir_imap(c, senha or ler_senha(c["usuario"]))
    try:
        desde = f"{agora.day:02d}-{MESES[agora.month - 1]}-{agora.year}"
        tipo, dados = caixa.search(None, "SINCE", desde)
        numeros = (dados[0].split() if tipo == "OK" and dados and dados[0] else [])[::-1]
        return {"total": len(numeros), "itens": _cabecalhos(caixa, numeros[:LIMITE_LISTA])}
    finally:
        try:
            caixa.logout()
        except Exception:  # noqa: BLE001
            pass


def _texto_da_mensagem(msg):
    for parte in msg.walk() if msg.is_multipart() else [msg]:
        if parte.get_content_type() == "text/plain" and not parte.get_filename():
            carga = parte.get_payload(decode=True) or b""
            return carga.decode(parte.get_content_charset() or "utf-8", "replace").strip()
    for parte in msg.walk() if msg.is_multipart() else [msg]:
        if parte.get_content_type() == "text/html":
            carga = (parte.get_payload(decode=True) or b"").decode(parte.get_content_charset() or "utf-8", "replace")
            return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", carga))).strip()
    return ""


def ultimo_de(quem, c=None, senha=None):
    """O e-mail mais recente de alguém (nome ou endereço): {de, data, assunto, texto} ou None."""
    c = c or conta()
    quem = re.sub(r'["\\\r\n]', "", quem).strip()
    if not quem:
        return None
    caixa = _abrir_imap(c, senha or ler_senha(c["usuario"]))
    try:
        tipo, dados = caixa.search(None, "FROM", f'"{quem}"')
        numeros = dados[0].split() if tipo == "OK" and dados and dados[0] else []
        if not numeros:
            return None
        tipo, dados = caixa.fetch(numeros[-1], f"(BODY.PEEK[]<0.{LIMITE_BAIXAR}>)")
        if tipo != "OK" or not dados or not isinstance(dados[0], tuple):
            return None
        msg = email.message_from_bytes(dados[0][1])
        nome, endereco = email.utils.parseaddr(_decodificar(msg.get("From")))
        return {"de": nome or endereco, "data": msg.get("Date", ""), "assunto": _decodificar(msg.get("Subject")),
                "texto": _texto_da_mensagem(msg)[:LIMITE_TEXTO]}
    finally:
        try:
            caixa.logout()
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------- SMTP: enviar
EMAIL_VALIDO = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")


def enviar(para, assunto, texto, c=None, senha=None):
    """Manda UM e-mail. Quem chama já pediu a aprovação da pessoa."""
    c = c or conta()
    if not EMAIL_VALIDO.match(para):
        raise ValueError("destinatário inválido")
    if not (senha or ler_senha(c["usuario"])):
        raise SemCofre("sem senha")
    msg = email.message.EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = c["usuario"], para, assunto
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg.set_content(texto)
    porta, contexto = int(c.get("smtp_porta") or 465), ssl.create_default_context()
    senha = senha or ler_senha(c["usuario"])
    if porta == 465:
        with smtplib.SMTP_SSL(c["smtp"], porta, timeout=TEMPO_REDE, context=contexto) as s:
            s.login(c["usuario"], senha)
            s.send_message(msg)
    else:
        with smtplib.SMTP(c["smtp"], porta, timeout=TEMPO_REDE) as s:
            s.starttls(context=contexto)
            s.login(c["usuario"], senha)
            s.send_message(msg)


def testar(c=None, senha=None):
    """Entra na caixa e sai (só leitura). Devolve None se deu certo, ou o motivo."""
    c = c or conta()
    try:
        caixa = _abrir_imap(c, senha or ler_senha(c["usuario"]))
        caixa.logout()
        return None
    except (imaplib.IMAP4.error, OSError, ssl.SSLError) as e:
        return str(e)[:100] or type(e).__name__


# ---------------------------------------------------------------- frases
_NOVOS = re.compile(r"\b(meus|my|novos?|new|chegou|chegaram|tenho|do i have|check|ver|mostra|mostre|show|quais|que|what|resume|resumo|summar\w+)\b.*"
                    r"\be-?mails?\b.*\b(hoje|today)\b|\b(tenho|do i have|any)\b.*\b(novos?|new)\b.*\be-?mails?\b|\b(novos?|new) e-?mails?\b")
_LER = re.compile(r"\b(ler|le|leia|abre|abra|mostra|mostre|read|show|open)\b.*\b(ultimo|ultima|last|latest|most recent)\b.*\be-?mail\b.*"
                  r"\b(de|da|do|from)\s+(?P<quem>.+)$")
_ENVIAR = re.compile(r"^\s*(?:por favor,?\s+|please,?\s+)?(?:envia|envie|enviar|manda|mande|mandar|escreve|escreva|send|write|email)\b.*?\be-?mails?\b.*?"
                     r"\b(?:para|pra|to)\s+(?P<para>[^\s,;<>]+@[^\s,;<>]+?)[.,;]?(?P<resto>\s.*)?$", re.IGNORECASE | re.DOTALL)
_CORPO = re.compile(r"\b(?:dizendo|falando|avisando|com o texto|com a mensagem|saying|telling (?:him|her|them)|with the message|that says)\b[:\s]*(?P<c>.+)$", re.IGNORECASE | re.DOTALL)
_ASSUNTO = re.compile(r"\b(?:assunto|subject)\b[:\s]+(?P<a>.+?)(?=\s+(?:dizendo|falando|avisando|com o texto|com a mensagem|saying|with the message|that says)\b|$)", re.IGNORECASE | re.DOTALL)


def _data_curta(texto):
    try:
        return email.utils.parsedate_to_datetime(texto).astimezone().strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return texto[:16]


def responder(pedido, idioma, core=None):
    """Lista os e-mails de hoje, lê o último de alguém ou manda um e-mail (com aprovação). None se a frase não é de e-mail.
    Desligado (sem conta) também devolve None: o pedido segue para o modelo, como antes."""
    n = normalizar(pedido).replace("e-mail", "email")
    c = conta()
    if c is None:
        return None
    m_env = _ENVIAR.match(pedido)
    if m_env:
        return _enviar_por_frase(m_env, idioma, core, c)
    try:
        m = _LER.search(n)
        if m:
            quem = pedido[len(pedido) - len(m.group("quem")):].strip(" ?.!")           # com as maiúsculas e acentos de quem escreveu
            achado = ultimo_de(quem, c)
            if not achado:
                return _t("nao_achei", idioma, quem=quem)
            return _t("de", idioma, de=achado["de"], data=_data_curta(achado["data"]), assunto=achado["assunto"] or _t("sem_assunto", idioma),
                      texto=achado["texto"] or _t("sem_texto", idioma))
        if _NOVOS.search(n):
            hoje = de_hoje(c=c)
            if not hoje["itens"]:
                return _t("nada_hoje", idioma)
            linhas = [_t("hoje_um" if hoje["total"] == 1 else "hoje", idioma, n=hoje["total"])]
            linhas += [f"• {i['de']}: {i['assunto'] or _t('sem_assunto', idioma)}" for i in hoje["itens"]]
            if hoje["total"] > len(hoje["itens"]):
                linhas.append(_t("mais", idioma, n=hoje["total"] - len(hoje["itens"])))
            return "\n".join(linhas)
    except SemCofre:
        return _t("sem_senha", idioma)
    except (imaplib.IMAP4.error, OSError, ssl.SSLError, smtplib.SMTPException) as e:
        return _t("erro", idioma, erro=str(e)[:80] or type(e).__name__)
    return None


def _enviar_por_frase(m, idioma, core, c):
    resto = m.group("resto") or ""
    corpo = _CORPO.search(resto)
    if "@" in (resto[:corpo.start()] if corpo else ""):          # "para a@x.com e b@y.com dizendo...": um destinatário por vez
        return _t("so_um", idioma)
    texto = re.sub(r"^(?:que|that)\s+", "", (corpo.group("c") if corpo else resto.strip(" :,-")).strip(), flags=re.IGNORECASE)
    if not texto:
        return _t("sem_corpo", idioma)
    texto = texto[:1].upper() + texto[1:]
    assunto = _ASSUNTO.search(resto)
    assunto = (assunto.group("a").strip(" .,:") if assunto else "") or _t("sem_assunto", idioma)
    para = m.group("para").strip("<>")
    if not EMAIL_VALIDO.match(para):
        return _t("sem_corpo", idioma)
    # nunca sai sem a pessoa ver e dizer sim: sem janela para perguntar, ou com as perguntas desligadas (TARS_SEM_CONFIRMACAO_PERIGOSOS), não envia
    if core is None or not getattr(core, "_CONFIRMAR_COMANDOS_PERIGOSOS", False) \
            or not core._confirmar_comando_perigoso(_t("pedir", idioma, para=para, assunto=assunto, texto=texto[:500])):
        return _t("negado", idioma)
    try:
        enviar(para, assunto, texto, c)
    except SemCofre:
        return _t("sem_senha", idioma)
    except (imaplib.IMAP4.error, OSError, ssl.SSLError, smtplib.SMTPException, ValueError) as e:
        return _t("erro", idioma, erro=str(e)[:80] or type(e).__name__)
    return _t("enviado", idioma, para=para)
