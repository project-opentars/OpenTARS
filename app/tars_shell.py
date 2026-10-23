"""5.2 (F5): um mini-shell em Python para os comandos de bash que o Gargantua aprendeu, onde não há bash (Windows) ou
onde o comando não existe (macOS: `free`, `gio trash`). Só biblioteca padrão (e psutil para o `free`).

Os dados de treino (20/10, 2.408 chamadas de execute_terminal) são quase todos destas formas, e é o que este arquivo cobre:
    echo/printf 'texto' > arquivo (e >>)     mkdir -p pasta && echo ... > pasta/arq     ls -1 pasta | wc -l
    mv a b     rm -rf pasta     touch arq     free -h     cat arq     wc -l arq     find pasta -name x
com `~`, `${HOME}`, `$HOME`, `$(xdg-user-dir DOCUMENTS)`, aspas e espaços escapados (`Área\\ de\\ Trabalho`).
A saída imita a do GNU (é o que o modelo viu no treino). As regras de comando perigoso continuam valendo antes daqui,
porque leem o mesmo texto de bash.

    suportado(comando) -> bool         todo comando da linha está aqui
    executar(comando, cwd=None) -> {"sucesso", "codigo", "stdout", "stderr", "mensagem"}   (o formato do executar_terminal)
"""
import datetime as dt
import fnmatch
import glob
import os
import re
import shutil
from pathlib import Path

import tars_plataforma as plataforma

OPERADORES = ("&&", "||", ";", "|", ">>", ">", "2>&1", "2>")
PASTAS_XDG = {"DESKTOP": "Desktop", "DOCUMENTS": "Documents", "DOWNLOAD": "Downloads", "MUSIC": "Music",
              "PICTURES": "Pictures", "VIDEOS": "Videos"}


class ErroDeShell(Exception):
    pass


# ------------------------------------------------------------
# Leitura da linha: palavras (com o que estava entre aspas) e operadores
# ------------------------------------------------------------
class Palavra(str):
    """Uma palavra já sem aspas; `glob` diz se tinha * ou ? fora de aspas (só essas se expandem)."""
    glob = False


def _variavel(nome):
    if nome == "HOME":
        return str(plataforma.pastas()["casa"])
    if nome == "USER":
        return plataforma.pastas()["casa"].name
    return os.environ.get(nome, "")


def _substituir_comando(texto):
    """Só o que aparece no treino: $(xdg-user-dir NOME) e $(pwd)."""
    m = re.fullmatch(r"\s*xdg-user-dir\s+([A-Z]+)\s*", texto)
    if m:
        return str(pasta_do_usuario(m.group(1)))
    if texto.strip() == "pwd":
        return os.getcwd()
    raise ErroDeShell(f"command substitution not supported: $({texto})")


def pasta_do_usuario(chave):
    """Documents, Desktop, Downloads...: no Linux pelo user-dirs.dirs; fora dele, a pasta de nome em inglês."""
    casa = plataforma.pastas()["casa"]
    if plataforma.sistema() == "linux":
        try:
            config = Path(os.environ.get("XDG_CONFIG_HOME") or casa / ".config")
            texto = (config / "user-dirs.dirs").read_text(encoding="utf-8")
            m = re.search(rf'^XDG_{chave}_DIR="(.+)"', texto, re.M)
            if m:
                return Path(m.group(1).replace("$HOME", str(casa)))
        except OSError:
            pass
    return casa / PASTAS_XDG.get(chave, chave.title())


def tokens(linha):
    """Lista de Palavra e de operadores (str). Levanta ErroDeShell com aspas abertas."""
    saida, atual, tem, i, n = [], [], False, 0, len(linha)
    glob_fora = False

    def fechar():
        nonlocal atual, tem, glob_fora
        if tem:
            p = Palavra("".join(atual))
            p.glob = glob_fora
            saida.append(p)
        atual, tem, glob_fora = [], False, False

    while i < n:
        c = linha[i]
        if c in " \t\n":
            fechar()
            i += 1
            continue
        op = next((o for o in OPERADORES if linha.startswith(o, i)), None)
        if op and not (op == "2>" and tem) and not (op == "2>&1" and tem):
            if op in (">", ">>", "2>") and tem and atual == ["2"]:
                atual, tem = [], False
                op = "2>"
            fechar()
            saida.append(op)
            i += len(op)
            continue
        if c == "\\" and i + 1 < n:
            atual.append(linha[i + 1])
            tem = True
            i += 2
            continue
        if c == "'":
            fim = linha.find("'", i + 1)
            if fim < 0:
                raise ErroDeShell("unterminated single quote")
            atual.append(linha[i + 1:fim])
            tem = True
            i = fim + 1
            continue
        if c == '"':
            i += 1
            while i < n and linha[i] != '"':
                if linha[i] == "\\" and i + 1 < n and linha[i + 1] in '"\\$`':
                    atual.append(linha[i + 1])
                    i += 2
                    continue
                if linha[i] == "$":
                    texto, i = _ler_dolar(linha, i)
                    atual.append(texto)
                    continue
                atual.append(linha[i])
                i += 1
            if i >= n:
                raise ErroDeShell("unterminated double quote")
            tem = True
            i += 1
            continue
        if c == "$":
            texto, i = _ler_dolar(linha, i)
            atual.append(texto)
            tem = True
            continue
        if c == "~" and not tem and (i + 1 == n or linha[i + 1] in "/ \t;|&>"):
            atual.append(str(plataforma.pastas()["casa"]))
            tem = True
            i += 1
            continue
        if c in "*?[":
            glob_fora = True
        if c in "`<(){}" and not (c in "{}" and tem):
            raise ErroDeShell(f"unsupported shell syntax: {c}")
        atual.append(c)
        tem = True
        i += 1
    fechar()
    return saida


def _ler_dolar(linha, i):
    """$VAR, ${VAR} ou $(comando) a partir de linha[i] == '$'. Devolve (texto, nova posição)."""
    if linha.startswith("$(", i):
        fim = linha.find(")", i)
        if fim < 0:
            raise ErroDeShell("unterminated $(")
        return _substituir_comando(linha[i + 2:fim]), fim + 1
    if linha.startswith("${", i):
        fim = linha.find("}", i)
        if fim < 0:
            raise ErroDeShell("unterminated ${")
        return _variavel(linha[i + 2:fim]), fim + 1
    m = re.match(r"\$([A-Za-z_]\w*)", linha[i:])
    if m:
        return _variavel(m.group(1)), i + m.end()
    return "$", i + 1


def _expandir(palavra, cwd):
    if not palavra.glob:
        return [str(palavra)]
    caminho = palavra if os.path.isabs(palavra) else os.path.join(cwd, palavra)
    achados = sorted(glob.glob(caminho), key=str.lower)
    if not achados:
        return [str(palavra)]
    return achados if os.path.isabs(palavra) else [os.path.relpath(a, cwd) for a in achados]


def _windows_caminhos(linha):
    r"""C:\Users\sam\x fora de aspas viraria C:Userssamx no bash; no Windows, as barras viram /."""
    if plataforma.sistema() != "windows":
        return linha
    return re.sub(r"(?<![\w\\])([A-Za-z]:\\[^\s\"';|&<>]*)", lambda m: m.group(1).replace("\\", "/"), linha)


# ------------------------------------------------------------
# A linha em comandos: [(sequência, [pipeline, ...]), ...]; pipeline = [(argv, redirecionamentos)]
# ------------------------------------------------------------
def _analisar(linha, cwd):
    lista, pipeline, argv, redir, ligacao = [], [], [], [], ";"
    toks = tokens(_windows_caminhos(linha))
    i = 0
    while i < len(toks):
        t = toks[i]
        if isinstance(t, Palavra):
            argv.extend(_expandir(t, cwd))
        elif t in (">", ">>", "2>"):
            if i + 1 >= len(toks) or not isinstance(toks[i + 1], Palavra):
                raise ErroDeShell(f"syntax error near {t}")
            redir.append((t, str(toks[i + 1])))
            i += 1
        elif t == "2>&1":
            redir.append(("2>&1", None))
        elif t == "|":
            pipeline.append((argv, redir))
            argv, redir = [], []
        else:   # && || ;
            pipeline.append((argv, redir))
            lista.append((ligacao, pipeline))
            pipeline, argv, redir, ligacao = [], [], [], t
        i += 1
    if argv or redir or pipeline:
        pipeline.append((argv, redir))
        lista.append((ligacao, pipeline))
    for _lig, pipe in lista:
        for argv, _r in pipe:
            if not argv:
                raise ErroDeShell("syntax error: empty command")
    return lista


def suportado(comando):
    try:
        return all(argv[0] in COMANDOS for _l, pipe in _analisar(comando, os.getcwd()) for argv, _r in pipe)
    except ErroDeShell:
        return False


# ------------------------------------------------------------
# Os comandos: cada um recebe (args, entrada, ctx) e devolve (código, saída, erro)
# ------------------------------------------------------------
class Contexto:
    def __init__(self, cwd):
        self.cwd = cwd

    def caminho(self, p):
        p = os.path.expanduser(p) if p.startswith("~") else p
        return Path(p if os.path.isabs(p) else os.path.join(self.cwd, p))


def _opcoes(args, conhecidas=""):
    """Separa -abc (letras) dos operandos; '--' encerra as opções."""
    letras, resto, fim = set(), [], False
    for a in args:
        if not fim and a == "--":
            fim = True
        elif not fim and a.startswith("-") and len(a) > 1:
            letras.update(a[1:] if not a.startswith("--") else [a])
        else:
            resto.append(a)
    return letras, resto


def c_echo(args, entrada, ctx):
    n = bool(args) and args[0] == "-n"
    e = bool(args) and args[0] in ("-e", "-ne", "-en")
    if args and args[0] in ("-n", "-e", "-ne", "-en"):
        n = "n" in args[0]
        args = args[1:]
    texto = " ".join(args)
    if e:
        texto = texto.encode("utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8", "replace")
    return 0, texto + ("" if n else "\n"), ""


def c_printf(args, entrada, ctx):
    if not args:
        return 1, "", "printf: usage: printf format [arguments]\n"
    formato, valores = args[0], list(args[1:])
    formato = formato.replace("\\n", "\n").replace("\\t", "\t")
    saida = re.sub(r"%[sd]", lambda _m: valores.pop(0) if valores else "", formato).replace("%%", "%")
    return 0, saida, ""


def c_mkdir(args, entrada, ctx):
    letras, pastas = _opcoes(args)
    erros, codigo = "", 0
    for p in pastas:
        try:
            ctx.caminho(p).mkdir(parents="p" in letras, exist_ok="p" in letras)
        except FileExistsError:
            erros, codigo = erros + f"mkdir: cannot create directory '{p}': File exists\n", 1
        except FileNotFoundError:
            erros, codigo = erros + f"mkdir: cannot create directory '{p}': No such file or directory\n", 1
    return codigo, "", erros


def c_touch(args, entrada, ctx):
    _l, arquivos = _opcoes(args)
    for a in arquivos:
        try:
            ctx.caminho(a).touch()
        except OSError as e:
            return 1, "", f"touch: cannot touch '{a}': {e.strerror}\n"
    return 0, "", ""


def c_cat(args, entrada, ctx):
    _l, arquivos = _opcoes(args)
    if not arquivos:
        return 0, entrada, ""
    saida = []
    for a in arquivos:
        try:
            saida.append(ctx.caminho(a).read_text(encoding="utf-8", errors="replace"))
        except IsADirectoryError:
            return 1, "".join(saida), f"cat: {a}: Is a directory\n"
        except OSError:
            return 1, "".join(saida), f"cat: {a}: No such file or directory\n"
    return 0, "".join(saida), ""


def c_ls(args, entrada, ctx):
    letras, alvos = _opcoes(args)
    alvos = alvos or ["."]
    saida, erros, codigo = [], "", 0
    for alvo in alvos:
        p = ctx.caminho(alvo)
        if not p.exists():
            erros, codigo = erros + f"ls: cannot access '{alvo}': No such file or directory\n", 2
            continue
        nomes = [p] if p.is_file() else sorted(p.iterdir(), key=lambda x: x.name.lower().lstrip("."))
        if p.is_dir() and not ({"a", "A"} & letras):
            nomes = [x for x in nomes if not x.name.startswith(".")]
        if len(alvos) > 1 and p.is_dir():
            saida.append(f"{alvo}:")
        for x in nomes:
            nome = alvo if x is p else x.name
            if "l" in letras:
                info = x.stat()
                tipo = "d" if x.is_dir() else "-"
                data = dt.datetime.fromtimestamp(info.st_mtime).strftime("%b %d %H:%M")
                tamanho = _humano(info.st_size) if "h" in letras else str(info.st_size)
                saida.append(f"{tipo}rw-r--r-- 1 {plataforma.pastas()['casa'].name} {tamanho:>6} {data} {nome}")
            else:
                saida.append(nome)
    return codigo, "".join(s + "\n" for s in saida), erros


def c_mv(args, entrada, ctx):
    _l, ops = _opcoes(args)
    if len(ops) < 2:
        return 1, "", "mv: missing destination file operand\n"
    destino = ctx.caminho(ops[-1])
    for origem in ops[:-1]:
        o = ctx.caminho(origem)
        if not o.exists():
            return 1, "", f"mv: cannot stat '{origem}': No such file or directory\n"
        alvo = destino / o.name if destino.is_dir() else destino
        shutil.move(str(o), str(alvo))
    return 0, "", ""


def c_cp(args, entrada, ctx):
    letras, ops = _opcoes(args)
    if len(ops) < 2:
        return 1, "", "cp: missing destination file operand\n"
    destino = ctx.caminho(ops[-1])
    for origem in ops[:-1]:
        o = ctx.caminho(origem)
        alvo = destino / o.name if destino.is_dir() else destino
        if o.is_dir():
            if not ({"r", "R", "a"} & letras):
                return 1, "", f"cp: -r not specified; omitting directory '{origem}'\n"
            shutil.copytree(o, alvo, dirs_exist_ok=True)
        elif o.exists():
            shutil.copy2(o, alvo)
        else:
            return 1, "", f"cp: cannot stat '{origem}': No such file or directory\n"
    return 0, "", ""


def c_rm(args, entrada, ctx):
    letras, alvos = _opcoes(args)
    for a in alvos:
        p = ctx.caminho(a)
        if not p.exists() and not p.is_symlink():
            if "f" not in letras:
                return 1, "", f"rm: cannot remove '{a}': No such file or directory\n"
            continue
        if p.is_dir() and not p.is_symlink():
            if not ({"r", "R"} & letras):
                return 1, "", f"rm: cannot remove '{a}': Is a directory\n"
            shutil.rmtree(p)
        else:
            p.unlink()
    return 0, "", ""


def c_rmdir(args, entrada, ctx):
    _l, alvos = _opcoes(args)
    for a in alvos:
        try:
            ctx.caminho(a).rmdir()
        except OSError:
            return 1, "", f"rmdir: failed to remove '{a}': Directory not empty\n"
    return 0, "", ""


def _contar(texto):
    return texto.count("\n"), len(texto.split()), len(texto.encode("utf-8"))


def c_wc(args, entrada, ctx):
    letras, arquivos = _opcoes(args)
    quais = [i for i, l in enumerate("lwc") if l in letras] or [0, 1, 2]
    linhas = []
    if not arquivos:
        valores = _contar(entrada)
        return 0, " ".join(str(valores[i]) for i in quais) + "\n" if len(quais) == 1 else \
            " ".join(f"{valores[i]:>7}" for i in quais) + "\n", ""
    totais = [0, 0, 0]
    for a in arquivos:
        try:
            valores = _contar(ctx.caminho(a).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            return 1, "", f"wc: {a}: No such file or directory\n"
        totais = [x + y for x, y in zip(totais, valores)]
        linhas.append(([valores[i] for i in quais], a))
    if len(arquivos) > 1:
        linhas.append(([totais[i] for i in quais], "total"))
    # o GNU alinha pela quantidade de dígitos do total de bytes quando há mais de um arquivo ou de uma coluna
    largura = len(str(max(totais[2], 1))) if len(linhas) > 1 or len(quais) > 1 else 0
    return 0, "".join(" ".join(f"{v:>{largura}}" for v in vs) + f" {nome}\n" for vs, nome in linhas), ""


def _humano(n):
    for unidade in ("B", "Ki", "Mi", "Gi", "Ti"):
        if n < 1024 or unidade == "Ti":
            if unidade == "B":
                return f"{n}B"
            return f"{n:.1f}{unidade}" if n < 10 else f"{int(n)}{unidade}"      # o GNU corta, não arredonda
        n /= 1024


def c_free(args, entrada, ctx):
    import psutil
    letras, _r = _opcoes(args)
    ram, swap = psutil.virtual_memory(), psutil.swap_memory()
    if "h" in letras:
        f = _humano
    else:
        div = 1024 ** (3 if "g" in letras else 2 if "m" in letras else 1)
        f = lambda b: str(int(b // div))  # noqa: E731
    compartilhado = getattr(ram, "shared", 0)
    cache = getattr(ram, "buffers", 0) + getattr(ram, "cached", 0)
    usado = ram.total - ram.available
    linhas = [f"{'':8}{'total':>12}{'used':>12}{'free':>12}{'shared':>12}{'buff/cache':>12}{'available':>12}",
              f"{'Mem:':8}{f(ram.total):>12}{f(usado):>12}{f(ram.free):>12}{f(compartilhado):>12}{f(cache):>12}{f(ram.available):>12}",
              f"{'Swap:':8}{f(swap.total):>12}{f(swap.used):>12}{f(swap.free):>12}"]
    return 0, "\n".join(linhas) + "\n", ""


def c_find(args, entrada, ctx):
    if not args or args[0].startswith("-"):
        args = ["."] + list(args)
    raiz, resto = args[0], args[1:]
    padrao, tipo, sem_caixa = None, None, False
    i = 0
    while i < len(resto):
        if resto[i] in ("-name", "-iname") and i + 1 < len(resto):
            padrao, sem_caixa = resto[i + 1], resto[i] == "-iname"
            i += 2
        elif resto[i] == "-type" and i + 1 < len(resto):
            tipo = resto[i + 1]
            i += 2
        elif resto[i] in ("-maxdepth",) and i + 1 < len(resto):
            i += 2
        else:
            return 1, "", f"find: unknown predicate '{resto[i]}'\n"
    base = ctx.caminho(raiz)
    if not base.exists():
        return 1, "", f"find: '{raiz}': No such file or directory\n"
    achados = []
    for pasta, dirs, arqs in os.walk(base):
        dirs.sort(key=str.lower)
        for nome in [*dirs, *sorted(arqs, key=str.lower)]:
            completo = os.path.join(pasta, nome)
            if tipo == "f" and not os.path.isfile(completo) or tipo == "d" and not os.path.isdir(completo):
                continue
            if padrao and not (fnmatch.fnmatch(nome.lower(), padrao.lower()) if sem_caixa else fnmatch.fnmatchcase(nome, padrao)):
                continue
            achados.append(completo if os.path.isabs(raiz) or raiz.startswith("~") else
                           os.path.join(raiz, os.path.relpath(completo, base)))
    return 0, "".join(a + "\n" for a in achados), ""


def c_head_tail(nome):
    def comando(args, entrada, ctx):
        n, arquivos, i = 10, [], 0
        while i < len(args):
            if args[i] == "-n" and i + 1 < len(args):
                n, i = int(args[i + 1]), i + 2
            elif re.fullmatch(r"-\d+", args[i]):
                n, i = int(args[i][1:]), i + 1
            else:
                arquivos.append(args[i])
                i += 1
        texto = entrada
        if arquivos:
            codigo, texto, erro = c_cat(arquivos, "", ctx)
            if codigo:
                return codigo, "", erro.replace("cat:", f"{nome}:")
        linhas = texto.splitlines(keepends=True)
        return 0, "".join(linhas[:n] if nome == "head" else linhas[-n:] if n else []), ""
    return comando


def c_grep(args, entrada, ctx):
    letras, ops = _opcoes(args)
    if not ops:
        return 2, "", "grep: missing pattern\n"
    padrao = re.compile(ops[0], re.I if "i" in letras else 0)
    fontes = [(None, entrada)] if len(ops) == 1 else []
    for a in ops[1:]:
        codigo, texto, erro = c_cat([a], "", ctx)
        if codigo:
            return 2, "", erro.replace("cat:", "grep:")
        fontes.append((a, texto))
    saida, achou = [], 0
    for nome, texto in fontes:
        for k, linha in enumerate(texto.splitlines(), 1):
            if bool(padrao.search(linha)) != ("v" in letras):
                achou += 1
                prefixo = (f"{nome}:" if nome and len(fontes) > 1 else "") + (f"{k}:" if "n" in letras else "")
                saida.append(prefixo + linha)
    if "c" in letras:
        return (0 if achou else 1), f"{achou}\n", ""
    return (0 if achou else 1), "".join(s + "\n" for s in saida), ""


def c_sort(args, entrada, ctx):
    letras, _o = _opcoes(args)
    linhas = sorted(entrada.splitlines(), key=str.lower, reverse="r" in letras)
    return 0, "".join(l + "\n" for l in linhas), ""


def c_pwd(args, entrada, ctx):
    return 0, ctx.cwd + "\n", ""


def c_cd(args, entrada, ctx):
    destino = ctx.caminho(args[0]) if args else plataforma.pastas()["casa"]
    if not destino.is_dir():
        return 1, "", f"cd: {args[0] if args else ''}: No such file or directory\n"
    ctx.cwd = str(destino)
    return 0, "", ""


def c_whoami(args, entrada, ctx):
    return 0, plataforma.pastas()["casa"].name + "\n", ""


def c_date(args, entrada, ctx):
    return 0, dt.datetime.now().astimezone().strftime("%a %b %d %H:%M:%S %Z %Y") + "\n", ""


def c_gio(args, entrada, ctx):
    """gio trash (o que o prompt ensina para apagar) e gio open."""
    if args[:1] == ["trash"]:
        for a in [x for x in args[1:] if x != "--"]:
            try:
                plataforma.lixeira(str(ctx.caminho(a)))
            except OSError as e:
                return 1, "", f"gio: {a}: {e}\n"
        return 0, "", ""
    if args[:1] == ["open"] and len(args) > 1:
        plataforma.abrir(str(ctx.caminho(args[1])) if not re.match(r"\w+://", args[1]) else args[1])
        return 0, "", ""
    return 1, "", "gio: only 'gio trash' and 'gio open' are available here\n"


def c_xdg_open(args, entrada, ctx):
    if not args:
        return 1, "", "xdg-open: missing argument\n"
    plataforma.abrir(args[0] if re.match(r"\w+://", args[0]) else str(ctx.caminho(args[0])))
    return 0, "", ""


def c_true(args, entrada, ctx):
    return 0, "", ""


COMANDOS = {"echo": c_echo, "printf": c_printf, "mkdir": c_mkdir, "touch": c_touch, "cat": c_cat, "ls": c_ls, "mv": c_mv,
            "cp": c_cp, "rm": c_rm, "rmdir": c_rmdir, "wc": c_wc, "free": c_free, "find": c_find, "head": c_head_tail("head"),
            "tail": c_head_tail("tail"), "grep": c_grep, "sort": c_sort, "pwd": c_pwd, "cd": c_cd, "whoami": c_whoami,
            "date": c_date, "gio": c_gio, "xdg-open": c_xdg_open, "true": c_true}


# ------------------------------------------------------------
# Rodar
# ------------------------------------------------------------
def _rodar_pipeline(pipe, ctx):
    entrada, codigo, erros = "", 0, ""
    for argv, redir in pipe:
        try:
            codigo, saida, erro = COMANDOS[argv[0]](argv[1:], entrada, ctx)
        except KeyError:
            codigo, saida, erro = 127, "", f"{argv[0]}: command not found\n"
        except OSError as e:
            codigo, saida, erro = 1, "", f"{argv[0]}: {e.strerror or e}\n"
        for tipo, alvo in redir:
            if tipo == "2>&1":
                saida, erro = saida + erro, ""
            elif tipo == "2>":
                erro = "" if alvo in ("/dev/null", "nul", "NUL") else erro
            elif alvo in ("/dev/null", "nul", "NUL"):
                saida = ""
            else:
                with open(ctx.caminho(alvo), "a" if tipo == ">>" else "w", encoding="utf-8", newline="\n") as f:
                    f.write(saida)
                saida = ""
        erros += erro
        entrada = saida
    return codigo, entrada, erros


def executar(comando, cwd=None):
    """Roda a linha e devolve o mesmo dicionário que o executar_terminal do núcleo."""
    ctx = Contexto(cwd or os.getcwd())
    try:
        lista = _analisar(comando, ctx.cwd)
    except ErroDeShell as e:
        return {"sucesso": False, "codigo": 2, "stdout": "", "stderr": f"{e}\n", "mensagem": "Command finished with an error."}
    codigo, saidas, erros = 0, [], ""
    for ligacao, pipe in lista:
        if (ligacao == "&&" and codigo != 0) or (ligacao == "||" and codigo == 0):
            continue
        codigo, saida, erro = _rodar_pipeline(pipe, ctx)
        saidas.append(saida)
        erros += erro
    return {"sucesso": codigo == 0, "codigo": codigo, "stdout": "".join(saidas), "stderr": erros,
            "mensagem": "Command finished." if codigo == 0 else "Command finished with an error."}
