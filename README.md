# Voto de Verdade

Mostra ao cidadão como cada deputado federal votou, por assunto e por deputado, em linguagem simples.

Os dados vêm da API de Dados Abertos da Câmara dos Deputados. Este repositório guarda a rotina que
busca esses dados todo dia e monta o banco de dados que alimenta o site.

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
3. Se algo falhar, a execução fica vermelha na aba Actions e o GitHub avisa o dono do repositório por e-mail.

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
`{"<id do projeto>": {"assunto", "assunto_secundario", "confianca_assunto", "resumo", "pontos_chave", "tags"}}`.
Ele será preenchido na etapa dos resumos por IA, que ainda não foi construída.

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

## Arquivos

| Arquivo | Para que serve |
| --- | --- |
| `coleta/coletar_votacoes.py` | Coleta e classifica as votações |
| `coleta/construir_banco.py` | Monta o banco SQLite |
| `dados/cache_v5.json` | Tudo o que veio da API (a base do banco) |
| `dados/resumos.json` | Assunto e resumo de cada projeto, com confiança |
| `.github/workflows/atualizacao-diaria.yml` | A rotina diária |

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

## Como saber se deu certo

- A execução fica verde na aba Actions. Se ficar vermelha, o log do passo **Coletar os dados da Câmara**
  diz o que falhou, e a rodada seguinte tenta de novo o que faltou.
- No fim do passo **Construir o banco de dados**, o log mostra:
  - quantas votações há por tipo (nominal, simbólica, secreta);
  - quantas votações ficaram com confiança alta, média e baixa;
  - quantos votos estão sem o partido do dia do voto (esperado: 0 depois da primeira rodada completa).
- A tabela `execucoes` guarda o histórico de cada rodada, com problemas e avisos.

## Limitações conhecidas

- **Sem revisão humana.** A rede de segurança são os avisos de confiança e um canal de "Reportar erro", que
  ainda precisa de um responsável para receber e tratar os relatos.
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

## Fora do escopo

- Nota, ranking ou "índice de fidelidade" de deputados.
- "Votou diferente do partido".
- Ausências.

## Dados e licença

Os dados são da Câmara dos Deputados, de acesso aberto. A licença do código ainda está por definir.
