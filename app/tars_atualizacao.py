"""openTARS Endurance Neo: aviso de versão nova (só biblioteca padrão + requests).

Uma vez por dia, no máximo, lê o tars.py publicado no GitHub (um GET, sem
mandar nada do PC) e compara a REVISAO de lá com a deste openTARS. Se a de
lá for maior, avisa. Sem internet ou com erro, fica quieto.
TARS_SEM_AVISO_VERSAO=1 desliga."""

import datetime
import json
import os
import re
import time
from pathlib import Path

import tars_plataforma as plataforma

URL_TARS_PUBLICADO = ("https://raw.githubusercontent.com/project-opentars/OpenTARS/"
                      "main/tars.py")
INTERVALO_S = 24 * 3600


def arquivo_cache():
    return plataforma.pastas()["cache"] / "versao_publicada.json"


def ler_versao(texto):
    """{'revisao': 2026100101, 'versao': '4.0', 'codinome': 'Endurance Neo'} do tars.py, ou None."""
    revisao = re.search(r"^REVISAO\s*=\s*(\d+)", texto or "", re.M)
    if not revisao:
        return None
    versao = re.search(r'^VERSAO\s*=\s*"([^"]+)"', texto, re.M)
    codinome = re.search(r'^CODINOME\s*=\s*"([^"]+)"', texto, re.M)
    return {"revisao": int(revisao.group(1)), "versao": versao.group(1) if versao else "?",
            "codinome": codinome.group(1) if codinome else ""}


def _buscar(timeout=5):
    import requests
    r = requests.get(URL_TARS_PUBLICADO, timeout=timeout)
    return r.text if r.status_code == 200 else None


def versao_publicada(agora=None, buscar=None, cache=None):
    """A versão publicada (do cache de até 24 h, ou buscada agora), ou None."""
    if os.environ.get("TARS_SEM_AVISO_VERSAO", "0") not in ("0", "", "off", "no", "nao"):
        return None
    agora = agora or time.time()
    cache = Path(cache or arquivo_cache())
    try:
        dados = json.loads(cache.read_text(encoding="utf-8"))
        if agora - float(dados.get("quando", 0)) < INTERVALO_S:
            return dados.get("publicada")
    except (OSError, ValueError):
        pass
    try:
        publicada = ler_versao((buscar or _buscar)())
    except Exception:
        publicada = None
    if publicada is None:
        return None  # sem internet agora: não guarda a falha por 24 h
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"quando": agora, "publicada": publicada}), encoding="utf-8")
    except OSError:
        pass
    return publicada


def versao_nova(revisao_local, **kw):
    """A versão publicada, se for mais nova que esta; senão None."""
    publicada = versao_publicada(**kw)
    if publicada and int(publicada.get("revisao", 0)) > int(revisao_local):
        return publicada
    return None


# ============================================================
# 5.0 Tesseract: atualizar com um clique (nunca sozinho)
# ============================================================
# A janela mostra "Nova versão: X" e o botão Atualizar. Só com o clique: baixa o AppImage (ou o .deb)
# do release no GitHub, confere o SHA-256 (do arquivo SHA256SUMS do mesmo release) e só então troca.
# Hash diferente = apaga o arquivo e não instala nada. Nada é enviado: só GETs.
import hashlib
import shutil
import subprocess
import tempfile
from urllib.parse import quote, urlparse

REPOSITORIO = "project-opentars/OpenTARS"
URL_CONTEUDO = os.environ.get("TARS_URL_CONTEUDO") or f"https://api.github.com/repos/{REPOSITORIO}/contents/"
URL_ARVORE = os.environ.get("TARS_URL_ARVORE") or f"https://api.github.com/repos/{REPOSITORIO}/git/trees/HEAD?recursive=1"
URL_COMMITS = os.environ.get("TARS_URL_COMMITS") or f"https://api.github.com/repos/{REPOSITORIO}/commits?per_page=1"
URL_RELEASE = os.environ.get("TARS_URL_RELEASE") or f"https://api.github.com/repos/{REPOSITORIO}/releases/latest"
HOSTS_PERMITIDOS = ("github.com", "api.github.com", "objects.githubusercontent.com", "github-releases.githubusercontent.com",
                    "release-assets.githubusercontent.com")


def host_permitido(url, extras=()):
    """Só HTTPS e só o GitHub (ou os `extras`, que são dos testes)."""
    p = urlparse(url or "")
    host = (p.hostname or "").lower()
    if host in extras:
        return True
    return p.scheme == "https" and (host in HOSTS_PERMITIDOS or host.endswith(".githubusercontent.com"))


def numeros_da_versao(texto):
    """'v5.0.1' -> (5, 0, 1); 'abc' -> ()."""
    return tuple(int(x) for x in re.findall(r"\d+", str(texto or "").split("-")[0])[:4])


def ler_somas(texto):
    """{'arquivo': 'sha256'} de um SHA256SUMS ('<hash>  <arquivo>' por linha)."""
    somas = {}
    for linha in (texto or "").splitlines():
        partes = linha.strip().split(None, 1)
        if len(partes) == 2 and re.fullmatch(r"[0-9a-fA-F]{64}", partes[0]):
            somas[partes[1].lstrip("*").strip()] = partes[0].lower()
    return somas


def _get_json(url, timeout=6):
    import requests
    r = requests.get(url, timeout=timeout, headers={"Accept": "application/vnd.github+json"})
    return r.json() if r.status_code == 200 else None


def _get_texto(url, timeout=6):
    import requests
    r = requests.get(url, timeout=timeout)
    return r.text if r.status_code == 200 else None


def _estado_arquivo():
    return Path(os.environ.get("TARS_ARQUIVO_ATUALIZACAO") or os.path.expanduser("~/.config/opentars/atualizacao.json"))


def marcar_instalada(sha256):
    """Guarda o hash do arquivo que o usuário instalou por aqui (para não oferecer o mesmo de novo)."""
    try:
        arq = _estado_arquivo()
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(json.dumps({"sha256": str(sha256).lower()}), encoding="utf-8")
    except Exception:
        pass


def _ultima_instalada():
    try:
        return str(json.loads(_estado_arquivo().read_text(encoding="utf-8")).get("sha256") or "")
    except Exception:
        return ""


def _epoch(iso):
    """'2026-10-06T22:10:00Z' -> segundos desde 1970 (0 se não entender)."""
    try:
        return datetime.datetime.strptime(str(iso)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc).timestamp()
    except Exception:
        return 0.0


def compilado_em():
    """Quando este pacote foi montado: o dpkg guarda a data dos arquivos, então é a data do .deb instalado."""
    try:
        return os.path.getmtime(__file__)
    except Exception:
        return 0.0


def _versao_da_release(release, nomes_de_arquivos=()):
    """Número de versão da Release, se houver (tag, título, nome do arquivo ou texto); '' se não há.
    Tag como 'update' não atrapalha: a detecção principal é pela data do arquivo enviado."""
    for fonte in (release.get("tag_name"), release.get("name"), *nomes_de_arquivos):
        n = numeros_da_versao(str(fonte or ""))
        if n and n[0] >= 1:
            return ".".join(str(x) for x in n)
    m = re.search(r"\bv?(\d+\.\d+(?:\.\d+)?)\b", str(release.get("body") or ""))
    return m.group(1) if m else ""


def _release_mais_recente(obter_json):
    """A Release 'Latest'; se não existir (só pre-release, por ex.), a mais nova que não seja rascunho."""
    release = obter_json(URL_RELEASE)
    if isinstance(release, dict) and release.get("assets") is not None:
        return release
    lista = obter_json(URL_RELEASE.rsplit("/", 1)[0])
    if isinstance(lista, list):
        for r in lista:
            if isinstance(r, dict) and not r.get("draft"):
                return r
    return None


def procurar_no_repositorio(obter_json=None, extras=(), compilado=None, ultima=None):
    """Upload direto no repositório ('Add files via upload'): olha o .deb que está na raiz e quando ele foi enviado.
    Novo = o commit que mexeu nele é posterior à montagem deste pacote e o arquivo não é o que já foi instalado.
    Devolve o mesmo formato de procurar_atualizacao ('id' = SHA-1 git do arquivo; 'sha256' só se houver SHA256SUMS)."""
    obter_json = obter_json or _get_json
    try:
        raiz = obter_json(URL_CONTEUDO)
    except Exception:
        return None
    if not isinstance(raiz, list):
        return None
    debs = [a for a in raiz if isinstance(a, dict) and a.get("type") == "file" and str(a.get("name", "")).endswith(".deb")]
    if not debs:      # não está na raiz: procura em qualquer pasta do repositório
        try:
            arvore = (obter_json(URL_ARVORE) or {}).get("tree") or []
        except Exception:
            arvore = []
        for a in arvore:
            if isinstance(a, dict) and a.get("type") == "blob" and str(a.get("path", "")).endswith(".deb"):
                debs.append({"name": a["path"], "sha": a.get("sha"),
                             "download_url": f"https://raw.githubusercontent.com/{REPOSITORIO}/HEAD/" + quote(a["path"])})
    if not debs:
        return None
    arq = next((a for a in debs if str(a.get("name")).split("/")[-1] == "opentars_all.deb"), debs[0])
    url = arq.get("download_url")
    blob = str(arq.get("sha") or "").lower()
    if not url or not host_permitido(url, extras) or not re.fullmatch(r"[0-9a-f]{40}", blob):
        return None
    instalada = _ultima_instalada() if ultima is None else ultima
    if blob == instalada:
        return None
    try:
        commits = obter_json(URL_COMMITS + "&path=" + quote(str(arq.get("name"))))
        data = commits[0]["commit"]["committer"]["date"]
    except Exception:
        return None
    enviado = _epoch(data)
    meu_pacote = compilado_em() if compilado is None else compilado
    if not enviado or enviado <= meu_pacote + 60:
        return None
    quando = datetime.datetime.fromtimestamp(enviado).strftime("%d/%m %H:%M")
    return {"versao": quando, "notas": "", "arquivos": {"deb": {"nome": str(arq["name"]).split("/")[-1], "url": url, "sha256": "", "git_sha": blob, "id": blob}}}


def procurar_atualizacao(versao_local, obter_json=None, obter_texto=None, extras=(), compilado=None, ultima=None):
    """Primeiro o upload direto no repositório; se não houver, a Release do GitHub. TARS_SEM_AVISO_VERSAO desliga os dois."""
    if os.environ.get("TARS_SEM_AVISO_VERSAO", "0") not in ("0", "", "off", "no", "nao"):
        return None
    achou = procurar_no_repositorio(obter_json, extras, compilado, ultima)
    return achou or procurar_em_release(versao_local, obter_json, obter_texto, extras, compilado, ultima)


def procurar_em_release(versao_local, obter_json=None, obter_texto=None, extras=(), compilado=None, ultima=None):
    """{'versao', 'arquivos': {'appimage': {...}, 'deb': {...}}, 'notas'} se há arquivo mais novo no GitHub; senão None.

    Automático: olha o último .deb/.AppImage enviado à Release. É novo quando foi enviado DEPOIS de este pacote
    ter sido montado e o hash não é o do que o usuário já instalou por aqui (ou quando o número de versão é maior).
    Tag, título e SHA256SUMS não são obrigatórios: o hash vem do SHA256SUMS (se existir) ou do campo `digest`
    que o próprio GitHub calcula para cada arquivo enviado. Sem hash para conferir: não instala."""
    if os.environ.get("TARS_SEM_AVISO_VERSAO", "0") not in ("0", "", "off", "no", "nao"):
        return None
    try:
        release = _release_mais_recente(obter_json or _get_json)
    except Exception:
        return None
    if not isinstance(release, dict) or release.get("draft"):
        return None
    lista = [a for a in release.get("assets", []) if isinstance(a, dict)]
    ativos = {a.get("name"): a for a in lista}
    versao = _versao_da_release(release, [n for n in ativos if str(n).endswith((".deb", ".AppImage"))])
    nova_versao = numeros_da_versao(versao)
    local = numeros_da_versao(versao_local)
    if nova_versao and nova_versao < local:
        return None
    somas = {}
    url_somas = (ativos.get("SHA256SUMS") or {}).get("browser_download_url")
    if url_somas and host_permitido(url_somas, extras):
        try:
            somas = ler_somas((obter_texto or _get_texto)(url_somas))
        except Exception:
            somas = {}
    meu_pacote = compilado_em() if compilado is None else compilado
    instalada = _ultima_instalada() if ultima is None else ultima
    arquivos, mais_recente = {}, 0.0
    for nome, a in ativos.items():
        tipo = "appimage" if str(nome).endswith(".AppImage") else "deb" if str(nome).endswith(".deb") else None
        url = a.get("browser_download_url")
        if not tipo or not url or not host_permitido(url, extras):
            continue
        sha = somas.get(nome) or str(a.get("digest") or "").lower().replace("sha256:", "")
        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            continue
        enviado = _epoch(a.get("created_at") or a.get("updated_at"))
        novo = (nova_versao > local) or (enviado > meu_pacote + 60)
        if novo and sha != instalada:
            arquivos[tipo] = {"nome": nome, "url": url, "sha256": sha, "id": sha}
            mais_recente = max(mais_recente, enviado)
    if not arquivos:
        return None
    if not versao and mais_recente:
        versao = datetime.datetime.fromtimestamp(mais_recente).strftime("%d/%m %H:%M")
    return {"versao": versao or "?", "arquivos": arquivos, "notas": str(release.get("body") or "")[:2000]}


def baixar_verificado(url, destino, sha256, ao_progredir=None, cancelado=None, extras=(), abrir=None, git_sha=None):
    """Baixa `url` em `destino` e confere o SHA-256. (True, '') ou (False, motivo). Falhou = nada fica no disco."""
    if not host_permitido(url, extras):
        return False, "endereço"
    destino = Path(destino)
    parcial = destino.with_name(destino.name + ".parte")
    soma = hashlib.sha256()
    try:
        if abrir is None:
            import requests
            atual = url
            for _salto in range(6):         # redireciona à mão: CADA endereço do caminho tem que ser do GitHub
                resposta = requests.get(atual, stream=True, timeout=15, allow_redirects=False)
                if resposta.status_code in (301, 302, 303, 307, 308) and resposta.headers.get("Location"):
                    atual = requests.compat.urljoin(atual, resposta.headers["Location"])
                    resposta.close()
                    if not host_permitido(atual, extras):
                        return False, "endereço"
                    continue
                break
            else:
                return False, "rede"
            total = int(resposta.headers.get("Content-Length") or 0)
            if total > TAMANHO_MAXIMO_BYTES:
                resposta.close()
                return False, "tamanho"
            blocos = resposta.iter_content(1 << 16)
            ok_http = resposta.status_code == 200
        else:
            blocos, total, ok_http = abrir(url)
        if not ok_http:
            return False, "rede"
        feito = 0
        destino.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(parcial, "wb") as f:
            for bloco in blocos:
                if cancelado and cancelado():
                    raise InterruptedError
                f.write(bloco)
                soma.update(bloco)
                feito += len(bloco)
                if feito > TAMANHO_MAXIMO_BYTES:
                    raise OverflowError
                if ao_progredir:
                    ao_progredir(feito, total)
        if sha256:
            certo = soma.hexdigest() == str(sha256).lower()
        else:   # arquivo do repositório sem SHA256SUMS: confere o SHA-1 git (o mesmo que o GitHub mostra) do arquivo
            dados = parcial.read_bytes()
            certo = bool(git_sha) and hashlib.sha1(b"blob %d\0" % len(dados) + dados).hexdigest() == str(git_sha).lower()
        if not certo:
            parcial.unlink(missing_ok=True)
            return False, "hash"
        os.replace(parcial, destino)
        return True, ""
    except InterruptedError:
        parcial.unlink(missing_ok=True)
        return False, "cancelado"
    except OverflowError:
        parcial.unlink(missing_ok=True)
        return False, "tamanho"
    except Exception:
        parcial.unlink(missing_ok=True)
        return False, "rede"


TAMANHO_MAXIMO_BYTES = 600 * 1024 * 1024      # um .deb/AppImage do openTARS tem ~1 a 70 MB; mais que isso não é o nosso

# Roda COMO ROOT (pkexec): copia o .deb pra uma pasta só do root, CONFERE o hash lá e só então instala. Conferir antes,
# no arquivo da pasta da pessoa, deixava uma janela (o aviso da senha) em que outro programa dela trocava o arquivo.
_SCRIPT_INSTALAR_DEB = r'''set -e
d=$(mktemp -d)
trap 'rm -rf "$d"' EXIT
cp -- "$1" "$d/pacote.deb"
chmod 755 "$d"; chmod 644 "$d/pacote.deb"
if [ "$2" = sha256 ]; then
  echo "$3  $d/pacote.deb" | sha256sum -c - >/dev/null
else
  n=$(stat -c %s "$d/pacote.deb")
  h=$( (printf 'blob %s\0' "$n"; cat "$d/pacote.deb") | sha1sum | cut -d' ' -f1 )
  [ "$h" = "$3" ]
fi
# --reinstall: a versão do pacote nem sempre muda entre dois envios; sem ele o apt diz "já é a mais nova", sai com 0 e não instala nada
apt-get install -y --reinstall "$d/pacote.deb"
# confere que o arquivo do pacote está mesmo no disco; se não, falha (e o app não marca como instalado)
dpkg-deb --fsys-tarfile "$d/pacote.deb" | tar -xO ./usr/share/opentars/tars.py | cmp -s - /usr/share/opentars/tars.py
'''


def instalar_arquivo(arquivo, appimage_atual=None, rodar=None, sha256="", git_sha=""):
    """Instala o que foi baixado e conferido. AppImage: troca o arquivo que está rodando (reabrir pra usar a nova);
    .deb: instala com a senha do sistema (pkexec apt-get). Devolve (ok, mensagem)."""
    arquivo = Path(arquivo)
    rodar = rodar or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True, timeout=900))
    try:
        if arquivo.name.endswith(".AppImage"):
            atual = appimage_atual or os.environ.get("APPIMAGE")
            if not atual:
                return False, "sem_appimage"
            novo = Path(str(atual) + ".novo")
            shutil.copyfile(arquivo, novo)
            novo.chmod(0o755)
            os.replace(novo, atual)
            return True, "reabrir"
        if arquivo.name.endswith(".deb"):
            if sha256 or git_sha:
                comando = ["pkexec", "sh", "-c", _SCRIPT_INSTALAR_DEB, "_", str(arquivo),
                           "sha256" if sha256 else "git", str(sha256 or git_sha).lower()]
            else:
                comando = ["pkexec", "apt-get", "install", "-y", "--reinstall", str(arquivo)]
            r = rodar(comando)
            return (True, "reabrir") if r.returncode == 0 else (False, (r.stderr or r.stdout or "").strip()[-300:])
    except Exception as e:
        return False, str(e)
    return False, "formato"
