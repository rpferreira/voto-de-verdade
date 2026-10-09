#!/usr/bin/env python3
"""Números do painel (tela "Painel"): votações simbólicas × nominais ao longo do tempo, por assunto e o resultado.

Só conta e descreve. Não ordena pessoas, não dá nota e não compara partidos.
Roda sozinho a cada atualização diária (o exportar_dados.py chama montar_painel) e também pode ser
rodado à mão a partir dos arquivos que o site já lê:

    python3 site/painel.py                 # lê site/dados/*.json e escreve site/dados/painel.json

Arquivo gerado (painel.json):
    gerado_em, de, ate           quando foi feito e o período coberto
    totais                       votações, nominais, simbolicas, secretas, aprovadas, rejeitadas
    meses                        uma linha por mês do período (meses sem votação entram com zero):
                                 m = "AAAA-MM", n = nominais, s = simbólicas, x = secretas
    assuntos                     uma linha por assunto, na ordem fixa dos assuntos do site (não por tamanho):
                                 slug, nome, n, s, x. Cada votação conta no assunto principal do projeto
    resultado                    por tipo de votação (nominal, simbolica, secreta): aprovadas e rejeitadas
"""
import json
import os
import sys

TIPOS = ("nominal", "simbolica", "secreta")
CHAVE = {"nominal": "n", "simbolica": "s", "secreta": "x"}


def _meses(de, ate):
    """Todos os meses de «AAAA-MM-DD» a «AAAA-MM-DD», inclusive, sem pular nenhum."""
    ano, mes = int(de[:4]), int(de[5:7])
    fim = (int(ate[:4]), int(ate[5:7]))
    while (ano, mes) <= fim:
        yield f"{ano:04d}-{mes:02d}"
        mes += 1
        if mes == 13:
            ano, mes = ano + 1, 1


def montar_painel(votacoes, projetos, assuntos, gerado_em):
    """votacoes: lista de {id, p, d, t, ap}; projetos: lista de {id, a}; assuntos: lista de {slug, nome} na ordem do site."""
    assunto_do_projeto = {p["id"]: p["a"] for p in projetos}
    votacoes = [v for v in votacoes if v["t"] in TIPOS]
    if not votacoes:
        return {"gerado_em": gerado_em, "de": None, "ate": None, "totais": {}, "meses": [], "assuntos": [], "resultado": {}}
    de, ate = min(v["d"] for v in votacoes), max(v["d"] for v in votacoes)

    meses = {m: {"m": m, "n": 0, "s": 0, "x": 0} for m in _meses(de, ate)}
    por_assunto = {a["slug"]: {"slug": a["slug"], "nome": a["nome"], "n": 0, "s": 0, "x": 0} for a in assuntos}
    resultado = {t: {"aprovadas": 0, "rejeitadas": 0} for t in TIPOS}
    for v in votacoes:
        k = CHAVE[v["t"]]
        meses[v["d"][:7]][k] += 1
        slug = assunto_do_projeto.get(v["p"])
        if slug in por_assunto:
            por_assunto[slug][k] += 1
        resultado[v["t"]]["aprovadas" if v["ap"] else "rejeitadas"] += 1

    totais = {
        "votacoes": len(votacoes),
        "nominais": sum(1 for v in votacoes if v["t"] == "nominal"),
        "simbolicas": sum(1 for v in votacoes if v["t"] == "simbolica"),
        "secretas": sum(1 for v in votacoes if v["t"] == "secreta"),
        "aprovadas": sum(r["aprovadas"] for r in resultado.values()),
        "rejeitadas": sum(r["rejeitadas"] for r in resultado.values()),
    }
    return {
        "gerado_em": gerado_em, "de": de, "ate": ate,
        "totais": totais,
        "meses": list(meses.values()),
        "assuntos": [a for a in por_assunto.values() if a["n"] + a["s"] + a["x"] > 0],
        "resultado": resultado,
    }


def main():
    pasta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados")
    if len(sys.argv) > 1:
        pasta = sys.argv[1]

    def ler(nome):
        with open(os.path.join(pasta, nome), encoding="utf-8") as f:
            return json.load(f)

    meta = ler("meta.json")
    painel = montar_painel(ler("votacoes.json"), ler("projetos.json"), ler("assuntos.json"), meta["gerado_em"])
    caminho = os.path.join(pasta, "painel.json")
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(painel, f, ensure_ascii=False, separators=(",", ":"))
    print(f"   {caminho}: {os.path.getsize(caminho) / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
