#!/usr/bin/env python3
"""Passa os dados do banco SQLite para arquivos JSON que o site lê.

Uso (na raiz do repositório):
    python3 site/exportar_dados.py                       # lê dados/voto_de_verdade.db, escreve site/dados/
    python3 site/exportar_dados.py --banco outro.db --saida pasta/

Só usa a biblioteca padrão do Python. Arquivos gerados:
    assuntos.json   os assuntos, com contagens (tela inicial)
    projetos.json   um registro enxuto por projeto (busca e página do assunto)
    meta.json       totais e período dos dados (rodapé e textos de ajuda)
    votacoes.json   uma linha por votação (lista de votações de cada projeto e tela de votação)
    deputados.json  nome, partido e estado de cada deputado
    votacoes/<id>.json   o voto de cada deputado, só das votações nominais (tela de votação)
    deputados/<id>.json  os votos de um deputado em todas as votações nominais (página do deputado)
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import unicodedata
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "coleta"))
from construir_banco import ASSUNTOS  # noqa: E402  (a lista de assuntos fica em um lugar só)

# O que cada assunto inclui, em linguagem de quem não conhece o Congresso. Mantenha curto.
DESCRICOES = {
    "Saúde": "SUS, remédios, planos de saúde e profissionais da saúde",
    "Educação": "escolas, universidades, professores e o dinheiro da educação",
    "Impostos e Economia": "impostos, orçamento, crédito, bancos, empresas e preços",
    "Segurança Pública": "crimes e penas, polícia, presídios, armas e violência",
    "Meio Ambiente": "natureza, clima, florestas, lixo, água e proteção dos animais",
    "Trabalho e Direitos": "emprego, salário, aposentadoria, benefícios e direitos de mulheres, crianças, idosos e pessoas com deficiência",
    "Infraestrutura e Transporte": "estradas, portos, aeroportos, energia, saneamento, moradia e trânsito",
    "Tecnologia e Comunicação": "internet, dados pessoais, inteligência artificial, telefonia, rádio e TV",
    "Administração Pública e Congresso": "regras internas da Câmara, servidores públicos, cargos, órgãos e eleições",
    "Cultura, Esporte e Turismo": "cultura, esporte, turismo, datas comemorativas e homenagens",
    "Relações Internacionais e Defesa": "acordos com outros países, política externa e Forças Armadas",
    "Agropecuária e Campo": "agricultura, pecuária, pesca, terra e trabalhadores do campo",
    "Outros": "projetos que não couberam bem em nenhum dos outros assuntos",
}

# Como o voto de cada deputado é guardado (curto, para os arquivos ficarem leves).
CODIGO_VOTO = {"Sim": "S", "Não": "N", "Abstenção": "A", "Obstrução": "O", "Artigo 17": "P"}

AVISO_IA = "O resumo foi feito por inteligência artificial e pode conter erros"
AVISO_SUBSTITUTIVO = "O resumo foi feito a partir da ementa do projeto original."


def slug(texto):
    t = unicodedata.normalize("NFKD", texto)
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


ABREVIATURAS = {"art", "arts", "inc", "al", "n", "no", "nº", "dr", "dra", "sr", "sra", "dep", "ex", "av", "pl", "prof", "profa", "cap", "par", "p", "cf", "obs"}


def primeira_frase(texto, limite=200):
    """Primeira frase do texto. Não termina a frase em abreviaturas como "art." ou "nº."."""
    texto = " ".join((texto or "").split())
    frase = texto
    for m in re.finditer(r"[.!?](?=\s)", texto):
        antes = re.search(r"([\wº°ª]+)$", texto[: m.start()])
        if antes and antes.group(1).lower() in ABREVIATURAS:
            continue
        frase = texto[: m.end()]
        break
    if len(frase) > limite:
        corte = frase[: limite - 1]
        if " " in corte:
            corte = corte.rsplit(" ", 1)[0]  # não corta no meio de uma palavra ou número
        frase = corte.rstrip(" ,;:") + "…"
    return frase


def separar_avisos_do_resumo(aviso):
    """O banco guarda os dois avisos do resumo juntos. A tela mostra cada um de um jeito."""
    if not aviso:
        return None, False
    ia = None
    m = re.search(re.escape(AVISO_IA) + r"[^.]*\.", aviso)
    if m:
        ia = m.group(0)
    return ia, AVISO_SUBSTITUTIVO in aviso


def carregar_json_texto(valor):
    if not valor:
        return []
    try:
        dado = json.loads(valor)
        return dado if isinstance(dado, list) else []
    except ValueError:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--banco", default="dados/voto_de_verdade.db")
    ap.add_argument("--saida", default="site/dados")
    args = ap.parse_args()
    if not os.path.exists(args.banco):
        print(f"ERRO: não achei {args.banco}. Rode antes: python3 coleta/construir_banco.py", file=sys.stderr)
        return 1
    os.makedirs(args.saida, exist_ok=True)

    con = sqlite3.connect(args.banco)
    con.row_factory = sqlite3.Row
    slugs = {a: slug(a) for a in ASSUNTOS}

    # resumo das votações de cada projeto
    vot = {}
    for r in con.execute("SELECT projeto_id, data, aprovacao, tipo_votacao FROM votacoes "
                         "WHERE projeto_id IS NOT NULL ORDER BY data, id"):
        v = vot.setdefault(r["projeto_id"], {"n": 0, "ind": False, "ultima": None, "aprovada": None, "tipo": None})
        v["n"] += 1
        v["ind"] = v["ind"] or r["tipo_votacao"] == "nominal"
        v["ultima"], v["aprovada"], v["tipo"] = r["data"], bool(r["aprovacao"]), r["tipo_votacao"]

    projetos = []
    for r in con.execute("SELECT * FROM projetos WHERE assunto IS NOT NULL ORDER BY id"):
        v = vot.get(r["id"])
        if not v:
            continue  # projeto sem votação ligada: não aparece no site
        ia, subst = separar_avisos_do_resumo(r["aviso_resumo"])
        resumo = r["resumo"]
        projetos.append({
            "id": r["id"],
            "nome": f'{r["tipo"]} {r["numero"]}/{r["ano"]}',
            "titulo": primeira_frase(resumo or r["ementa"]),
            "resumo": resumo,
            "ementa": " ".join((r["ementa"] or "").split()),
            "texto": r["url_texto_integral"],
            "a": slugs.get(r["assunto"]),
            "s": slugs.get(r["assunto_secundario"]),
            "ca": r["confianca_assunto"],
            "aa": r["aviso_assunto"],
            "cr": r["confianca_resumo"],
            "ar": ia,
            "subst": subst,
            "pontos": carregar_json_texto(r["pontos_chave"]),
            "tags": carregar_json_texto(r["tags"]),
            "n": v["n"],
            "ind": v["ind"],
            "ultima": v["ultima"],
            "aprovada": v["aprovada"],
            "tipo": v["tipo"],
        })
    projetos.sort(key=lambda p: (p["ultima"] or "", p["id"]), reverse=True)

    assuntos = []
    for nome in ASSUNTOS:
        s = slugs[nome]
        meus = [p for p in projetos if p["a"] == s or p["s"] == s]
        if not meus:
            continue
        assuntos.append({
            "slug": s, "nome": nome, "descricao": DESCRICOES[nome],
            "n": len(meus),
            "n_ind": sum(1 for p in meus if p["ind"]),
            "n_principal": sum(1 for p in meus if p["a"] == s),
            "ultima": max(p["ultima"] for p in meus),
        })

    tot = con.execute("SELECT COUNT(*) n, MIN(data) de, MAX(data) ate, "
                      "SUM(tipo_votacao='nominal') nom, SUM(tipo_votacao='simbolica') sim, "
                      "SUM(tipo_votacao='secreta') sec FROM votacoes").fetchone()
    meta = {
        "gerado_em": date.today().isoformat(),
        "de": tot["de"], "ate": tot["ate"],
        "votacoes": tot["n"], "nominais": tot["nom"], "simbolicas": tot["sim"], "secretas": tot["sec"],
        "projetos": len(projetos),
        "projetos_com_voto_individual": sum(1 for p in projetos if p["ind"]),
        "deputados": con.execute("SELECT COUNT(*) FROM deputados").fetchone()[0],
    }
    # votações (uma linha cada) e o voto de cada deputado nas nominais
    ids_projeto = {p["id"] for p in projetos}
    votacoes = []
    for r in con.execute("SELECT * FROM votacoes WHERE projeto_id IS NOT NULL ORDER BY data, id"):
        if r["projeto_id"] not in ids_projeto:
            continue
        votacoes.append({
            "id": r["id"], "p": r["projeto_id"], "d": r["data"], "t": r["tipo_votacao"],
            "ap": bool(r["aprovacao"]), "c": r["confianca"], "av": r["aviso"],
            "desc": " ".join((r["descricao"] or "").split()),
        })
    deputados = [{"id": r["id"], "nome": r["nome"], "uf": r["uf"], "partido": r["partido"], "ex": bool(r["em_exercicio"])}
                 for r in con.execute("SELECT * FROM deputados ORDER BY nome")]

    pasta_votos = os.path.join(args.saida, "votacoes")
    os.makedirs(pasta_votos, exist_ok=True)
    for antigo in os.listdir(pasta_votos):
        if antigo.endswith(".json"):
            os.remove(os.path.join(pasta_votos, antigo))
    por_votacao = {}
    for r in con.execute("SELECT votacao_id, deputado_id, voto, partido FROM votos ORDER BY votacao_id, deputado_id"):
        codigo = CODIGO_VOTO.get(r["voto"])
        if codigo is None:
            print(f"AVISO: voto desconhecido “{r['voto']}” (ignorado)", file=sys.stderr)
            continue
        por_votacao.setdefault(r["votacao_id"], []).append([r["deputado_id"], codigo, r["partido"] or ""])
    # placar de cada votação nominal: [sim, não, abstenção, obstrução, presidia a sessão]
    for v in votacoes:
        lista = por_votacao.get(v["id"])
        if lista:
            v["s"] = [sum(1 for x in lista if x[1] == c) for c in "SNAOP"]
    ids_votacao = {v["id"] for v in votacoes}
    n_arquivos = 0
    for vid, lista in por_votacao.items():
        if vid not in ids_votacao:
            continue
        with open(os.path.join(pasta_votos, f"{vid}.json"), "w", encoding="utf-8") as f:
            json.dump({"v": lista}, f, ensure_ascii=False, separators=(",", ":"))
        n_arquivos += 1
    # voto a voto de cada deputado (página do deputado) e os partidos por onde passou, em ordem de data
    data_de = {v["id"]: v["d"] for v in votacoes}
    pasta_dep = os.path.join(args.saida, "deputados")
    os.makedirs(pasta_dep, exist_ok=True)
    for antigo in os.listdir(pasta_dep):
        if antigo.endswith(".json"):
            os.remove(os.path.join(pasta_dep, antigo))
    por_dep = {}
    for vid, lista in por_votacao.items():
        if vid not in data_de:
            continue
        for did, codigo, partido in lista:
            por_dep.setdefault(did, []).append((data_de[vid], vid, codigo, partido))
    for did, itens in por_dep.items():
        itens.sort()
        partidos, vistos = [], set()
        for _, _, _, partido in itens:
            if partido and partido not in vistos:
                vistos.add(partido)
                partidos.append(partido)
        with open(os.path.join(pasta_dep, f"{did}.json"), "w", encoding="utf-8") as f:
            json.dump({"v": [[vid, codigo] for _, vid, codigo, _ in itens], "pt": partidos},
                      f, ensure_ascii=False, separators=(",", ":"))
    # deputado sem nenhum voto nominal: arquivo vazio, para a página dele mostrar «sem votos» e não um erro
    for dep in deputados:
        if dep["id"] not in por_dep:
            with open(os.path.join(pasta_dep, f"{dep['id']}.json"), "w", encoding="utf-8") as f:
                json.dump({"v": [], "pt": []}, f, separators=(",", ":"))
    con.close()

    def gravar(nome, dado):
        caminho = os.path.join(args.saida, nome)
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(dado, f, ensure_ascii=False, separators=(",", ":"))
        print(f"   {caminho}: {os.path.getsize(caminho) / 1024:.0f} KB")

    gravar("assuntos.json", assuntos)
    gravar("projetos.json", projetos)
    gravar("meta.json", meta)
    gravar("votacoes.json", votacoes)
    gravar("deputados.json", deputados)
    print(f"   {pasta_votos}/: {n_arquivos} arquivos")
    print(f"   {pasta_dep}/: {len(por_dep)} arquivos")
    print(f"Pronto: {len(assuntos)} assuntos, {len(projetos)} projetos, {meta['votacoes']} votações.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
