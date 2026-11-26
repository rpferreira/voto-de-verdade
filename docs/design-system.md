# Design system: cores, letras e formas

O espaçamento tem documento próprio ([`espacamento.md`](espacamento.md)). Este cobre o resto dos tokens de `site/estilos.css`: **cores**, **tamanhos de letra** e **raios e sombras**. A regra é a mesma do espaçamento: os componentes só usam os valores daqui, e `python testes/tokens.py` barra o que sair da lista. As tabelas abaixo são lidas pelo teste, então não podem ficar diferentes do CSS.

Para ver tudo isso na tela, com as peças de verdade: o [catálogo de componentes](https://votodeverdade.com.br/catalogo/) (`#/catalogo`, função `telaCatalogo` em `site/app.js`).

## 1. Cores

Cada cor tem um **papel**, não um nome de cor. Ficam em `:root` (tema claro) e em `:root[data-theme="dark"]` (tema escuro). O site abre sempre no claro; o escuro vem do botão e fica guardado só no navegador. Nenhuma cor lembra partido: azul (cobalto) para destaque e para o voto «Sim»; âmbar só para avisos de incerteza.

| Token | Papel | Claro | Escuro |
|---|---|---|---|
| `--papel` | Fundo da página | `#f5f6fa` | `#0b1018` |
| `--superficie` | Fundo de cartões e painéis | `#ffffff` | `#131a26` |
| `--tinta` | Texto | `#0f1523` | `#e9edf5` |
| `--tinta-suave` | Texto de apoio | `#4a566b` | `#a9b5c9` |
| `--linha` | Filetes e bordas | `#dde2ec` | `#263145` |
| `--cobalto` | Destaque: links, foco e o voto «Sim» | `#2341d8` | `#94a9ff` |
| `--cobalto-claro` | Fundo suave do destaque | `#e8ecfd` | `#1a2347` |
| `--sobre-cobalto` | Texto sobre o cobalto | `#ffffff` | `#0b1018` |
| `--cinza-voto` | Abstenção, obstrução e presidia | `#98a3b8` | `#67738a` |
| `--aviso-fundo` | Aviso de incerteza: fundo | `#fff3d1` | `#38290a` |
| `--aviso-borda` | Aviso de incerteza: borda | `#c98a00` | `#d9a62e` |
| `--aviso-texto` | Aviso de incerteza: texto | `#5e3d00` | `#f6dc9a` |

**Regras**

1. **Só tokens.** Fora das definições (`--nome: valor`) e do `@media print`, nenhuma cor escrita à mão (`#…`, `rgb()`, `hsl()` com número). Para variar uma cor, use `color-mix()` com tokens.
2. **Os dois temas.** Todo token de cor de `:root` precisa ter valor no tema escuro.
3. **Contraste.** O texto precisa de pelo menos 4,5:1 sobre o fundo, nos dois temas: `--tinta` e `--tinta-suave` sobre `--papel` e `--superficie`; `--cobalto` sobre `--papel`, `--superficie` e `--cobalto-claro`; `--sobre-cobalto` sobre `--cobalto`; `--aviso-texto` sobre `--aviso-fundo`.
4. **Cor por assunto.** Cada assunto tem um matiz (`HUES` em `site/app.js`); o CSS deriva fundo, borda e destaque do cartão com `hsl(var(--h) …)` e os tokens `--tile-*`, que mudam no tema escuro. Assunto novo = matiz novo, nunca cor solta.
5. **Gráficos de Em números** (`--pn-1`, `--pn-2`, `--pn-sec`, `--pn-ok`, `--pn-no`, `--pn-traco`) são definidos em `.numeros`, com versão para o tema escuro. Cada série também tem textura, para não depender só da cor.
6. **Impressão** (`@media print`) usa preto sobre branco com valores fixos, de propósito.

## 2. Letras

Uma fonte só, **Atkinson Hyperlegible Next** (`--sans`), servida pelo próprio site. Nada de outra `font-family`. Pesos leves; os títulos usam `--titulo` (470) com letras mais juntas.

### Tamanhos de letra

`font-size` só aceita estes valores, ou `inherit`.

| Tamanho | Em pixels | Onde |
|---|---|---|
| `0.75rem` | 12 | Etiquetas pequenas (beta, «Novo», selo de IA) e eixos dos gráficos |
| `0.875rem` | 14 | Texto de selos e de legendas, datas |
| `0.95rem` | 15 | Notas, contagens, links do topo, descrições de cartão |
| `1rem` | 16 | Texto comum |
| `1.0625rem` | 17 | Títulos pequenos (h3) e linhas de lista |
| `1.125rem` | 18 | Texto de apoio abaixo do título e resumos |
| `1.2rem` | 19 | A marca no topo, o texto de abertura e o campo de busca grande |
| `1.25rem` | 20 | Título de cartão, estado vazio e texto de abertura dos números |
| `1.6rem` | 26 | Números grandes (placar, contagem do cartão de assunto) |

Os títulos que crescem com a tela usam `clamp()`, só com estes:

| Tamanho fluido | Onde |
|---|---|
| `clamp(2rem, 5.6vw, 3rem)` | Título de página (h1): 32 a 48 px |
| `clamp(2.3rem, 7.2vw, 4.4rem)` | Título da abertura da tela inicial |
| `clamp(1.5rem, 3.6vw, 1.85rem)` | Título de seção (h2): 24 a 30 px |
| `clamp(1.3rem, 3.2vw, 1.5rem)` | Título de seção secundário |
| `clamp(1.9rem, 5vw, 2.6rem)` | Número de destaque |
| `clamp(1.55rem, 4.4vw, 2.3rem)` | Número de destaque, versão menor |

Exceção rara: escrever `token-ok: motivo` num comentário na mesma linha (por exemplo, o cabeçalho compacto do celular).

## 3. Formas e sombras

### Raios

`border-radius` só aceita estes valores (também em formas como `0 var(--raio) var(--raio) 0`).

| Valor | Para quê |
|---|---|
| `0` | Canto reto |
| `var(--raio)` | Cartões, linhas de lista, campos (16 px) |
| `var(--raio-grande)` | Painéis grandes e cartões de assunto (24 px) |
| `var(--perto)` | Peça dentro de uma caixa de raio comum com 8 px de respiro |
| `calc(var(--raio) - var(--perto))` | Idem, calculado: raio da caixa menos o respiro dela (cantos concêntricos) |
| `99px` | Pílulas (botões, etiquetas) |
| `999px` | Pílulas muito compridas |
| `50%` | Círculos |
| `0.25rem` | Contorno do foco |
| `3px` | Barras e amostras dos gráficos |
| `4px` | Pontas das barras dos gráficos |

Cantos concêntricos: um elemento que encosta no canto de uma caixa arredondada tem raio igual ao da caixa menos o respiro dela (ver [`espacamento.md`](espacamento.md)).

### Sombras

Duas sombras, `--sombra` (comum) e `--sombra-alta` (cartão sob o cursor), com valor nos dois temas. Os filetes de 1 px são `box-shadow: inset 0 0 0 1px var(--linha)` (e variações com tokens), nunca `border`: assim não ocupam espaço e as alturas continuam em múltiplos de 4 px. Nenhuma cor escrita à mão em sombra.

## 4. Como conferir

```
python testes/tokens.py
```

Confere, no `site/estilos.css`: as tabelas deste documento batem com os valores do CSS; todo token de cor tem versão para o tema escuro; não há cor escrita à mão fora das definições e da impressão; `font-size`, `font-family` e `border-radius` só usam os valores acima; e os pares de cores de texto têm contraste de pelo menos 4,5:1 nos dois temas. Roda em todo pull request.
