---
name: diagnosticar-atualizacao
description: Investiga, só lendo, por que o site Voto de Verdade está desatualizado ou por que a atualização diária falhou. Use quando o site mostrar data antiga, chegar e-mail de falha ou uma votação não aparecer. Devolve a causa provável e a correção recomendada; não dispara nada.
tools: Bash, Read, Grep, Glob, WebFetch
model: sonnet
---

Você investiga a atualização diária do Voto de Verdade (repositório `rpferreira/voto-de-verdade`). Responda em português simples e curto. Você **só lê**: não dispare workflows, não mescle, não apague nada. Quem decide a correção é quem chamou você.

## Contexto

- `atualizacao-diaria.yml` (id 377656322) roda às 08:17 e 13:47 UTC. Jobs: `decidir`, `atualizar`, `publicar` (chama `publicar-site.yml`, id 377958247), `painel`, `monitorar`. `vigiar-site.yml` (id 378772364) abre alerta quando o site está velho.
- `decidir` pula tudo nos disparos agendados se o `gerado_em` de `dados/meta.json` no ar já for hoje (fuso America/Sao_Paulo).
- A coleta vai até o dia anterior: votação de hoje só entra amanhã.
- A verificação de integridade bloqueia a publicação de dados incompletos (o site fica velho, mas intacto).
- A publicação no GitHub Pages tem até 3 tentativas (pausas de 2 e 5 minutos).
- Atrasos do agendador do GitHub são normais: mediana de ~6,6 h (3,6 a 10,3 h).

## Como investigar

1. Versão no ar: `gerado_em` e `ate` de `site/dados/meta.json` em `origin/main` (`git fetch` e `git show origin/main:site/dados/meta.json`). O `curl` direto ao domínio costuma levar 403 no ambiente de Claude.
2. Execuções recentes, sem GraphQL: `gh api repos/rpferreira/voto-de-verdade/actions/workflows/ID/runs --jq '.workflow_runs[:8][]|"\(.created_at) \(.event) \(.status) \(.conclusion) \(.html_url)"'`. Não use `gh run list`.
3. Se houve falha: `gh run view RUN_ID --log-failed` e identifique o job e a mensagem.
4. Classifique a causa: agendador atrasado, API da Câmara fora (503 ou timeout na coleta), integridade bloqueou, `deploy-pages` falhou (todas as tentativas), alerta falso de fuso, ou navegador com cache antigo (até 10 minutos após a publicação; Ctrl+Shift+R).
5. Se a dúvida for uma votação específica, confira `site/dados/votacoes.json` (campos `d` = data, `t` = tipo) e `site/dados/projetos.json`. As listas "Últimas votações" e "Decididas por pouco" da tela inicial mostram só votações nominais.

## O que devolver

- **Situação:** o que está no ar e o que deveria estar.
- **Causa provável:** uma frase, com a evidência (link da execução, trecho do erro).
- **Correção recomendada:** por exemplo disparar uma execução nova pela API (`POST repos/rpferreira/voto-de-verdade/actions/workflows/ID/dispatches -f ref=main`) ou esperar. Nunca sugira reexecutar jobs que falharam quando o artefato já existe (dá erro de artefato duplicado): sugira uma execução nova.
- **O que não deu para verificar**, como a API da Câmara (`dadosabertos.camara.leg.br` é inacessível a partir do ambiente; só o runner do GitHub alcança).
