"""Os pedidos de terminal mais comuns viram comando por regra, com o caminho exato que a pessoa escreveu.

Medido em 06/11: o modelo de 270M acerta a intenção, mas troca o caminho (`apaga /tmp/velho.txt` virou `rm -rf ~/Documents/velho.txt`)
em 8 de 20 pedidos. Aqui o comando sai certo e na hora; ele passa pela mesma aprovação de qualquer outro.
"""
import os
import re
import shlex
import shutil

from tars_atalhos_textos import t

_CAMINHO = r"(~?/[^\s'\"?,;]*|(?:[\w.-]+/)+[\w.-]+|[\w.-]+\.[A-Za-z0-9]{1,6})"


_PASTAS = {"documentos": "Documents", "area de trabalho": "Desktop", "imagens": "Pictures", "musicas": "Music", "home": "", "pessoal": ""}
_NOMES = r"(downloads|documents|documentos|desktop|area de trabalho|pictures|imagens|music|musicas|videos|home|pessoal)\b"


def _q(caminho):
    """O caminho entre aspas, mantendo o ~ fora delas para o shell expandir."""
    caminho = caminho.rstrip(".")
    if caminho.startswith("~/"):
        return "~/" + shlex.quote(caminho[2:])
    return shlex.quote(caminho)


def _eh_pasta(caminho):
    return os.path.isdir(os.path.expanduser(caminho))


def _achar(padrao, n):
    return re.search(padrao, n)


_RODAR = re.compile(r"^(?:please |por favor |pode |can you |could you )?(?:run|execute|exec|launch|start|roda|rode|rodar|executa|executar|inicia|inicie)\s+(?:o |a |the )?(?:comando |command |programa |program )?"
                    r"(.+?)(?:\s+(?:on|in|no|na|pelo|pela)\s+(?:o |a |the |this |esta |este )?(?:terminal|shell|console|board|placa))?[.!?]?$")
_SO_TELA = {"top": "top -bn1 | head -20", "htop": "top -bn1 | head -20", "btop": "top -bn1 | head -20"}     # interativos não têm tela aqui


def _programa(linha):
    """O comando, se a linha é mesmo um programa desta máquina. "run a speed test" não é; "run fastfetch" sempre é tentado, para a falta dele aparecer."""
    partes = linha.split()
    if not partes or (len(partes) > 1 and not shutil.which(partes[0])) or partes[0].startswith("-"):
        return None
    if len(partes) > 1 and not any(p.startswith(("-", "/", "~", ".")) or "=" in p for p in partes[1:]):
        return None             # "start a timer" ou "run the tests": frase, não comando
    return _SO_TELA.get(partes[0], linha)


_GERENTES = (("apt-get", "sudo apt install -y {p}"), ("dnf", "sudo dnf install -y {p}"), ("pacman", "sudo pacman -S --noconfirm {p}"),
             ("zypper", "sudo zypper install -y {p}"))


def _instalar(n):
    """"instala o vlc" -> o comando do gerenciador desta máquina (o modelo escrevia `apt install -yvlc`)."""
    a = re.match(r"^(?:por favor |please |pode |can you |could you )?(?:instala|instale|instalar|install|baixa e instala|bota)\s+(?:o |a |os |as |the |me )?"
                 r"(?:programa |pacote |app |aplicativo |package |program )?([a-z0-9][a-z0-9.+-]{1,40})(?:\s+(?:pra mim|para mim|for me|aqui|here))?\s*[.!?]*$", n)
    if not a or a.group(1) in ("um", "uma", "a", "an", "isso", "it", "this", "that", "tudo", "everything", "atualizacoes", "updates"):
        return None
    pacote = {"python": "python3", "pip": "python3-pip", "node": "nodejs", "chrome": "chromium", "code": "code"}.get(a.group(1), a.group(1))
    comando = next((modelo.format(p=pacote) for programa, modelo in _GERENTES if shutil.which(programa)), None)
    if comando and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")) and shutil.which("pkexec"):
        comando = comando.replace("sudo apt install", "pkexec apt-get install").replace("sudo ", "pkexec ")   # o app roda sem terminal: a senha vem pela janela do sistema
    return comando


def plano(pedido, n, idioma="pt"):
    """O comando para o pedido, ou None. pedido: como a pessoa escreveu. n: normalizado, do mesmo tamanho quando possível."""
    original = pedido.strip() if len(pedido.strip()) == len(n) else n
    instalar = _instalar(n)
    if instalar:
        return instalar
    a = _RODAR.match(n)
    if a and (comando := _programa(original[a.start(1):a.end(1)])):
        programa = original[a.start(1):a.end(1)].split()[0]
        if not shutil.which(programa):          # dizer como instalar vale mais que "command not found"
            if programa in _SO_TELA:
                return {"comando": comando, "nota": t("htop_falta", idioma)}
            return {"fala": t("nao_instalado", idioma, programa=programa, pacote=programa)}
        return comando
    if re.fullmatch(r"[a-z0-9_.-]+( +(-{1,2}[\w-]+|[/~.][^\s]*))+", n) and shutil.which(n.split()[0]):    # "df -h": já é um comando
        return original

    def grupo(achado, numero):
        return original[achado.start(numero):achado.end(numero)]

    # escrever num arquivo
    a = _achar(r"\b(?:cria|crie|criar|faz|faca|make|create)\b.{0,15}\b(?:arquivo|file)\b(?: chamado| named| called)?\s+" + _CAMINHO + r"\s+(?:com|with)(?: o| the)?(?: texto| text| conteudo| content)?\s+(.+)$", n)
    if a:
        return f"printf '%s\\n' {shlex.quote(grupo(a, 2).strip(' .'))} > {_q(grupo(a, 1))}"
    a = _achar(r"\b(?:escreve|escreva|escrever|write|put|grava|grave|salva|salve|save)\s+(?:o texto |the text )?(.+?)\s+(?:no arquivo|num arquivo|em um arquivo|em|to the file|to a file named|to a file called|to|into|in)\s+" + _CAMINHO + r"\s*$", n)
    if a:
        return f"printf '%s\\n' {shlex.quote(grupo(a, 1).strip(chr(34) + chr(39)))} > {_q(grupo(a, 2))}"
    a = _achar(r"\b(?:cria|crie|criar|faz|faca|make|create)\b.{0,15}\b(?:arquivo|file)\b(?: vazio)?(?: chamado| named| called)?\s+" + _CAMINHO + r"\s*$", n)
    if a:
        return f"touch {_q(grupo(a, 1))}"
    # pastas
    sem_home = re.sub(r"\s+(?:na|em|in)\s+(?:minha |my |a )?home\s*$", "", n)
    a = _achar(r"\b(?:pasta|diretorio|folder|directory)\b(?: nova| novo)?(?: chamada| chamado| called| named)?\s+([\w.-]+)\s+(?:dentro d[eao]|em|na|no|in|inside|under)\s+(?:a pasta |the folder )?" + _CAMINHO, n)
    if a and _achar(r"\b(cria|crie|criar|faz|faca|make|create|new|nova)\b", n):
        return "mkdir -p " + _q(grupo(a, 2).rstrip("/") + "/" + grupo(a, 1))
    a = _achar(r"\b(?:cria|crie|criar|faz|faca|make|create|new|nova)\b.{0,20}\b(?:pasta|diretorio|folder|directory)\b(?: chamada| chamado| called| named)?\s+(?:a |the )?" + r"(~?/[^\s'\"?,;]*|[\w.-]+)\s*$", sem_home)
    if a:
        destino = grupo(a, 1)
        return "mkdir -p " + _q(destino if destino.startswith(("/", "~")) else "~/" + destino)
    a = _achar(r"\b(?:cria|crie|criar|faz|faca|make|create|new|nova)\b.{0,20}\b(?:pasta|diretorio|folder|directory)\b\s+(?:em|na|no|in|inside|under|dentro d[eao])\s+" + _CAMINHO + r"\s+(?:chamada|chamado|called|named)\s+([\w.-]+)", n)
    if a:
        return "mkdir -p " + _q(grupo(a, 1).rstrip("/") + "/" + grupo(a, 2))
    # copiar e mover
    a = _achar(r"\b(cp|copia|copie|copiar|copy)\s+(?:o arquivo |a pasta |the file |the folder )?" + _CAMINHO + r"\s+(?:para|pra|to|em|into)\s+(?:a pasta |the folder )?" + _CAMINHO, n)
    if a:
        return f"cp -r {_q(grupo(a, 2))} {_q(grupo(a, 3))}"
    a = _achar(r"\b(mv|move|mova|mover|renomeia|renomeie|renomear|rename)\s+(?:o arquivo |a pasta |the file |the folder )?" + _CAMINHO + r"\s+(?:para|pra|to|em|into|as|como)\s+(?:a pasta |the folder )?" + _CAMINHO, n)
    if a:
        return f"mv {_q(grupo(a, 2))} {_q(grupo(a, 3))}"
    # esvaziar uma pasta ("apaga tudo da pasta /tmp"): o modelo trazia o comando da pergunta anterior
    a = _achar(r"\b(?:apaga|apague|apagar|deleta|delete|remove|remova|limpa|limpe|limpar|esvazia|esvazie|esvaziar|clear|empty|wipe)\b\s+"
               r"(?:(?:tudo|todo o conteudo|o conteudo|todos os arquivos|everything|all files|all|the contents)\s+(?:da|de|do|na|no|of|in|inside|from)\s+)?"
               r"(?:a pasta |the folder |pasta |folder |o diretorio |the directory )" + _CAMINHO, n) or \
        _achar(r"\b(?:apaga|apague|apagar|deleta|delete|remove|remova|limpa|limpe|limpar|esvazia|esvazie|clear|empty|wipe)\b\s+"
               r"(?:tudo|todo o conteudo|o conteudo|todos os arquivos|everything|all files|all|the contents)\s+(?:da|de|do|na|no|of|in|inside|from)\s+" + _CAMINHO, n)
    if a and _achar(r"\b(tudo|conteudo|todos|everything|all|contents|esvazia|esvazie|esvaziar|limpa|limpe|limpar|empty|clear|wipe)\b", n):
        pasta = grupo(a, 1).rstrip("/")
        if os.path.realpath(os.path.expanduser(pasta or "/")) in ("/", os.path.realpath(os.path.expanduser("~"))):
            return None          # a raiz ou a pasta pessoal inteira: não vira regra, mesmo pedindo para digitar
        return f"rm -rf -- {_q(pasta)}/*"
    # apagar
    a = _achar(r"\b(?:apaga|apague|apagar|deleta|delete|deletar|remove|remova|remover|exclui|exclua|excluir|rm)\s+(?:o arquivo |a pasta |the file |the folder |o |a |the )?" + _CAMINHO, n)
    if a:
        caminho = grupo(a, 1)
        return ("rm -r " if _eh_pasta(caminho) else "rm ") + _q(caminho)
    # procurar arquivos
    a = _achar(r"\b(?:procura|procure|acha|ache|encontra|encontre|find|locate|search for)\b.{0,20}\b(?:arquivos?|files?)\b(?: chamados?| named| called| com nome)?\s+(?:terminados em |ending in )?([\w*.?-]+)\s+(?:em|na|no|in|under)\s+" + _CAMINHO, n)
    if a:
        nome = grupo(a, 1)
        nome = "*" + nome if nome.startswith(".") else nome
        return f"find {_q(grupo(a, 2))} -name {shlex.quote(nome)} 2>/dev/null | head -50"
    a = _achar(r"\b(?:procura|procure|acha|ache|encontra|encontre|find|locate|list|lista)\b(?: all| the| todos os| os)*\s+(\*?\.[\w-]+|\*[\w.*?-]*)\s+(?:arquivos|files)\s+(?:em|na|no|in|under)\s+" + _CAMINHO, n)
    if a:
        nome = grupo(a, 1)
        return f"find {_q(grupo(a, 2))} -name {shlex.quote('*' + nome if nome.startswith('.') else nome)} 2>/dev/null | head -50"
    a = _achar(r"\b(?:procura|procure|acha|ache|encontra|encontre|find|locate|list|lista|liste|mostra|mostre)\b(?: all| the| todos os| os| my| meus)*\s+"
               r"(?:(?:arquivos|files)\s+(?:terminados em |ending in |com extensao |with extension |do tipo )?(\*?\.[a-z0-9]{1,8})|(\*?\.[a-z0-9]{1,8})\s+(?:arquivos|files))"
               r"(?:\s+(?:em|na|no|in|on|under)\s+(?:a |minha |my |the )?(?:home|pasta pessoal|home folder|placa|board|pasta inicial))?\s*[?.!]*$", n)
    if a:
        nome = a.group(1) or a.group(2)
        return f"find ~ -name {shlex.quote(nome if nome.startswith('*') else '*' + nome)} -not -path '*/.*' 2>/dev/null | head -50"
    # procurar dentro de um arquivo
    a = _achar(r"\b(?:procura|procure|busca|busque|acha|ache|encontra|encontre|search|find|look)\b(?: for)?(?: a palavra| o texto| the word| the text)?\s+[\"']?([\w-]+)[\"']?\s+"
               r"(?:dentro d[eao]|no|na|em|in|inside)\s+(?:o arquivo |the file )?" + _CAMINHO, n)
    if a and not _eh_pasta(grupo(a, 2)):
        return f"grep -n -- {shlex.quote(grupo(a, 1))} {_q(grupo(a, 2))} | head -50"
    # contar e medir
    a = _achar(r"\b(?:linhas|lines)\b.{0,25}?" + _CAMINHO, n) or _achar(_CAMINHO + r".{0,10}\b(?:linhas|lines)\b", n)
    if a and _achar(r"\b(conta|conte|contar|count|quantas|how many)\b", n):
        return "wc -l " + _q(grupo(a, 1))
    a = _achar(r"\b(?:quantos arquivos|how many files)\b.{0,20}?" + _CAMINHO, n)
    if a:
        return f"ls -1 {_q(grupo(a, 1))} | wc -l"
    a = _achar(r"\b(?:tamanho|quanto ocupa|quanto pesa|quanto espaco|how big|how large|how much space|size of|disk usage of)\b.{0,25}?" + _CAMINHO, n)
    if a:
        return "du -sh " + _q(grupo(a, 1))
    a = _achar(r"\b(?:tamanho|quanto ocupa|quanto pesa|quanto espaco|how big|how large|how much space|size of|disk usage of)\b.{0,25}?\b(?:my|minha|meus|meu|a|na|da|the)?\s*(?:pasta |folder )?" + _NOMES, n)
    if a:
        pasta = _PASTAS.get(a.group(1), a.group(1).capitalize())
        return "du -sh ~/" + (shlex.quote(pasta) if pasta else "")
    # olhar
    a = _achar(r"\b(?:(primeiras|first|ultimas|last)\s+(\d{1,4})|(\d{1,4})\s+(primeiras|ultimas))\s+(?:linhas|lines)\b.{0,20}?" + _CAMINHO, n)
    if a:
        programa = "head" if (a.group(1) or a.group(4)) in ("primeiras", "first") else "tail"
        return f"{programa} -n {a.group(2) or a.group(3)} {_q(grupo(a, 5))}"
    a = _achar(r"\b(?:lista|liste|listar|list|ls|mostra|mostre|show|ver|veja|o que tem|what is|what's|whats|conteudo|contents)\b.{0,30}?" + _CAMINHO, n)
    if a:
        caminho = grupo(a, 1)
        if _eh_pasta(caminho) or caminho.endswith("/"):
            return "ls -la " + _q(caminho)
        return "head -n 100 " + _q(caminho)
    a = _achar(r"\b(?:le|leia|ler|read|exibe|print|display|cat|abre|abra|open)\b.{0,25}?" + _CAMINHO, n)
    if a:
        return "head -n 100 " + _q(grupo(a, 1))
    # as pastas da pessoa, pelo nome
    a = _achar(r"\b(?:lista|liste|listar|list|mostra|mostre|show|ver|veja|o que tem|what is in|what's in|whats in|what's inside|contents of)\b.{0,25}?\b(?:my|minha|meus|meu|a|na|da)?\s*(?:pasta )?" + _NOMES, n)
    if a:
        literal = original[a.start(1):a.end(1)]
        pasta = literal if os.path.isdir(os.path.expanduser("~/" + literal)) else _PASTAS.get(a.group(1), a.group(1).capitalize())   # a pasta "Imagens" que existe ganha do apelido
        return "ls -la ~/" + (shlex.quote(pasta) if pasta else "")
    # o sistema
    if _achar(r"\b(processos?|processes|what is running|what's running|whats running|o que esta rodando|programas rodando)\b", n) and not _achar(r"\b(mata|mate|matar|kill|encerra|encerre|para|pare|stop)\b", n):
        return "ps aux --sort=-%" + ("cpu" if _achar(r"\b(cpu|processador)\b", n) else "mem") + " | head -8"
    if _achar(r"\b(tem internet|estou online|esta online|am i online|internet working|internet funcionando|testa a internet|test the internet)\b", n):
        return "ping -c 2 -W 3 1.1.1.1"
    a = _achar(r"^(?:ping|pinga)\s+([\w.-]+)", n)
    if a:
        return f"ping -c 3 -W 3 {shlex.quote(a.group(1))}"
    if _achar(r"\b(versao do kernel|kernel version|qual kernel|que kernel|which kernel|what kernel)\b", n) and not _achar(r"\b(ultima|mais nova|latest|newest)\b", n):
        return "uname -r"
    if _achar(r"\b(portas? (?:estao )?abertas?|portas? em uso|open ports?|listening ports?|ports? (?:are )?open)\b", n):
        return "ss -tuln"
    if _achar(r"\b(quem esta logado|quem esta conectado|who is logged in|who's logged in)\b", n):
        return "who"
    if _achar(r"\b(usuarios|users|contas de usuario|user accounts)\b", n) and _achar(r"\b(quais|que|quantos|lista|liste|mostra|mostre|existem|tem|which|what|list|show|how many|are there)\b", n):
        return "ls /home"
    a = _achar(r"\b(?:log|logs|journal|registro) (?:do sistema|da placa|do kernel|of the system)\b|\bsystem ?logs?\b|\b(?:journal|syslog)\b", n)
    if a:
        quantas = _achar(r"\b(\d{1,3})\b", n)
        return f"journalctl -n {quantas.group(1) if quantas else 20} --no-pager"
    return None
