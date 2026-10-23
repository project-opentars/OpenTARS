"""
Diagnóstico e autoteste do openTARS, pra rodar no PC de quem usa:

    opentars --diagnostico   confere o ambiente (rápido, não mexe em nada)
    opentars --autoteste     diagnóstico + precisão da helper Murph + um teste
                             de verdade: a IA abre a calculadora, faz 7 + 2
                             clicando nos botões e o resultado é conferido
                             lendo o visor (sem depender do que a IA diz)

O relatório vai pra tela e pra ~/opentars-autoteste.txt (texto puro, pra
mandar pra quem estiver ajudando).

Recebe o núcleo como parâmetro (não importa o tars.py: quando ele roda
como script, importar de novo criaria uma segunda cópia do estado).
"""

import os
import platform
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

ARQUIVO_RELATORIO = Path(os.environ.get("TARS_ARQUIVO_AUTOTESTE") or Path.home() / "opentars-autoteste.txt")
ACERTO_MINIMO_CLASSIFICADOR = 0.8
# "9" sozinho (não 19, 9.5 ou 0,9); "é 9." no fim da frase vale.
_RE_NOVE = re.compile(r"(?<!\d)(?<!\d[.,])9(?!\d|[.,]\d)")


class _Relatorio:
    def __init__(self, core):
        self.core = core
        self.linhas = []
        self.falhas = 0
        self.avisos = 0

    def secao(self, titulo):
        c, Cor = self.core.c, self.core.Cor
        print("\n" + c(titulo, Cor.NEGRITO + Cor.CIANO))
        self.linhas.append(f"\n== {titulo} ==")

    def item(self, estado, rotulo, detalhe=""):
        """estado: True (ok), False (falha), None (aviso), "info"."""
        c, Cor = self.core.c, self.core.Cor
        marca, cor = {True: ("✓", Cor.VERDE), False: ("✗", Cor.VERMELHO), None: ("!", Cor.AMARELO)}.get(
            estado, ("·", Cor.CINZA))
        if estado is False:
            self.falhas += 1
        elif estado is None:
            self.avisos += 1
        texto = f"{rotulo}: {detalhe}" if detalhe else rotulo
        print(f"  {c(marca, cor)} {texto}")
        self.linhas.append(f"[{marca}] {texto}")

    def salvar(self):
        try:
            ARQUIVO_RELATORIO.write_text("\n".join(self.linhas).strip() + "\n", encoding="utf-8")
            return True
        except OSError:
            return False


def _versao_ollama(core):
    try:
        r = core._SESSION.get(f"{core.OLLAMA_HOST}/api/version", timeout=core.TIMEOUT_HTTP_CURTO)
        return r.json().get("version") if r.status_code == 200 else None
    except Exception:
        return None


def diagnostico(core, rel):
    t = core.t
    i18n, acess = core.i18n, core.acess

    rel.secao(t("diag.titulo_sistema"))
    rel.item("info", "openTARS", f"{core.VERSAO_EXIBIDA} · Python {platform.python_version()}")
    nova = core.aviso_versao_nova()
    if nova:
        rel.item(None, t("diag.versao"), nova)
    rel.item("info", t("diag.idioma"), f"{i18n.nome_idioma(i18n.idioma_atual())} ({i18n.idioma_atual()})")
    desktop = os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION") or "?"
    rel.item("info", t("diag.sistema"), f"{core._nome_distro()} · {desktop} · {core.SESSAO_GRAFICA}")
    so = core.plataforma.descrever()
    rel.item("info", t("diag.plataforma"), f"{so['sistema']} {so['versao']} · {so['arquitetura']} · {so['nucleos']} threads · "
             f"{so['ram_gb']} GB")
    faltam = [f for f, existe in core.plataforma.recursos().items() if not existe]
    if faltam:
        rel.item(None, t("diag.plataforma"), t("diag.plataforma_falta", funcoes=", ".join(faltam)))
    # 4.5: onde estamos (WSL? sem interface?)
    amb = core.AMBIENTE
    chave = ("diag.amb_wslg" if amb["tipo"] == "wslg" else "diag.amb_wsl_sem_tela" if amb["wsl"] and amb["tipo"] == "sem_tela"
             else "diag.amb_ssh" if amb["ssh"] and amb["tipo"] == "sem_tela" else "diag.amb_sem_tela" if amb["tipo"] == "sem_tela"
             else "diag.amb_desktop")
    rel.item("info", t("diag.ambiente"), t(chave, wsl=amb["wsl"] or ""))
    if core.SESSAO_GRAFICA == "wayland" and core.ENTRADA_WAYLAND:
        rel.item(True, t("diag.sessao"), t("diag.wayland_ydotool"))
    elif core.SESSAO_GRAFICA == "wayland":
        rel.item(None, t("diag.sessao"), t("aviso.wayland") + " "
                 + t("aviso.wayland_ydotool", motivo=core.MOTIVO_SEM_YDOTOOL or "-"))

    rel.secao(t("diag.titulo_ia"))
    versao = _versao_ollama(core)
    if versao:
        rel.item(True, "Ollama", t("diag.ollama_ok", versao=versao, host=core.OLLAMA_HOST))
        if core.OLLAMA_NO_WINDOWS:
            rel.item("info", "Ollama", t("diag.wsl_ollama_windows", host=core.OLLAMA_HOST))
    else:
        rel.item(False, "Ollama", t("aviso.ollama_offline", host=core.OLLAMA_HOST))
        if core.EM_WSL and not os.environ.get("OLLAMA_HOST"):
            rel.item("info", "Ollama", t("diag.wsl_sem_ollama"))

    catalogo = core.catalogar_modelos(forcar=True) if versao else {}
    # A helper Murph vem no pacote e decide o tipo de cada pedido (sem Ollama).
    if core.murph.disponivel():
        rel.item(True, t("diag.ajudante"), t("diag.helper_murph", versao=core.murph.versao()))
    else:
        rel.item(False, t("diag.ajudante"), t("diag.helper_sem_murph"))

    # 4.0: o Gargantua, a IA oficial
    if versao:
        tag = core.gargantua_instalado(catalogo)
        if tag and core.gargantua_desligado():
            rel.item("info", "Gargantua", t("gargantua.desligado", modelo=tag))
        elif tag:
            rel.item(True, "Gargantua", t("gargantua.ok", versao=core.VERSAO_GARGANTUA, modelo=tag))
        else:
            rel.item(None, "Gargantua", t("gargantua.nao_instalado", modelo=core.MODELO_GARGANTUA))

    # 4.5: a visão da tela (o Gargantua 2; o Cooper foi descontinuado)
    if versao:
        visao_tag = core.visao_lib.achar_instalado(list(catalogo.keys()))
        if visao_tag and not core.visao_lib.ligado():
            rel.item("info", "Visão", t("visao.desligado", modelo=visao_tag))
        elif visao_tag:
            rel.item(True, "Visão", t("visao.ok", modelo=visao_tag))
        elif not core.SEM_INTERFACE:
            rel.item(None, "Visão", t("visao.nao_instalado", comando=core.visao_lib.COMANDO_INSTALAR))

    ajudantes = core.MODELOS_AJUDANTES
    conversa = sorted(
        m["tag"] for m in catalogo.values() if m["categoria"] != "embedding" and m["tag"] not in ajudantes
    )
    if versao:
        if conversa:
            rel.item(True, t("diag.modelos"), f"{len(conversa)}: {', '.join(conversa)}")
        else:
            rel.item(False, t("diag.modelos"), t("aviso.sem_modelo_conversa"))

    gpu = core.detectar_gpu(forcar=True)
    ram = core.ram_total_gb()
    ram_txt = f"{ram:.0f} GB RAM" if ram else "RAM ?"
    if gpu:
        rel.item("info", "GPU", f"{gpu.get('fabricante', 'GPU')} {gpu['vram_total_gb']} GB "
                                f"({gpu['vram_livre_gb']} GB {t('diag.livres')}) · {ram_txt}")
    else:
        rel.item("info", "GPU", f"{t('lista.sem_gpu')} · {ram_txt}")
    if versao and conversa:
        for tarefa in ("acao", "tecnico"):
            cadeia = core.construir_cadeia_fallback(tarefa)
            if cadeia:
                rel.item("info", t("diag.escolha_auto", tarefa=core.nome_tarefa(tarefa)), cadeia[0])

    rel.secao(t("diag.titulo_controle"))
    if core.SEM_INTERFACE:
        # 4.5: sem tela não é falha: é o modo terminal (conversa, comandos, arquivos)
        rel.item("info", t("diag.titulo_controle"), t("diag.modo_sem_interface"))
        return bool(versao and conversa)
    if core.ERRO_PYAUTOGUI:
        rel.item(False, t("diag.mouse"), core.ERRO_PYAUTOGUI)
    else:
        rel.item(True, t("diag.mouse"), "pyautogui")

    janelas = core.listar_janelas_x()
    if janelas is None:
        rel.item(None if core.SESSAO_GRAFICA == "wayland" else False, t("diag.janelas"), t("diag.janelas_sem_x"))
    else:
        rel.item(True, t("diag.janelas"), t("diag.janelas_ok", n=len(janelas)))

    if core.SESSAO_GRAFICA != "nenhuma":
        inicio = time.time()
        try:
            img = core._capturar_tela()
            ms = (time.time() - inicio) * 1000
            if core.SESSAO_GRAFICA == "wayland" and core._imagem_toda_preta(img):
                rel.item(False, t("diag.print"), t("diag.print_preto"))
            else:
                rel.item(True, t("diag.print"), f"{img.size[0]}x{img.size[1]} · {ms:.0f} ms")
        except Exception as e:
            rel.item(False, t("diag.print"), str(e)[:200])

    motivo = acess.indisponivel()
    if motivo:
        rel.item(False, t("diag.acessibilidade"), f"{motivo} → sudo apt install gir1.2-atspi-2.0 python3-gi at-spi2-core")
    else:
        acessiveis = acess.janelas()
        if acessiveis:
            apps = sorted({j["app"] or j["titulo"] for j in acessiveis})
            rel.item(True, t("diag.acessibilidade"), t("diag.acessiveis", n=len(acessiveis), apps=", ".join(apps[:8])))
        else:
            rel.item(None, t("diag.acessibilidade"), t("diag.nenhuma_acessivel"))

    copia = next((p for p in ("wl-copy", "xclip", "xsel") if shutil.which(p)), None)
    rel.item(True if copia else None, t("diag.clipboard"), copia or t("diag.clipboard_falta"))

    try:
        import tkinter  # noqa: F401
        rel.item(True, t("diag.interface"), "tkinter")
    except Exception as e:
        rel.item(False, t("diag.interface"), f"{e} → sudo apt install python3-tk")

    try:
        import tars_atalho
        estado = tars_atalho.estado()
        if estado.get("registrado"):
            rel.item(True, t("diag.atalho"), f"{estado['legivel']} ({estado.get('ambiente', '?')})")
        else:
            rel.item(None, t("diag.atalho"), estado.get("motivo") or t("atalho.nao_registrado"))
    except Exception as e:
        rel.item(None, t("diag.atalho"), str(e)[:200])

    return bool(versao and conversa)


def _teste_classificador(core, rel):
    t = core.t
    rel.secao(t("auto.titulo_classificador"))
    frases = [tuple(par) for par in core.i18n.lista("avaliacao") if isinstance(par, list) and len(par) == 2]
    print(core.c(f"  {t('auto.classificando', n=len(frases))}", core.Cor.CINZA))
    r = core.medir_classificador(frases)
    taxa = r["acertos_total"] / max(1, r["n"])
    rel.item(
        True if taxa >= ACERTO_MINIMO_CLASSIFICADOR else None,
        t("auto.classificador"),
        t("auto.classificador_resultado", acertos=r["acertos_total"], n=r["n"], pct=f"{100 * taxa:.0f}",
          murph=r["acertos_local"], ms=f"{r['ms_medio']:.1f}"),
    )
    for frase, esperado, resposta in r["erros_total"][:12]:
        rel.linhas.append(f"    {frase} | {esperado} | {resposta}")


def _janela_calculadora(core, nome):
    """A janela acessível da calculadora (pra ler o visor)."""
    try:
        return core.acess.achar_janela(termos=core._termos_para_janela(nome), ignorar_pids=core._pids_protegidos())
    except Exception:
        return None


def _teste_calculadora(core, rel):
    t = core.t
    rel.secao(t("auto.titulo_calculadora"))

    nome = t("auto.calculadora")
    if core.SESSAO_GRAFICA == "nenhuma":
        rel.item(None, t("auto.calculadora_teste"), t("aviso.sem_display"))
        return
    if not core._buscar_app_no_sistema(nome):
        rel.item(None, t("auto.calculadora_teste"), t("auto.sem_calculadora", nome=nome))
        return

    print(core.c("  " + t("auto.nao_mexa"), core.Cor.AMARELO))
    time.sleep(2)

    chamadas = []
    executar_original = core.executar_ferramenta

    def registrar(nome_ferramenta, argumentos):
        resultado = executar_original(nome_ferramenta, argumentos)
        chamadas.append((nome_ferramenta, core._resumo_argumentos(argumentos), bool(resultado.get("sucesso"))))
        return resultado

    # A conversa do teste não entra no histórico de quem usa.
    conversa_antes = [dict(m) for m in core.conversa]
    arquivo_antes = core.ARQUIVO_SESSOES
    modo_antes = (core.modo_modelo, core.modelo_manual)
    temporario = Path(tempfile.mkdtemp(prefix="opentars-teste-")) / "sessao.json"
    core.ARQUIVO_SESSOES = temporario
    core.executar_ferramenta = registrar
    core.modo_modelo, core.modelo_manual = "AUTO", None
    core.conversa[:] = [{"role": "system", "content": core.montar_system_prompt()}]

    resposta = None
    inicio = time.time()
    try:
        resposta = core.processar_mensagem(t("auto.pedido_calculadora"))
    except Exception as e:
        rel.item(False, t("auto.calculadora_teste"), f"{type(e).__name__}: {e}")
    finally:
        segundos = time.time() - inicio
        core.executar_ferramenta = executar_original
        core.ARQUIVO_SESSOES = arquivo_antes
        core.modo_modelo, core.modelo_manual = modo_antes
        core.conversa[:] = conversa_antes
        shutil.rmtree(temporario.parent, ignore_errors=True)

    # Conferência independente: o que o visor mostra de verdade.
    janela = _janela_calculadora(core, nome)
    visor = core.acess.listar(janela)["textos"] if janela else []
    visor_mostra_9 = any(_RE_NOVE.search(texto) for texto in visor)
    resposta_diz_9 = bool(resposta and _RE_NOVE.search(resposta))

    usadas = [n for n, _r, _ok in chamadas]
    resumo = ", ".join(
        f"{n}×{usadas.count(n)}" if usadas.count(n) > 1 else n for n in dict.fromkeys(usadas)
    ) or "-"
    detalhe = t("auto.calculadora_detalhe", segundos=f"{segundos:.1f}", ferramentas=resumo)

    if visor_mostra_9 and resposta_diz_9:
        rel.item(True, t("auto.calculadora_teste"), t("auto.passou") + " · " + detalhe)
    elif visor_mostra_9:
        rel.item(None, t("auto.calculadora_teste"), t("auto.visor_ok_resposta_nao") + " · " + detalhe)
    elif janela is None and "click_element" not in usadas:
        rel.item(False, t("auto.calculadora_teste"), t("auto.sem_janela_acessivel") + " · " + detalhe)
    else:
        rel.item(False, t("auto.calculadora_teste"),
                 t("auto.falhou", visor=" | ".join(visor[:4]) or "-") + " · " + detalhe)

    rel.linhas.append("    " + t("auto.resposta_ia") + ": " + " ".join((resposta or "-").split())[:300])
    for nome_ferramenta, resumo_args, ok in chamadas:
        rel.linhas.append(f"    {'✓' if ok else '✗'} {nome_ferramenta} {resumo_args}")

    if janela is not None or core._buscar_app_no_sistema(nome):
        try:
            core.fechar_aplicativo(nome)
        except Exception:
            pass


def executar(core, completo=False):
    """Roda o diagnóstico (e, com completo=True, o autoteste). Devolve o
    código de saída: 0 sem falhas, 1 com alguma."""
    t = core.t
    rel = _Relatorio(core)
    print(core.c(f"\nopenTARS {core.VERSAO} — {t('auto.titulo') if completo else t('diag.titulo')}", core.Cor.NEGRITO + core.Cor.MAGENTA))
    rel.linhas.append(f"openTARS {core.VERSAO} — {t('auto.titulo') if completo else t('diag.titulo')}")
    rel.linhas.append(time.strftime("%Y-%m-%d %H:%M"))

    pode_testar = diagnostico(core, rel)

    if completo:
        if pode_testar:
            _teste_classificador(core, rel)
            _teste_calculadora(core, rel)
        else:
            rel.secao(t("auto.titulo_calculadora"))
            rel.item(False, t("auto.calculadora_teste"), t("auto.sem_ia"))

    print()
    resumo = t("diag.resumo", falhas=rel.falhas, avisos=rel.avisos)
    rel.linhas.append("\n" + resumo)
    print(core.c(resumo, core.Cor.VERDE if not rel.falhas else core.Cor.AMARELO))
    if completo and rel.salvar():
        print(core.c(t("auto.relatorio_salvo", arquivo=ARQUIVO_RELATORIO), core.Cor.CINZA))
    print()
    sys.stdout.flush()
    return 1 if rel.falhas else 0
