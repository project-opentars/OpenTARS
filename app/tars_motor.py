"""A porta do motor de modelos, como o tars_plataforma é a porta do sistema. Hoje o motor é o Ollama; a 5.3 troca pelo llama.cpp
(PLANO_5.3.md, F9). Cada rota abaixo é uma operação que o motor novo precisa responder, e nenhum endereço da API mora fora daqui:
tests/test_motor.py confere."""

ROTAS = {
    "versao": "/api/version",       # está de pé?
    "modelos": "/api/tags",         # o que está instalado
    "detalhes": "/api/show",        # capacidades, parâmetros e quantização de um modelo
    "rodando": "/api/ps",           # o que está na memória
    "conversa": "/api/chat",        # conversa com ferramentas, em streaming ou não
    "gerar": "/api/generate",       # carregar e descarregar da memória (keep_alive), e pergunta simples
    "baixar": "/api/pull",
    "apagar": "/api/delete",
    "conta": "/api/me",             # conta do ollama.com (nuvem): não existe no llama.cpp
}


def url(rota, host):
    return f"{str(host).rstrip('/')}{ROTAS[rota]}"
