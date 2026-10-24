"""openTARS 5.0: rotinas agendadas (módulo puro, sem Qt).

Uma rotina é um pedido que o TARS roda sozinho num horário. Regras (plano da 5.0):
  * Pré-aprovação ao criar: a pessoa escolhe quais AÇÕES ARRISCADAS a rotina pode fazer sem perguntar
    (apagar, enviar, instalar). Fora disso, a rotina PARA e avisa. Padrão: nenhuma.
  * Rotina criada pela IA nasce desligada e sem aprovação: só a pessoa liga, na janela.
  * Computador desligado (ou o openTARS fechado) na hora: a rotina é PULADA e a pessoa é avisada.
  * Só roda com o openTARS aberto.

Arquivo: ~/.config/opentars/agenda.json (0600). O arquivo `rotinas.json` das versões antigas não é lido nem apagado.
"""

import datetime as dt
import json
import os
import re
import tempfile
import threading
import time
import unicodedata
import uuid
from pathlib import Path

import tars_plataforma as plataforma

TIPOS = ("diaria", "semanal", "intervalo", "uma_vez")
PERMISSOES = ("apagar", "enviar", "instalar")      # as ações arriscadas que se pode pré-aprovar
LIMITE_ROTINAS = 20
LIMITE_PEDIDO = 500
LIMITE_NOME = 60
INTERVALO_MINIMO = 5          # minutos
TOLERANCIA = dt.timedelta(minutes=10)   # passou disso do horário: foi pulada
DIAS = ("seg", "ter", "qua", "qui", "sex", "sab", "dom")


def arquivo_agenda():
    env = os.environ.get("TARS_ARQUIVO_AGENDA")
    if env:
        return Path(env)
    return plataforma.pastas()["config"] / "agenda.json"


def _sem_acento(texto):
    texto = unicodedata.normalize("NFKD", str(texto or "").lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


# ------------------------------------------------------------
# Quando
# ------------------------------------------------------------

def ler_hora(texto):
    """'8', '8h', '08:30', '8h30' -> (8, 30) ou None."""
    m = re.fullmatch(r"\s*(\d{1,2})\s*(?:[:h]\s*(\d{1,2})?)?\s*", str(texto or "").lower())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    return (h, mi) if 0 <= h <= 23 and 0 <= mi <= 59 else None


def ler_dias(valor):
    """[0,2], ['seg','quarta'], 'seg,qua', 'segunda a sexta' -> [0,2] (0 = segunda)."""
    if valor is None:
        return []
    if isinstance(valor, str):
        t = _sem_acento(valor)
        if re.search(r"\bsegunda\s*(a|ate|-)\s*sexta\b|dias? uteis|weekdays", t):
            return [0, 1, 2, 3, 4]
        if re.search(r"fim de semana|weekend", t):
            return [5, 6]
        partes = re.split(r"[,\s;/]+", t)
    else:
        partes = list(valor) if isinstance(valor, (list, tuple, set)) else [valor]
    dias = []
    for p in partes:
        if isinstance(p, str) and len(p.strip()) > 3 and re.search(r"[,\s;/]|dias? uteis|weekdays|weekend|fim de semana", _sem_acento(p)):
            dias.extend(ler_dias(p))      # a IA às vezes manda ["seg, qua"] ou ["weekdays"] dentro da lista
            continue
        if isinstance(p, int) or (isinstance(p, str) and p.strip().isdigit()):
            n = int(p)
            if 0 <= n <= 6:
                dias.append(n)
            continue
        p = _sem_acento(p).strip()[:3]
        mapa = {"seg": 0, "mon": 0, "ter": 1, "tue": 1, "qua": 2, "wed": 2, "qui": 3, "thu": 3,
                "sex": 4, "fri": 4, "sab": 5, "sat": 5, "dom": 6, "sun": 6}
        if p in mapa:
            dias.append(mapa[p])
    return sorted(set(dias))


def normalizar_quando(q):
    """Valida e limpa o 'quando'. Devolve (quando, erro) — erro é uma chave curta ('tipo', 'hora', 'dias', 'intervalo', 'data')."""
    if not isinstance(q, dict) or q.get("tipo") not in TIPOS:
        return None, "tipo"
    tipo = q["tipo"]
    if tipo == "intervalo":
        try:
            n = int(q.get("cada_minutos"))
        except (TypeError, ValueError):
            return None, "intervalo"
        if n < INTERVALO_MINIMO or n > 7 * 24 * 60:
            return None, "intervalo"
        return {"tipo": tipo, "cada_minutos": n}, None
    if tipo == "uma_vez":
        try:
            d = dt.datetime.fromisoformat(str(q.get("data")).strip().replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None, "data"
        if d.tzinfo is not None:      # 2026-10-31T09:00:00Z -> hora local, sem fuso (a agenda só trabalha com hora local)
            d = d.astimezone().replace(tzinfo=None)
        return {"tipo": tipo, "data": d.replace(microsecond=0).isoformat()}, None
    hora = ler_hora(q.get("hora"))
    if hora is None:
        return None, "hora"
    saida = {"tipo": tipo, "hora": f"{hora[0]:02d}:{hora[1]:02d}"}
    if tipo == "semanal":
        dias = ler_dias(q.get("dias"))
        if not dias:
            return None, "dias"
        saida["dias"] = dias
    return saida, None


def proxima_execucao(quando, depois_de, criada=None):
    """O próximo horário ESTRITAMENTE depois de `depois_de` (datetime), ou None (uma_vez que já passou)."""
    tipo = quando["tipo"]
    if tipo == "uma_vez":
        d = dt.datetime.fromisoformat(quando["data"])
        return d if d > depois_de else None
    if tipo == "intervalo":
        base = criada or depois_de
        passo = dt.timedelta(minutes=quando["cada_minutos"])
        if base > depois_de:
            return base
        n = int((depois_de - base) / passo) + 1
        return base + passo * n
    h, mi = (int(x) for x in quando["hora"].split(":"))
    dia = depois_de.replace(hour=h, minute=mi, second=0, microsecond=0)
    for i in range(0, 9):
        candidato = dia + dt.timedelta(days=i)
        if candidato <= depois_de:
            continue
        if tipo == "diaria" or candidato.weekday() in quando["dias"]:
            return candidato
    return None


def descrever_quando(quando, t):
    """Frase no idioma da pessoa. `t` é tars_i18n.t."""
    tipo = quando["tipo"]
    if tipo == "diaria":
        return t("rot.q_diaria", hora=quando["hora"])
    if tipo == "semanal":
        nomes = ", ".join(t(f"rot.dia_{DIAS[d]}") for d in quando["dias"])
        return t("rot.q_semanal", dias=nomes, hora=quando["hora"])
    if tipo == "intervalo":
        return t("rot.q_intervalo", n=quando["cada_minutos"])
    d = dt.datetime.fromisoformat(quando["data"])
    return t("rot.q_uma_vez", data=d.strftime("%d/%m/%Y"), hora=d.strftime("%H:%M"))


# ------------------------------------------------------------
# Ações arriscadas
# ------------------------------------------------------------

_CATEGORIAS = (
    ("apagar", (r"\brm\b", r"\bfind\b.*\s-delete\b", r"\bshred\b", r"\bgit\b.*\b(reset\s+--hard|clean\s+-[a-z]*f)",
                r"\bdd\b.*\bif=", r"\bmkfs\b", r"\bwipefs\b", r"\bfdisk\b", r"\bparted\b", r">\s*/dev/(sd|nvme|hd)",
                r"\bchmod\b.*-R", r"\bchown\b.*-R", r"\bmv\b.*\s/(\s|$)", r"\btruncate\b", r"\brsync\b.*--delete",
                r"\bunlink\b", r"\bshutil\.rmtree\b")),
    ("enviar", (r"\bgit\b.*\bpush\b", r"\b(scp|sftp|rsync)\b.*\S+:\S*", r"\bcurl\b.*(-X\s*(POST|PUT|DELETE|PATCH)|--data|\s-d\s|\s-F\s|--upload-file|\s-T\s)",
                r"\bwget\b.*--post", r"\b(mail|mailx|sendmail|mutt|msmtp)\b", r"\bssh\b", r"\b(nc|ncat|netcat|telnet)\b", r"\b(twine|npm|cargo)\b.*\bpublish\b")),
    ("instalar", (r"\bsudo\b", r"\b(apt|apt-get|aptitude|dpkg|snap|flatpak|pip3?|pipx|npm|yarn|cargo|gem|dnf|yum|pacman|zypper)\b.*"
                  r"\b(install|remove|purge|upgrade|dist-upgrade|uninstall|autoremove)\b",
                  r"\bsystemctl\b", r"\b(shutdown|reboot|poweroff|halt)\b", r"\bcrontab\b",
                  r"\|\s*(sudo\s+)?(ba|z|da)?sh\b")),
)


def categorias_do_comando(comando):
    """Todas as categorias ('apagar', 'enviar', 'instalar') em que o comando cai (um comando pode cair em várias)."""
    return {nome for nome, padroes in _CATEGORIAS if any(re.search(p, comando, re.IGNORECASE | re.DOTALL) for p in padroes)}


def categoria_do_comando(comando):
    """'apagar' | 'enviar' | 'instalar' | None (a primeira que bate; veja categorias_do_comando)."""
    achadas = categorias_do_comando(comando)
    return next((n for n, _ in _CATEGORIAS if n in achadas), None)


def autorizado(rotina, comando):
    """A rotina pode rodar este comando arriscado sem perguntar? Só se foi aprovada e TODAS as categorias do
    comando estão na lista (aprovar "apagar" não libera "rm x && git push")."""
    cats = categorias_do_comando(comando)
    return bool(rotina.get("aprovada")) and bool(cats) and cats <= set(rotina.get("permitidas") or ())


_RE_ROTINA = re.compile(
    r"\b(agend\w*|rotina\w*|todo\s+dia|todos\s+os\s+dias|toda\s+(manha|tarde|noite|semana|segunda|terca|quarta|quinta|sexta|sabado|domingo)|"
    r"todas\s+as\s+(manhas|segundas|tercas|quartas|quintas|sextas)|a\s+cada\s+\d+\s*(min|h|hora|dia)\w*|"
    r"schedul\w*|every\s+(day|morning|evening|night|week|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d+\s*(min|hour))\w*|"
    r"daily|weekly|recurring)\b")


def fala_de_rotina(texto):
    return bool(_RE_ROTINA.search(_sem_acento(texto)))


# ------------------------------------------------------------
# A agenda
# ------------------------------------------------------------

def _ler(caminho):
    try:
        d = json.loads(Path(caminho).read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except OSError:
        return []
    except ValueError:
        # arquivo quebrado: guarda uma cópia antes que o próximo salvamento o sobrescreva
        try:
            os.replace(caminho, str(caminho) + ".corrompido")
        except OSError:
            pass
        return []


class _Trava:
    """Trava reentrante entre threads E entre processos (o modo terminal e a janela têm cada um a sua Agenda)."""

    def __init__(self, caminho):
        self._rlock = threading.RLock()
        self._arquivo = str(caminho) + ".lock"
        self._fd = None
        self._n = 0

    def __enter__(self):
        self._rlock.acquire()
        if self._n == 0:
            try:
                Path(self._arquivo).parent.mkdir(parents=True, exist_ok=True)
                self._fd = os.open(self._arquivo, os.O_RDWR | os.O_CREAT, 0o600)
                if os.name == "nt":
                    # 5.2: sem fcntl no Windows a trava não travava nada, e a janela e o serviço dos Probes liam e gravavam o
                    # mesmo arquivo juntos (uma leitura no meio do os.replace voltava vazia). msvcrt espera como o flock.
                    import msvcrt
                    while True:
                        try:
                            os.lseek(self._fd, 0, os.SEEK_SET)
                            msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)
                            break
                        except OSError:
                            time.sleep(0.02)
                else:
                    import fcntl
                    fcntl.flock(self._fd, fcntl.LOCK_EX)
            except (ImportError, OSError):
                self._fd = None
        self._n += 1
        return self

    def __exit__(self, *a):
        self._n -= 1
        if self._n == 0 and self._fd is not None:
            try:
                if os.name == "nt":
                    import msvcrt
                    os.lseek(self._fd, 0, os.SEEK_SET)
                    msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
                os.close(self._fd)       # fechar solta o flock
            except OSError:
                pass
            self._fd = None
        self._rlock.release()


class Agenda:
    def __init__(self, caminho=None, agora=None):
        self.caminho = Path(caminho or arquivo_agenda())
        self.agora = agora or dt.datetime.now
        self._trava = _Trava(self.caminho)

    # -- arquivo ----------------------------------------------------------------
    def _rotinas(self):
        return [r for r in _ler(self.caminho) if isinstance(r, dict) and r.get("id") and r.get("quando")]

    def _gravar(self, rotinas):
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        fd, temporario = tempfile.mkstemp(prefix=".agenda-", suffix=".tmp", dir=str(self.caminho.parent))   # 0600
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(rotinas, ensure_ascii=False, indent=1))
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporario, self.caminho)
        except BaseException:
            try:
                os.unlink(temporario)
            except OSError:
                pass
            raise

    def listar(self):
        with self._trava:
            return self._rotinas()

    def obter(self, id_):
        return next((r for r in self.listar() if r["id"] == id_), None)

    def achar_por_nome(self, nome):
        chave = _sem_acento(nome).strip()
        if not chave:
            return None
        rotinas = self.listar()
        exata = [r for r in rotinas if _sem_acento(r["nome"]).strip() == chave]
        parecidas = exata or [r for r in rotinas if chave in _sem_acento(r["nome"])]
        return parecidas[0] if len(parecidas) == 1 or exata else None

    # -- criar e mudar ------------------------------------------------------------
    def criar(self, nome, pedido, quando, permitidas=(), ativa=True, aprovada=True, origem="pessoa"):
        """(rotina, erro). erro: 'nome', 'pedido', 'limite' ou o erro do 'quando'."""
        nome = " ".join(str(nome or "").split())[:LIMITE_NOME]
        pedido = " ".join(str(pedido or "").split())
        if not nome:
            return None, "nome"
        if not pedido or len(pedido) > LIMITE_PEDIDO:
            return None, "pedido"
        q, erro = normalizar_quando(quando)
        if erro:
            return None, erro
        agora = self.agora().replace(microsecond=0)
        with self._trava:
            rotinas = self._rotinas()
            if len(rotinas) >= LIMITE_ROTINAS:
                return None, "limite"
            r = {"id": uuid.uuid4().hex[:10], "nome": nome, "pedido": pedido, "quando": q,
                 "permitidas": [p for p in PERMISSOES if p in set(permitidas or ())],
                 "ativa": bool(ativa), "aprovada": bool(aprovada), "origem": origem,
                 "criada_em": agora.isoformat(), "ultima": None}
            r["proxima"] = self._calcular_proxima(r, agora)
            if r["proxima"] is None:
                r["ativa"] = False        # uma_vez no passado
            rotinas.append(r)
            self._gravar(rotinas)
            return r, None

    def _calcular_proxima(self, r, agora):
        p = proxima_execucao(r["quando"], agora, dt.datetime.fromisoformat(r["criada_em"]))
        return p.isoformat() if p else None

    def atualizar(self, id_, **campos):
        """Muda nome, pedido, quando, permitidas, ativa, aprovada. Ligar exige estar aprovada. (rotina, erro)."""
        with self._trava:
            rotinas = self._rotinas()
            r = next((x for x in rotinas if x["id"] == id_), None)
            if r is None:
                return None, "inexistente"
            antes = (r["quando"], r.get("ativa"), r.get("aprovada"))
            if "nome" in campos:
                nome = " ".join(str(campos["nome"] or "").split())[:LIMITE_NOME]
                if not nome:
                    return None, "nome"
                r["nome"] = nome
            if "pedido" in campos:
                pedido = " ".join(str(campos["pedido"] or "").split())
                if not pedido or len(pedido) > LIMITE_PEDIDO:
                    return None, "pedido"
                r["pedido"] = pedido
                r["aprovada"] = campos.get("aprovada", False)     # mudou o que ela faz: precisa aprovar de novo
            if "quando" in campos:
                q, erro = normalizar_quando(campos["quando"])
                if erro:
                    return None, erro
                r["quando"] = q
            if "permitidas" in campos:
                r["permitidas"] = [p for p in PERMISSOES if p in set(campos["permitidas"] or ())]
            if "aprovada" in campos:
                r["aprovada"] = bool(campos["aprovada"])
            if "ativa" in campos:
                r["ativa"] = bool(campos["ativa"]) and bool(r["aprovada"])
            if not r["aprovada"]:
                r["ativa"] = False
            if (r["quando"], r.get("ativa"), r.get("aprovada")) != antes or not r.get("proxima"):
                r["proxima"] = self._calcular_proxima(r, self.agora().replace(microsecond=0))
                if r["proxima"] is None:
                    r["ativa"] = False
            self._gravar(rotinas)
            return r, None

    def apagar(self, id_):
        with self._trava:
            rotinas = self._rotinas()
            restantes = [r for r in rotinas if r["id"] != id_]
            if len(restantes) == len(rotinas):
                return False
            self._gravar(restantes)
            return True

    def apagar_tudo(self):
        with self._trava:
            n = len(self._rotinas())
            try:
                self.caminho.unlink()
            except OSError:
                pass
            return n

    # -- rodar ---------------------------------------------------------------------
    def devidas(self, agora=None):
        """([rotinas para rodar agora], [rotinas pulas]). Chamar de tempos em tempos.
        Quem passou da tolerância (computador desligado, app fechado) é PULADA: já fica registrada como 'perdida'."""
        agora = (agora or self.agora()).replace(microsecond=0)
        rodar, perdidas = [], []
        with self._trava:
            rotinas = self._rotinas()
            mudou = False
            for r in rotinas:
                if not r.get("ativa") or not r.get("aprovada") or not r.get("proxima"):
                    continue
                prevista = dt.datetime.fromisoformat(r["proxima"])
                if prevista > agora:
                    continue
                if agora - prevista <= TOLERANCIA:
                    rodar.append(dict(r, prevista=prevista.isoformat()))
                else:
                    r["ultima"] = {"quando": prevista.isoformat(), "resultado": "perdida", "detalhe": ""}
                    perdidas.append(dict(r))
                    p = proxima_execucao(r["quando"], agora, dt.datetime.fromisoformat(r["criada_em"]))
                    r["proxima"] = p.isoformat() if p else None
                    if p is None:
                        r["ativa"] = False
                    mudou = True
            if mudou:
                self._gravar(rotinas)
        return rodar, perdidas

    def reservar(self, id_, prevista, agora=None):
        """Quem vai rodar a rotina "pega" a execução antes: já aponta para a próxima vez e marca 'rodando'. Devolve
        False se outra janela/processo já a pegou (ou se mudou): a mesma execução nunca roda duas vezes, nem se a
        janela fechar no meio. registrar() anota o resultado de verdade quando ela termina."""
        agora = (agora or self.agora()).replace(microsecond=0)
        with self._trava:
            rotinas = self._rotinas()
            r = next((x for x in rotinas if x["id"] == id_), None)
            if r is None or r.get("proxima") != prevista:
                return False
            r["ultima"] = {"quando": agora.isoformat(), "resultado": "rodando", "detalhe": ""}
            p = proxima_execucao(r["quando"], agora, dt.datetime.fromisoformat(r["criada_em"]))
            r["proxima"] = p.isoformat() if p else None
            self._gravar(rotinas)
            return True

    def registrar(self, id_, resultado, detalhe="", agora=None):
        """Anota o resultado de uma execução ('ok' | 'parou' | 'erro' | 'ocupada') e agenda a próxima."""
        agora = (agora or self.agora()).replace(microsecond=0)
        with self._trava:
            rotinas = self._rotinas()
            r = next((x for x in rotinas if x["id"] == id_), None)
            if r is None:
                return None
            r["ultima"] = {"quando": agora.isoformat(), "resultado": resultado, "detalhe": str(detalhe)[:300]}
            p = proxima_execucao(r["quando"], agora, dt.datetime.fromisoformat(r["criada_em"]))
            r["proxima"] = p.isoformat() if p else None
            if p is None:
                r["ativa"] = False        # uma_vez já feita
            self._gravar(rotinas)
            return dict(r)

    def anotar_ultima(self, id_, resultado, detalhe="", agora=None):
        """Só anota o resultado (usado por 'Rodar agora': o calendário não muda)."""
        agora = (agora or self.agora()).replace(microsecond=0)
        with self._trava:
            rotinas = self._rotinas()
            r = next((x for x in rotinas if x["id"] == id_), None)
            if r is None:
                return None
            r["ultima"] = {"quando": agora.isoformat(), "resultado": resultado, "detalhe": str(detalhe)[:300]}
            self._gravar(rotinas)
            return dict(r)
