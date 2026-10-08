#!/usr/bin/env python3
"""Monta a pasta do site pronta para publicar (GitHub Pages).

Copia site/ (menos os .py) para a pasta de saída e cria:

- uma página própria para cada projeto (projeto/<id>/), deputado (deputado/<id>/) e assunto
  (assunto/<slug>/), mais deputados/, sobre/ e apoie/, cada uma com título, descrição, prévia de
  compartilhamento, dados estruturados (schema.org) e o conteúdo principal já escrito no HTML, para quem
  ainda não carregou o JavaScript, para os buscadores e para agentes de IA. Essas páginas abrem o mesmo
  aplicativo (app.js), que mostra a tela completa;
- uma versão em Markdown de cada página (index.md), mais fácil de ler para agentes de IA;
- sitemap.xml, robots.txt, 404.html, llms.txt, openapi.json (descrição dos dados abertos),
  dados/LEIA-ME.md e os arquivos de descoberta em .well-known/ (api-catalog e agent-skills).

Uso: python site/gerar_paginas.py --saida _site --url https://usuario.github.io/repositorio
"""
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
from urllib.parse import urlparse

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]
VOTO_NOME = {"S": "Sim", "N": "Não", "A": "Abstenção", "O": "Obstrução", "P": "Presidia a sessão"}
FONTE_DADOS = "https://dadosabertos.camara.leg.br/"
NOME = "Voto de Verdade"
LEMA = ("Site independente, neutro e apartidário: mostra o que a Câmara dos Deputados votou e como cada "
        "deputado federal votou, sem nota e sem ranking.")


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


def titulo_completo(pr):
    """Se o título foi cortado com «…» e o resumo começa com o mesmo texto, usa a primeira frase inteira do resumo."""
    t, r = pr.get("titulo") or "", pr.get("resumo") or ""
    if not t.endswith("…") or not r:
        return t
    base = t[:-1].rstrip()
    if not r.startswith(base):
        return t
    m = re.search(r"[.!?](?=\s|$)", r[len(base):])
    inteiro = r[: len(base) + m.start() + 1] if m else r
    return inteiro if len(inteiro) <= 400 else t


def contagem_assunto(a):
    """«N projetos com voto de cada deputado (M no total)» ou só o total, no singular/plural certo."""
    def proj(n):
        return f"{n} projeto" if n == 1 else f"{n} projetos"
    ni = a.get("n_ind")
    if ni is None:
        return proj(a["n"])
    return f'{proj(ni)} com voto de cada deputado ({a["n"]} no total)'


def jsonld(obj):
    """<script> de dados estruturados (schema.org)."""
    return ('<script type="application/ld+json">'
            + json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + "</script>")


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


def aviso_ia(pr):
    """Avisos de possível erro da classificação automática (mesma regra do site: só quando não é 'alta')."""
    avisos = []
    if pr.get("ca") and pr["ca"] != "alta":
        avisos.append(pr.get("aa") or f"A inteligência artificial tem dúvida sobre o assunto deste projeto (confiança {pr['ca']}).")
    if pr.get("cr") and pr["cr"] != "alta":
        avisos.append(pr.get("ar") or f"A inteligência artificial tem dúvida sobre o resumo deste projeto (confiança {pr['cr']}).")
    return avisos


class Gerador:
    def __init__(self, modelo, url, saida, doacao=""):
        self.doacao = doacao
        self.modelo = modelo
        self.url = url.rstrip("/")
        self.saida = saida
        self.paginas = []

    def escrever(self, caminho, texto):
        destino = os.path.join(self.saida, caminho)
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        with open(destino, "w", encoding="utf-8") as f:
            f.write(texto)

    def cabeca(self, titulo, descricao, canonico, extra="", noindex=False):
        t, d, c = esc(titulo), esc(descricao), esc(canonico)
        robos = "noindex" if noindex else "index, follow, max-image-preview:large, max-snippet:-1"
        linhas = [
            f'<title>{t}</title>',
            f'<meta name="description" content="{d}">',
            f'<meta name="robots" content="{robos}">',
            f'<link rel="canonical" href="{c}">',
            '<meta name="theme-color" content="#f5f6fa" media="(prefers-color-scheme: light)">',
            '<meta name="theme-color" content="#0b1018" media="(prefers-color-scheme: dark)">',
            '<meta property="og:type" content="website">',
            '<meta property="og:locale" content="pt_BR">',
            f'<meta property="og:site_name" content="{NOME}">',
            f'<meta property="og:title" content="{t}">',
            f'<meta property="og:description" content="{d}">',
            f'<meta property="og:url" content="{c}">',
            f'<meta property="og:image" content="{esc(self.url)}/og.png">',
            '<meta property="og:image:width" content="1200">',
            '<meta property="og:image:height" content="630">',
            f'<meta property="og:image:alt" content="{NOME}: como a Câmara dos Deputados votou">',
            '<meta name="twitter:card" content="summary_large_image">',
            f'<meta name="twitter:title" content="{t}">',
            f'<meta name="twitter:description" content="{d}">',
            f'<link rel="sitemap" type="application/xml" href="{esc(self.url)}/sitemap.xml">',
            f'<link rel="describedby" type="text/markdown" href="{esc(self.url)}/llms.txt">',
        ]
        if extra:
            linhas.append(extra)
        return "\n  ".join(linhas)

    def montar(self, caminho, rota, titulo, descricao, corpo, raiz=None, noindex=False, estruturados=None, markdown=None):
        """caminho: pasta de saída ('projeto/123'); rota: rota do aplicativo ('projeto/123').
        estruturados: dados schema.org (dict). markdown: texto da versão em Markdown (index.md)."""
        if raiz is None:
            raiz = "../" * len(caminho.split("/")) if caminho else ""
        pagina = self.modelo
        ini, fim = pagina.index("<!--INICIO-CABECA-->"), pagina.index("<!--FIM-CABECA-->")
        canonico = f"{self.url}/{caminho}/" if caminho else self.url + "/"
        extra = []
        if markdown and not noindex:
            extra.append(f'<link rel="alternate" type="text/markdown" href="{esc(canonico)}index.md">')
        if estruturados:
            extra.append(jsonld(estruturados))
        cab = self.cabeca(titulo, descricao, canonico, "\n  ".join(extra), noindex)
        pagina = pagina[:ini] + cab + pagina[fim + len("<!--FIM-CABECA-->"):]
        ini, fim = pagina.index("<!--INICIO-CONTEUDO-->"), pagina.index("<!--FIM-CONTEUDO-->")
        pagina = pagina[:ini] + corpo + pagina[fim + len("<!--FIM-CONTEUDO-->"):]
        apoio = ""
        if self.doacao:
            apoio = f'<p class="rodape__apoie">O Voto de Verdade é gratuito. <a href="{raiz}apoie/">Apoie com uma doação única</a>, sem assinatura.</p>'
        botao = ""
        if self.doacao:
            botao = (f'<a class="apoie-topo" href="{raiz}apoie/" aria-label="Apoie o Voto de Verdade com uma doação única"><svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" '
                     'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/></svg>'
                     '<span class="apoie-topo__txt">Apoie</span></a>')
        if self.doacao:
            pagina = pagina.replace('<header class="topo">', '<header class="topo" data-apoio>', 1)
        ini, fim = pagina.index("<!--INICIO-APOIO-TOPO-->"), pagina.index("<!--FIM-APOIO-TOPO-->")
        pagina = pagina[:ini] + botao + pagina[fim + len("<!--FIM-APOIO-TOPO-->"):]
        ini, fim = pagina.index("<!--INICIO-APOIO-->"), pagina.index("<!--FIM-APOIO-->")
        pagina = pagina[:ini] + apoio + pagina[fim + len("<!--FIM-APOIO-->"):]
        trocas = [
            ('href="fontes/', f'href="{raiz}fontes/'),
            ('href="estilos.css"', f'href="{raiz}estilos.css"'),
            ('src="app.js"', f'src="{raiz}app.js"'),
            ('class="marca" href="#/"', f'class="marca" href="{raiz or "./"}"'),
            ('id="nav-assuntos" href="#/"', f'id="nav-assuntos" href="{raiz or "./"}"'),
            ('id="nav-deputados" href="#/deputados"', f'id="nav-deputados" href="{raiz}deputados/"'),
            ('<a href="#/sobre">', f'<a href="{raiz}sobre/">'),
            ('<script>window.RAIZ = "";</script>',
             f'<script>window.RAIZ = {json.dumps(raiz)}; window.ROTA_INICIAL = {json.dumps(rota)}; window.DOACAO = {json.dumps(self.doacao)};</script>'),
        ]
        for velho, novo in trocas:
            if velho not in pagina:
                sys.exit(f"ERRO: o modelo index.html não tem {velho!r}")
            pagina = pagina.replace(velho, novo)
        self.escrever(os.path.join(caminho, "index.html") if caminho else "index.html", pagina)
        if markdown and not noindex:
            self.escrever(os.path.join(caminho, "index.md") if caminho else "index.md", markdown)
        if not noindex and caminho:
            self.paginas.append(canonico)


PRINCIPIOS = [
    ("M12 4v16|M7 20h10|M5 8h14|M5 8l-3 6a3.5 3.5 0 0 0 6 0z|M19 8l-3 6a3.5 3.5 0 0 0 6 0z",
     "Neutro e apartidário", "Sem ligação com partidos, candidatos ou a Câmara."),
    ("M5 20v-6|M10 20V8|M15 20v-9|M20 20V5|M3 3l18 18",
     "Sem nota e sem ranking", "Não dizemos quem votou certo ou errado."),
    ("M4 4h16v16H4z|M8 12l3 3 5-6",
     "Só o que foi votado", "O voto de cada deputado, dos dados oficiais."),
    ("M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z|M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z|M3 3l18 18",
     "Sem cookies nem rastreio", "Não usamos ferramentas que rastreiam quem visita."),
]


def principios_html():
    """Os pontos fortes da tela inicial (os mesmos de app.js), já em HTML para quem lê sem JavaScript."""
    itens = []
    for caminhos, titulo, texto in PRINCIPIOS:
        paths = "".join(f'<path d="{d}"/>' for d in caminhos.split("|"))
        itens.append(
            '<li><span class="principios__icone"><svg class="icone" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + paths + '</svg></span>'
            f'<strong>{esc(titulo)}</strong><span class="principios__desc">{esc(texto)}</span></li>')
    return '<ul class="principios" aria-label="O que diferencia o Voto de Verdade">' + "".join(itens) + "</ul>"


def migalhas_ld(itens):
    """BreadcrumbList: itens = [(nome, url ou None)]."""
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, **({"item": u} if u else {})} for i, (n, u) in enumerate(itens)]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--saida", default="_site")
    ap.add_argument("--url", default=os.environ.get("SITE_URL", "https://rpferreira.github.io/voto-de-verdade"))
    args = ap.parse_args()
    URL = args.url.rstrip("/")

    if os.path.exists(args.saida):
        shutil.rmtree(args.saida)
    shutil.copytree(args.site, args.saida, ignore=shutil.ignore_patterns("*.py", "__pycache__", "modelos", "config.json"))

    with open(os.path.join(args.site, "index.html"), encoding="utf-8") as f:
        modelo = f.read()
    projetos = carregar(args.site, "projetos.json")
    votacoes = carregar(args.site, "votacoes.json")
    deputados = carregar(args.site, "deputados.json")
    assuntos = carregar(args.site, "assuntos.json")
    meta = carregar(args.site, "meta.json")
    try:
        with open(os.path.join(args.site, "config.json"), encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        config = {}
    doacao = config.get("doacao") or {}
    g = Gerador(modelo, URL, args.saida, doacao.get("url", ""))
    nome_assunto = {a["slug"]: a["nome"] for a in assuntos}
    nome_dep = {d["id"]: d for d in deputados}
    por_projeto = {}
    for v in votacoes:
        por_projeto.setdefault(v["p"], []).append(v)
    pr_por_id = {p["id"]: p for p in projetos}
    fonte_aviso = ("Assunto e resumo são feitos por inteligência artificial e podem conter erros; o texto oficial de "
                   "cada projeto está sempre disponível no site da Câmara.")

    def link_projeto(pr, raiz):
        return f'<li><a href="{raiz}projeto/{pr["id"]}/">{esc(pr["titulo"])}</a></li>'

    def votos_da_votacao(vid):
        arq = os.path.join(args.site, "dados", "votacoes", f"{vid}.json")
        if not os.path.exists(arq):
            return []
        with open(arq, encoding="utf-8") as f:
            return json.load(f)["v"]

    # ---- projetos
    for pr in projetos:
        minhas = sorted(por_projeto.get(pr["id"], []), key=lambda v: v["d"])
        nominais = [v for v in minhas if v["t"] == "nominal" and v.get("s")]
        raiz = "../../"
        ult = nominais[-1] if nominais else None
        if ult:
            votos = (f'Votação de {data_br(ult["d"])} ({"aprovada" if ult["ap"] else "rejeitada"}): '
                     f'{placar_texto(ult["s"])}.')
        else:
            votos = ("Votação secreta: o voto de cada deputado não é divulgado." if pr["tipo"] == "secreta" else
                     "Votação simbólica: o resultado foi anunciado sem registrar o voto de cada deputado.")
        resumo = pr.get("resumo") or pr.get("ementa") or ""
        descricao = curto(resumo, 150)
        if ult:
            descricao += f' Votação de {data_br(ult["d"])}: {placar_texto(ult["s"])}. Veja como cada deputado votou.'
        avisos = aviso_ia(pr)
        assunto = nome_assunto.get(pr["a"], "")

        # votos de cada deputado da última votação nominal, agrupados (links para as páginas dos deputados)
        grupos_html, grupos_md = "", ""
        if ult:
            por_cod = {}
            for dep_id, cod, partido in votos_da_votacao(ult["id"]):
                d = nome_dep.get(dep_id)
                por_cod.setdefault(cod, []).append((d["nome"] if d else f"Deputado {dep_id}", dep_id, partido or (d or {}).get("partido", "")))
            partes_h, partes_m = [], []
            for cod in "SNAOP":
                lista = sorted(por_cod.get(cod, []), key=lambda x: x[0])
                if not lista:
                    continue
                partes_h.append(f'<h3>{VOTO_NOME[cod]} ({len(lista)})</h3><p>' + ", ".join(
                    f'<a href="{raiz}deputado/{i}/">{esc(n)}</a>' + (f' ({esc(p)})' if p else "") for n, i, p in lista) + "</p>")
                partes_m.append(f"### {VOTO_NOME[cod]} ({len(lista)})\n\n" + "; ".join(
                    f"[{n}]({URL}/deputado/{i}/)" + (f" ({p})" if p else "") for n, i, p in lista) + "\n")
            grupos_html = '<details><summary>Lista de deputados por voto</summary>' + "".join(partes_h) + "</details>"
            grupos_md = "\n".join(partes_m)

        corpo = (
            '<div class="miolo pagina-projeto">'
            f'<nav class="migalhas" aria-label="Você está em"><ol><li><a href="{raiz}">Assuntos</a></li>'
            f'<li><a href="{raiz}assunto/{pr["a"]}/">{esc(assunto)}</a></li><li aria-current="page">{esc(pr["nome"])}</li></ol></nav>'
            f'<header class="cabeca-projeto"><h1>{esc(titulo_completo(pr))}</h1>'
            f'<p class="cabeca-projeto__meta">{esc(pr["nome"])} · última votação em {data_br(pr["ultima"])}</p></header>'
            f'<div class="resumo-projeto"><p>{esc(resumo)}</p></div>'
            + "".join(f'<p class="nota">{esc(a)}</p>' for a in avisos)
            + f'<section class="bloco"><h2>Como cada deputado votou</h2><p class="nota">{esc(votos)}</p>{grupos_html}</section>'
            f'<p class="nota">Assunto: <a href="{raiz}assunto/{pr["a"]}/">{esc(assunto)}</a>. {esc(fonte_aviso)}</p>'
            + (f'<p><a href="{esc(pr["texto"])}" rel="noopener noreferrer">Texto completo no site da Câmara</a></p>' if pr.get("texto") else "")
            + "</div>")

        md = [f"# {pr['titulo']}", "",
              f"- Projeto: {pr['nome']}",
              f"- Assunto: [{assunto}]({URL}/assunto/{pr['a']}/)",
              f"- Última votação: {data_br(pr['ultima'])}",
              f"- Página: {URL}/projeto/{pr['id']}/"]
        if pr.get("texto"):
            md.append(f"- Texto oficial: {pr['texto']}")
        md += ["", "## Resumo", "", resumo, ""]
        md += [f"> Aviso: {a}" for a in avisos] + ([""] if avisos else [])
        if pr.get("pontos"):
            md += ["## Pontos principais", ""] + [f"- {p}" for p in pr["pontos"]] + [""]
        md += ["## Votações", ""]
        for v in minhas:
            tipo = {"nominal": "nominal (voto de cada deputado registrado)", "simbolica": "simbólica (sem o voto de cada deputado)",
                    "secreta": "secreta"}.get(v["t"], v["t"])
            md.append(f"- {data_br(v['d'])}: {'aprovada' if v['ap'] else 'rejeitada'}, votação {tipo}."
                      + (f" Placar: {placar_texto(v['s'])}." if v.get("s") else "") + (f" {v['desc']}" if v.get("desc") else ""))
        if grupos_md:
            md += ["", f"## Como cada deputado votou ({data_br(ult['d'])})", "", grupos_md]
        md += ["", "---", fonte_aviso + " Sem nota e sem ranking."]
        ld = {"@context": "https://schema.org", "@graph": [
            {"@type": "Legislation", "name": pr["titulo"], "legislationIdentifier": pr["nome"], "description": curto(resumo, 300),
             "inLanguage": "pt-BR", "legislationJurisdiction": "BR", "url": f"{URL}/projeto/{pr['id']}/",
             "dateModified": pr["ultima"], **({"sameAs": pr["texto"]} if pr.get("texto") else {}),
             "about": assunto, "publisher": {"@type": "GovernmentOrganization", "name": "Câmara dos Deputados"}},
            migalhas_ld([("Assuntos", URL + "/"), (assunto, f"{URL}/assunto/{pr['a']}/"), (pr["nome"], None)])]}
        g.montar(f'projeto/{pr["id"]}', f'projeto/{pr["id"]}', f"{pr['nome']}: {curto(pr['titulo'], 56)} | {NOME}", descricao, corpo,
                 estruturados=ld, markdown="\n".join(md) + "\n")

    # ---- deputados
    n_dep = 0
    por_id_votacao = {v["id"]: v for v in votacoes}
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
            n_vot = len(votos_dep)
            resumo = (f'Votou em {n_vot} {"votação nominal" if n_vot == 1 else "votações nominais"}, de {data_br(meta["de"])} a {data_br(meta["ate"])}: '
                      f'{total.get("S", 0)} sim e {total.get("N", 0)} não.')
        else:
            resumo = "Sem voto registrado nas votações nominais do período."
        descricao = f'Veja como {d["nome"]} ({sigla}) votou na Câmara dos Deputados. {resumo} Sem nota e sem ranking.'
        ordenados = sorted(((por_id_votacao[vid], cod) for vid, cod in votos_dep if vid in por_id_votacao),
                           key=lambda x: x[0]["d"], reverse=True)
        recentes, vistos, md_votos = [], set(), []
        for v, cod in ordenados:
            pr = pr_por_id.get(v["p"])
            if not pr:
                continue
            md_votos.append(f"- {data_br(v['d'])}: **{VOTO_NOME[cod]}** em [{pr['titulo']}]({URL}/projeto/{pr['id']}/) ({pr['nome']})")
            if pr["id"] not in vistos and len(recentes) < 12:
                vistos.add(pr["id"])
                recentes.append(link_projeto(pr, "../../"))
        corpo = (
            '<div class="miolo">'
            f'<nav class="migalhas" aria-label="Você está em"><ol><li><a href="../../deputados/">Deputados</a></li><li aria-current="page">{esc(d["nome"])}</li></ol></nav>'
            f'<header class="cabeca-dep"><div><h1>{esc(d["nome"])}</h1><p class="cabeca-dep__sub">{esc(sigla)}</p></div></header>'
            f'<section><h2>Votos registrados</h2><p class="nota">{esc(resumo)}</p></section>'
            + (f'<section class="bloco"><h2>Votações recentes</h2><ul>{"".join(recentes)}</ul></section>' if recentes else "")
            + "</div>")
        md = [f"# {d['nome']}", "", f"- Partido e estado: {sigla}",
              f"- Situação: {'em exercício' if d.get('ex') else 'não está em exercício agora'}",
              f"- Página: {URL}/deputado/{d['id']}/", "", "## Votos registrados", "", resumo, ""]
        if md_votos:
            md += ["## Como votou (votações nominais, da mais recente para a mais antiga)", ""] + md_votos + [""]
        md += ["---", "Votar sim ou não numa votação não diz, sozinho, se o deputado apoia o assunto do projeto. Sem nota e sem ranking."]
        pessoa = {"@type": "Person", "name": d["nome"],
                  **({"jobTitle": "Deputado Federal", "worksFor": {"@type": "GovernmentOrganization", "name": "Câmara dos Deputados"}} if d.get("ex") else {}),
                  **({"memberOf": {"@type": "Organization", "name": d["partido"]}} if d.get("partido") else {})}
        ld = {"@context": "https://schema.org", "@graph": [
            {"@type": "ProfilePage", "url": f"{URL}/deputado/{d['id']}/", "name": d["nome"], "inLanguage": "pt-BR", "mainEntity": pessoa},
            migalhas_ld([("Deputados", f"{URL}/deputados/"), (d["nome"], None)])]}
        g.montar(f'deputado/{d["id"]}', f'deputado/{d["id"]}', f'{d["nome"]}: {NOME}', descricao, corpo,
                 estruturados=ld, markdown="\n".join(md) + "\n")
        n_dep += 1

    # ---- assuntos
    for a in assuntos:
        todos = sorted((p for p in projetos if p["a"] == a["slug"] or p["s"] == a["slug"]),
                       key=lambda p: (p["ind"], p["ultima"] or ""), reverse=True)
        meus = todos[:150]
        descricao = (f'{a["descricao"].capitalize()}. {a["n"]} projetos votados na Câmara dos Deputados, '
                     f'{a["n_ind"]} com o voto de cada deputado. Sem nota e sem ranking.')
        corpo = (
            '<div class="miolo">'
            f'<nav class="migalhas" aria-label="Você está em"><ol><li><a href="../../">Assuntos</a></li><li aria-current="page">{esc(a["nome"])}</li></ol></nav>'
            f'<header class="cabeca-assunto"><h1>{esc(a["nome"])}</h1><p>{esc(a["descricao"].capitalize())}.</p></header>'
            '<p class="nota">Votação simbólica: os partidos chegam a um acordo e o resultado é anunciado sem registrar o voto de cada deputado. '
            'Só nos projetos com voto de cada deputado dá para ver como cada um votou.</p>'
            f'<ul class="projetos">{"".join(link_projeto(p, "../../") for p in meus)}</ul></div>')
        md = [f"# {a['nome']}", "", f"{a['descricao'].capitalize()}.", "",
              f"{a['n']} projetos votados na Câmara dos Deputados; {a['n_ind']} com o voto de cada deputado registrado.", "",
              "## Projetos", ""]
        md += [f"- [{p['titulo']}]({URL}/projeto/{p['id']}/) ({p['nome']}, {data_br(p['ultima'])}"
               + (", com voto de cada deputado" if p["ind"] else "") + ")" for p in todos]
        md += ["", "---", "Votação simbólica: os partidos chegam a um acordo e o resultado é anunciado sem registrar o voto de cada deputado. Sem nota e sem ranking."]
        ld = {"@context": "https://schema.org", "@graph": [
            {"@type": "CollectionPage", "name": f'{a["nome"]}: {NOME}', "url": f"{URL}/assunto/{a['slug']}/", "inLanguage": "pt-BR",
             "description": descricao,
             "mainEntity": {"@type": "ItemList", "numberOfItems": len(todos), "itemListElement": [
                 {"@type": "ListItem", "position": i + 1, "url": f"{URL}/projeto/{p['id']}/", "name": p["titulo"]} for i, p in enumerate(meus)]}},
            migalhas_ld([("Assuntos", URL + "/"), (a["nome"], None)])]}
        g.montar(f'assunto/{a["slug"]}', f'assunto/{a["slug"]}', f'{a["nome"]}: {NOME}', descricao, corpo,
                 estruturados=ld, markdown="\n".join(md) + "\n")

    # ---- lista de deputados (todos, por estado) e como funciona
    por_uf = {}
    for d in sorted(deputados, key=lambda x: x["nome"]):
        por_uf.setdefault(d.get("uf") or "—", []).append(d)
    corpo = ('<div class="miolo"><nav class="migalhas" aria-label="Você está em"><ol><li><a href="../">Início</a></li><li aria-current="page">Deputados</li></ol></nav>'
             '<h1>Deputados federais</h1><p class="nota">Escolha um deputado para ver como ele votou. Sem nota e sem ranking.</p>'
             + "".join(f'<section><h2>{esc(uf)}</h2><ul>' + "".join(
                 f'<li><a href="../deputado/{d["id"]}/">{esc(d["nome"])}</a> ({esc(d.get("partido") or "")})</li>' for d in lista)
                 + "</ul></section>" for uf, lista in sorted(por_uf.items())) + "</div>")
    md = ["# Deputados federais", "", f"{len(deputados)} deputados com voto registrado ou em exercício no período. Sem nota e sem ranking.", ""]
    for uf, lista in sorted(por_uf.items()):
        md += [f"## {uf}", ""] + [f"- [{d['nome']}]({URL}/deputado/{d['id']}/) ({d.get('partido') or ''})" for d in lista] + [""]
    g.montar("deputados", "deputados", f"Deputados federais: {NOME}",
             "Procure um deputado federal pelo nome ou pelo estado e veja como ele votou na Câmara dos Deputados. Sem nota e sem ranking.",
             corpo, markdown="\n".join(md) + "\n",
             estruturados={"@context": "https://schema.org", "@type": "CollectionPage", "name": "Deputados federais",
                           "url": f"{URL}/deputados/", "inLanguage": "pt-BR"})

    pct = round(100 * meta["simbolicas"] / meta["votacoes"])
    sobre = [
        ("Neutro e apartidário, sem nota e sem ranking",
         "O Voto de Verdade não dá nota, não faz ranking e não diz quem votou certo ou errado. Mostra o que cada deputado votou. "
         "Votar sim ou não numa votação não diz, sozinho, se o deputado apoia o assunto do projeto: muitas votações são sobre emendas, substitutivos ou pontos separados do texto."),
        ("De onde vêm os dados",
         f"Do portal de Dados Abertos da Câmara dos Deputados. O site mostra {meta['votacoes']} votações em plenário, de {data_br(meta['de'])} a {data_br(meta['ate'])}, e é atualizado todos os dias."),
        ("Só a Câmara dos Deputados, por enquanto",
         "O site cobre os deputados federais. O Senado, as assembleias estaduais e as câmaras de vereadores não estão aqui."),
        ("Quais votações o site mostra",
         "Um projeto costuma passar por várias votações no plenário. Aqui entram só as que decidem sobre o projeto em si, isto é, aprovar ou rejeitar. "
         "Ficam de fora as votações de urgência (que só decidem se o projeto anda mais rápido), de requerimentos, de emendas ou destaques isolados (que votam a mudança de um trecho) e de procedimento. "
         "Por isso um projeto que foi votado muitas vezes pode aparecer com uma só votação. "
         "Às vezes a Câmara vota um substitutivo, um texto novo que troca o original. Essa votação aparece, com um aviso: o resumo foi feito a partir da ementa do projeto original, e o texto votado pode ser diferente."),
        ("Assunto e resumo são feitos por inteligência artificial",
         "Uma inteligência artificial lê o texto oficial de cada projeto, escolhe o assunto e escreve um resumo em linguagem simples. Ela pode errar. Quando há dúvida, o projeto mostra um aviso. "
         "Ninguém revisa os resumos antes de irem ao ar, e por enquanto o site não tem um canal para pedir correções. Se algo parecer estranho, confira no texto oficial."),
        ("Por que nem todo projeto mostra o voto de cada deputado",
         f"{meta['simbolicas']} das {meta['votacoes']} votações ({pct}%) foram simbólicas: os partidos chegam a um acordo e o resultado é anunciado sem registrar o voto de cada deputado."),
        ("Quem faz e privacidade",
         "O Voto de Verdade é um site independente, sem ligação com a Câmara dos Deputados, com partidos ou com candidatos. Não usa cookies nem ferramentas que rastreiam quem visita."),
    ]
    corpo = ('<div class="miolo texto-longo"><nav class="migalhas" aria-label="Você está em"><ol><li><a href="../">Início</a></li><li aria-current="page">Como o site funciona</li></ol></nav>'
             '<h1>Como o site funciona</h1>' + "".join(f"<h2>{esc(t)}</h2><p>{esc(x)}</p>" for t, x in sobre) + "</div>")
    g.montar("sobre", "sobre", f"Como o site funciona: {NOME}",
             "Neutro e apartidário, sem nota e sem ranking. De onde vêm os dados, como a inteligência artificial é usada e o que o site não faz.",
             corpo, markdown="# Como o site funciona\n\n" + "\n\n".join(f"## {t}\n\n{x}" for t, x in sobre) + "\n",
             estruturados={"@context": "https://schema.org", "@type": "AboutPage", "name": "Como o site funciona",
                           "url": f"{URL}/sobre/", "inLanguage": "pt-BR"})

    # ---- apoie (só quando há um link de doação em site/config.json)
    if doacao.get("url"):
        g.montar("apoie", "apoie", f"Apoie o {NOME}",
                 "Faça uma doação única, sem assinatura, para manter o Voto de Verdade no ar. Doar não muda o que o site mostra: sem nota e sem ranking.",
                 '<div class="miolo texto-longo"><h1>Apoie o Voto de Verdade</h1>'
                 '<p>Doe uma vez, o valor que quiser, sem assinatura. Doar não muda o que o site mostra: quem doa não escolhe o que aparece nem ganha destaque.</p>'
                 f'<p><a href="{esc(doacao["url"])}" rel="noopener noreferrer">Fazer uma doação</a></p></div>',
                 markdown=f"# Apoie o Voto de Verdade\n\nDoação única, sem assinatura: {doacao['url']}\n")

    # ---- página inicial (com o endereço de compartilhamento certo e o conteúdo já escrito)
    recentes = sorted((v for v in votacoes if v["t"] == "nominal"), key=lambda v: v["d"], reverse=True)
    vistos, lista_rec = set(), []
    for v in recentes:
        pr = pr_por_id.get(v["p"])
        if pr and pr["id"] not in vistos and len(lista_rec) < 6:
            vistos.add(pr["id"])
            lista_rec.append((pr, v))
    corpo = (
        '<div class="miolo"><section class="heroi"><div>'
        '<h1>Veja como a Câmara votou, assunto por assunto</h1>'
        '<p class="heroi__texto">Escolha um tema e leia o que foi votado, com o voto de cada deputado federal.</p></div></section>'
        + principios_html()
        + '<section class="secao"><h2>Assuntos</h2><ul>'
        + "".join(f'<li><a href="assunto/{a["slug"]}/">{esc(a["nome"])}</a>: {contagem_assunto(a)}</li>' for a in assuntos)
        + '</ul></section><section class="secao"><h2>Últimas votações</h2><ul>'
        + "".join(f'<li><a href="projeto/{pr["id"]}/">{esc(curto(pr["titulo"], 120))}</a> ({data_br(v["d"])})</li>' for pr, v in lista_rec)
        + '</ul></section><p><a href="deputados/">Procure um deputado pelo nome</a> · <a href="sobre/">Como o site funciona</a></p></div>')
    dist = [{"@type": "DataDownload", "encodingFormat": "application/json", "name": n, "contentUrl": f"{URL}/dados/{n}"}
            for n in ("meta.json", "assuntos.json", "projetos.json", "votacoes.json", "deputados.json")]
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebSite", "@id": URL + "/#site", "name": NOME, "url": URL + "/", "inLanguage": "pt-BR", "description": LEMA},
        {"@type": "Dataset", "name": "Votações da Câmara dos Deputados, com assunto e resumo em linguagem simples",
         "description": (f"{meta['votacoes']} votações em plenário da Câmara dos Deputados, de {data_br(meta['de'])} a {data_br(meta['ate'])}, "
                         f"{meta['projetos']} projetos com assunto e resumo feitos por inteligência artificial, e o voto de cada deputado nas "
                         f"{meta['nominais']} votações nominais. Dados originais: Dados Abertos da Câmara dos Deputados."),
         "url": URL + "/", "inLanguage": "pt-BR", "isAccessibleForFree": True, "isBasedOn": FONTE_DADOS,
         "temporalCoverage": f"{meta['de']}/{meta['ate']}", "spatialCoverage": "Brasil", "dateModified": meta["gerado_em"],
         "keywords": ["Câmara dos Deputados", "votações", "deputados federais", "transparência", "Brasil"],
         "creator": {"@type": "Organization", "name": NOME, "url": URL + "/"}, "distribution": dist}]}
    md_home = [f"# {NOME}", "", f"> {LEMA}", "", "## Assuntos", ""]
    md_home += [f"- [{a['nome']}]({URL}/assunto/{a['slug']}/): {a['n']} projetos" for a in assuntos]
    md_home += ["", "## Últimas votações com o voto de cada deputado", ""]
    md_home += [f"- [{pr['titulo']}]({URL}/projeto/{pr['id']}/) ({data_br(v['d'])})" for pr, v in lista_rec]
    md_home += ["", f"- [Deputados]({URL}/deputados/)", f"- [Como o site funciona]({URL}/sobre/)"]
    g.montar("", "", f"{NOME}: como a Câmara dos Deputados votou",
             "Escolha um assunto e veja o que a Câmara dos Deputados votou e como cada deputado federal votou. Sem nota e sem ranking.",
             corpo, raiz="", estruturados=ld, markdown="\n".join(md_home) + "\n")

    base = urlparse(URL).path.rstrip("/") + "/"
    g.montar("404", "nao-encontrada", f"Página não encontrada: {NOME}", "Página não encontrada.",
             '<div class="miolo"><div class="vazio vazio--pagina"><div class="vazio__corpo">'
             '<h1 class="vazio__titulo">Não achamos esta página</h1>'
             '<p class="vazio__texto">O endereço pode ter mudado ou estar escrito errado. Comece por um destes caminhos.</p>'
             f'<div class="vazio__acoes"><a class="botao botao--leve" href="{base}">Ver todos os assuntos</a>'
             f'<a class="botao botao--leve" href="{base}deputados/">Procurar um deputado</a>'
             f'<a class="botao botao--leve" href="{base}sobre/">Como o site funciona</a></div></div></div></div>',
             raiz=base, noindex=True)
    os.replace(os.path.join(args.saida, "404", "index.html"), os.path.join(args.saida, "404.html"))
    os.rmdir(os.path.join(args.saida, "404"))

    # ---- sitemap, robots, llms.txt, dados abertos e descoberta por agentes
    linhas = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
              f'<url><loc>{esc(URL)}/</loc><lastmod>{meta["gerado_em"]}</lastmod></url>']
    linhas += [f'<url><loc>{esc(u)}</loc><lastmod>{meta["gerado_em"]}</lastmod></url>' for u in g.paginas]
    linhas.append("</urlset>")
    g.escrever("sitemap.xml", "\n".join(linhas) + "\n")
    # Buscadores e agentes de IA podem ler tudo. O sinal de uso diz que pode indexar e usar para responder
    # perguntas; sobre treinar modelos, o site não manifesta preferência.
    g.escrever("robots.txt", f"User-agent: *\nAllow: /\nContent-Signal: search=yes, ai-input=yes\n\nSitemap: {URL}/sitemap.xml\n")

    arquivos_dados = [
        ("meta.json", "números gerais e datas de cobertura"),
        ("assuntos.json", "os assuntos, com quantidade de projetos"),
        ("projetos.json", "um registro por projeto: título, resumo em linguagem simples, assunto, avisos da inteligência artificial, links"),
        ("votacoes.json", "uma linha por votação: data, tipo (nominal, simbólica, secreta), resultado e placar"),
        ("deputados.json", "um registro por deputado: nome, partido, estado, se está em exercício"),
        ("votacoes/<id da votação>.json", "o voto de cada deputado numa votação nominal: {\"v\": [[id do deputado, código do voto, partido], ...]}"),
        ("deputados/<id do deputado>.json", "todos os votos de um deputado: {\"v\": [[id da votação, código do voto], ...]}"),
    ]
    codigos = "S = Sim, N = Não, A = Abstenção, O = Obstrução, P = Presidia a sessão (artigo 17)"
    abertura = (f"Arquivos JSON públicos, sem chave e sem cadastro, atualizados todos os dias. Cobertura: {data_br(meta['de'])} a {data_br(meta['ate'])}. "
                f"Última atualização: {data_br(meta['gerado_em'])}. Origem dos dados de votação: Dados Abertos da Câmara dos Deputados ({FONTE_DADOS}). "
                "Assunto e resumo são feitos por inteligência artificial e podem conter erros; o campo de confiança indica quando há dúvida.")
    leia = ["# Dados abertos do Voto de Verdade", "", abertura, "", "## Arquivos", ""]
    leia += [f"- `{URL}/dados/{n}`: {d}" for n, d in arquivos_dados]
    leia += ["", f"Códigos de voto: {codigos}.", "",
             "## Campos principais", "",
             "- Projeto (`projetos.json`): `id`, `nome` (ex.: PL 1234/2024), `titulo`, `resumo`, `ementa` (texto oficial), `texto` (link oficial), "
             "`a` (assunto principal) e `s` (secundário), `ca`/`cr` (confiança do assunto/do resumo: alta, média ou baixa), `aa`/`ar` (avisos), "
             "`pontos`, `tags`, `n` (votações), `ind` (tem voto de cada deputado), `ultima` (data), `aprovada`, `tipo`.",
             "- Votação (`votacoes.json`): `id`, `p` (id do projeto), `d` (data), `t` (nominal, simbolica ou secreta), `ap` (aprovada), `desc`, "
             "`s` = [sim, não, abstenção, obstrução, art. 17] nas nominais.",
             "- Deputado (`deputados.json`): `id`, `nome`, `uf`, `partido`, `ex` (em exercício).", "",
             "## Regras de uso", "",
             "- Cite o Voto de Verdade e a Câmara dos Deputados como fontes.",
             "- O site é neutro e apartidário: não crie nota, ranking ou juízo de “certo e errado” sobre deputados a partir destes dados. "
             "Votar sim ou não numa votação não diz, sozinho, se o deputado apoia o assunto do projeto.",
             "- Votações simbólicas e secretas não têm o voto de cada deputado.",
             "- Diga sempre que assunto e resumo foram feitos por inteligência artificial.", "",
             f"Descrição técnica (OpenAPI): {URL}/openapi.json"]
    g.escrever("dados/LEIA-ME.md", "\n".join(leia) + "\n")

    def resp(desc):
        return {"200": {"description": desc, "content": {"application/json": {"schema": {"type": ["object", "array"]}}}}}
    caminhos = {f"/dados/{n}": {"get": {"summary": d.capitalize(), "operationId": n.replace(".json", ""), "responses": resp(d)}}
                for n, d in arquivos_dados if "<" not in n}
    caminhos["/dados/votacoes/{id}.json"] = {"get": {
        "summary": "Voto de cada deputado numa votação nominal", "operationId": "votos_da_votacao",
        "description": f"Códigos de voto: {codigos}. Use o campo id de votacoes.json (ex.: 2345468-38).",
        "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}], "responses": resp("Votos")}}
    caminhos["/dados/deputados/{id}.json"] = {"get": {
        "summary": "Votos de um deputado", "operationId": "votos_do_deputado",
        "description": f"Códigos de voto: {codigos}. Use o campo id de deputados.json.",
        "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}], "responses": resp("Votos")}}
    g.escrever("openapi.json", json.dumps({
        "openapi": "3.1.0",
        "info": {"title": f"{NOME}: dados abertos", "version": meta["gerado_em"], "description": abertura, "contact": {"url": URL + "/sobre/"}},
        "servers": [{"url": URL}], "paths": caminhos}, ensure_ascii=False, indent=2) + "\n")

    llms = [f"# {NOME}", "", f"> {LEMA}", "",
            "Notas para agentes de IA:",
            "- O site não dá nota nem faz ranking de deputados. Ao responder, não crie nota, ranking nem juízo de “certo e errado”; "
            "votar sim ou não numa votação não diz, sozinho, se o deputado apoia o assunto do projeto.",
            "- Assunto e resumo de cada projeto são feitos por inteligência artificial e podem conter erros (há aviso quando a confiança não é alta). "
            "O texto oficial está sempre no site da Câmara.",
            "- Votações simbólicas e secretas não têm o voto de cada deputado.",
            f"- Toda página tem uma versão em Markdown: acrescente `index.md` ao endereço (ex.: {URL}/assunto/saude/index.md).", "",
            "## Páginas principais", "",
            f"- [Início, com as últimas votações]({URL}/index.md)",
            f"- [Deputados, por estado]({URL}/deputados/index.md)",
            f"- [Como o site funciona]({URL}/sobre/index.md)", "",
            "## Assuntos", ""]
    llms += [f"- [{a['nome']}]({URL}/assunto/{a['slug']}/index.md): {a['descricao']} ({a['n']} projetos)" for a in assuntos]
    llms += ["", "## Dados abertos (JSON, sem chave)", "",
             f"- [Como usar os dados]({URL}/dados/LEIA-ME.md)", f"- [Descrição OpenAPI]({URL}/openapi.json)",
             f"- [Projetos, com resumo e assunto]({URL}/dados/projetos.json)", f"- [Votações]({URL}/dados/votacoes.json)",
             f"- [Deputados]({URL}/dados/deputados.json)", f"- [Mapa do site]({URL}/sitemap.xml)", "",
             "## Opcional", "",
             "- Em navegadores com WebMCP, as telas do site oferecem ferramentas de consulta (buscar_projetos, votos_do_projeto, buscar_deputado, votos_do_deputado, listar_assuntos)."]
    g.escrever("llms.txt", "\n".join(llms) + "\n")

    # Descoberta: .well-known/api-catalog (RFC 9727) e .well-known/agent-skills
    caminho_base = urlparse(URL).path.rstrip("/") + "/"
    modelo_skill = os.path.join(args.site, "modelos", "skill.md")
    elos = {"anchor": URL + "/", "describedby": [{"href": URL + "/llms.txt", "type": "text/markdown"}],
            "sitemap": [{"href": URL + "/sitemap.xml", "type": "application/xml"}],
            "service-desc": [{"href": URL + "/openapi.json", "type": "application/vnd.oai.openapi+json"}],
            "service-doc": [{"href": URL + "/dados/LEIA-ME.md", "type": "text/markdown"}]}
    if os.path.exists(modelo_skill):
        with open(modelo_skill, encoding="utf-8") as f:
            skill = (f.read().replace("{URL}", URL).replace("{DE}", data_br(meta["de"])).replace("{ATE}", data_br(meta["ate"])))
        g.escrever(".well-known/agent-skills/voto-de-verdade/SKILL.md", skill)
        digest = hashlib.sha256(skill.encode("utf-8")).hexdigest()
        g.escrever(".well-known/agent-skills/index.json", json.dumps({
            "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
            "skills": [{"name": "voto-de-verdade", "type": "skill-md",
                        "description": "Use para responder perguntas sobre como a Câmara dos Deputados votou e como cada deputado federal votou, "
                                       "com dados abertos em JSON, de forma neutra e sem nota ou ranking.",
                        "url": caminho_base + ".well-known/agent-skills/voto-de-verdade/SKILL.md", "digest": "sha256:" + digest}]},
            ensure_ascii=False, indent=2) + "\n")
        elos["item"] = [{"href": URL + "/.well-known/agent-skills/index.json", "type": "application/json"}]
    catalogo = json.dumps({"linkset": [elos]}, ensure_ascii=False, indent=2) + "\n"
    g.escrever(".well-known/api-catalog", catalogo)
    g.escrever(".well-known/api-catalog.json", catalogo)

    print(f"Pronto: {len(g.paginas)} páginas em {args.saida}/ ({len(projetos)} projetos, {n_dep} deputados, {len(assuntos)} assuntos).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
