# Agendador externo da atualização diária

O agendador do GitHub (`schedule`) atrasa muito as rodadas deste projeto: de 3,6 h a 10,3 h, com mediana de 6,6 h, em 40 execuções medidas em novembro de 2026. Em 17 e 18/11/2026 a rodada nem apareceu. O resultado é um site com a data do dia anterior até o começo da tarde.

A saída é um serviço externo chamar a API do GitHub na hora certa. Uma chamada `workflow_dispatch` começa em segundos. Este documento mostra como ligar isso, sem mudar nada no site.

## Como funciona

1. O serviço externo manda um `POST` para a API do GitHub pedindo para rodar a **Atualização diária**.
2. Ele envia `pular_se_atualizado = sim`. Assim, o job `decidir` olha o `dados/meta.json` do site no ar: se `gerado_em` já é a data de hoje (UTC), pula o resto. Pode-se chamar duas ou três vezes por dia sem repetir trabalho nem gastar IA à toa.
3. Os dois agendamentos do GitHub (`17 8` e `47 13` UTC) continuam como reserva e usam a mesma regra de pular.

## Passo 1: criar um token do GitHub (só para isso)

Em **GitHub, Settings, Developer settings, Personal access tokens, Fine-grained tokens, Generate new token**:

| Campo | Valor |
|---|---|
| Nome | `agendador-voto-de-verdade` |
| Expiração | 1 ano (anote a data para renovar) |
| Repository access | **Only select repositories**, só `rpferreira/voto-de-verdade` |
| Permissions, Repository | **Actions: Read and write** (o resto fica em «No access»; `Metadata: Read` vem sozinho) |

Copie o token (começa com `github_pat_`) e **guarde só no agendador externo**. Nunca no repositório, em issue ou em conversa.

Esse token só consegue mexer em Actions deste repositório. Se vazar, apague em **Settings, Developer settings** e crie outro.

## Passo 2: testar a chamada no seu computador

```bash
curl -i -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer COLE_O_TOKEN_AQUI" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/rpferreira/voto-de-verdade/actions/workflows/atualizacao-diaria.yml/dispatches \
  -d '{"ref":"main","inputs":{"pular_se_atualizado":"sim"}}'
```

- **`HTTP/2 204`**: deu certo. Na aba Actions aparece uma execução «Atualização diária» com o evento **workflow_dispatch**. Se o site já estiver atualizado hoje, o job `decidir` termina verde e o resto fica «skipped».
- **401 ou 403**: token errado, vencido ou sem a permissão **Actions: Read and write**.
- **404**: o token não enxerga o repositório (escolha o repositório certo no passo 1).
- **422**: o nome do arquivo ou da ramificação (`main`) está errado.

## Passo 3: criar o agendamento no serviço externo

Qualquer serviço que faça `POST` com cabeçalhos e corpo serve. O [cron-job.org](https://cron-job.org) é gratuito e avisa por e-mail quando a chamada falha. Os nomes dos campos podem variar um pouco.

Crie um job com:

- **URL:** `https://api.github.com/repos/rpferreira/voto-de-verdade/actions/workflows/atualizacao-diaria.yml/dispatches`
- **Método:** `POST`
- **Cabeçalhos:**
  - `Accept: application/vnd.github+json`
  - `Authorization: Bearer SEU_TOKEN`
  - `X-GitHub-Api-Version: 2022-11-28`
  - `Content-Type: application/json`
- **Corpo:** `{"ref":"main","inputs":{"pular_se_atualizado":"sim"}}`
- **Sucesso:** código `204` (o GitHub não devolve texto)
- **Fuso do agendamento:** `America/Sao_Paulo`
- **Horários:** **5h20** e **10h50** (duas chamadas por dia). A segunda só age se a primeira não funcionou, por exemplo se a API da Câmara estava fora do ar.
- **Avisos:** ligar o e-mail de falha, para saber se o token venceu.

## Como conferir se deu certo

Na aba **Actions**, em **Atualização diária**, depois do primeiro horário:

- a execução começa no minuto marcado (hoje atrasa horas);
- o evento é **workflow_dispatch**;
- o site mostra a data do dia em «Atualizado em».

Se o site já estiver atualizado quando a segunda chamada chegar, a execução tem só o job `decidir` verde. Isso é o esperado.

## Cuidados

- **Segredo:** o token é uma senha. Não o coloque em arquivos do repositório nem em issues.
- **Validade:** quando o token vencer, as chamadas falham com 401 e o serviço externo avisa por e-mail. Gere outro e troque no serviço. Enquanto isso, os dois agendamentos do GitHub seguem como reserva (com atraso).
- **Disparo manual:** em **Run workflow** o padrão é `pular_se_atualizado = nao`: roda tudo, mesmo com o site atualizado.
- **Mesclar:** um commit na ramificação principal pode ressincronizar os agendamentos do GitHub. Evite mesclar entre 5h e 17h (Brasília), principalmente enquanto o agendamento for o do GitHub.
- **Desligar:** pausar ou apagar o job no serviço externo basta. Nada no repositório precisa mudar.
