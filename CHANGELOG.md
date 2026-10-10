# Histórico de mudanças do Voto de Verdade

Como a versão é escolhida: [docs/versionamento.md](docs/versionamento.md). Dados atualizados todos os dias não entram aqui.

## 0.3.0 (2026-10-10)

### Novidades
- Página do projeto: o número oficial (por exemplo «PLP 74/2026») e o resultado («Aprovada» ou «Rejeitada») aparecem em destaque acima do título. A etiqueta de resultado é neutra: a mesma cor para aprovada e rejeitada.
- Na seção «Como cada deputado votou», a data da votação ganha a etiqueta de resultado e uma barra de sim, não e demais votos acima dos cartões.

### Ajustes
- Faixa de versão beta da página inicial mais curta (cabe em duas linhas no celular, antes eram quatro).
- O convite para a versão em inglês cabe em uma linha no celular; a frase inteira é o link.
- O botão de idioma passa a ter nome acessível que começa pelo texto visível («EN: English»), para quem usa leitor de tela ou comando de voz.

## 0.2.1 (2026-10-10)

### Ajustes
- «Como o site funciona»: os pontos mais importantes ficam em semibold (versão beta, sem nota e sem ranking, a IA pode errar, ninguém revisa os resumos, o que são votações simbólicas e como citar o site).
- Links para as fontes: portal de Dados Abertos da Câmara, site da Câmara, artigo 17 do Regimento Interno, licenças MIT e CC BY 4.0, além de Em números, Transparência da IA e a licença completa. Links para fora abrem em outra aba.
- A página pronta de «Como o site funciona» (a que buscadores e leitores sem JavaScript veem) passa a ter o mesmo texto da tela do aplicativo, inclusive a explicação de «presidia a sessão».

## 0.2.0 (2026-10-10)

### Novidades
- Página **Licença e uso do conteúdo** (`/licenca/`, também em inglês), com o que está sob licença MIT (código) e CC BY 4.0 (textos e resumos), o que não está coberto e o pedido para não treinar modelos de IA.
- Os textos das licenças agora são publicados como arquivos no próprio site: `/LICENSE` (código, MIT) e `/LICENSE-CONTEUDO.md` (conteúdo).
- Link «Licença» no rodapé e «Ler a licença completa» em «Como o site funciona».

### Ajustes
- Todas as páginas declaram a licença do conteúdo (`<link rel="license">`); a página de licença entra no mapa do site, no `llms.txt` e no catálogo de APIs (`.well-known/api-catalog`).

## 0.1.0 (2026-10-10)

Primeira versão numerada. O site passa a mostrar a versão no rodapé.

### Novidades
- Versão do site no rodapé de todas as páginas, com link para este histórico.

### Já existia nesta data
- Votações por assunto, projeto e deputado, com o voto de cada deputado federal nas votações nominais.
- Busca por tema ou palavra, página do deputado (com filtros), tela **Em números** (com exportação em CSV e JSON) e **Transparência da IA**.
- Versão em inglês (`/en/`) e modo escuro.
- Lista de deputados em cartões clicáveis, pílulas para «Fora do exercício agora» e votação simbólica ou secreta, e a etiqueta **Novo** nas últimas votações (para projetos que chegarem a partir de 10/10/2026).
- Dados abertos em JSON (`dados/`), atualizados todos os dias.
