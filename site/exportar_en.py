#!/usr/bin/env python3
"""Voto de Verdade: arquivos em inglês que ficam POR CIMA dos dados em português (site/dados/en/).

O aplicativo (app.js) e o gerador de páginas (gerar_paginas.py) leem os dados em português e, na versão em inglês,
trocam só os campos traduzidos pelos que estão aqui. O que ainda não foi traduzido (ou cujo português mudou depois da
tradução) não entra: aparece em português, nunca errado.

    en/assuntos.json         {slug: {nome, descricao}}
    en/projetos.json         {id: {titulo, resumo, tags, aa, ar}}
    en/projetos/<id>.json    {pontos}
    en/votacoes.json         {id: {desc, av}}
    en/painel.json           {assuntos: {slug: nome}}

A fonte é dados/traducoes_en.json (feito por coleta/traduzir_projetos.py).

Uso (na raiz do repositório):  python3 site/exportar_en.py [--dados site/dados] [--traducoes dados/traducoes_en.json]
"""
import argparse
import json
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "coleta"))
import traducoes as T  # noqa: E402
from traduzir_projetos import origem_dos_dados  # noqa: E402

# Nome e descrição de cada assunto (slug → inglês). Os mesmos assuntos de site/exportar_dados.py (DESCRICOES).
ASSUNTOS_EN = {
    "saude": ("Health", "SUS (Brazil's public health system), medicines, health plans and health professionals"),
    "educacao": ("Education", "schools, universities, teachers and education funding"),
    "impostos-e-economia": ("Taxes and Economy", "taxes, the budget, credit, banks, businesses and prices"),
    "seguranca-publica": ("Public Safety", "crimes and penalties, police, prisons, weapons and violence"),
    "meio-ambiente": ("Environment", "nature, climate, forests, waste, water and animal protection"),
    "trabalho-e-direitos": ("Labor and Rights",
                            "jobs, wages, retirement, benefits and the rights of women, children, older people and people with disabilities"),
    "infraestrutura-e-transporte": ("Infrastructure and Transport", "roads, ports, airports, energy, sanitation, housing and traffic"),
    "tecnologia-e-comunicacao": ("Technology and Communication", "the internet, personal data, artificial intelligence, telephony, radio and TV"),
    "administracao-publica-e-congresso": ("Public Administration and Congress",
                                          "the Chamber's internal rules, public servants, positions, agencies and elections"),
    "cultura-esporte-e-turismo": ("Culture, Sport and Tourism", "culture, sport, tourism, commemorative dates and tributes"),
    "relacoes-internacionais-e-defesa": ("International Relations and Defense", "agreements with other countries, foreign policy and the Armed Forces"),
    "agropecuaria-e-campo": ("Agriculture and Rural Affairs", "farming, livestock, fishing, land and rural workers"),
    "outros": ("Other", "bills that did not fit well into any of the other subjects"),
}

# Siglas e abreviaturas depois das quais um ponto não termina a frase.
ABREVIATURAS_EN = {"no", "nos", "art", "arts", "sec", "inc", "st", "vs", "etc", "dr", "mr", "mrs", "ms", "paras", "para", "vol", "ed"}


def primeira_frase_en(texto, limite=200):
    """Primeira frase do texto em inglês, com o mesmo corte de exportar_dados.primeira_frase."""
    texto = " ".join((texto or "").split())
    frase = texto
    for m in re.finditer(r"[.!?](?=\s)", texto):
        antes = re.search(r"([\w]+)$", texto[: m.start()])
        if antes and antes.group(1).lower() in ABREVIATURAS_EN:
            continue
        frase = texto[: m.end()]
        break
    if len(frase) > limite:
        corte = frase[: limite - 1]
        if " " in corte:
            corte = corte.rsplit(" ", 1)[0]
        frase = corte.rstrip(" ,;:") + "…"
    return frase


def gravar(caminho, dado):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dado, f, ensure_ascii=False, separators=(",", ":"))


def exportar(pasta_dados, arquivo_traducoes):
    """Escreve pasta_dados/en/*. Devolve (projetos traduzidos, votações traduzidas, projetos sem tradução, votações sem tradução)."""
    origem, _ = origem_dos_dados(pasta_dados)
    trad = T.carregar(arquivo_traducoes)
    saida = os.path.join(pasta_dados, "en")
    # recomeça do zero: um arquivo velho nunca fica por cima do português que mudou
    if os.path.isdir(saida):
        for raiz, _, nomes in os.walk(saida):
            for n in nomes:
                os.remove(os.path.join(raiz, n))
    os.makedirs(os.path.join(saida, "projetos"), exist_ok=True)

    with open(os.path.join(pasta_dados, "assuntos.json"), encoding="utf-8") as f:
        assuntos = json.load(f)
    en_assuntos = {}
    for a in assuntos:
        par = ASSUNTOS_EN.get(a["slug"])
        if par:
            en_assuntos[a["slug"]] = {"nome": par[0], "descricao": par[1]}
    gravar(os.path.join(saida, "assuntos.json"), en_assuntos)
    gravar(os.path.join(saida, "painel.json"), {"assuntos": {s: v["nome"] for s, v in en_assuntos.items()}})

    projetos, n_proj = {}, 0
    for pid, item in origem["projetos"].items():
        t = trad["projetos"].get(pid)
        if not t or t.get("h") != T.impressao(item):
            continue
        n_proj += 1
        campos = {}
        if t.get("resumo"):
            campos["resumo"] = t["resumo"]
            campos["titulo"] = primeira_frase_en(t["resumo"])
        if t.get("tags"):
            campos["tags"] = t["tags"]
        if t.get("aviso_assunto"):
            campos["aa"] = t["aviso_assunto"]
        if t.get("aviso_resumo"):
            campos["ar"] = t["aviso_resumo"]
        if campos:
            projetos[pid] = campos
        if t.get("pontos"):
            gravar(os.path.join(saida, "projetos", f"{pid}.json"), {"pontos": t["pontos"]})
    gravar(os.path.join(saida, "projetos.json"), projetos)

    votacoes, n_vot = {}, 0
    for vid, item in origem["votacoes"].items():
        t = trad["votacoes"].get(vid)
        if not t or t.get("h") != T.impressao(item):
            continue
        n_vot += 1
        campos = {}
        if t.get("descricao"):
            campos["desc"] = t["descricao"]
        if t.get("aviso"):
            campos["av"] = t["aviso"]
        if campos:
            votacoes[vid] = campos
    gravar(os.path.join(saida, "votacoes.json"), votacoes)
    return n_proj, n_vot, len(origem["projetos"]) - n_proj, len(origem["votacoes"]) - n_vot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dados", default="site/dados")
    ap.add_argument("--traducoes", default=T.ARQUIVO)
    args = ap.parse_args()
    n_p, n_v, f_p, f_v = exportar(args.dados, args.traducoes)
    print(f"Inglês: {n_p} projetos e {n_v} votações traduzidos; sem tradução (ficam em português): {f_p} projetos, {f_v} votações.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
