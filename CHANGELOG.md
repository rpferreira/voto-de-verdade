# Histórico de mudanças do Voto de Verdade

Como a versão é escolhida: [docs/versionamento.md](docs/versionamento.md). Dados atualizados todos os dias não entram aqui.

## 0.11.2 (2026-11-26)

### Ajustes
- **Código do site em módulos:** o `app.js` (com mais de 2 mil linhas) começa a ser dividido em arquivos menores, que o navegador abre como módulos JavaScript. Nesta primeira etapa saem as funções puras (montar elementos, busca sem acento, conta de porcentagem) para `site/js/util.js`. O site faz o mesmo que antes: as telas, em português e em inglês, nos modos claro e escuro, ficaram idênticas, ponto a ponto.
- **Versão dos arquivos:** o `?v=` do `app.js` agora vale para o conjunto (o `app.js` e tudo que está em `site/js/`), e o gerador coloca o mesmo código em todo `import`; assim o navegador nunca mistura um `app.js` novo com um módulo velho. As páginas também avisam o navegador dos módulos (`modulepreload`), para baixá-los junto com o `app.js`.
- **Testes:** novo `testes/modulos.py` (imports relativos e existentes, nenhum módulo sem uso, nenhum import circular, mesmo `?v=` em todo lugar). O teste de idiomas passa a ler também os módulos.

## 0.11.1 (2026-11-26)

### Ajustes
- **Tamanhos de letra:** o site usava 22 tamanhos diferentes, vários quase iguais (de 14,4 a 15,6 px, por exemplo). Agora há uma escala fixa, e os valores soltos foram para o degrau mais próximo, com diferença de no máximo 0,8 px: links do topo, abas, descrição dos cartões de assunto, fichas de voto, partido e estado nos cartões de deputado e descrições dos princípios (15 px); seletor de idioma, guia da votação e detalhe dos gráficos (14 px); título do rodapé (17 px). O cabeçalho do celular mantém os tamanhos compactos de propósito.
- **Painel «Princípios» da tela inicial:** o canto passa de 20 para 24 px de raio, o mesmo dos outros painéis grandes.
- **Documentação e testes:** novo `docs/design-system.md` com as cores (claro e escuro), a escala de letras e os raios, e novo teste `testes/tokens.py` que barra cor escrita à mão, tamanho de letra ou raio fora das tabelas, token de cor sem versão escura e contraste de texto abaixo de 4,5:1.

## 0.11.0 (2026-11-26)

### Novidades
- **Catálogo de componentes (`/catalogo/`):** página pública, em português e em inglês, com as cores, os tipos de letra, os espaços, as formas e as peças com que as telas são montadas: botões, campo de busca, fichas de voto, placar, selos, avisos, cartões de projeto, de deputado e de assunto, estado vazio e ícones. As peças são as mesmas das telas, com exemplos inventados, e dá para ver nos modos claro e escuro. Ela não aparece no menu nem no rodapé: abre pelo endereço.

### Ajustes
- **Selos de duas linhas no celular:** o selo «Votação simbólica, sem o voto de cada deputado» tinha 42px de altura quando o texto passava para a segunda linha, fora da grade de 4px do site. O filete de 1px do selo passa a ser sombra interna, e o selo fica com 40px. Vale também para o selo de aviso. O visual é o mesmo.
- **Testes:** o catálogo entra nos testes de navegador, de espaçamento, de idiomas e de segurança.

## 0.10.4 (2026-11-18)

### Ajustes
- **Rotina diária de dados:** quando a API da Câmara cai (erro 503 ou sem resposta), a coleta agora espera e tenta de novo, em vez de desistir depois de poucos segundos: pausas de 30 s, 90 s, 3 min e 5 min, com no máximo 15 minutos de espera na coleta toda. Em 10/11 e 18/11 a API falhou nas consultas mais recentes e a lista de deputados, a coleta ficou incompleta, o teste de segurança bloqueou a publicação, e o site ficou desatualizado. Há um teste novo (`testes/coleta_repeticao.py`).

## 0.10.3 (2026-10-21)

### Ajustes
- **Tela inicial:** sai a linha «Já sabe quem? Procure um deputado pelo nome. Ou veja os números das votações e as últimas votações» sob a busca. Esses caminhos continuam no menu.
- **Resultado da busca:** a contagem («11 projetos com “impostos”») deixa de ficar ao lado do título «Projetos», onde confundia, e passa para a linha logo abaixo dele, antes da frase sobre os projetos com voto de cada deputado.

## 0.10.2 (2026-10-21)

### Ajustes
- **Página «Como o site funciona»:** a frase de privacidade dizia que o navegador guarda só a escolha do modo escuro. Agora diz tudo o que ele guarda: o modo escuro, o idioma e o fechamento da faixa «Read in English», sem enviar nada a ninguém. Nova seção explica que «Últimas votações» e «Decididas por pouco», na tela inicial, mostram só votações nominais, e onde achar as simbólicas. Em português e em inglês.

## 0.10.1 (2026-10-14)

### Ajustes
- **Rotina diária de dados:** em 14/10 ela falhou na etapa que guarda as traduções no repositório e o site não foi publicado com os dados do dia. O motivo: o git se recusa a juntar as novidades quando há arquivos já refeitos pela rotina e ainda não guardados (como `site/dados`). O script agora os põe de lado e os devolve (`--autostash`). Há um teste novo (`testes/guardar.py`), que falha sem o conserto.

## 0.10.0 (2026-10-13)

### Novidades
- **Botão «Filtrar» em «Em números»:** o filtro de ano agora tem o mesmo botão das outras caixas de filtros. Ao apertar, o ano é aplicado e a tela vai até o resultado. A tela agora diz também de que ano são os números.

### Ajustes
- **Cartões de projeto no celular:** o texto «Votação simbólica, sem o voto de cada deputado» passava para a segunda linha e ficava por cima da etiqueta cinza e da linha de baixo. A etiqueta agora cresce para duas linhas quando o texto não cabe, e a de «Classificação incerta» também.
- **Votos na página do deputado, no celular:** o «Sim» ou «Não» tomava a largura da linha e deixava o título do projeto numa coluna estreita. Agora o voto fica embaixo do título, que usa a largura toda.

## 0.9.0 (2026-10-13)

### Novidades
- **Botão «Buscar» (lupa) na busca da tela inicial e da página de erro.** Ele faz o mesmo que o Enter, e o teclado do celular também tem a sua tecla de buscar.
- **Botão «Filtrar» nas caixas de filtros** (assunto, projeto, lista de deputados e página do deputado). É um botão só para tudo: o nome ou a palavra e os filtros de partido, estado, voto e assunto. Ele aplica o que está nos campos e leva ao resultado, como o Enter.

### Mudanças
- **Ao confirmar uma busca ou um filtro, a tela e o foco vão para o resultado.** No celular, o resultado ficava abaixo da dobra e a pessoa tinha de rolar para achá-lo. Agora, ao apertar Enter, tocar em «Buscar» ou «Filtrar», ou escolher um tema de exemplo (como «impostos» ou «trabalho»), a página rola até o resultado e o foco vai para a contagem logo acima dele («12 deputados»), o que também avisa quem usa leitor de tela. Digitar e trocar um filtro continuam atualizando a lista sem rolar a tela. A busca da página de erro (404) também leva ao resultado na tela inicial.

## 0.8.0 (2026-10-12)

### Mudanças
- **Os números de Sim, Não, Abstenção e Presidia deixam de ser filtro.** Eles continuam mostrando o total, mas não são mais botões, nem na página do projeto nem na do deputado. O filtro por voto já existia na caixa «Filtrar por» e fazia o mesmo, então o clique era repetido e ficava ruim no celular. Saem também a frase «Toque em um número…» e o destaque de «número escolhido».
- **No celular, a página do projeto passa a ter o campo «Voto» na caixa de filtros.** Antes ele só aparecia no computador, porque no celular o clique no número fazia esse papel.

## 0.7.0 (2026-10-10)

### Novidades
- **Imagem de compartilhamento própria** ao colar o link no WhatsApp, X, LinkedIn e afins: cada deputado (foto, nome, partido e estado), cada assunto (nome, descrição e quantidade de projetos) e as páginas fixas (Deputados, Em números, Como o site funciona, Transparência da IA, Licença, Apoie) têm a sua, em português e em inglês. Os projetos continuam com a imagem geral do site.
- As imagens são feitas na hora de montar o site, sem IA e sem ir para o repositório (precisa do Pillow, que já entra nos testes e na publicação). Sem o Pillow, o site usa a imagem geral, como antes. Só mostram nome, partido e estado ou o texto da página: nada de nota, placar ou ranking.

## 0.6.1 (2026-10-10)

### Ajustes
- **Busca (SEO):** título da tela inicial com «como cada deputado federal votou na Câmara»; páginas de assunto com título «Saúde na Câmara: projetos e votos | Voto de Verdade» (o aplicativo usa o mesmo título depois de abrir); `twitter:image` nas páginas.
- **Dados estruturados:** mais palavras-chave na tela inicial (de 5 para 12) e organização do site; deputados com link para a página oficial da Câmara, foto e data da última votação; projetos com tipo (PL, PEC…) e as tags do projeto como palavras-chave.
- **Mapa do site (sitemap):** cada página passa a informar a data em que o conteúdo mudou de verdade (a última votação do projeto, do deputado ou do assunto), em vez de a data de hoje em todas. O Google ignora datas que mudam todo dia sem motivo.

## 0.6.0 (2026-10-10)

### Novidades
- **Visual padronizado em todas as telas.** Os projetos das listas (últimas votações, assuntos e busca) agora são cartões com seta à direita, iguais aos de Deputados. Os votos na página do deputado também viram cartões, com o voto Sim/Não antes da seta.
- Títulos de página com o mesmo tamanho em todas as telas (exceções: a abertura da home e o título do projeto, que é uma frase inteira); títulos de seção, subtítulos, textos de apoio, notas e contagens também seguem uma escala só.
- Botões secundários («Limpar filtros», «Mostrar mais», «Compartilhar», atalhos da página de erro) com o mesmo tamanho; só o botão de doação é maior.
- Espaço entre o caminho de navegação («Início / Em números») e o título igual em todas as telas; as páginas de texto (Como o site funciona, Apoie, Licença) alinham à esquerda como as demais, com o texto corrido numa coluna de leitura.

### Ajustes
- Saiu o seletor **Ordem** da lista de votos do projeto: a lista fica sempre em ordem alfabética por nome.

## 0.5.0 (2026-10-10)

### Novidades
- Número oficial («PLP 74/2026») antes do título em todas as listas de projetos: últimas votações, assuntos e busca.
- Lista de votos do projeto: cada deputado em um cartão clicável (nome, partido e estado, voto Sim/Não e seta), igual ao da lista de Deputados, e novo seletor **Ordem** (nome, partido, estado ou voto; sempre em ordem alfabética dentro de cada grupo). A ordem escolhida vai para o endereço da página.
- Caixas de filtros ganham o título **Filtrar por** (votos do projeto, Deputados, assunto e página do deputado).
- Botão **Voltar ao topo**, que aparece depois de duas telas de rolagem.
- **Impressão e PDF:** somem o menu, as faixas, os filtros e os botões; o texto sai em preto sobre branco (com as cores do modo claro no Sim/Não), os blocos recolhidos «Pontos principais e texto oficial» abrem sozinhos e os links para fora mostram o endereço.

### Ajustes
- Temas de exemplo sob a busca da home: três no computador e dois no celular (saiu «servidores públicos» e, no celular, «segurança pública»).
- `destaques.json` passa a trazer o número oficial de cada projeto.

## 0.4.0 (2026-10-10)

### Novidades
- Página inicial: o campo de busca diz «Busque por assunto ou palavra» e os temas de exemplo ficam em botões logo abaixo («impostos», «trabalho»…), que preenchem o campo com um toque; novo link «as últimas votações», que leva direto à lista.
- Deputados: o campo de nome vem primeiro e, no celular, os 27 estados ficam recolhidos em «Deputados do seu estado» (abrem sozinhos se já houver um estado escolhido, e o título mostra qual).

### Correções
- Página do projeto: a etiqueta de resultado não se repete mais na seção «Como cada deputado votou». Ela só reaparece ali quando a votação escolhida teve resultado diferente do da última votação.

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
