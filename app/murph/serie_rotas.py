"""Série de rotas da Murph do app, escrita em 14/11/2026 ANTES de retreinar (o método do Pi, PLANO_5.3 F2.7). Não entra no
treino e o filtro das frases novas tira as parecidas com ela. Mede a Murph instalada no arquivo que se passar:

    python3 murph/serie_rotas.py [modelos/murph.json]

Traz os defeitos já vistos: o poema que disparava a busca, a saudação que ia para o search_web, a pergunta de identidade.
Depois de ajustar o treino por causa dela, ela deixa de valer como prova: escreva outra.
"""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

SERIE = [
    # conversa simples: saudação, agradecimento, identidade, papo (nunca busca)
    ("oi gargantua", "simples"), ("e aí, tudo certo?", "simples"), ("hey there", "simples"), ("good morning!", "simples"),
    ("valeu mano", "simples"), ("thanks a lot, that worked", "simples"), ("quem é você?", "simples"), ("who are you", "simples"),
    ("qual é o seu nome", "simples"), ("what can you do?", "simples"), ("boa noite, até amanhã", "simples"), ("tô entediado", "simples"),
    # geral: escrever, criar, explicar coisa que não muda (nunca busca)
    ("escreve um poema sobre a chuva", "geral"), ("write a short poem about the ocean", "geral"), ("me conta uma piada", "geral"),
    ("tell me a fun fact about octopuses", "geral"), ("como funciona um motor a combustão", "geral"), ("explain black holes like i'm five", "geral"),
    ("me ajuda a escrever uma mensagem de aniversário pro meu pai", "geral"), ("resume em três linhas o que é inflação", "geral"),
    ("qual a diferença entre vírus e bactéria", "geral"), ("give me ideas for a birthday party", "geral"),
    # busca: precisa da internet de agora
    ("quanto tá o dólar hoje", "busca"), ("what's the weather in lisbon tomorrow", "busca"), ("quem ganhou o jogo do corinthians ontem", "busca"),
    ("latest news about the iphone 18", "busca"), ("preço da rtx 5070 no brasil", "busca"), ("when does the next spacex launch happen", "busca"),
    ("procura um tutorial de crochê no youtube", "busca"), ("pesquisa restaurantes japoneses perto de curitiba", "busca"),
    # ação: fazer algo no computador
    ("abre o spotify", "acao"), ("open the calculator", "acao"), ("cria uma pasta chamada fotos2026 nos documentos", "acao"),
    ("aumenta o volume", "acao"), ("mute the sound", "acao"), ("fecha o firefox", "acao"), ("move os pdfs da área de trabalho pra pasta documentos", "acao"),
    ("liga o modo escuro", "acao"), ("lock my screen", "acao"), ("abre o gerenciador de arquivos na pasta downloads", "acao"),
    # visão: olhar a tela ou clicar no que aparece
    ("o que tem na minha tela agora?", "visao"), ("what does this error on my screen mean", "visao"), ("clica no botão azul de salvar", "visao"),
    ("read me what the popup says", "visao"), ("qual aba tá aberta no navegador", "visao"), ("click the settings gear icon", "visao"),
    ("olha essa janela e me diz o que ela quer", "visao"), ("describe the picture on my desktop", "visao"),
    # código: programar
    ("escreve um script em python que conta linhas de um arquivo", "codigo"), ("fix this javascript: let x = [1,2,3; console.log(x)", "codigo"),
    ("como faço um for em rust", "codigo"), ("write a bash function that backs up a folder", "codigo"), ("o que esse regex faz: ^\\d{3}-\\d{4}$", "codigo"),
    ("cria uma api simples em flask com uma rota /ping", "codigo"), ("why does my c++ code segfault on this line", "codigo"),
    # técnico: Linux, sistema, terminal, defeito do computador
    ("meu ubuntu não liga o wifi depois da atualização", "tecnico"), ("how do i check disk usage from the terminal", "tecnico"),
    ("o apt diz que não consegue o lock", "tecnico"), ("como vejo qual processo tá usando a porta 8080", "tecnico"),
    ("my nvidia driver isn't loading on fedora", "tecnico"), ("como monto um pendrive pelo terminal", "tecnico"),
    ("what's the difference between systemctl stop and disable", "tecnico"), ("o flatpak não abre o app, dá erro de permissão", "tecnico"),
]


def medir(caminho=None):
    import tars_murph as mm
    m = mm.Murph.carregar(caminho or mm.CAMINHO_PADRAO)
    certas, erros = 0, []
    for frase, esperada in SERIE:
        achada = m.classificar(frase)[0]
        if achada == esperada:
            certas += 1
        else:
            erros.append((frase, esperada, achada))
    return certas, erros


if __name__ == "__main__":
    certas, erros = medir(sys.argv[1] if len(sys.argv) > 1 else None)
    for frase, esperada, achada in erros:
        print(f"errou: {frase!r}: esperava {esperada}, deu {achada}")
    print(f"{certas}/{len(SERIE)}")
