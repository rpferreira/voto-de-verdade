#!/usr/bin/env python3
"""Monta dados/destaques.json: as duas listas curtas da tela inicial («Últimas votações» e «Decididas por pouco»).

Por que existe: a tela inicial só precisa de 10 votações, mas para escolhê-las no navegador era preciso baixar
projetos.json e votacoes.json inteiros (cerca de 156 KB comprimidos, dois terços do que a primeira visita baixava).
Agora a escolha é feita aqui, junto com os outros dados, e o navegador só baixa o resultado (poucos KB). Os dois
arquivos grandes só são baixados quando a pessoa busca alguma coisa.

Regras (as mesmas que a tela inicial sempre usou):
  - só votações nominais com placar, de projetos que existem na base;
  - uma votação por projeto (a mais recente dele);
  - «Últimas votações»: as 5 mais recentes;
  - «Decididas por pouco»: as 5 de menor diferença entre sim e não, entre as que tiveram 100 votos de sim e não ou mais
    e diferença menor que 15%; mostradas da mais recente para a mais antiga.

Cada projeto leva "inc" (a data em que entrou no site, de dados/primeira_vez.json, veja site/novos.py) quando entrou depois de o
registro começar; a tela inicial usa isso para a etiqueta «Novo» em «Últimas votações».

Arquivos gerados:
    destaques.json      {"recentes": [{"v": votação, "p": projeto}], "apertadas": [...]}
    en/destaques.json   {id do projeto: {"titulo": título em inglês}}, só dos projetos que aparecem e já têm tradução

Uso (na raiz do repositório):
    python3 site/destaques.py            # lê site/dados/*.json e escreve site/dados/destaques.json (e en/destaques.json)
    python3 site/destaques.py pasta/     # o mesmo, em outra pasta de dados
"""
import json
import os
import sys

QUANTOS = 5
MINIMO_DE_VOTOS = 100   # sim + não
LIMITE_DA_DIFERENCA = 0.15  # o mesmo limite do painel (faixa «decididas por pouco»)


def _mais_recente(v):
    """Chave para ordenar da votação mais recente para a mais antiga (empate: pelo código, do maior para o menor)."""
    return (v["d"], v["id"])


def _unicas(lista, n=QUANTOS):
    vistos, saida = set(), []
    for v in lista:
        if v["p"] in vistos:
            continue
        vistos.add(v["p"])
        saida.append(v)
        if len(saida) == n:
            break
    return saida


def montar_destaques(votacoes, projetos, incluidos=None):
    """`incluidos` = {id do projeto: data em que entrou no site} (site/novos.py): vai como "inc" no projeto, para a etiqueta «Novo»."""
    incluidos = incluidos or {}
    por_id = {p["id"]: p for p in projetos}
    nominais = [v for v in votacoes if v["t"] == "nominal" and v.get("s") and v["p"] in por_id]

    def margem(v):
        return abs(v["s"][0] - v["s"][1]) / (v["s"][0] + v["s"][1])

    recentes = _unicas(sorted(nominais, key=_mais_recente, reverse=True))
    apertadas = _unicas(sorted((v for v in nominais if v["s"][0] + v["s"][1] >= MINIMO_DE_VOTOS and margem(v) < LIMITE_DA_DIFERENCA), key=margem))
    apertadas.sort(key=_mais_recente, reverse=True)

    def item(v):
        p = por_id[v["p"]]
        proj = {"id": p["id"], "titulo": p["titulo"], "ca": p.get("ca"), "cr": p.get("cr")}
        if str(p["id"]) in incluidos:
            proj["inc"] = incluidos[str(p["id"])]
        return {"v": {"id": v["id"], "p": v["p"], "d": v["d"], "ap": v["ap"], "s": v["s"]}, "p": proj}

    return {"recentes": [item(v) for v in recentes], "apertadas": [item(v) for v in apertadas]}


def traduzir_titulos(destaques, projetos_en):
    """Só o título em inglês dos projetos que aparecem nas duas listas (o resto da linha não tem texto)."""
    saida = {}
    for lista in (destaques["recentes"], destaques["apertadas"]):
        for it in lista:
            pid = str(it["p"]["id"])
            titulo = (projetos_en.get(pid) or {}).get("titulo")
            if titulo:
                saida[pid] = {"titulo": titulo}
    return saida


def gravar(pasta, destaques):
    """Escreve destaques.json e, se já existir a tradução (en/projetos.json), en/destaques.json."""
    def escrever(caminho, dado):
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(dado, f, ensure_ascii=False, separators=(",", ":"))
        print(f"   {caminho}: {os.path.getsize(caminho) / 1024:.1f} KB")

    escrever(os.path.join(pasta, "destaques.json"), destaques)
    arq_en = os.path.join(pasta, "en", "projetos.json")
    if os.path.exists(arq_en):
        with open(arq_en, encoding="utf-8") as f:
            escrever(os.path.join(pasta, "en", "destaques.json"), traduzir_titulos(destaques, json.load(f)))


def main():
    pasta = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados")

    def ler(nome):
        with open(os.path.join(pasta, nome), encoding="utf-8") as f:
            return json.load(f)

    import novos
    gravar(pasta, montar_destaques(ler("votacoes.json"), ler("projetos.json"), novos.datas(novos.carregar())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
