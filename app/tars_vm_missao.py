"""5.3 (F7, passos 2 e 3): a MISSÃO de um Probe na VM: liga uma cópia descartável da base, deixa o agente trabalhar pela tela, pelo mouse e
pelo teclado (de fora, ver tars_vm_controle), recolhe o que ele guardou na pasta de saída e APAGA tudo. Sem modelo aqui: quem decide cada
passo é um `decisor` que se troca (os testes usam um roteiro; o de verdade olha a tela com o Gargantua).

Três portas, as únicas entre a VM e o PC:
- o canal de controle (socket unix privado, sem rede);
- a saída de internet: o proxy deste arquivo. A rede do QEMU é "restrict=on" (a VM não alcança NADA sozinha, nem os serviços do PC em
  127.0.0.1) e só o proxy é encaminhado (guestfwd). O proxy recusa endereço que não seja público (privado, loopback, link-local), recusa
  porta que não seja 80 ou 443 (sem e-mail nem SSH), limita o total transferido e anota cada site para o aviso na tela. Limite: o proxy
  vê o site, não o que vai dentro do HTTPS: "enviar pede aprovação" não se impõe na rede, é regra da ferramenta e do aviso;
- a pasta de saída: um disco FAT pequeno (rótulo SAIDA) que o agente enxerga em ~/saida. O PC NUNCA o monta: lê com o 7z, num lugar de
  quarentena, como dado, com limite de arquivos e de tamanho. O que sai de lá para o usuário só depois de aprovação (`liberar`)."""
import ipaddress
import os
import select
import shutil
import socket
import socketserver
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import tars_vm
from tars_vm_controle import ControleVM

PORTAS_PERMITIDAS = (80, 443)
LIMITE_PROXY_MB = 500
TEMPO_OCIOSO_PROXY_S = 120
SAIDA_MB = 64
SAIDA_MAX_ARQUIVOS = 200


# ---------------------------------------------------------------- proxy de saída
def endereco_publico(ip):
    """Só endereço de internet de verdade: nada de rede local, loopback, link-local, multicast ou reservado."""
    try:
        a = ipaddress.ip_address(ip)
        if getattr(a, "ipv4_mapped", None):
            a = a.ipv4_mapped
        return a.is_global and not (a.is_multicast or a.is_loopback or a.is_link_local or a.is_private or a.is_reserved or a.is_unspecified)
        # (o is_global sozinho deixa passar multicast, 224.0.0.1)
    except ValueError:
        return False


def _resolver_publico(host, porta):
    """O primeiro endereço público do nome (e é nele que se conecta: um nome que aponta para o PC não passa), ou None."""
    try:
        for familia, _t, _p, _c, destino in socket.getaddrinfo(host, porta, type=socket.SOCK_STREAM):
            if endereco_publico(destino[0]):
                return familia, destino
    except socket.gaierror:
        pass
    return None


class ProxySaida:
    """Proxy HTTP/HTTPS (CONNECT) em 127.0.0.1, só para a VM. `acessos` guarda (hora, host, porta, permitido, bytes)."""

    def __init__(self, resolver=_resolver_publico, limite_mb=LIMITE_PROXY_MB):
        self.resolver, self.limite = resolver, limite_mb * 1024 * 1024
        self.acessos, self.bytes_total, self._trava = [], 0, threading.Lock()
        proxy = self

        class Tratador(socketserver.BaseRequestHandler):
            def handle(self):
                proxy._atender(self.request)

        class Servidor(socketserver.ThreadingTCPServer):
            daemon_threads = True
            allow_reuse_address = True

        self.servidor = Servidor(("127.0.0.1", 0), Tratador)
        self.porta = self.servidor.server_address[1]
        self._fio = threading.Thread(target=self.servidor.serve_forever, daemon=True)

    def iniciar(self):
        self._fio.start()
        return self

    def parar(self):
        self.servidor.shutdown()
        self.servidor.server_close()

    def _anotar(self, host, porta, permitido, n=0):
        with self._trava:
            self.acessos.append((time.strftime("%H:%M:%S"), host, porta, permitido, n))

    def _atender(self, cliente):
        cliente.settimeout(TEMPO_OCIOSO_PROXY_S)
        cabeca = b""
        try:
            while b"\r\n\r\n" not in cabeca and len(cabeca) < 16384:
                bloco = cliente.recv(4096)
                if not bloco:
                    return
                cabeca += bloco
            linha = cabeca.split(b"\r\n", 1)[0].decode("latin-1")
            metodo, alvo, *_ = linha.split(" ")
            if metodo.upper() == "CONNECT":
                host, _, porta = alvo.rpartition(":")
                porta, resto = int(porta), b""
            else:                                           # http://host[:porta]/caminho
                if metodo.upper() not in ("GET", "POST", "HEAD", "PUT", "DELETE", "OPTIONS", "PATCH") or not alvo.lower().startswith("http://"):
                    raise ValueError("pedido que não é de proxy")
                sem = alvo.split("://", 1)[-1]
                autoridade, _, caminho = sem.partition("/")
                host, _, p = autoridade.partition(":")
                porta = int(p or 80)
                cabeca = cabeca.replace(alvo.encode(), ("/" + caminho).encode(), 1)
                resto = cabeca
        except (ValueError, OSError):
            return self._recusar(cliente, "400 Bad Request")
        if porta not in PORTAS_PERMITIDAS or self.bytes_total >= self.limite:
            self._anotar(host, porta, False)
            return self._recusar(cliente, "403 Forbidden")
        destino = self.resolver(host, porta)
        if destino is None:
            self._anotar(host, porta, False)
            return self._recusar(cliente, "403 Forbidden")
        try:
            upstream = socket.socket(destino[0]) if isinstance(destino, tuple) and not hasattr(destino, "sendall") else destino
            if isinstance(destino, tuple):
                upstream.settimeout(15)
                upstream.connect(destino[1])
        except OSError:
            self._anotar(host, porta, True)
            return self._recusar(cliente, "502 Bad Gateway")
        if metodo.upper() == "CONNECT":
            cliente.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
        else:
            upstream.sendall(resto)
        n = self._passar(cliente, upstream)
        self._anotar(host, porta, True, n)
        upstream.close()

    @staticmethod
    def _recusar(cliente, status):
        try:
            cliente.sendall(f"HTTP/1.1 {status}\r\nConnection: close\r\nContent-Length: 0\r\n\r\n".encode())
        except OSError:
            pass

    def _passar(self, a, b):
        total = 0
        pares = {a: b, b: a}
        try:
            while True:
                prontos, _, _ = select.select(list(pares), [], [], TEMPO_OCIOSO_PROXY_S)
                if not prontos:
                    break
                for s in prontos:
                    dados = s.recv(65536)
                    if not dados:
                        return total
                    pares[s].sendall(dados)
                    total += len(dados)
                    with self._trava:
                        self.bytes_total += len(dados)
                    if self.bytes_total >= self.limite:
                        return total
        except OSError:
            pass
        return total


# ---------------------------------------------------------------- pasta de saída (disco FAT, lido como dado)
def criar_disco_de_saida(destino, mb=SAIDA_MB):
    destino = Path(destino)
    subprocess.run(["qemu-img", "create", "-f", "raw", str(destino), f"{mb}M"], check=True, capture_output=True, timeout=30)
    subprocess.run(["mkfs.vfat", "-n", "SAIDA", str(destino)], check=True, capture_output=True, timeout=30)
    return destino


def ler_saida(disco, quarentena, max_arquivos=SAIDA_MAX_ARQUIVOS):
    """Extrai o disco FAT para `quarentena` com o 7z (sem montar nada do convidado) e lista [{nome, tamanho, caminho}]. Só arquivos
    comuns, até `max_arquivos`; o disco já limita o tamanho total. O conteúdo é DADO: nunca é aberto nem executado por aqui."""
    quarentena = Path(quarentena)
    shutil.rmtree(quarentena, ignore_errors=True)
    quarentena.mkdir(parents=True)
    r = subprocess.run(["7z", "x", "-y", f"-o{quarentena}", str(disco)], capture_output=True, timeout=120)
    achados = []
    for caminho in sorted(quarentena.rglob("*")):
        if caminho.is_symlink() or not caminho.is_file():
            continue
        if len(achados) >= max_arquivos:
            break
        achados.append({"nome": str(caminho.relative_to(quarentena)), "tamanho": caminho.stat().st_size, "caminho": str(caminho)})
    if r.returncode not in (0, 1) and not achados:           # 7z devolve 1 em aviso; sem arquivo e com erro é disco vazio ou estragado
        return []
    return achados


def liberar(arquivo, destino):
    """Copia UM arquivo da quarentena para o PC. Quem chama já mostrou o aviso e teve o sim da pessoa."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(arquivo["caminho"], destino)
    return destino


# ---------------------------------------------------------------- a missão
class Limites:
    def __init__(self, passos=40, segundos=900, boot_s=90):
        self.passos, self.segundos, self.boot_s = passos, segundos, boot_s


def executar_acao(controle, acao, pasta_telas=None):
    """Uma ação do agente: {"tipo": clicar|duplo|direito|digitar|atalho|rolar|esperar, ...}. Devolve texto curto do que fez."""
    tipo = acao.get("tipo")
    if tipo in ("clicar", "duplo", "direito"):
        controle.clicar(acao["x"], acao["y"], botao="direito" if tipo == "direito" else "esquerdo", duplo=tipo == "duplo")
        return f"{tipo} {acao['x']},{acao['y']}"
    if tipo == "digitar":
        ignorados = controle.digitar(str(acao.get("texto", "")))
        return "digitou" + (f" (sem os caracteres: {''.join(ignorados)})" if ignorados else "")
    if tipo == "atalho":
        controle.atalho(str(acao["teclas"]))
        return f"atalho {acao['teclas']}"
    if tipo == "rolar":
        controle.rolar(int(acao.get("passos", 3)))
        return "rolou"
    if tipo == "esperar":
        time.sleep(min(float(acao.get("segundos", 2)), 30))
        return "esperou"
    raise ValueError(f"ação desconhecida: {tipo!r}")


def executar(decisor, limites=None, internet=True, ao_passo=None, cancelar=None, ram_mb=3072, cpus=2, popen=subprocess.Popen, rodar_base=None,
            conectar=None):
    """Roda UMA missão do começo ao fim e devolve {"resultado", "passos", "arquivos", "acessos", "motivo", "segundos"}.
    `decisor(tela_png, historico)` devolve a próxima ação ({"tipo": ...}) ou {"tipo": "terminar", "resultado": texto}.
    Sempre apaga a cópia da VM, o disco de saída (depois de lido), o socket e a quarentena não liberada fica em `quarentena` até o chamador
    apagar."""
    limites = limites or Limites()
    base = rodar_base or tars_vm.imagem_base()
    if not Path(base).exists():
        raise RuntimeError("a imagem da VM ainda não foi montada")
    trabalho = Path(tempfile.mkdtemp(prefix="vmm-", dir=os.environ.get("XDG_RUNTIME_DIR") or None))
    os.chmod(trabalho, 0o700)                               # o socket e as telas são só do usuário
    proxy = ProxySaida().iniciar() if internet else None
    processo, controle, historico = None, None, []
    inicio, motivo, resultado = time.monotonic(), "terminou", ""
    try:
        overlay = tars_vm.criar_overlay(base, trabalho / "missao.qcow2")
        saida = criar_disco_de_saida(trabalho / "saida.img")
        argv = tars_vm.argumentos_qemu(overlay, internet=False, ram_mb=ram_mb, cpus=cpus, controle=trabalho / "q.sock")
        rede = argv.index("-netdev") + 1
        if proxy:                                           # restrict=on já está; só o proxy é encaminhado (nada de Ollama: o modelo roda no PC)
            argv[rede] += f",guestfwd=tcp:{tars_vm.ENDERECO_PROXY.split(':')[0]}:{tars_vm.ENDERECO_PROXY.split(':')[1]}-tcp:127.0.0.1:{proxy.porta}"
        argv += ["-drive", f"file={saida},if=virtio,format=raw"]
        processo = popen(["nice", "-n", "10"] + argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        controle = (conectar or (lambda caminho, espera: ControleVM(caminho).conectar(espera=espera)))(trabalho / "q.sock", limites.boot_s)
        time.sleep(1)
        for passo in range(limites.passos):
            if cancelar is not None and cancelar.is_set():
                motivo = "cancelada"
                break
            if time.monotonic() - inicio > limites.segundos:
                motivo = "tempo esgotado"
                break
            tela = controle.tela(trabalho / f"tela-{passo:03d}.png")
            acao = decisor(tela, list(historico))
            if acao.get("tipo") == "terminar":
                resultado = str(acao.get("resultado", ""))
                break
            feito = executar_acao(controle, acao)
            historico.append(feito)
            if ao_passo:
                ao_passo(passo, feito)
        else:
            motivo = "limite de passos"
        try:
            controle.desligar_suave()                        # dá uns segundos para o convidado gravar a pasta de saída
            for _ in range(20):
                if processo.poll() is not None:
                    break
                time.sleep(1)
        except (OSError, ConnectionError, RuntimeError):
            pass
    finally:
        if controle is not None:
            controle.encerrar()
        if processo is not None:
            if processo.poll() is None:
                processo.terminate()
            try:
                processo.wait(timeout=20)
            except subprocess.TimeoutExpired:
                processo.kill()
        arquivos = []
        if (trabalho / "saida.img").exists():
            arquivos = ler_saida(trabalho / "saida.img", trabalho.parent / (trabalho.name + "-quarentena"))
        acessos = list(proxy.acessos) if proxy else []
        if proxy:
            proxy.parar()
        quarentena = str(trabalho.parent / (trabalho.name + "-quarentena")) if arquivos else None
        shutil.rmtree(trabalho, ignore_errors=True)         # reset: overlay, disco de saída, socket e telas somem
        if not arquivos:
            shutil.rmtree(trabalho.parent / (trabalho.name + "-quarentena"), ignore_errors=True)
    return {"resultado": resultado, "passos": list(historico), "arquivos": arquivos, "acessos": acessos, "motivo": motivo,
            "segundos": round(time.monotonic() - inicio), "quarentena": quarentena}
