"""O que o assistente resolve sem o modelo (F4 do PLANO_5.3.md, 07/11): vem das camadas do openTARS Pi, onde levaram a prova
de 19 para 30 de 40 tarefas inéditas, e modelos maiores não ganharam do pequeno depois disso.

- estado do computador com avaliação ("está tranquilo") e capacidade ("cabe um arquivo de 10 GB?");
- memória: "guarda que...", "esquece...", "o que você sabe de mim?";
- contas;
- operações de arquivo com os nomes ligados ao disco e a resposta em palavras (tars_operacoes, tars_nomes);
- pedidos de vários passos (tars_passos);
- perguntas sobre o mundo respondidas por um resultado do SearXNG, com o site (tars_resposta_web).

resolver() devolve o texto da resposta, ou None: aí o pedido segue para o modelo, como antes. Os comandos passam por
executar_ferramenta, então valem as mesmas regras de segurança e o mesmo cartão de aprovação do resto do app.
As operações de arquivo só valem no Linux (os comandos são de bash e GNU); no Windows e no macOS o modelo continua com elas.
"""
import os
import re
import shlex
import time
import unicodedata

import tars_conta
import tars_email
import tars_integracoes
import tars_lembretes
import tars_midia
import tars_operacoes as operacoes
import tars_passos as passos
import tars_regras_terminal as regras_terminal
import tars_sistema_frases as sistema_frases
import tars_resposta_web as resposta_web
from tars_atalhos_textos import t

_MARCAS_PT = re.compile(r"[ãõçáéíóúâêô]|\b(o|os|as|um|uma|de|do|da|que|qual|quanto|quanta|quem|como|onde|por|para|pra|meu|minha|tem|tenho|e|é|cria|faz|lembra|esquece|"
                        r"em|no|na|foi|isso|voce|você|eu|quando|sim|não|nao|tá|ta|está|esta|mostra|apaga|copia|move|abre)\b", re.IGNORECASE)
_MARCAS_EN = re.compile(r"\b(the|an|of|what|which|who|how|where|is|are|my|me|do|does|can|please|create|make|remember|forget|search|and|in|to|when|did|was|"
                        r"were|has|have|it|this|that|you|your|i|show|delete|copy|move|open|file|folder)\b", re.IGNORECASE)


def idioma_do(texto):
    pt, en = len(_MARCAS_PT.findall(texto)), len(_MARCAS_EN.findall(texto))
    return "en" if en > pt else "pt"


def normalizar(texto):
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)).lower().strip()


# ---------------- estado do computador ----------------
_DA_ASSISTENTE = re.compile(r"\b(sua memoria|your memory|na memoria|da memoria|in memory|from memory|to memory|de mim|about me)\b")
_MEMORIA = re.compile(r"\b(ram|memoria|memory)\b")
_QUANTO = re.compile(r"\b(quanta|quanto|livre|disponivel|sobrando|sobrou|usada|uso|usando|how much|free|usage|used|left|available)\b")
_AVALIA = re.compile(r"\b(acabando|acabou|cheia|cheio|lotad[oa]|pouca|pouco|suficiente|enough|running out|low|full|tranquil\w*|apertad[oa]|limite|limit|"
                     r"sobrecarregad[oa]|ocupad[oa]|busy|pesad[oa]|heavy|alta|alto|high|ok|bem|fine|aguenta|aguentando|handle|almost|quase)\b")
_DISCO = re.compile(r"\b(disco|disk|armazenamento|storage|ssd|hd|espaco livre|espaco no|espaco em disco|free space|drive)\b")
_TAMANHO = re.compile(r"(\d+(?:[.,]\d+)?)\s*(tb|gb|g|giga\w*|mb|m|mega\w*|kb)\b")
_CABE = re.compile(r"\b(da pra|da para|cabe|caberia|cabem|consigo|posso|tem espaco|tem lugar|sobra espaco|is there (?:enough )?(?:room|space|memory)|"
                   r"enough (?:space|room|memory|ram)|can i (?:download|fit|store|save|run|keep|open)|fits?|would fit|aguenta|can it (?:run|handle))\b")
_USA_RAM = re.compile(r"\b(ram|memoria|memory|rodar|roda|run|running|abrir|open|programa|program|processo|process|app|aplicativo|servico|service|jogo|game)\b")
_CPU = re.compile(r"\b(uso|carga|usage|load|busy|ocupad[oa])\b.{0,15}\b(cpu|processador|processor)\b|\b(cpu|processador|processor)\b.{0,20}"
                  r"\b(uso|carga|usage|load|ocupad[oa]|busy|sobrecarregad[oa]|pesad[oa]|aguenta\w*)\b|\b(quantos nucleos|how many (cpu )?cores)\b")
_LIGADO = re.compile(r"\buptime\b|\b(ha )?quanto tempo\b.{0,30}\b(ligad|rodando)|\bhow long\b.{0,30}\b(running|been on|been up|up)\b")
_DE_PROCESSO = re.compile(r"\b(processos?|process(es)?|programas?|apps?|aplicativos?|quem esta|what'?s|whats|which program|o que esta)\b.{0,30}"
                          r"\b(usando|comendo|gastando|consumindo|using|eating|hogging|taking)\b")


def _folga(livre, total, idioma):
    parte = livre / total if total else 1
    return t("folga_boa" if parte > 0.3 else "folga_media" if parte > 0.1 else "folga_pouca", idioma)


def _memoria_mb():
    import psutil
    m = psutil.virtual_memory()
    return m.total // 2**20, m.available // 2**20       # disponível, não a coluna "free" (o cache conta como livre)


def _disco_gb():
    import shutil
    d = shutil.disk_usage(os.path.expanduser("~"))
    return d.total / 1e9, d.free / 1e9


def estado(n, idioma):
    if _DA_ASSISTENTE.search(n) or _DE_PROCESSO.search(n):
        return None
    tamanho = _TAMANHO.search(n)
    if tamanho and _CABE.search(n):
        valor = float(tamanho.group(1).replace(",", "."))
        mb = valor * {"t": 1024 * 1024, "g": 1024, "m": 1, "k": 1 / 1024}[tamanho.group(2)[0]]
        pedido = f"{tamanho.group(1)} {tamanho.group(2).upper()}"
        if _USA_RAM.search(n) and not re.search(r"\b(baixar|download|salvar|save|guardar|store|disco|disk|arquivo|file)\b", n):
            total, livre = _memoria_mb()
            return t("cabe_ram" if mb < livre * 0.9 else "nao_cabe_ram", idioma, livre=livre, pedido=pedido)
        total, livre = _disco_gb()
        return t("cabe_disco" if mb < livre * 1000 * 0.95 else "nao_cabe_disco", idioma, livre=livre, pedido=pedido)
    if _MEMORIA.search(n) and (_QUANTO.search(n) or _AVALIA.search(n)):
        total, livre = _memoria_mb()
        texto = t("mem", idioma, total=total, livre=livre, usada=total - livre)
        return texto + " " + _folga(livre, total, idioma) if _AVALIA.search(n) else texto
    if _DISCO.search(n) and (_QUANTO.search(n) or _AVALIA.search(n) or re.search(r"\b(espaco|space)\b", n)):
        total, livre = _disco_gb()
        texto = t("disco", idioma, total=total, livre=livre, usado=total - livre)
        return texto + " " + _folga(livre, total, idioma) if _AVALIA.search(n) else texto
    if _CPU.search(n):
        nucleos, carga = os.cpu_count() or 1, os.getloadavg()[0]
        return t("cpu", idioma, nucleos=nucleos, carga=carga) + " " + t("cpu_folga" if carga < 0.7 * nucleos else "cpu_media" if carga < nucleos else "cpu_cheia", idioma)
    if _LIGADO.search(n):
        import psutil
        segundos = int(time.time() - psutil.boot_time())
        dias, resto = divmod(segundos, 86400)
        horas, minutos = resto // 3600, resto % 3600 // 60
        return t("ligada", idioma, tempo=" ".join(p for p in (f"{dias} d" if dias else "", f"{horas} h" if horas else "", f"{minutos} min") if p))
    return None


# ---------------- memória da pessoa ----------------
_POLIDEZ = r"^(por favor,? |please,? |pode |voce pode |can you |could you |from now on,? |a partir de agora,? )?"
_LEMBRAR = re.compile(_POLIDEZ + r"(lembra|lembre|anota|anote|grava|grave|guarda|guarde|salva|salve|memoriza|memorize|nao esquece|nao esqueca|"
                      r"remember|note|save|make a note|keep in mind|don'?t forget|write down|jot down)\b( ai| isso| disso| this| na memoria| to memory)?"
                      r"( que| that|:|(?= (my|meu|minha|eu|i)\b))\s*")
_LEMBRAR_NO_FIM = re.compile(r"^(.+?)[,.]?\s+(keep that|remember that|remember this|guarda isso|lembra disso|anota isso|anota ai)[.!]?$")
_ESQUECER_TUDO = re.compile(r"^(esquece|esqueca|forget)\s+(tudo|everything)( que voce sabe( sobre mim)?| about me| you know( about me)?)?[.!]*$|"
                            r"\b(apaga|apague|limpa|limpe|zera|clear|wipe|erase|reset)\s+(toda |a |sua |your |the |all )*(memoria|memory)\b")
_ESQUECER = re.compile(_POLIDEZ + r"(esquece|esqueca|esquecer|forget)\b\s*(isso|that)?\s*(d[aeo]s?|que|about|sobre)?\s*(?P<alvo>.*)$")
_VER_MEMORIA = re.compile(r"\bo que (voce )?(lembra|guardou|sabe) (de|sobre) mim\b|\bwhat do you (remember|know)( about me)?\b|"
                          r"\b(mostra|mostre|show)( a| your)? (sua )?(memoria|memory)\b")
_VAZIAS = {"o", "a", "os", "as", "de", "do", "da", "que", "eu", "meu", "minha", "the", "of", "my", "i", "that", "isso", "about", "sobre", "is", "e"}


def memoria(pedido, n, idioma, core):
    mem = core.memoria
    if _VER_MEMORIA.search(n):
        fatos = mem.listar()
        return t("memoria", idioma, fatos="\n".join("- " + f for f in fatos)) if fatos else t("memoria_vazia", idioma)
    if _ESQUECER_TUDO.search(n):
        mem.esquecer("*")
        return t("esqueci_tudo", idioma)
    achado = _LEMBRAR.search(n) or None
    if achado:
        fato = pedido.strip()[achado.end():].strip(" .") if len(pedido.strip()) == len(n) else n[achado.end():].strip(" .")
        ok, _ = mem.lembrar(fato) if fato else (False, None)
        return t("anotado", idioma, fato=fato) if ok else None
    achado = _LEMBRAR_NO_FIM.search(n)
    if achado:
        fato = (pedido.strip() if len(pedido.strip()) == len(n) else n)[:achado.end(1)]
        ok, _ = mem.lembrar(fato)
        return t("anotado", idioma, fato=fato) if ok else None
    achado = _ESQUECER.search(n)
    if achado and achado.group("alvo"):
        palavras = [p for p in re.findall(r"[\w-]+", achado.group("alvo")) if p not in _VAZIAS and len(p) > 2]
        fatos = mem.listar()
        notas = [(sum(normalizar(p) in normalizar(f) for p in palavras), f) for f in fatos]
        melhor = max((x for x, _ in notas), default=0)
        if not melhor:
            return t("nada_guardado", idioma)
        saiu = [f for x, f in notas if x == melhor]
        for f in saiu:
            mem.esquecer(f)
        return t("esqueci", idioma, fato="; ".join(saiu))
    return None


# ---------------- comandos (operações de arquivo) ----------------
def _rodar(core, comando):
    """O resultado no formato que tars_operacoes.resumir lê (o do openTARS Pi)."""
    r = core.executar_ferramenta("execute_terminal", {"command": comando})
    r = r if isinstance(r, dict) else {}
    return {"success": bool(r.get("sucesso")), "exit_code": r.get("codigo"), "stdout": r.get("stdout") or "",
            "stderr": r.get("stderr") or "", "message": r.get("mensagem") or ""}


def _com_saida(texto, saida):
    linhas = [l for l in (saida or "").rstrip().splitlines()][:40]
    bloco = "```\n" + "\n".join(linhas) + "\n```" if linhas else ""
    return "\n\n".join(p for p in (texto, bloco) if p)


def comando(plano, idioma, core, estado_passos):
    """Roda o comando de uma operação e devolve (resposta, deu_certo)."""
    r = _rodar(core, plano["comando"])
    estado_passos["resultado"], estado_passos["comando"] = r, plano["comando"]
    if "did not confirm" in r["message"] or "cancelled by the user" in r["message"].lower():
        return t("negado", idioma), False           # a pessoa disse não: sem o texto em inglês do controle
    nada_achado = plano.get("resumo") in ("ocorrencias", "arquivos_com") and r["exit_code"] == 1 and not r["stderr"].strip()
    if not r["success"] and not nada_achado:
        erro = (r["stderr"] or r["message"] or "?").strip().splitlines()
        return t("falhou", idioma, erro=erro[-1] if erro else "?"), False
    if plano.get("lugar"):
        estado_passos["lugar"] = plano["lugar"]
    elif plano["comando"].startswith("mkdir -p ") and "&&" not in plano["comando"]:
        estado_passos["lugar"] = shlex.split(plano["comando"])[-1]          # a pasta criada vira o "ela" do passo seguinte
    if plano.get("alvo"):
        estado_passos["alvo"] = plano["alvo"]
    resumo = operacoes.resumir(plano, r, idioma)
    if resumo:
        return " ".join(p for p in (plano.get("nota"), resumo) if p), True
    if not r["stdout"].strip():
        return " ".join(p for p in (plano.get("nota"), plano.get("feito") or t("feito", idioma)) if p), True
    return _com_saida(plano.get("nota") or "", r["stdout"]), True


def _plano(pedido, n, idioma, linux):
    if not linux:
        return None
    p = operacoes.plano(pedido, n, idioma) or regras_terminal.plano(pedido, n, idioma)
    return {"comando": p} if isinstance(p, str) else p


def _uma_parte(pedido, idioma, core, estado_passos, linux, permitir_mundo=True):
    """(resposta, deu_certo) de uma frase, ou None se é com o modelo."""
    import tars_plataforma
    n = normalizar(pedido)
    fala = (tars_lembretes.resposta_da_rotina(pedido) or tars_lembretes.agendar(pedido, idioma) or tars_integracoes.responder(pedido, idioma)
            or tars_midia.responder(pedido, idioma)
            or tars_email.responder(pedido, idioma, core)
            or memoria(pedido, n, idioma, core))
    if fala:
        return fala, True
    if not linux:                    # 5.3: Windows e macOS: as mesmas frases, executadas direto (volume, brilho, tema, Wi-Fi, bloquear)
        fala = sistema_frases.responder_outros(n, idioma, tars_plataforma.sistema(), core)
        if fala:
            return fala, True
    plano = sistema_frases.plano(n, idioma) if linux else None
    plano = plano or _plano(pedido, n, idioma, linux)
    if plano:
        if "fala" in plano:
            return plano["fala"], True
        return comando(plano, idioma, core, estado_passos)
    fala = estado(n, idioma) or tars_conta.resolver(n, idioma)
    if fala:
        return fala, True
    if permitir_mundo:
        fala = mundo(pedido, n, idioma)
        if fala:
            return fala, True
    return None


# ---------------- perguntas sobre o mundo ----------------
_PERGUNTA = re.compile(r"^(quem|qual|quais|quando|onde|quanto|quanta|quantos|quantas|em que ano|o que e|o que foi|what|who|which|when|where|how (tall|far|high|long|big|many|much|old)|"
                       r"in what year|what year)\b")
_PESSOAL = re.compile(r"\b(voce|seu|sua|you|your|eu|meu|minha|meus|minhas|me|mim|my|i|computador|computer|pc|arquivo|arquivos|file|files|pasta|folder|disco|disk|"
                      r"memoria|memory|ram|cpu|processador|processor|wifi|internet|placa|ip|senha|password|lembr|remind|timer|alarme|alarm)\b")


def mundo(pedido, n, idioma):
    """Uma frase de um resultado do SearXNG que responde, com o site. None: sem SearXNG ligado, sem resultado bom, ou não é pergunta sobre o mundo."""
    if not _PERGUNTA.search(n) or _PESSOAL.search(n):
        return None
    try:
        import tars_web
        if not tars_web.config()["ligada"]:
            return None
        achado = resposta_web.responder(pedido.strip(" ?"))
    except Exception:  # noqa: BLE001 - sem busca, o modelo responde como antes
        return None
    if not achado:
        return None
    import urllib.parse
    site = urllib.parse.urlsplit(achado["url"]).hostname or achado["url"]
    return t("de_onde", idioma, site=site, trecho=achado["trecho"])


# ---------------- entrada ----------------
def resolver(texto, core):
    """A resposta sem o modelo, ou None. core: o módulo tars (memória, executar_ferramenta)."""
    texto = (texto or "").strip()
    if not texto or len(texto) > 400 or os.environ.get("TARS_SEM_ATALHOS"):
        return None
    import tars_plataforma
    linux = tars_plataforma.sistema() == "linux"
    idioma = idioma_do(texto)
    estado_passos = {"lugar": None, "resultado": None, "comando": None, "alvo": None}
    partes = passos.dividir(texto, normalizar(texto))
    if partes:
        falas = []
        for i, parte in enumerate(partes):
            n = normalizar(parte)
            if i and passos.pede_contagem(n) and estado_passos["resultado"]:
                saida = estado_passos["resultado"].get("stdout") or ""
                quantos = len([l for l in saida.splitlines() if l.strip()])
                falas.append(t("r_e_um", idioma) if quantos == 1 else t("r_sao", idioma, n=quantos))
                continue
            destino = passos.salvar_em(n) if i else None
            if destino:
                anterior = estado_passos["comando"] if (estado_passos["resultado"] or {}).get("success") else None
                if not anterior or not linux:
                    if i == 1 and not falas:
                        return None
                    falas.append(t("nada_para_salvar", idioma))
                    break
                comeco = n.rfind(destino)
                destino = parte[comeco:comeco + len(destino)] if comeco >= 0 else destino
                resposta, ok = comando({"comando": f"{anterior} > {operacoes._q(destino)}"}, idioma, core, estado_passos)
            else:
                parte = passos.com_lugar(parte, estado_passos["lugar"]) if i else parte
                feito = _uma_parte(parte, idioma, core, estado_passos, linux, permitir_mundo=False)
                if feito is None and i and estado_passos["alvo"]:
                    feito = _uma_parte(f"{parte} {'de' if idioma == 'pt' else 'of'} {estado_passos['alvo']}", idioma, core, estado_passos, linux, False)
                if feito is None:
                    if i == 0:
                        return None          # o primeiro passo não é de regra: o pedido inteiro vai para o modelo
                    falas.append(t("falhou", idioma, erro=parte))
                    break
                resposta, ok = feito
            if resposta and (not falas or resposta != falas[-1]):
                falas.append(resposta)
            if not ok:
                break
        return "\n".join(falas) if falas else None
    feito = _uma_parte(texto, idioma, core, estado_passos, linux)
    return feito[0] if feito else None
