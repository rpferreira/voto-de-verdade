# Espaçamento: grade de 8px com regras

Usar múltiplos de 8px não basta. Para o site ter o mesmo ritmo em todas as telas, todo espaço vem de uma **escala
fixa** e os componentes só usam **papéis**: nomes que dizem a relação entre dois elementos. Quem mexe no CSS escolhe
o papel, não um número. Quanto mais distante o parentesco, maior o espaço.

## 1. Papéis

| Papel | px | Relação | Exemplos |
|---|---|---|---|
| `--junto` | 4 | Partes de uma coisa só | Rótulo e campo, título e subtítulo de uma linha de lista, número e legenda |
| `--perto` | 8 | Itens do mesmo grupo | Ícone e texto, chips, botões lado a lado, título pequeno e seu conteúdo, título, data e barra de um projeto |
| `--item` | 16 | Padrão: irmãos | Entre itens de uma pilha, recuo de cartões, filtros e linhas, título (h1/h2) e conteúdo |
| `--grupo` | 24 | Grupos dentro de um bloco | Recuo de painéis grandes (assunto), topo de página, entre filtros e lista |
| `--bloco` | 32, 48 (≥ 48rem) | Blocos de uma seção | Entre blocos de uma página, início de página, entre seções de texto |
| `--respiro` | 40, 64 (≥ 48rem) | Seções da página | Entre seções, topo da tela inicial, antes do rodapé |
| `--margem` | 16, 32 (≥ 40rem) | Lateral da página | |
| `--calha` | 32, 48 (≥ 56rem) | Entre colunas | |
| `--recuo-icone` | 56 | Uso único | Texto da busca, para caber a lupa |
| `--topo-fixo` | 80 | Uso único | Margem de rolagem sob o cabeçalho fixo |

Os papéis apontam para a **escala** (`--e-meio` 4, `--e-1` 8, `--e-2` 16 … `--e-10` 80), que fica só em `:root`.
Os papéis que crescem com a tela mudam num único `@media`, logo depois dos temas, nunca dentro de componentes.

## 2. Padrões

- **Cabeçalho de página**: migalhas com `--grupo` em cima; páginas sem migalhas começam com `--bloco`; a tela inicial, com `--respiro`.
- **Título e conteúdo**: h1 e h2 ficam a `--item` do que vem abaixo; títulos pequenos (h3, rótulos), a `--perto`.
- **Linha de lista** (projeto, deputado, voto): recuo `--item`; linhas de texto do mesmo item a `--junto`; um item com
  mais de duas partes (título, data, barra) usa `--perto`. Linhas separadas por filete de 1px.
- **Cartão ou painel**: recuo `--item` (compacto) ou `--grupo` (assunto, tile); partes internas a `--junto` ou `--perto`.
- **Controle** (campo, botão, aba): recuo vertical `--perto`, horizontal `--item` (botão redondo grande: `--grupo`). Altura mínima 40px ou 48px.
- **Grade de itens**: `gap` `--item`; colunas de conteúdo, `--calha`.

## 3. Regras

1. **Só papéis.** Em `margin`, `padding`, `gap`, `inset`, `top/right/bottom/left` e `scroll-padding` só entram `0`, `auto`,
   `var(--papel)` ou o negativo de um papel (`calc(-1 * var(--item))`). A escala (`var(--e-*)`) só aparece em `:root`.
2. **Proximidade.** O espaço dentro de um grupo é sempre menor que o espaço entre grupos.
3. **Um dono por espaço.** Em pilhas, o espaço vem do `gap` do contêiner; fora disso, do `margin-top` do elemento de baixo.
4. **Texto.** `line-height` e alturas em múltiplos de 4px (`round(up, 1.1em, 4px)` em títulos).
5. **Linhas finas** de 1px são `box-shadow: inset`, para não ocupar espaço.
6. **Margem negativa** só para alinhar o fundo de um item clicável com o texto da página, do mesmo tamanho do recuo que compensa.
7. **Exceções** são raras e precisam de `espaco-ok: motivo` num comentário na mesma linha.

## 4. Como conferir

```
python testes/espacamento.py            # confere o CSS
python testes/espacamento.py _site      # confere também os valores calculados no navegador
```

O teste roda a cada pull request e barra qualquer valor fora dos papéis ou fora da escala.
