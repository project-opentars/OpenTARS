# Murph: treino

A Murph é a ajudante local que decide o tipo de cada pedido (visão, código,
Linux, ação, busca, conversa simples, geral). O modelo pronto fica em
`modelos/murph.json` e roda com `tars_murph.py`, em Python puro.

Esta pasta é só pra treinar de novo. Não vai no pacote `.deb`.

| Arquivo | O que é |
|---|---|
| `gerado/*.json` | frases novas escritas por um modelo grande, por idioma (quem escreveu não viu as frases de teste) |
| `limpar.py` | junta as geradas, tira repetidas e as parecidas com qualquer frase de teste, em qualquer idioma -> `gerado_limpo.json` |
| `filtro_traducoes_teste.json` | as frases de `tests/frases_classificador.py` traduzidas nos 5 idiomas, SÓ pro filtro achar traduções |
| `treinar_murph.py` | treina (exemplos do openTARS + `gerado_limpo.json`), calibra a confiança e salva `modelos/murph.json` |
| `comparar.py` | Murph x classificador antigo nas frases de teste (sozinhos e no modo AUTO) |
| `teste_cego.json` / `teste_cego.py` | 280 pedidos bagunçados escritos por quem não viu nada do projeto; o script tira os parecidos com o treino e compara |
| `dados.py` | onde ficam o treino e o teste |

Pra treinar de novo (precisa de `pip install scikit-learn numpy`):

```bash
python3 murph/limpar.py
python3 murph/treinar_murph.py
python3 murph/comparar.py
python3 murph/teste_cego.py
python3 tests/test_murph.py
```

As frases de teste (`idiomas/*.json` "avaliacao" e `tests/frases_classificador.py`)
nunca entram no treino. Pra corrigir um erro, escreva frases NOVAS parecidas com o
pedido real que errou, não copie a frase de teste.

## Resultado da 3.0.4

| | NB antigo | Murph |
|---|---|---|
| Teste cego, sozinho (140) | 84,3% | 92,9% |
| Teste cego, modo AUTO sem Ollama | 87,9% | 95,0% |
| Teste cego, AUTO com ajudante perfeito | 91,4% (34 chamadas) | 98,6% (20 chamadas) |
| Avaliação de sempre, sozinho (261) | 88,1% | 95,0% |
| Avaliação de sempre, AUTO sem Ollama | 92,0% | 95,4% |

O teste cego vale mais: foi rodado uma vez só, com o modelo já pronto. As
261 frases de sempre foram vistas durante o desenvolvimento.
