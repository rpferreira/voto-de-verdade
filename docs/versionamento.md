# Versionamento do Voto de Verdade

A versão do site aparece no rodapé de todas as páginas («Versão 0.1.0 (beta) · Histórico de mudanças») e vem de **um único arquivo**: `VERSION`, na raiz do repositório. O histórico fica em `CHANGELOG.md`.

> Não confunda com o `?v=abc123` que aparece nos endereços de `app.js` e `estilos.css`. Aquilo é só um código para o navegador baixar de novo o arquivo quando ele muda (veja `versao()` em `site/gerar_paginas.py`). A versão do site é esta.

## 1. Formato

`MAJOR.MINOR.PATCH`, por exemplo `0.3.2`, no estilo do [Versionamento Semântico](https://semver.org/lang/pt-BR/), adaptado a um site com dados abertos.

| Parte | Quando sobe | Exemplos |
|---|---|---|
| **MAJOR** | Muda algo que **quebra quem usa o site ou os dados**: um endereço deixa de funcionar, um campo some ou muda de nome em `dados/*.json`, o formato dos CSV/JSON exportados muda | renomear `projetos.json`; mudar `/projeto/<id>/` |
| **MINOR** | Novidade que a pessoa **vê ou pode usar** | tela nova, filtro novo, idioma novo, dado ou campo público novo, nova exportação, nova etiqueta |
| **PATCH** | Correção ou ajuste que **não muda o que o site faz** | bug, texto, espaçamento e cores, acessibilidade, desempenho, testes e documentação que mexem no código do site |

Quando uma mudança cabe em dois níveis, vale o **maior**. Ao subir uma parte, as à direita voltam a zero (`0.3.2` → `0.4.0`).

## 2. Fase atual: beta (`0.x.y`)

Enquanto o site tiver a etiqueta **beta** no topo, a versão começa com `0`:

- o formato dos dados e os endereços ainda podem mudar. Uma mudança que quebra sobe o **MINOR** e é marcada como **Quebra** no `CHANGELOG.md`;
- **`1.0.0`** sai no dia em que a etiqueta beta for retirada. Daí em diante vale a tabela acima por inteiro (quebra = MAJOR).

## 3. O que não muda a versão

São a rotina de dados e não o código do site:

- a atualização diária dos dados, os resumos e traduções feitos por IA, as fotos novas e a foto do painel (os commits do robô);
- mudanças só em `site/dados/`, `site/fotos/` e `dados/`.

A data dos dados aparece à parte, no rodapé («Atualizado em …»).

## 4. Quem muda a versão e quando

Cada pull request **muda a versão uma vez**, escolhendo o nível pelo que ela traz:

1. mexeu no código do site (`site/`, menos `site/dados/` e `site/fotos/`) ou na coleta (`coleta/`)? **Sobe `VERSION` e escreve a entrada no `CHANGELOG.md`**;
2. mexeu só em testes, documentação ou fluxos do GitHub (`.github/`)? Não precisa subir (pode, se quiser registrar).

Como as pull requests entram uma por vez (squash), **uma versão = uma pull request mesclada**.

## 5. O `CHANGELOG.md`

Uma seção por versão, da mais nova para a mais antiga, com data ISO e português simples, escrito para quem usa o site e não para quem lê o código:

```
## 0.2.0 (2026-10-14)

### Novidades
- …
### Ajustes
- …
### Correções
- …
### Quebra
- … (só quando algo deixa de funcionar como antes)
```

Só entram as seções que têm conteúdo. A primeira versão do arquivo tem de ser igual a `VERSION`.

## 6. Conferência automática

`python3 testes/versao.py _site` roda em todo pull request (fluxo «Testar o site») e confere:

- `VERSION` no formato `X.Y.Z`;
- `CHANGELOG.md` em ordem, sem versão repetida, e com a entrada mais nova igual a `VERSION`;
- que o rodapé de cada página montada (português, inglês, 404 e páginas prontas) mostra a versão certa;
- no pull request (`--base origin/main`): quem mexeu no código do site ou na coleta subiu `VERSION` para um número maior que o da `main` e acrescentou a entrada no `CHANGELOG.md`.
