"""O mascote do openTARS 5.0: um monólito articulado (como o TARS) que anda pela conversa, dá dicas e reage ao que a IA faz.

É um widget filho da área da conversa (nada de janela solta: funciona igual em X11 e Wayland) e só existe enquanto a conversa
está à vista. Ele não decide nada: a janela principal repassa os eventos do núcleo (`reagir`, `ocupado`, `espera`, `concluido`).
Desligar: Configurações > Geral, o menu do botão direito nele, ou TARS_SEM_MASCOTE=1.
"""

import math
import os
import random
import time

from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QLabel, QMenu, QWidget

import tars_i18n
from tars_i18n import t

from .tema import CORES, seguro

LARGURA, ALTURA = 80, 80
PIXEL = 3                       # cada pixel do desenho vira 3x3 na tela: pixel art de verdade, sem suavizar
SPRITE_L, SPRITE_A = 23, 25
N_DICAS = 10
VELOCIDADE = 34.0            # px/s andando
SONO_S = 180                 # parado sem nada acontecendo por 3 min: cochila (para de andar e de dar dicas)
def ligado():
    """Config do usuário (padrão: ligado) e TARS_SEM_MASCOTE=1 (desliga mesmo ligado)."""
    if str(os.environ.get("TARS_SEM_MASCOTE", "")).strip().lower() in ("1", "sim", "yes", "true", "on"):
        return False
    return bool(tars_i18n.ler_config().get("mascote", True))


class Balao(QLabel):
    """O balão de fala: some sozinho, nunca pega o mouse."""

    def __init__(self, pai):
        super().__init__(pai)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setWordWrap(True)
        self.setStyleSheet(f"background:{CORES['cartao']}; color:{CORES['texto']}; border:2px solid {CORES['borda3']};"
                           "border-radius:0px; padding:7px 10px; font-family:'IBM Plex Mono'; font-size:12px;")
        self._some = QTimer(self)
        self._some.setSingleShot(True)
        self._some.timeout.connect(self.hide)
        self.hide()

    def dizer(self, texto, ms):
        self.setText(seguro(texto))
        largura = min(260, self.fontMetrics().horizontalAdvance(self.text()) + 30)   # frase curta: balão justo; longa: quebra em 260
        self.setFixedWidth(largura)
        self.setFixedHeight(self.heightForWidth(largura))
        self.show()
        self.raise_()
        self._some.start(ms)


class Mascote(QWidget):
    escondeu = Signal()          # a pessoa escolheu esconder no menu dele

    def __init__(self, pai, referencia=None):
        super().__init__(pai)
        self.setFixedSize(LARGURA, ALTURA)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("KIPP")
        self._ref = referencia          # o widget em cima do qual ele anda (o campo de escrever)
        self.balao = Balao(pai)
        self.estado = "ocioso"
        self._x = 24.0
        self._dir = 1
        self._parado_ate = time.monotonic() + 2
        self._fase = 0.0
        self._pulo_ate = 0.0
        self._erro_ate = 0.0
        self._ultima_fala = 0.0
        self._ultima_dica = time.monotonic()
        self._dicas = []
        self._ultimo_tick = time.monotonic()
        self._ultima_atividade = time.monotonic()
        self._t = QTimer(self)
        self._t.timeout.connect(self._tick)
        self._t.start(33)
        self.setVisible(ligado())

    # -- o que a janela conta pra ele ------------------------------------------------------------
    def _acordar(self):
        self._ultima_atividade = time.monotonic()
        if self.estado == "sono":
            self.estado = "ocioso"

    def ocupado(self, sim):
        self._acordar()
        self.estado = "pensando" if sim else "ocioso"
        if sim:
            self._ultima_dica = time.monotonic()

    def reagir(self, tipo, d, nome_da_ferramenta=""):
        """Eventos do núcleo (os mesmos que a conversa recebe)."""
        self._acordar()
        if tipo == "ferramenta":
            self.estado = "trabalhando"
            self._falar(f"{nome_da_ferramenta}…" if nome_da_ferramenta else t("mascote.trabalhando"), 2200, minimo=2.5)
        elif tipo == "ferramenta_fim":
            if d.get("sucesso") is False:
                self._erro_ate = time.monotonic() + 0.7
                self.estado = "erro"
                self._falar(t("mascote.ops"), 3000, minimo=2.5)
            else:
                self.estado = "pensando"
        elif tipo == "plano":
            self._falar(t("mascote.plano", n=len(d.get("etapas") or [])), 3000, minimo=0)
        elif tipo in ("pensamento", "resposta"):
            if self.estado != "trabalhando":
                self.estado = "pensando"

    def espera(self):
        self._acordar()
        self.estado = "espera"
        self._falar(t("mascote.permissao"), 6000, minimo=0)

    def concluido(self, resposta=""):
        self._acordar()
        self.estado = "feliz"
        self._pulo_ate = time.monotonic() + 0.7
        self._falar(t("mascote.pronto"), 2500, minimo=0)
        QTimer.singleShot(2600, lambda: setattr(self, "estado", "ocioso") if self.estado == "feliz" else None)
        self._ultima_dica = time.monotonic()

    def dica(self):
        if not self._dicas:
            self._dicas = list(range(1, N_DICAS + 1))
            random.shuffle(self._dicas)
        self._falar(t(f"mascote.dica{self._dicas.pop()}"), 7000, minimo=0)
        self._ultima_dica = time.monotonic()

    def _falar(self, texto, ms, minimo):
        agora = time.monotonic()
        if not self.isVisible() or agora - self._ultima_fala < minimo:
            return
        self._ultima_fala = agora
        self.balao.dizer(texto, ms)
        self._posicionar_balao()

    # -- movimento ---------------------------------------------------------------------------------
    def _limites(self):
        p = self.parentWidget()
        return 16.0, max(16.0, p.width() - LARGURA - 16.0)

    def _tick(self):
        agora = time.monotonic()
        dt, self._ultimo_tick = min(0.1, agora - self._ultimo_tick), agora
        if not self.isVisible():
            return
        if self.estado == "ocioso" and agora - self._ultima_atividade > SONO_S:
            self.estado = "sono"
        esq, dir_ = self._limites()
        anda = self._andando(agora)
        if anda:
            self._x += self._dir * VELOCIDADE * dt
            self._fase += dt * 9
            if self._x <= esq or self._x >= dir_:
                self._x = min(max(self._x, esq), dir_)
                self._dir = -self._dir
                self._parado_ate = agora + random.uniform(2.0, 5.0)
            elif random.random() < 0.004:                   # de vez em quando para e olha em volta
                self._parado_ate = agora + random.uniform(1.5, 4.0)
        elif self.estado != "ocioso":
            self._fase += dt * 3
        self._x = min(max(self._x, esq), dir_)
        if self.estado == "ocioso" and agora - self._ultima_dica > 50 and not self.balao.isVisible():
            self.dica()
        pulo = max(0.0, self._pulo_ate - agora)
        y_chao = self._y_do_chao()
        self.move(int(self._x), int(y_chao - (math.sin(pulo / 0.7 * math.pi) * 16 if pulo else 0)))
        if self.balao.isVisible():
            self._posicionar_balao()
        self.update()

    def _y_do_chao(self):
        p = self.parentWidget()
        if self._ref is not None and self._ref.isVisible():
            return self._ref.mapTo(p, self._ref.rect().topLeft()).y() - ALTURA + 4
        return p.height() - ALTURA - 8

    def _posicionar_balao(self):
        p = self.parentWidget()
        b = self.balao
        x = min(max(8, self.x() + LARGURA // 2 - b.width() // 2), max(8, p.width() - b.width() - 8))
        b.move(int(x), max(4, self.y() - b.height() - 6))

    # -- interação ---------------------------------------------------------------------------------
    def mousePressEvent(self, e):
        self._acordar()
        if e.button() == Qt.LeftButton:
            self.dica()
        elif e.button() == Qt.RightButton:
            m = QMenu(self)
            m.addAction(t("mascote.menu_dica"), self.dica)
            m.addAction(t("mascote.menu_esconder"), self._esconder)
            m.exec(e.globalPosition().toPoint())

    def _esconder(self):
        tars_i18n.salvar_config(mascote=False)
        self.balao.hide()
        self.hide()
        self.escondeu.emit()

    def mostrar_de_novo(self):
        """A configuração ligou o mascote: ele volta."""
        self.setVisible(ligado())
        if not self.isVisible():
            self.balao.hide()

    # -- desenho (pixel art) -------------------------------------------------------------------------
    def paintEvent(self, _e):
        agora = time.monotonic()
        dx = 0
        if agora < self._erro_ate:
            dx = 1 if math.sin(agora * 60) > 0 else -1          # treme quando erra
        elif self.estado == "pensando":
            dx = round(1.4 * math.sin(agora * 2.2))              # balança de um lado pro outro, pensando
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        sprite = desenhar_sprite(self.estado, self._fase, self._andando(agora), self._dir, agora)
        x = (LARGURA - SPRITE_L * PIXEL) // 2 + dx * PIXEL
        p.fillRect(QRect(x + PIXEL, ALTURA - 2 * PIXEL, (SPRITE_L - 2) * PIXEL, PIXEL), QColor(0, 0, 0, 70))   # sombra
        p.drawImage(QRect(x, ALTURA - (SPRITE_A + 1) * PIXEL, SPRITE_L * PIXEL, SPRITE_A * PIXEL), sprite)
        p.end()

    def _andando(self, agora):
        return self.estado == "ocioso" and agora >= self._parado_ate


# As 4 colunas gordinhas do logo do openTARS com a tela verde-neon no lugar da fresta do logo. O rosto é só a tela e dois
# olhinhos que piscam: quem reage é o corpo (as colunas sobem, descem, acenam, encolhem). Poucos tons, como um jogo antigo.
_CLARO, _MEIO, _ESCURO, _CONTORNO = QColor("#F4F6FB"), QColor("#D3DAEC"), QColor("#8E9ABF"), QColor("#0B1020")
_NEON, _NEON_BRILHO, _NEON_SOMBRA = QColor("#39FF88"), QColor("#B6FFD2"), QColor("#1FC968")
_COLUNAS = (0, 6, 12, 18)       # x de cada coluna (5 pixels de largura, 1 de vão)


def _subida_das_colunas(estado, fase, andando, agora):
    """Quantos pixels cada coluna sobe (negativo: afunda). É aqui que mora a "expressão" dele."""
    if andando:                                   # o passo do TARS: os pares se alternam
        return [1 if math.sin(fase + (math.pi if i in (1, 2) else 0)) > 0 else 0 for i in range(4)]
    if estado == "trabalhando":                   # as colunas bombeiam em onda, rápido: mão na massa
        return [1 if math.sin(agora * 14 - i * 1.4) > 0.2 else 0 for i in range(4)]
    if estado == "espera":                        # acena com a coluna da ponta: "ei, preciso de você"
        aceno = 3 if math.sin(agora * 9) > 0 else 1
        return [0, 0, 0, aceno]
    if estado == "erro":                          # encolhe, desanimado
        return [-1, -2, -2, -1]
    if estado == "feliz":                         # braços pra cima: comemora (e o widget faz ele pular)
        return [2, 0, 0, 2]
    if estado == "sono":                          # respira fundo e devagar, cochilando
        return [-1] * 4 if math.sin(agora * 1.5) > 0 else [0] * 4
    if estado == "pensando":                      # respira devagar
        return [1 if math.sin(agora * 2.2) > 0.5 else 0] * 4
    return [0, 0, 0, 0]


def desenhar_sprite(estado, fase, andando, direcao, agora):
    """O mascote num QImage de 23x25 pixels (transparente em volta), pro estado e o momento."""
    img = QImage(SPRITE_L, SPRITE_A, QImage.Format_ARGB32)
    img.fill(Qt.transparent)

    def px(x, y, cor):
        if 0 <= x < SPRITE_L and 0 <= y < SPRITE_A:
            img.setPixelColor(x, y, cor)

    subidas = _subida_das_colunas(estado, fase, andando, agora)
    for i, x0 in enumerate(_COLUNAS):
        sobe = subidas[i]
        topo = 4 - sobe                                  # afundar (negativo) baixa o topo: a coluna fica mais curta
        fundo = 23 - max(0, sobe)
        for y in range(topo, fundo + 1):
            for dx in range(5):
                if y in (topo, fundo) and dx in (0, 4):
                    continue                          # cantos arredondados
                px(x0 + dx, y, _CLARO if dx == 0 else _ESCURO if dx == 4 else _MEIO)
        for dx in range(1, 4):                        # contorno de cima e de baixo
            px(x0 + dx, topo - 1, _CONTORNO)
            px(x0 + dx, fundo + 1, _CONTORNO)
        px(x0 + 2, fundo - 5, _ESCURO)                # juntas
        px(x0 + 2, fundo - 2, _ESCURO)
    # a tela verde-neon, presa às colunas do meio (sobe e desce com elas)
    meio = min(subidas[1], subidas[2])
    t0 = 8 - meio
    for y in range(t0, t0 + 6):
        for x in range(2, 21):
            if y in (t0, t0 + 5) and x in (2, 20):
                continue
            px(x, y, _NEON_BRILHO if y == t0 else _NEON_SOMBRA if y == t0 + 5 else _NEON)
    _rosto(px, estado, t0, direcao if andando else 0, agora)
    _acima_da_cabeca(px, estado, agora)
    return img


def _rosto(px, estado, t0, olhar, agora):
    """Olhos, sobrancelhas e boca na tela verde. Olhos em x=7 e x=14 (2 px cada); a boca fica no centro (x=10..12)."""
    c = _CONTORNO
    ciclo = agora % 4.2
    piscando = ciclo < 0.12 or 0.3 < ciclo < 0.42 and int(agora / 4.2) % 3 == 0
    for ex in (7, 14):
        if estado == "feliz":                                   # olhos de arco: ^ ^
            px(ex, t0 + 2, c); px(ex + 1, t0 + 2, c); px(ex - 1, t0 + 3, c); px(ex + 2, t0 + 3, c)
        elif estado in ("sono",) or piscando and estado in ("ocioso", "pensando"):
            px(ex, t0 + 3, c); px(ex + 1, t0 + 3, c)            # fechados
        elif estado == "pensando":                              # olhando pra cima e pro lado, pensativo
            px(ex + 1, t0 + 1, c); px(ex + 2, t0 + 1, c)
        elif estado == "trabalhando":                           # apertados, sobrancelhas franzidas: concentrado
            px(ex, t0 + 3, c); px(ex + 1, t0 + 3, c)
            px(ex, t0 + (0 if ex == 7 else 1), c); px(ex + 1, t0 + (1 if ex == 7 else 0), c)
        elif estado == "erro":                                  # baixos, sobrancelhas caídas pra fora: triste
            px(ex, t0 + 3, c); px(ex + 1, t0 + 3, c)
            px(ex, t0 + (1 if ex == 7 else 0), c); px(ex + 1, t0 + (0 if ex == 7 else 1), c)
        elif estado == "espera":                                # arregalados
            for dy in (1, 2, 3):
                px(ex, t0 + dy, c); px(ex + 1, t0 + dy, c)
        else:                                                   # normal; andando, olha pra onde vai
            for dy in (2, 3):
                px(ex + olhar, t0 + dy, c); px(ex + 1 + olhar, t0 + dy, c)
    if estado == "feliz":                                       # sorriso
        px(9, t0 + 4, c); px(13, t0 + 4, c)
        for x in (10, 11, 12):
            px(x, t0 + 5, c)
    elif estado == "erro":                                      # boca pra baixo
        for x in (10, 11, 12):
            px(x, t0 + 4, c)
        px(9, t0 + 5, c); px(13, t0 + 5, c)
    elif estado == "espera":                                    # boca aberta: "ei!"
        for x in (10, 11, 12):
            px(x, t0 + 4, c)
        px(10, t0 + 5, c); px(12, t0 + 5, c)


def _acima_da_cabeca(px, estado, agora):
    """Sinais em cima da cabeça: reticências pensando, "!" pedindo permissão, "z" dormindo."""
    if estado == "pensando":                                    # . .. ... acendendo um por vez
        for x in (8, 11, 14)[:int(agora * 3) % 4]:
            px(x, 0, _CLARO)
    elif estado == "espera" and math.sin(agora * 6) > -0.3:     # "!" piscando, no vão entre as colunas do meio
        px(11, 0, _NEON); px(11, 1, _NEON); px(11, 3, _NEON)
    elif estado == "sono":                                      # um "z" que vai flutuando pro lado
        dx = int(agora * 1.2) % 2
        for x, y in ((0, 0), (1, 0), (2, 0), (3, 0), (2, 1), (1, 2), (0, 3), (1, 3), (2, 3), (3, 3)):
            px(16 + dx + x, y, _CLARO)
