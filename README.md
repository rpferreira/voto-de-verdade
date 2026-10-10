# Voto de Verdade

Mostra ao cidadão como cada deputado federal votou, por assunto e por deputado, em linguagem simples.

Os dados vêm da API de Dados Abertos da Câmara dos Deputados. Este repositório guarda a rotina que
busca esses dados todo dia e monta o banco de dados que alimenta o site.

## Endereço do site

O site fica em **https://votodeverdade.com.br** (domínio registrado no registro.br, publicado pelo GitHub Pages).
O DNS é configurado no painel do registro.br e o domínio é informado em *Settings → Pages → Custom domain*; como o
site é publicado por workflow, não existe arquivo `CNAME` no repositório. O endereço antigo
(`rpferreira.github.io/voto-de-verdade`) redireciona sozinho para o novo. Se o domínio mudar, troque o endereço em
`site/gerar_paginas.py` (padrão do `--url`), em `site/index.html` e nos dois workflows que passam `--site`
(`atualizacao-diaria.yml` e `vigiar-site.yml`).

## Princípios do produto

- **Sem nota e sem ranking.** O site mostra o que cada deputado votou, não quem é "melhor" ou "mais fiel".
  Nenhum filtro ou ordenação ordena deputados por quanto votaram de um jeito.
- **Entrada pelo assunto do cidadão.** Primeiro o assunto, depois os itens votados, e só então como cada
  deputado votou. Também há a entrada por deputado.
- **Honestidade sobre o tipo de voto.** Votação de mérito, urgência e emenda são separadas. Votação
  simbólica (sem voto individual) e votação secreta têm avisos próprios.
- **Conferível.** Cada resumo traz ao lado a ementa original e o link do texto integral.
- **Sem revisão humana, com incerteza assumida.** Toda classificação automática leva uma confiança
  (alta, média ou baixa). Quando não é alta, a tela avisa: "A classificação desta votação foi feita
  automaticamente e pode estar errada", com o motivo em palavras simples.

## Como funciona

1. Todo dia, às 6h (horário de Brasília), o GitHub roda `coleta/coletar_votacoes.py`. Ele busca as votações
   novas na API da Câmara e atualiza `dados/cache_v5.json`, que é commitado no repositório.
2. Em seguida, `coleta/construir_banco.py` monta o banco `dados/voto_de_verdade.db` a partir do cache e de
   `dados/resumos.json`. O banco é refeito do zero a cada rodada, fica guardado por 7 dias na aba Actions
   e não vai para o repositório.
3. Depois, `coleta/resumir_projetos.py` pede a uma IA o assunto e o resumo dos projetos novos, mede a confiança de
   cada um e guarda tudo em `dados/resumos.json`. O banco é refeito com os resumos.
4. Se algo falhar, a execução fica vermelha na aba Actions e o GitHub avisa o dono do repositório por e-mail.

```
API da Câmara ──► coletar_votacoes.py ──► dados/cache_v5.json ─┐
                                                               ├──► construir_banco.py ──► voto_de_verdade.db
                          dados/resumos.json (assunto, resumo) ┘
```

## O que é coletado

- **Fonte:** `https://dadosabertos.camara.leg.br/api/v2` (aberta, sem chave de acesso).
- **Período:** a legislatura inteira, desde 1/2/2023.
- **Quais votações:** só plenário, e só as de mérito (a decisão sobre a proposta em si). Urgência, emenda,
  requerimento, destaque e procedimento ficam de fora do site.
- **Votos individuais:** Sim, Não, Abstenção, Obstrução e Artigo 17. O partido guardado em cada voto é o que
  a API informa junto com o voto.
- **Simbólica:** votação sem voto individual. Aparece com um aviso e pode ser filtrada.
- **Secreta:** quando todos os registros de uma votação vêm sem tipo de voto, ela é tratada como secreta.

### Como cada votação é classificada

A categoria sai do texto da descrição da votação, por regras de texto (mérito, urgência, emenda,
requerimento, destaque, parecer, redação final, tramitação, procedimento, outros). O projeto votado é
descoberto pelo tipo, número e ano citados no texto e, se isso falhar, pelas proposições afetadas que a
própria Câmara indica na votação.

A confiança de cada votação é a **menor** entre estas três:

| Verificação | Resultado |
| --- | --- |
| Texto da descrição | Baixa se o texto mistura tipos de decisão (por exemplo, projeto e emenda) |
| Ligação com o projeto | Baixa se não achou o projeto ou se o número citado não existe na Câmara; média se o texto não cita o número |
| Totais de votos | Baixa se "Sim: N; Não: N" do texto não bate com os votos de cada deputado |

## Banco de dados

SQLite, refeito do zero a cada rodada.

| Tabela | Conteúdo |
| --- | --- |
| `deputados` | Nome, partido atual, estado, foto, e-mail, se está em exercício |
| `projetos` | Tipo, número, ano, ementa, link do texto integral, assunto (principal e secundário), confiança do assunto, resumo |
| `votacoes` | Data, projeto, descrição, resultado, tipo (nominal, simbólica ou secreta), confiança e aviso, totais |
| `votos` | Voto de cada deputado em cada votação, com o partido do dia do voto |
| `execucoes` | Histórico das rodadas: contagens, problemas e avisos |

`dados/resumos.json` guarda o assunto e o resumo de cada projeto, no formato
`{"<id do projeto>": {"assunto", "assunto_secundario", "confianca_assunto", "motivo_assunto", "resumo",
"confianca_resumo", "motivo_resumo", "pode_diferir", "pontos_chave", "tags"}}`. Quem escreve é o `resumir_projetos.py`.

## Assunto e resumo por IA

Não há revisão humana, então a confiança é medida por checagens automáticas:

1. **Modelo principal** (Claude Sonnet 5.5): escolhe o assunto, escreve o resumo e diz quanto tem de certeza.
2. **Segunda leitura** (Claude Haiku 4.5): escolhe o assunto sem ver a resposta do primeiro. Se os dois discordam, a
   confiança do assunto é baixa.
3. **Palavras-chave** da ementa conferem se o assunto faz sentido.
4. **Conferência do resumo** (Claude Haiku 4.5): compara o resumo com o texto original e aponta o que não tem apoio
   nele. Resumo sem apoio no texto é descartado, e a tela mostra só a ementa original.
5. **Substitutivo ou emenda:** quando a votação foi sobre um substitutivo, o texto votado pode ser diferente da
   ementa. O banco guarda um aviso para a tela dizer isso.

O texto enviado à IA é a ementa oficial e os textos das votações. Ela é instruída a usar só esse texto, a ser neutra e
a não dizer se o projeto foi aprovado ou rejeitado (o resultado vem de cada votação, e um projeto pode ter várias).
Todo resumo deve aparecer na tela com o selo "gerado por inteligência artificial", a ementa original e o link do texto
integral.

**Custo.** A API é paga por uso, com créditos pré-pagos. Pelos preços de outubro de 2026, a carga inicial dos cerca de
900 projetos deve custar poucos dólares, e depois a rotina diária gasta centavos. O log de cada rodada mostra o gasto
estimado. Sem a chave `ANTHROPIC_API_KEY` no GitHub, a etapa é pulada sem erro.

**Teste barato.** Em Actions, **Run workflow**, preencha "limite_resumos" com `5`. A rotina resume só 5 projetos e
mostra o gasto no log.

**Reavaliar sem custo.** Em Actions, **Run workflow**, com "reavaliar" = `sim`, a rotina refaz só as confianças dos resumos
já feitos, sem chamar a IA e sem gastar. Ela tira o aviso "uma conferência automática achou partes do resumo sem apoio"
quando tudo o que a conferência apontou estava no próprio texto ou era só "a ementa não detalha...".

**Testes com projetos escolhidos.** "espalhar" = `sim` sorteia projetos de toda a lista (em vez dos mais recentes), e "ids"
aceita uma lista de projetos separados por vírgula.

## Versão em inglês

O site inteiro existe também em inglês, em `/en/` (mesmas telas e endereços: `/en/projeto/<id>/`, `/en/deputado/<id>/`…). Um seletor **PT | EN** fica no cabeçalho; no celular, dentro do menu (o botão de modo escuro continua ao lado do menu). Cada página aponta para a outra versão (`hreflang`, `x-default` e alternativas no `sitemap.xml`), e há também `llms.txt`, Markdown, `dados/LEIA-ME.md` e `openapi.json` em inglês.

- **Textos fixos** (botões, títulos, explicações): `site/idiomas/en.json`. A chave é o texto em português, igual ao do código; `{0}`, `{1}`… marcam os trechos que mudam. O mesmo dicionário serve ao JavaScript (`tx()`) e ao Python (`site/idioma.py`).
- **Projetos e votações**: a IA traduz o assunto, o resumo, os pontos-chave e a descrição de cada votação (`coleta/traduzir_projetos.py`, que grava em `dados/traducoes_en.json`). Cada tradução guarda uma impressão do texto em português; se o português muda, a tradução é refeita. `site/exportar_en.py` junta tudo em `site/dados/en/`, que o site lê no lugar dos dados em português.
- **Ementa oficial**: continua em português (é o texto da Câmara), marcada com `lang="pt-BR"` e uma nota dizendo isso.
- **Rotina diária**: depois dos resumos, a etapa "Traduzir para o inglês os projetos novos com IA" traduz só o que é novo ou mudou (`limite_traducoes` no Run workflow; use `5` para um teste barato). Sem a chave `ANTHROPIC_API_KEY`, a etapa é pulada. Se algo ficar sem tradução, o site em inglês mostra esse item em português e o monitoramento avisa quando passam de 50.
- **Testar**: `python3 testes/idiomas.py _site` confere o dicionário, os dados, as páginas e as telas no navegador (nenhum texto faltando nem português solto). Roda em todo pull request.
- **Convite para o inglês**: quem abre o site em português com o navegador em inglês vê uma faixa fina "Read in English" (leva à mesma tela em inglês). Ela some ao dispensar ou ao escolher PT no seletor, e a escolha fica só no navegador.
- **Só em português**: os arquivos `.well-known/` (a skill de agentes).
- **Página de erro (404)**: uma em cada idioma (`404.html` e `en/404.html`), com busca, os caminhos principais e uma mensagem conforme o tipo de endereço (projeto, deputado, assunto). O GitHub Pages só usa a `404.html` da raiz; para endereços que começam por `/en/`, o `app.js` leva à versão em inglês.
- **Imagem de compartilhamento**: `site/og-en.png` nas páginas em inglês. Para refazer (se a legenda ou o `og.png` mudarem): `python3 site/criar_og_en.py`.
- **Montar só um idioma**: `python3 site/gerar_paginas.py --saida _site --idiomas pt` (ou `en`).

## Telas e filtros planejados

| Tela | Filtros | Ordenações (a primeira é a padrão) |
| --- | --- | --- |
| Início por assunto | busca por palavra | A–Z; votação mais recente; mais votações |
| Página do assunto | período, tipo de proposta, resultado, como foi votada, só confiança alta, assunto secundário, busca | mais recente; mais antiga; mais disputada; nome A–Z |
| Votação | voto, partido, estado, só em exercício, nome | nome A–Z; partido; estado; voto |
| Busca de deputados | estado, partido, em exercício, nome | nome A–Z; estado; partido |
| Página do deputado | assunto, período, como votou, resultado, busca | mais recente; mais antiga; mais disputada; por assunto |

Os filtros vão no endereço da página, para o cidadão poder compartilhar o link de uma busca. Nada some sem
o cidadão pedir: o filtro de confiança vem desligado.

## O site

A pasta `site/` é o site (HTML, CSS e JavaScript puros, sem instalar nada). Telas prontas:

- **Buscadores e agentes de IA**: `site/gerar_paginas.py` escreve, para cada projeto, deputado e assunto, uma página com o conteúdo já no HTML (lê-se sem JavaScript), dados estruturados (schema.org: Legislation, ProfilePage, CollectionPage, Dataset e BreadcrumbList), links entre as páginas e uma versão em Markdown (`index.md`). Também cria `llms.txt`, `robots.txt` (com `Content-Signal: search=yes, ai-input=yes, ai-train=no`: busca e uso para responder perguntas liberados, treino de modelos não), `openapi.json` e `dados/LEIA-ME.md` (os JSON em `dados/` são uma API aberta, sem chave), `.well-known/api-catalog` e `.well-known/agent-skills/` (a skill fica em `site/modelos/skill.md`). No navegador, o `app.js` registra ferramentas WebMCP de leitura (`listar_assuntos`, `buscar_projetos`, `votos_do_projeto`, `buscar_deputado`, `votos_do_deputado`) quando o navegador tem `document.modelContext`. Observação: `robots.txt`, `llms.txt` e `.well-known/` só são lidos por buscadores e agentes na raiz do domínio; no endereço `usuario.github.io/repositorio` eles ficam numa subpasta e não são descobertos sozinhos. Com domínio próprio passam a valer.
- **Apoie (doação única)**: preencha `doacao.url` em `site/config.json` com o link de pagamento do serviço escolhido (link de pagamento único, sem assinatura). Enquanto estiver vazio, nada de doação aparece. Com o link, o rodapé ganha o convite e a página `apoie/` explica que doar não muda o conteúdo (neutro e apartidário, sem nota e sem ranking) e leva ao serviço de pagamento. O site não vê nem guarda dados de pagamento.
- **Modo escuro**: o site segue o aparelho; um botão (ícone no topo, ou "Modo escuro" no rodapé no celular) troca na hora e a escolha fica só no navegador.
- **Início**: título e busca. A busca acha projetos e assuntos. Logo abaixo, os três compromissos do site (neutro e apartidário, sem nota e sem ranking, só o que foi votado) e os assuntos em cartões coloridos, as últimas votações e as votações decididas por pouca diferença (sim e não a menos de 15% uma da outra).
- **Assunto** (`#/assunto/<assunto>`): lista de projetos votados, com abas "com o voto de cada deputado" e "todos". Cada linha mostra o placar e abre o projeto.
- **Projeto** (`#/projeto/<id>`): título e resumo (aviso amarelo só quando a IA tem dúvida sobre o assunto ou o resumo; a nota sobre substitutivo é cinza e discreta), o placar e o voto de cada deputado. Tocar num número do placar mostra só aqueles deputados. Filtros por nome, partido, estado e voto. Se o projeto teve mais de uma votação, dá para escolher qual ver. O endereço antigo `#/votacao/<id>` abre a mesma página.
- **Deputados** (`#/deputados`): atalho por estado, busca por nome e partido.
- **Deputado** (`#/deputado/<id>`): os votos dele nas votações nominais, com filtros por assunto e voto. Sem nota e sem ranking.
- **Como o site funciona** (`#/sobre`): de onde vêm os dados, o que a IA faz, por que nem toda votação mostra o voto de cada deputado, quem faz o site e privacidade (sem cookies, sem rastreamento).

**Páginas para compartilhar.** `site/gerar_paginas.py` cria uma página para cada projeto (`projeto/<id>/`), deputado (`deputado/<id>/`) e assunto (`assunto/<slug>/`), com título, descrição e imagem de prévia próprios (WhatsApp, Google), mais `sitemap.xml`, `robots.txt` e a página de erro (`404.html`). As páginas abrem o mesmo aplicativo. O botão "Compartilhar" copia o endereço dessa página.

**Visual.** Uma fonte só, sem serifa: Atkinson Hyperlegible Next (livre, licença OFL, servida pelo próprio site). Uma cor de destaque (azul), âmbar só para avisos de incerteza, pesos leves, modo claro e escuro, menos movimento se o sistema pedir.

**Versão dos arquivos.** O navegador guarda cópia do `app.js`, do `estilos.css`, do `tema.js` e do dicionário (`idiomas/en.json`) por alguns minutos. O gerador de páginas põe no endereço uma impressão do conteúdo (`app.js?v=…`), então uma versão nova nunca se mistura com a velha.

Os dados que o site lê ficam em `site/dados/` e são gerados por `python3 site/exportar_dados.py` a partir do banco. As fotos dos deputados ficam em `site/fotos/` (`python3 site/baixar_fotos.py` baixa só as que faltam). A atualização diária faz tudo isso e publica no GitHub Pages. Mudanças em `site/` publicadas no ramo principal também vão ao ar sozinhas (fluxo **Publicar o site**), sem precisar rodar a atualização diária.

**Em números.** A tela só conta e descreve (nada ordena pessoas, não dá nota e não compara partidos): votações ao longo do tempo, por assunto e resultado; quantos deputados votaram, o placar das nominais e como a inteligência artificial é usada (modelos, confiança e avisos). Cada gráfico tem a tabela numa página própria (`/em-numeros/<tabela>/`), um filtro por ano (`?ano=2025`; o `painel.json` traz o período inteiro e, em `por_ano`, os mesmos campos de cada ano) e os botões **Baixar CSV** e **Baixar JSON**. Como a inteligência artificial é usada tem menu e página próprios, **Transparência da IA** (`/inteligencia-artificial/`: o que faz, como é feito, confiança, avisos e limites). Só «Confiança» tem tabela própria e exportação; os outros blocos são texto. O mesmo filtro por ano e a mesma exportação existem na página do assunto, na lista de deputados, na página do deputado e nos votos de cada projeto. Os arquivos baixados (CSV com BOM e CRLF, para abrir direto no Excel; JSON com título, fonte, licença, data e filtros usados) são montados no navegador, sem enviar nada a ninguém; nas páginas estáticas, sem JavaScript, o filtro e os botões não aparecem. Os números são refeitos a cada atualização diária, e o fluxo **Foto do painel (Em números)** tira um PNG da tela, anexa à execução (Artifacts, 30 dias) e guarda a mais recente em `painel/ultima-geracao.png`.

**Testes.** `python3 site/gerar_paginas.py --saida _site` e `python3 testes/fumaca.py _site` abrem o site num navegador de verdade e conferem as telas principais (precisa de `pip install -r testes/requirements.txt` e `playwright install chromium`). O fluxo **Testar o site** roda isso em todo pull request.

**Segurança.** `python3 testes/seguranca.py` (roda em todo pull request) troca os dados por versões com código malicioso, gera o site e confere que nada executa, que links só valem se forem `https://` e que a política de segurança (CSP) bloqueia script embutido. Detalhes em [`SECURITY.md`](SECURITY.md).

**Atualizar as versões fixas.** O Dependabot abre pull requests semanais para as ações do GitHub e para o programa de teste. Os testes do pull request só cobrem o site; as ações usadas pela rotina diária (`checkout`, `upload-artifact`, `deploy-pages`) só são exercitadas de verdade depois do merge. Por isso: mescle um pull request por vez e, depois de mesclar um de `github-actions`, rode **Actions → Atualização diária → Run workflow** com `limite_resumos` = 0 e `reavaliar` = sim (não gasta IA) e confira que as três etapas ficam verdes.

**Espaçamento.** O site usa uma grade de 8px com regras, não só múltiplos de 8: escala de passos (4px a 80px), papéis que dizem a relação entre elementos (`--junto`, `--perto`, `--item`, `--grupo`, `--bloco`, `--respiro`, `--margem`, `--calha`) e padrões de uso (cabeçalho de página, linha de lista, cartão, controle). Os componentes só usam papéis. As regras estão em [`docs/espacamento.md`](docs/espacamento.md) e `python3 testes/espacamento.py _site` barra qualquer valor fora da escala (roda em todo pull request).

Para ver no seu computador: `python3 site/exportar_dados.py` e depois `python3 -m http.server --directory site`, e abra http://localhost:8000.

## Arquivos

| Arquivo | Para que serve |
| --- | --- |
| `coleta/coletar_votacoes.py` | Coleta e classifica as votações |
| `coleta/construir_banco.py` | Monta o banco SQLite |
| `coleta/resumir_projetos.py` | Assunto e resumo por IA, com confiança |
| `coleta/monitorar.py` | Monitoramento: confere custo, dados e site no ar, e abre alerta na aba Issues |
| `coleta/guardar_no_repositorio.sh` | Guarda arquivos da rotina no repositório, repetindo se alguém mexeu nele |
| `dados/cache_v5.json` | Tudo o que veio da API (a base do banco) |
| `dados/resumos.json` | Assunto e resumo de cada projeto, com confiança (escrito pela IA) |
| `dados/custo.json` | Quanto cada rodada de resumos e traduções gastou com a IA (escrito pela rotina) |
| `dados/monitor.json` | Histórico das conferências do monitoramento (escrito pela rotina) |
| `site/` | O site (`index.html`, `estilos.css`, `app.js`, fontes, `og.png`) |
| `site/exportar_dados.py` | Passa o banco para os JSON que o site lê (`site/dados/`) |
| `site/painel.py` | Faz `site/dados/painel.json`, os números da tela **Em números** (simbólicas × nominais ao longo do tempo, por assunto e resultado, participação, placar e transparência da IA). Roda junto com o `exportar_dados.py` |
| `testes/captura_painel.py` | Tira a foto (PNG) da tela Em números; a atualização diária guarda a mais recente em `painel/ultima-geracao.png` |
| `site/gerar_paginas.py` | Cria as páginas de cada projeto, deputado e assunto, o sitemap e o 404, em português e em inglês (`--idiomas`) |
| `site/criar_og_en.py` | Cria `site/og-en.png`, a imagem de compartilhamento em inglês |
| `site/idioma.py` | Carrega o dicionário de um idioma para o gerador de páginas |
| `site/idiomas/en.json` | Dicionário português → inglês dos textos fixos do site |
| `site/exportar_en.py` | Junta as traduções de projetos e votações em `site/dados/en/` |
| `coleta/traducoes.py` | Guarda e confere as traduções (impressão do texto em português) |
| `coleta/traduzir_projetos.py` | Traduz para o inglês, com IA, os projetos e votações novos |
| `dados/traducoes_en.json` | Tradução em inglês de cada projeto e votação (escrito pela IA) |
| `site/baixar_fotos.py` | Guarda as fotos dos deputados em `site/fotos/` |
| `testes/fumaca.py` | Teste de fumaça do site num navegador de verdade |
| `testes/espacamento.py` | Confere as regras de espaçamento (grade de 8px) no CSS e nas telas |
| `testes/idiomas.py` | Confere a versão em inglês: dicionário, dados, páginas e telas |
| `testes/seguranca.py` | Ataca o site com dados maliciosos e confere a política de segurança (CSP), sem rastreio e sem cookies |
| `testes/requirements.txt` | Versão fixa do programa de teste (o Dependabot avisa quando sai nova) |
| `SECURITY.md` | Como avisar de uma falha e o que o site garante |
| `.github/dependabot.yml` | Mantém em dia as versões fixas das ações do GitHub e do programa de teste |
| `docs/espacamento.md` | As regras de espaçamento: escala, papéis e padrões |
| `.github/workflows/atualizacao-diaria.yml` | A rotina diária: coleta, resumos, traduções, dados do site, fotos e publicação |
| `.github/workflows/publicar-site.yml` | Põe o site no ar (depois da rotina diária e a cada mudança em `site/`) |
| `.github/workflows/vigiar-site.yml` | Todo dia à noite, confere se o site está no ar e com dados recentes |
| `.github/workflows/testar-site.yml` | Testa o site em cada pull request |

## Rodar a rotina

### No GitHub

Aba **Actions**, **Atualização diária**, **Run workflow**. A rotina também roda sozinha todo dia às 6h.
O workflow precisa estar em `.github/workflows/atualizacao-diaria.yml` (com esse caminho exato) para
aparecer na aba Actions.

Se o passo de guardar o cache falhar com erro de permissão, em Settings, Actions, General, Workflow
permissions, marque **Read and write permissions**.

### No seu computador

Precisa só de Python 3.12 ou mais novo (usa apenas a biblioteca padrão).

```bash
cd dados
python3 ../coleta/coletar_votacoes.py --diario     # atualiza o cache
cd ..
python3 coleta/construir_banco.py                  # monta dados/voto_de_verdade.db
```

Para um teste rápido, use `--desde 2026-06-01`. A primeira coleta completa leva de 30 a 50 minutos, porque a
rotina faz pausas entre as consultas para não ser bloqueada. Nos dias seguintes leva poucos minutos.

## Monitoramento

Ninguém precisa abrir o GitHub para saber se está tudo bem: o que sai do normal chega por e-mail.

**Quando.** No fim de cada atualização diária (job `monitorar`) e, separado, uma vez por dia às 18h30 de
Brasília (workflow `Vigiar o site`, que só olha o site no ar).

**O que confere** (`coleta/monitorar.py`):

| Área | Vira erro (alerta) quando | Vira só aviso quando |
| --- | --- | --- |
| Execução | a atualização ou a publicação terminaram com falha | |
| Dados | não foram gerados hoje; o número de votações, projetos, deputados ou votos **diminuiu**; algum voto, votação ou projeto aponta para algo que não existe; a coleta registrou problemas; a parte de projetos com aviso de incerteza saltou mais de 5 pontos de um dia para o outro | faz mais de 45 dias sem votação; mais de 50 projetos sem resumo; mais de 25% com aviso de incerteza; mais de 50 projetos ou votações sem tradução para o inglês |
| Custo da IA | a rodada gastou mais de US$ 5; o mês passou de US$ 30; o saldo de créditos acabou | o mês passou de 70% do limite; projetos deram erro na rodada |
| Site no ar | a página inicial, os dados, o mapa do site, uma página de projeto ou uma de deputado não abrem; os dados no ar são mais velhos que os de hoje | |

**Como avisa.** Um erro deixa a execução vermelha (o GitHub manda e-mail) e abre um alerta na aba
**Issues**, com o marcador `monitoramento` e a lista do que falhou. Se os problemas mudam, o alerta é
atualizado; quando tudo volta ao normal, ele se fecha sozinho. Avisos ficam só no relatório da execução
(aba Actions, resumo da execução).

**Para receber o e-mail.** Em GitHub, Settings, Notifications, marque as notificações de **Actions**
("Failed workflows only" basta) e deixe ligado o aviso por e-mail.

**Mudar os limites.** Em Settings, Secrets and variables, Actions, aba **Variables**, crie
`LIMITE_CUSTO_RODADA`, `LIMITE_CUSTO_MES`, `LIMITE_PENDENTES`, `LIMITE_PENDENTES_EN`, `DIAS_SEM_VOTACAO` ou `LIMITE_INCERTOS`.
Sem elas valem os números da tabela.

**Histórico.** `dados/monitor.json` guarda o resultado de cada dia (as contagens também servem de base para
perceber se algo diminuiu) e `dados/custo.json`, o gasto de cada rodada de resumos. Como esses arquivos mudam
todo dia, o repositório nunca fica parado, o que também impede o GitHub de desligar as rotinas agendadas
depois de 60 dias sem atividade.

**No computador.** `python coleta/monitorar.py` confere os arquivos; com `--site https://usuario.github.io/repositorio`,
confere também o site no ar.

## Como saber se deu certo

- A execução fica verde na aba Actions (inclusive o job **monitorar**, veja a seção Monitoramento). Se ficar vermelha, o log do passo **Coletar os dados da Câmara**
  diz o que falhou, e a rodada seguinte tenta de novo o que faltou.
- No fim do passo **Construir o banco de dados**, o log mostra:
  - quantas votações há por tipo (nominal, simbólica, secreta);
  - quantas votações ficaram com confiança alta, média e baixa;
  - quantos votos estão sem o partido do dia do voto (esperado: 0 depois da primeira rodada completa).
- A tabela `execucoes` guarda o histórico de cada rodada, com problemas e avisos.

## Limitações conhecidas

- **Sem revisão humana.** A rede de segurança são os avisos de confiança. Um canal de "Reportar erro" está no
  backlog, com baixa prioridade, e o site não tem esse botão por enquanto.
- **Resumos por IA.** Podem conter erros. A confiança e a conferência automática reduzem o risco, mas não o eliminam.
  Os 13 assuntos são fixos. Em testes com 59 projetos, "Outros" ficou com 13 de 40 no começo, e todos eram regras
  internas do Congresso, servidores, acordos internacionais, datas e homenagens. Por isso existem os assuntos
  "Administração Pública e Congresso", "Relações Internacionais e Defesa" e "Cultura, Esporte e Turismo". "Agropecuária
  e Campo" foi criado depois de aparecerem reforma agrária, trabalho por safra e programa de alimentos. Vale conferir a
  distribuição de novo depois da primeira carga completa.
- **Projeto em dois assuntos.** Muitos projetos cabem em dois assuntos (por exemplo, um fundo de telecomunicações que
  muda regras fiscais). A IA escolhe um assunto principal e um secundário, e o site lista o projeto nos dois. A
  confiança do assunto só cai para média ou baixa quando a segunda leitura discorda dos dois assuntos, quando as
  palavras da ementa apontam para outro, ou quando o projeto ficou em "Outros".
- **Projetos com outro número.** Em 23 projetos (27 votações), o texto cita um número que a Câmara não tem
  registrado hoje, e a Câmara indica o projeto com outro número. Conferimos o ano de apresentação: nos 23 casos ele
  é igual ao ano citado no texto, ou seja, é o mesmo projeto com outro número. Se o ano não bater, a votação fica
  com confiança baixa e aviso.
- **PEC 45/2019.** A busca acha dois registros com esse número. Escolhemos o mais recente que já tinha sido
  apresentado na data da votação, com confiança média e aviso. A votação de 15/12/2023 afeta, segundo a Câmara, a
  PEC 293/2004, que não usamos porque o texto cita a 45/2019.
- **Partido no dia do voto.** A coleta guarda o partido que a API informa junto com cada voto. Falta
  confirmar, na primeira rodada real, que é o partido do dia do voto.
- **Sem ausências.** A API só lista quem votou, então o site não mostra "não votou".
- **Só a Câmara.** O Senado não está incluído.
- **Sem votações novas.** Em recesso e em período de eleição a Câmara quase não vota; a data da última votação aparece no rodapé.

## Fora do escopo

- Nota, ranking ou "índice de fidelidade" de deputados.
- "Votou diferente do partido".
- Ausências.

## Dados e licença

Os dados são da Câmara dos Deputados, de acesso aberto.

- **Código:** licença MIT (arquivo [`LICENSE`](LICENSE)).
- **Textos do site e resumos feitos por inteligência artificial:** CC BY 4.0, citando o Voto de Verdade e `votodeverdade.com.br` (arquivo [`LICENSE-CONTEUDO.md`](LICENSE-CONTEUDO.md), que também diz o que não está coberto: dados da Câmara, fotos, fonte, nome e logotipo).
- **Treino de modelos de IA:** o site pede que o conteúdo não seja usado para treinar modelos (`ai-train=no` no `robots.txt`) e aceita consultas para responder perguntas, com link. É um pedido, não uma restrição jurídica. Para mudar essa posição, ajuste `robots.txt` em `site/gerar_paginas.py`, a página "Como o site funciona" (`site/app.js` e `site/gerar_paginas.py`), `LICENSE-CONTEUDO.md` e este texto.
