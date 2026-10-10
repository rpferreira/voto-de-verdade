#!/usr/bin/env python3
"""Guarda a data em que cada projeto entrou no site, para a tela inicial marcar os mais recentes com a etiqueta «Novo».

O banco de dados é refeito do zero todo dia, então a data de entrada precisa ficar num arquivo próprio, que a rotina
diária guarda no repositório: dados/primeira_vez.json.

    {"desde": "2026-10-10", "projetos": {"2634392": null, "2701234": "2026-10-14", ...}}

  - "desde": o dia em que o registro começou. Os projetos que já estavam no site nesse dia valem null («já existia»);
    só quem chega depois recebe a data da primeira vez que apareceu. Assim a etiqueta só vale «a partir de agora».
  - Quem some da base continua no arquivo (se voltar, não vira «novo» de novo).

A etiqueta aparece só em «Últimas votações» da tela inicial e some sozinha depois de DIAS_COMO_NOVO dias
(o aplicativo confere a data de hoje no navegador, então ela sai mesmo que a atualização diária atrase).
Esse prazo precisa ser o mesmo de DIAS_COMO_NOVO em site/app.js (um teste confere).

Uso (na raiz do repositório):
    python3 site/novos.py        # cria dados/primeira_vez.json com os projetos de site/dados/projetos.json, se ainda não existir
"""
import json
import os
import sys

DIAS_COMO_NOVO = 7
AQUI = os.path.dirname(os.path.abspath(__file__))
ARQUIVO = os.path.join(AQUI, "..", "dados", "primeira_vez.json")


def carregar(caminho=ARQUIVO):
    """O registro guardado, ou None se ainda não existe."""
    if not os.path.exists(caminho):
        return None
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def atualizar(registro, ids, hoje):
    """Devolve o registro com os projetos de `ids` incluídos. Sem registro, começa hoje: todos valem «já existia»."""
    ids = [str(i) for i in ids]
    if registro is None:
        return {"desde": hoje, "projetos": {i: None for i in ids}}
    projetos = dict(registro["projetos"])
    for i in ids:
        projetos.setdefault(i, hoje)
    return {"desde": registro["desde"], "projetos": projetos}


def datas(registro):
    """{id do projeto: data de entrada}, só dos que entraram depois de o registro começar."""
    return {} if not registro else {i: d for i, d in registro["projetos"].items() if d}


def gravar(registro, caminho=ARQUIVO):
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(registro, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        f.write("\n")


def main():
    if carregar() is not None:
        print(f"{os.path.normpath(ARQUIVO)} já existe; nada a fazer.")
        return 0
    pasta = os.path.join(AQUI, "dados")
    with open(os.path.join(pasta, "meta.json"), encoding="utf-8") as f:
        hoje = json.load(f)["gerado_em"]
    with open(os.path.join(pasta, "projetos.json"), encoding="utf-8") as f:
        ids = [p["id"] for p in json.load(f)]
    gravar(atualizar(None, ids, hoje))
    print(f"{os.path.normpath(ARQUIVO)}: {len(ids)} projetos já existentes em {hoje}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
