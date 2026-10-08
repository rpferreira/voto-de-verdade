#!/usr/bin/env python3
"""Monta a pasta do site pronta para publicar (GitHub Pages).

Copia site/ (menos os .py) para a pasta de saída e cria uma página própria para cada
projeto (projeto/<id>/), deputado (deputado/<id>/) e assunto (assunto/<slug>/), com título,
descrição e prévia de compartilhamento (WhatsApp, Google) e o conteúdo principal já escrito
no HTML, para quem ainda não carregou o JavaScript e para os buscadores. Essas páginas abrem
o mesmo aplicativo (app.js), que mostra a tela completa. Também cria sitemap.xml, robots.txt e 404.html.

Uso: python site/gerar_paginas.py --saida _site --url https://usuario.github.io/repositorio
"""
import argparse
import html
import json
import os
import shutil
import sys
from urllib.parse import urlparse

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]


def data_br(iso):
    if not iso:
        return ""
    a, m, d = iso.split("-")
    return f"{int(d)} de {MESES[int(m) - 1]} de {a}"


def esc(t):
    return html.escape(t or "", quote=True)


def curto(t, limite):
    t = " ".join((t or "").split())
    if len(t) <= limite:
        return t
    corte = t[: limite - 1]
    i = corte.rfind(" ")
    return corte[: i if i > limite // 2 else limite - 1].rstrip(" ,;:") + "…"


def carregar(pasta, nome):
    with open(os.path.join(pasta, "dados", nome), encoding="utf-8") as f:
        return json.load(f)


def placar_texto(s):
    sim, nao, abst, obs, pres = s
    partes = [f"{sim} sim", f"{nao} não"]
    if abst:
        partes.append(f"{abst} abstenç{'ão' if abst == 1 else 'ões'}")
    if obs:
        partes.append(f"{obs} obstruç{'ão' if obs == 1 else 'ões'}")
    return ", ".join(partes)


class Gerador:
    def __init__(self, modelo, url, saida):
        self.modelo = modelo
        self.url = url.rstrip("/")
        self.saida = saida
        self.paginas = []

    def cabeca(self, titulo, descricao, canonico):
        t, d, c = esc(titulo), esc(descricao), esc(canonico)
        return (
            f'<title>{t}</title>\n'
            f'  <meta name="description" content="{d}">\n'
            f'  <link rel="canonical" href="{c}">\n'
            f'  <meta property="og:type" content="website">\n'
            f'  <meta property="og:locale" content="pt_BR">\n'
            f'  <meta property="og:site_name" content="Voto de Verdade">\n'
            f'  <meta property="og:title" content="{t}">\n'
            f'  <meta property="og:description" content="{d}">\n'
            f'  <meta property="og:url" content="{c}">\n'
            f'  <meta property="og:image" content="{esc(self.url)}/og.png">\n'
            f'  <meta property="og:image:width" content="1200">\n'
            f'  <meta property="og:image:height" content="630">\n'
            f'  <meta name="twitter:card" content="summary_large_image">')

    def montar(self, caminho, rota, titulo, descricao, corpo, raiz=None, noindex=False):
        """caminho: pasta de saída ('projeto/123'); rota: rota do aplicativo ('projeto/123')."""
        if raiz is None:
            raiz = "../" * len(caminho.split("/"))
        pagina = self.modelo
        ini, fim = pagina.index("<!--INICIO-CABECA-->"), pagina.index("<!--FIM-CABECA-->")
        canonico = f"{self.url}/{caminho}/" if caminho else self.url + "/"
        cab = self.cabeca(titulo, descricao, canonico)
        if noindex:
            cab += '\n  <meta name="robots" content="noindex">'
        pagina = pagina[:ini] + cab + pagina[fim + len("<!--FIM-CABECA-->"):]
        ini, fim = pagina.index("<!--INICIO-CONTEUDO-->"), pagina.index("<!--FIM-CONTEUDO-->")
        pagina = pagina[:ini] + corpo + pagina[fim + len("<!--FIM-CONTEUDO-->"):]
        trocas = [
            ('href="fontes/', f'href="{raiz}fontes/'),
            ('href="estilos.css"', f'href="{raiz}estilos.css"'),
            ('src="app.js"', f'src="{raiz}app.js"'),
            ('class="marca" href="#/"', f'class="marca" href="{raiz or "./"}"'),
            ('id="nav-assuntos" href="#/"', f'id="nav-assuntos" href="{raiz or "./"}"'),
            ('id="nav-deputados" href="#/deputados"', f'id="nav-deputados" href="{raiz}#/deputados"'),
            ('<a href="#/sobre">', f'<a href="{raiz}#/sobre">'),
            ('<script>window.RAIZ = "";</script>',
             f'<script>window.RAIZ = {json.dumps(raiz)}; window.ROTA_INICIAL = {json.dumps(rota)};</script>'),
        ]
        for velho, novo in trocas:
            if velho not in pagina:
                sys.exit(f"ERRO: o modelo index.html não tem {velho!r}")
            pagina = pagina.replace(velho, novo)
        destino = os.path.join(self.saida, caminho, "index.html") if caminho else os.path.join(self.saida, "index.html")
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        with open(destino, "w", encoding="utf-8") as f:
            f.write(pagina)
        if not noindex and caminho:
            self.paginas.append(canonico)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--saida", default="_site")
    ap.add_argument("--url", default=os.environ.get("SITE_URL", "https://rpferreira.github.io/voto-de-verdade"))
    args = ap.parse_args()

    if os.path.exists(args.saida):
        shutil.rmtree(args.saida)
    shutil.copytree(args.site, args.saida, ignore=shutil.ignore_patterns("*.py", "__pycache__"))

    with open(os.path.join(args.site, "index.html"), encoding="utf-8") as f:
        modelo = f.read()
    projetos = carregar(args.site, "projetos.json")
    votacoes = carregar(args.site, "votacoes.json")
    deputados = carregar(args.site, "deputados.json")
    assuntos = carregar(args.site, "assuntos.json")
    meta = carregar(args.site, "meta.json")
    g = Gerador(modelo, args.url, args.saida)
    nome_assunto = {a["slug"]: a["nome"] for a in assuntos}
    por_projeto = {}
    for v in votacoes:
        por_projeto.setdefault(v["p"], []).append(v)
    pr_por_id = {p["id"]: p for p in projetos}

    def link_projeto(pr, raiz):
        return f'<li><a href="{raiz}projeto/{pr["id"]}/">{esc(pr["titulo"])}</a></li>'

    # ---- projetos
    for pr in projetos:
        minhas = sorted(por_projeto.get(pr["id"], []), key=lambda v: v["d"])
        nominais = [v for v in minhas if v["t"] == "nominal" and v.get("s")]
        raiz = "../../"
        if nominais:
            ult = nominais[-1]
            votos = (f'Votação de {data_br(ult["d"])} ({"aprovada" if ult["ap"] else "rejeitada"}): '
                     f'{placar_texto(ult["s"])}.')
        else:
            votos = ("Votação secreta: o voto de cada deputado não é divulgado." if pr["tipo"] == "secreta" else
                     "Votação simbólica: o resultado foi anunciado sem registrar o voto de cada deputado.")
        resumo = pr.get("resumo") or pr.get("ementa") or ""
        descricao = curto(resumo, 150)
        if nominais:
            descricao += f' Votação de {data_br(ult["d"])}: {placar_texto(ult["s"])}. Veja como cada deputado votou.'
        corpo = (
            '<div class="miolo pagina-projeto">'
            f'<header class="cabeca-projeto"><h1>{esc(pr["titulo"])}</h1>'
            f'<p class="cabeca-projeto__meta">{esc(pr["nome"])} · última votação em {data_br(pr["ultima"])}</p></header>'
            f'<div class="resumo-projeto"><p>{esc(resumo)}</p></div>'
            f'<section class="bloco"><h2>Como cada deputado votou</h2><p class="nota">{esc(votos)}</p></section>'
            f'<p class="nota">Assunto: <a href="{raiz}assunto/{pr["a"]}/">{esc(nome_assunto.get(pr["a"], ""))}</a>. '
            'O resumo é feito por inteligência artificial e pode conter erros.</p>'
            + (f'<p><a href="{esc(pr["texto"])}" rel="noopener noreferrer">Texto completo no site da Câmara</a></p>' if pr.get("texto") else "")
            + "</div>")
        g.montar(f'projeto/{pr["id"]}', f'projeto/{pr["id"]}', f"{curto(pr['titulo'], 70)} | Voto de Verdade", descricao, corpo)

    # ---- deputados
    n_dep = 0
    for d in deputados:
        arq = os.path.join(args.site, "dados", "deputados", f'{d["id"]}.json')
        votos_dep = []
        if os.path.exists(arq):
            with open(arq, encoding="utf-8") as f:
                votos_dep = json.load(f)["v"]
        total = {}
        for _, cod in votos_dep:
            total[cod] = total.get(cod, 0) + 1
        sigla = " · ".join(x for x in (d.get("partido"), d.get("uf")) if x)
        if votos_dep:
            resumo = (f'Votou em {len(votos_dep)} votações nominais, de {data_br(meta["de"])} a {data_br(meta["ate"])}: '
                      f'{total.get("S", 0)} sim e {total.get("N", 0)} não.')
        else:
            resumo = "Sem voto registrado nas votações nominais do período."
        descricao = f'Veja como {d["nome"]} ({sigla}) votou na Câmara dos Deputados. {resumo} Sem nota e sem ranking.'
        recentes = []
        datas = {v["id"]: v for v in votacoes}
        ordenados = sorted((datas[vid] for vid, _ in votos_dep if vid in datas), key=lambda v: v["d"], reverse=True)
        vistos = set()
        for v in ordenados:
            pr = pr_por_id.get(v["p"])
            if pr and pr["id"] not in vistos:
                vistos.add(pr["id"])
                recentes.append(link_projeto(pr, "../../"))
            if len(recentes) == 12:
                break
        corpo = (
            '<div class="miolo">'
            f'<header class="cabeca-dep"><div><h1>{esc(d["nome"])}</h1><p class="cabeca-dep__sub">{esc(sigla)}</p></div></header>'
            f'<section><h2>Votos registrados</h2><p class="nota">{esc(resumo)}</p></section>'
            + (f'<section class="bloco"><h2>Votações recentes</h2><ul>{"".join(recentes)}</ul></section>' if recentes else "")
            + "</div>")
        g.montar(f'deputado/{d["id"]}', f'deputado/{d["id"]}', f'{d["nome"]}: Voto de Verdade', descricao, corpo)
        n_dep += 1

    # ---- assuntos
    for a in assuntos:
        meus = sorted((p for p in projetos if p["a"] == a["slug"] or p["s"] == a["slug"]),
                      key=lambda p: (p["ind"], p["ultima"] or ""), reverse=True)[:150]
        descricao = (f'{a["descricao"].capitalize()}. {a["n"]} projetos votados na Câmara dos Deputados, '
                     f'{a["n_ind"]} com o voto de cada deputado. Sem nota e sem ranking.')
        corpo = (
            '<div class="miolo">'
            f'<header class="cabeca-assunto"><h1>{esc(a["nome"])}</h1><p>{esc(a["descricao"].capitalize())}.</p></header>'
            f'<ul class="projetos">{"".join(link_projeto(p, "../../") for p in meus)}</ul></div>')
        g.montar(f'assunto/{a["slug"]}', f'assunto/{a["slug"]}', f'{a["nome"]}: Voto de Verdade', descricao, corpo)

    # ---- página inicial (com o endereço de compartilhamento certo), 404, sitemap e robots
    g.montar("", "", "Voto de Verdade: como a Câmara dos Deputados votou",
             "Escolha um assunto e veja o que a Câmara dos Deputados votou e como cada deputado federal votou. Sem nota e sem ranking.",
             '<p class="miolo" style="padding-block:3rem">Carregando…</p>', raiz="")
    base = urlparse(args.url).path.rstrip("/") + "/"
    g.montar("404", "nao-encontrada", "Página não encontrada: Voto de Verdade", "Página não encontrada.",
             '<div class="miolo" style="padding-block:3rem"><h1>Não achamos esta página</h1>'
             f'<p><a href="{base}">Ver todos os assuntos</a></p></div>', raiz=base, noindex=True)
    os.replace(os.path.join(args.saida, "404", "index.html"), os.path.join(args.saida, "404.html"))
    os.rmdir(os.path.join(args.saida, "404"))

    linhas = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
              f'<url><loc>{esc(args.url)}/</loc><lastmod>{meta["gerado_em"]}</lastmod></url>']
    linhas += [f'<url><loc>{esc(u)}</loc><lastmod>{meta["gerado_em"]}</lastmod></url>' for u in g.paginas]
    linhas.append("</urlset>")
    with open(os.path.join(args.saida, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")
    with open(os.path.join(args.saida, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(f"User-agent: *\nAllow: /\n\nSitemap: {args.url}/sitemap.xml\n")
    print(f"Pronto: {len(g.paginas)} páginas em {args.saida}/ ({len(projetos)} projetos, {n_dep} deputados, {len(assuntos)} assuntos).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
