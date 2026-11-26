# Módulos do site (`site/js/`)

O `site/app.js` tem mais de 2 mil linhas e está sendo dividido, aos poucos, em módulos JavaScript nativos (`import`/`export`), **sem bundler**: o navegador abre os arquivos como estão. Uma fatia por pull request, sem mudar o que o site faz.

## Regras

1. **Sem mudança de comportamento.** Cada fatia só move código. Antes de abrir o PR, as telas (português e inglês, claro e escuro) têm de ficar idênticas, ponto a ponto, às da versão anterior.
2. **Só imports relativos**, com a extensão (`from "./js/util.js"`), e nada de biblioteca externa. A política de segurança (`script-src 'self'`) já cobre módulos do mesmo endereço.
3. **Sem `?v=` no código-fonte.** O gerador (`fixar_modulos` em `site/gerar_paginas.py`) acrescenta, só no `_site`, o mesmo `?v=` ao `app.js` e a todo `import`, e `<link rel="modulepreload">` em cada página. O código é a impressão do `app.js` e de `site/js/**` juntos, então qualquer mudança troca todos os endereços de uma vez e o navegador nunca mistura um arquivo novo com um velho.
4. **Nenhum módulo sem uso e nenhum import circular.** `python testes/modulos.py _site` confere isso e o `?v=`.
5. **Texto de tela passa por `tx()`** como antes. `testes/idiomas.py` lê o `app.js` e todos os arquivos de `site/js/`.
6. **Mudou `site/`?** Sobe a versão e o CHANGELOG (`docs/versionamento.md`); mover código sem mudar o que o site faz é PATCH.

## O que já saiu do `app.js`

| Módulo | Conteúdo | Depende de |
|---|---|---|
| `js/util.js` | `h`, `svg`, `semAcento`, `termos`, `casa`, `decodificar`, `soHttps`, `somaDe`, `pctNum` | só do `document` (`h` e `svg`) |

## Próximas fatias (esboço)

1. `ambiente.js` e `i18n.js`: configuração da página (`CONFIG`, `RAIZ`, `LANG`, `LOCALE`), `tx` e os formatadores de data, número e plural.
2. `dados.js`: `dados()` e a tradução dos dados.
3. `componentes/`: selos, fichas de voto, placar, cartões (inclui extrair `cartaoDeputado`, hoje repetido em 4 lugares).
4. `telas/`, uma por PR, começando pelo catálogo (o mais isolado) e terminando pelo início.
5. O roteador por último; só então sai a função que envolve o arquivo (hoje o `return` do redirecionamento 404 depende dela).

Cada passo atualiza esta tabela.
