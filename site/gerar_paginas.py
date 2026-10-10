#!/usr/bin/env python3
"""Monta a pasta do site pronta para publicar (GitHub Pages).

Copia site/ (menos os .py) para a pasta de saída e cria, em português (na raiz) e em inglês (em en/):

- uma página própria para cada projeto (projeto/<id>/), deputado (deputado/<id>/) e assunto
  (assunto/<slug>/), mais deputados/, sobre/ e apoie/, cada uma com título, descrição, prévia de
  compartilhamento, dados estruturados (schema.org) e o conteúdo principal já escrito no HTML, para quem
  ainda não carregou o JavaScript, para os buscadores e para agentes de IA. Essas páginas abrem o mesmo
  aplicativo (app.js), que mostra a tela completa;
- uma versão em Markdown de cada página (index.md), mais fácil de ler para agentes de IA;
- sitemap.xml (com as versões em cada idioma), robots.txt, 404.html, llms.txt, openapi.json (descrição dos dados
  abertos), dados/LEIA-ME.md e os arquivos de descoberta em .well-known/ (api-catalog e agent-skills).

O português é o texto de origem; o inglês vem do dicionário site/idiomas/en.json (veja site/idioma.py) e dos dados
traduzidos em site/dados/en/ (veja site/exportar_en.py). A ementa oficial fica em português nas duas versões.

Uso: python site/gerar_paginas.py --saida _site --url https://usuario.github.io/repositorio
     python site/gerar_paginas.py --idiomas pt        (só o português, sem seletor de idioma)
"""
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
from types import SimpleNamespace
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from idioma import Idioma  # noqa: E402

FONTE_DADOS = "https://dadosabertos.camara.leg.br/"
NOME = "Voto de Verdade"
LEMA = ("Site independente, neutro e apartidário: mostra o que a Câmara dos Deputados votou e como cada "
        "deputado federal votou, sem nota e sem ranking.")
IDIOMAS = ("pt", "en")
# Siglas depois das quais um ponto não termina a frase (só no inglês: «Law No. 15.201»).
ABREVIATURAS_EN = {"no", "nos", "art", "arts", "sec", "inc", "st", "vs", "etc", "dr", "mr", "mrs", "ms", "vol"}
CONFIANCA_EN = {"alta": "high", "media": "medium", "baixa": "low"}


def esc(t):
    return html.escape(t or "", quote=True)


def maiuscula(t):
    """Primeira letra maiúscula, sem mexer no resto («SUS, remédios…» continua com SUS)."""
    return t[:1].upper() + t[1:]


def curto(t, limite):
    t = " ".join((t or "").split())
    if len(t) <= limite:
        return t
    corte = t[: limite - 1]
    i = corte.rfind(" ")
    return corte[: i if i > limite // 2 else limite - 1].rstrip(" ,;:") + "…"


def titulo_projeto_seo(nome, titulo, marca):
    """«PL 1234/2024: texto curto | Voto de Verdade», com cerca de 60 caracteres. A marca só entra se couber sem cortar o título."""
    base = f"{nome}: {curto(titulo, 60 - len(nome) - 2)}"
    sufixo = f" | {marca}"
    return base + sufixo if len(base) + len(sufixo) <= 62 else base


def titulo_deputado_seo(L, nome, sigla, marca):
    """«Nome (PARTIDO · UF): votos na Câmara | Voto de Verdade», sem passar de cerca de 60 caracteres (corta o que não couber)."""
    t = nome
    for parte in ((f" ({sigla})" if sigla else ""), L(": votos na Câmara"), f" | {marca}"):
        if len(t) + len(parte) <= 60:
            t += parte
    return t


def titulo_completo(L, pr):
    """Se o título foi cortado com «…» e o resumo começa com o mesmo texto, usa a primeira frase inteira do resumo."""
    t, r = pr.get("titulo") or "", pr.get("resumo") or ""
    if not t.endswith("…") or not r:
        return t
    base = t[:-1].rstrip()
    if not r.startswith(base):
        return t
    fim = None
    for m in re.finditer(r"[.!?](?=\s|$)", r[len(base):]):
        antes = re.search(r"(\w+)$", r[: len(base) + m.start()])
        if L.en and antes and antes.group(1).lower() in ABREVIATURAS_EN:
            continue
        fim = m
        break
    inteiro = r[: len(base) + fim.start() + 1] if fim else r
    return inteiro if len(inteiro) <= 400 else t


def contagem_assunto(L, a):
    """«N projetos com voto de cada deputado (M no total)» ou só o total, no singular/plural certo."""
    def proj(n):
        return L("{0} projeto", n) if n == 1 else L("{0} projetos", n)
    ni = a.get("n_ind")
    if ni is None:
        return proj(a["n"])
    return L("{0} com voto de cada deputado ({1} no total)", proj(ni), a["n"])


def so_https(url):
    """Só deixa passar link https (nunca javascript:, data: etc.), mesmo que venha dos dados."""
    return url if isinstance(url, str) and url.lower().startswith("https://") else ""


def jsonld(obj):
    """<script> de dados estruturados (schema.org)."""
    return ('<script type="application/ld+json">'
            + json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + "</script>")


def carregar(pasta, nome, opcional=False):
    try:
        with open(os.path.join(pasta, "dados", nome), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        if opcional:
            return {}
        raise


def placar_texto(L, s):
    sim, nao, abst, obs, pres = s
    partes = [L("{0} sim", sim), L("{0} não", nao)]
    if abst:
        partes.append(L("{0} abstenção", abst) if abst == 1 else L("{0} abstenções", abst))
    if obs:
        partes.append(L("{0} obstrução", obs) if obs == 1 else L("{0} obstruções", obs))
    return ", ".join(partes)


def aviso_ia(L, pr):
    """Avisos de possível erro da classificação automática (mesma regra do site: só quando não é 'alta')."""
    def conf(c):
        return CONFIANCA_EN.get(c, c) if L.en else c
    avisos = []
    if pr.get("ca") and pr["ca"] != "alta":
        avisos.append(pr.get("aa") or L("A inteligência artificial tem dúvida sobre o assunto deste projeto (confiança {0}).", conf(pr["ca"])))
    if pr.get("cr") and pr["cr"] != "alta":
        avisos.append(pr.get("ar") or L("A inteligência artificial tem dúvida sobre o resumo deste projeto (confiança {0}).", conf(pr["cr"])))
    return avisos


# Textos fixos de index.html (o modelo da página), em português: (antes, texto, depois). Em outro idioma cada um é trocado
# pelo texto do dicionário. O mesmo texto em outro contexto não é tocado.
TEXTOS_DO_MODELO = [
    ('<a class="pular" href="#conteudo">', "Ir para o conteúdo", "</a>"),
    ('aria-label="', "Versão beta, em desenvolvimento. Saiba mais", '"'),
    ("<p><strong>", "Versão beta.", "</strong>"),
    ("</strong> ", "O Voto de Verdade está em desenvolvimento: pode ter erros e mudar sem aviso. Em caso de dúvida, confira no texto oficial da Câmara.", "</p>"),
    ('<p><a href="#/sobre">', "Ver objetivos e como o site funciona", "</a></p>"),
    ('<nav aria-label="', "Principal", '">'),
    ('<a id="nav-assuntos" href="#/" aria-current="page">', "Assuntos", "</a>"),
    ('<a id="nav-deputados" href="#/deputados">', "Deputados", "</a>"),
    ('<a id="nav-numeros" href="#/em-numeros">', "Em números", "</a>"),
    ('<a id="nav-ia" href="#/inteligencia-artificial">', "Transparência da IA", "</a>"),
    ('aria-label="', "Modo escuro", '" title="'),
    ('title="', "Modo escuro", '">'),
    ('<nav aria-label="', "Menu", '">'),
    ('class="menu-botao" type="button" popovertarget="menu-topo" aria-label="', "Menu", '"'),
    ('<a id="menu-assuntos" href="#/" aria-current="page">', "Assuntos", "</a>"),
    ('<a id="menu-deputados" href="#/deputados">', "Deputados", "</a>"),
    ('<a id="menu-numeros" href="#/em-numeros">', "Em números", "</a>"),
    ('<a id="menu-ia" href="#/inteligencia-artificial">', "Transparência da IA", "</a>"),
    ('<noscript><p class="miolo">', "Este site precisa de JavaScript para mostrar os dados.", "</p></noscript>"),
    ('<p class="rodape__destaque">', "Neutro e apartidário: aqui não há nota nem ranking de deputados.", "</p>"),
    ('<p id="rodape-dados">', "Dados da Câmara dos Deputados (Dados Abertos).", "</p>"),
    ("<p>", "Site independente, sem ligação com a Câmara dos Deputados, com partidos ou com candidatos. Não usamos cookies nem rastreamos quem visita. Por enquanto, cobrimos só a Câmara dos Deputados.", "</p>"),
    ("<p>", "Assuntos e resumos são feitos por inteligência artificial e podem conter erros. Quando não temos certeza, avisamos. O texto oficial de cada projeto está sempre ao lado. ", '<a href="#/sobre">'),
    ('<a href="#/sobre">', "Como o site funciona", "</a> · "),
    ('<a href="#/inteligencia-artificial">', "Transparência da IA", "</a></p>"),
]


class Gerador:
    """As páginas de um idioma. caminho e rota são sempre os do idioma (en/ é só a pasta onde o inglês é gravado)."""

    def __init__(self, modelo, url, saida, L, doacao="", servico="", idiomas=("pt",), versoes=None):
        self.versoes = versoes or {}  # arquivo do site -> impressão do conteúdo (vira ?v=... no endereço, para o navegador não usar cópia velha)
        self.doacao = doacao
        self.servico = servico
        self.modelo = modelo
        self.url = url.rstrip("/")
        self.saida = saida
        self.L = L
        self.idiomas = idiomas
        self.paginas = []  # caminhos das páginas que entram no sitemap (fora a inicial)

    def versao(self, arquivo):
        v = self.versoes.get(arquivo)
        return f"?v={v}" if v else ""

    def escrever(self, caminho, texto):
        destino = os.path.join(self.saida, self.L.prefixo + caminho)
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        with open(destino, "w", encoding="utf-8") as f:
            f.write(texto)

    def endereco(self, idioma, caminho):
        prefixo = "" if idioma == "pt" else idioma + "/"
        return f"{self.url}/{prefixo}{caminho}/" if caminho else f"{self.url}/{prefixo}"

    def cabeca(self, titulo, descricao, canonico, extra="", noindex=False):
        L = self.L
        t, d, c = esc(titulo), esc(descricao), esc(canonico)
        robos = "noindex" if noindex else "index, follow, max-image-preview:large, max-snippet:-1"
        linhas = [
            f'<title>{t}</title>',
            f'<meta name="description" content="{d}">',
            f'<meta name="robots" content="{robos}">',
            f'<link rel="canonical" href="{c}">',
            '<meta name="theme-color" content="#f5f6fa">',
            '<meta property="og:type" content="website">',
            f'<meta property="og:locale" content="{L.og}">',
            f'<meta property="og:site_name" content="{NOME}">',
            f'<meta property="og:title" content="{t}">',
            f'<meta property="og:description" content="{d}">',
            f'<meta property="og:url" content="{c}">',
            f'<meta property="og:image" content="{esc(self.url)}/{"og-en.png" if L.en else "og.png"}">',
            '<meta property="og:image:width" content="1200">',
            '<meta property="og:image:height" content="630">',
            f'<meta property="og:image:alt" content="{esc(L("{0}: como a Câmara dos Deputados votou", NOME))}">',
            '<meta name="twitter:card" content="summary_large_image">',
            f'<meta name="twitter:title" content="{t}">',
            f'<meta name="twitter:description" content="{d}">',
            f'<link rel="sitemap" type="application/xml" href="{esc(self.url)}/sitemap.xml">',
            f'<link rel="describedby" type="text/markdown" href="{esc(self.url)}/{L.prefixo}llms.txt">',
        ]
        if extra:
            linhas.append(extra)
        return "\n  ".join(linhas)

    def seletor_idioma(self, caminho, menu=False):
        """PT | EN: o idioma de agora é texto; o outro é link para a mesma página. O app.js acerta o link se a rota mudar."""
        L = self.L
        raiz = "../" * len(caminho.split("/")) if caminho else ""
        ativos = ("../" if L.en else "") + raiz  # raiz do site (onde ficam os dois idiomas)
        partes = []
        for cod, rotulo, nome_idioma, lang in (("pt", "PT", "Português", "pt-BR"), ("en", "EN", "English", "en")):
            if cod == L.codigo:
                partes.append(f'<span class="idioma__atual" lang="{lang}" aria-current="true" aria-label="{nome_idioma} ({rotulo})">{rotulo}</span>')
            else:
                alvo = f"{ativos}{'en/' if cod == 'en' else ''}{caminho + '/' if caminho else ''}"
                partes.append(f'<a class="idioma__outro" lang="{lang}" hreflang="{lang}" data-idioma="{cod}" href="{alvo or "./"}" aria-label="{nome_idioma} ({rotulo})">{rotulo}</a>')
        miolo = '<span class="idioma__sep" aria-hidden="true">|</span>'.join(partes)
        if menu:
            return f'<li class="menu-idioma"><span class="menu-idioma__rotulo">{esc(L("Idioma"))}</span><span class="idioma">{miolo}</span></li>'
        return f'<span class="idioma" role="group" aria-label="{esc(L("Idioma"))}">{miolo}</span>'

    def montar(self, caminho, rota, titulo, descricao, corpo, raiz=None, noindex=False, estruturados=None, markdown=None, ativos=None):
        """caminho: pasta de saída ('projeto/123', dentro da pasta do idioma); rota: rota do aplicativo ('projeto/123').
        estruturados: dados schema.org (dict). markdown: texto da versão em Markdown (index.md)."""
        L = self.L
        if raiz is None:
            raiz = "../" * len(caminho.split("/")) if caminho else ""
            ativos = ("../" if L.en else "") + raiz  # fontes, estilos e scripts ficam na raiz do site
        elif ativos is None:
            ativos = raiz
        pagina = self.modelo
        ini, fim = pagina.index("<!--INICIO-CABECA-->"), pagina.index("<!--FIM-CABECA-->")
        canonico = self.endereco(L.codigo, caminho)
        extra = []
        if markdown and not noindex:
            extra.append(f'<link rel="alternate" type="text/markdown" href="{esc(canonico)}index.md">')
        if len(self.idiomas) > 1 and not noindex:
            for cod in self.idiomas:
                extra.append(f'<link rel="alternate" hreflang="{Idioma.HTML[cod]}" href="{esc(self.endereco(cod, caminho))}">')
            extra.append(f'<link rel="alternate" hreflang="x-default" href="{esc(self.endereco("pt", caminho))}">')
            for cod in self.idiomas:
                if cod != L.codigo:
                    extra.append(f'<meta property="og:locale:alternate" content="{Idioma.OPEN_GRAPH[cod]}">')
        if estruturados:
            extra.append(jsonld(estruturados))
        cab = self.cabeca(titulo, descricao, canonico, "\n  ".join(extra), noindex)
        pagina = pagina[:ini] + cab + pagina[fim + len("<!--FIM-CABECA-->"):]
        ini, fim = pagina.index("<!--INICIO-CONTEUDO-->"), pagina.index("<!--FIM-CONTEUDO-->")
        pagina = pagina[:ini] + corpo + pagina[fim + len("<!--FIM-CONTEUDO-->"):]
        apoio = ""
        if self.doacao:
            link = f'<a href="{raiz}apoie/">{L("Apoie com uma doação única")}</a>'
            apoio = f'<p class="rodape__apoie">{L("O Voto de Verdade é gratuito. {0}, sem assinatura.", link)}</p>'
        botao = ""
        if self.doacao:
            botao = (f'<a class="apoie-topo" href="{raiz}apoie/" aria-label="{esc(L("Apoie o Voto de Verdade com uma doação única"))}"><svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" '
                     'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/></svg>'
                     f'<span class="apoie-topo__txt">{L("Apoie")}</span></a>')
        item_menu = ""
        if self.doacao:
            item_menu = (f'<li><a class="menu-apoie" href="{raiz}apoie/"><svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" '
                         'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/></svg>'
                         f'{L("Apoie com uma doação")}</a></li>')
        seletor_topo = seletor_menu = ""
        if len(self.idiomas) > 1 and not noindex:
            seletor_topo = self.seletor_idioma(caminho)
            seletor_menu = self.seletor_idioma(caminho, menu=True)
        for marca, conteudo in (("APOIO-MENU", item_menu + seletor_menu), ("APOIO-TOPO", botao), ("IDIOMA-TOPO", seletor_topo), ("APOIO", apoio)):
            ini, fim = pagina.index(f"<!--INICIO-{marca}-->"), pagina.index(f"<!--FIM-{marca}-->")
            pagina = pagina[:ini] + conteudo + pagina[fim + len(f"<!--FIM-{marca}-->"):]
        trocas = [
            ('href="fontes/', f'href="{ativos}fontes/'),
            ('href="estilos.css"', f'href="{ativos}estilos.css{self.versao("estilos.css")}"'),
            ('src="app.js"', f'src="{ativos}app.js{self.versao("app.js")}"'),
            ('src="tema.js"', f'src="{ativos}tema.js{self.versao("tema.js")}"'),
            ('class="marca" href="#/"', f'class="marca" href="{raiz or "./"}"'),
            ('id="nav-assuntos" href="#/"', f'id="nav-assuntos" href="{raiz or "./"}"'),
            ('id="nav-deputados" href="#/deputados"', f'id="nav-deputados" href="{raiz}deputados/"'),
            ('id="nav-numeros" href="#/em-numeros"', f'id="nav-numeros" href="{raiz}em-numeros/"'),
            ('id="menu-numeros" href="#/em-numeros"', f'id="menu-numeros" href="{raiz}em-numeros/"'),
            ('id="nav-ia" href="#/inteligencia-artificial"', f'id="nav-ia" href="{raiz}inteligencia-artificial/"'),
            ('id="menu-ia" href="#/inteligencia-artificial"', f'id="menu-ia" href="{raiz}inteligencia-artificial/"'),
            ('id="menu-assuntos" href="#/"', f'id="menu-assuntos" href="{raiz or "./"}"'),
            ('id="menu-deputados" href="#/deputados"', f'id="menu-deputados" href="{raiz}deputados/"'),
            ('<a href="#/sobre">', f'<a href="{raiz}sobre/">'),
            ('<a href="#/inteligencia-artificial">', f'<a href="{raiz}inteligencia-artificial/">'),
            ('<script type="application/json" id="config">{"raiz":""}</script>',
             '<script type="application/json" id="config">'
             + json.dumps({"raiz": ativos, "rota": rota, "doacao": self.doacao, "servico": self.servico, **({"lang": L.codigo, "dic": self.versoes.get("idiomas/en.json", "")} if L.en else {})},
                          ensure_ascii=False).replace("</", "<\\/")
             + "</script>"),
        ]
        if L.en:
            # os textos fixos do modelo passam pelo dicionário (antes de as trocas acima mexerem nos links)
            pagina = pagina.replace('<html lang="pt-BR">', f'<html lang="{L.html}">', 1)
            for antes, texto, depois in TEXTOS_DO_MODELO:
                velho = antes + texto + depois
                if velho not in pagina:
                    sys.exit(f"ERRO: o modelo index.html não tem {velho!r}")
                pagina = pagina.replace(velho, antes + L(texto) + depois)
        for velho, novo in trocas:
            if velho not in pagina:
                sys.exit(f"ERRO: o modelo index.html não tem {velho!r}")
            pagina = pagina.replace(velho, novo)
        self.escrever(os.path.join(caminho, "index.html") if caminho else "index.html", pagina)
        if markdown and not noindex:
            self.escrever(os.path.join(caminho, "index.md") if caminho else "index.md", markdown)
        if not noindex and caminho:
            self.paginas.append(caminho)


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


def principios_html(L):
    """Os pontos fortes da tela inicial (os mesmos de app.js), já em HTML para quem lê sem JavaScript."""
    itens = []
    for caminhos, titulo, texto in PRINCIPIOS:
        paths = "".join(f'<path d="{d}"/>' for d in caminhos.split("|"))
        itens.append(
            '<li><span class="principios__icone"><svg class="icone" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + paths + '</svg></span>'
            f'<strong>{esc(L(titulo))}</strong><span class="principios__desc">{esc(L(texto))}</span></li>')
    return f'<ul class="principios" aria-label="{esc(L("O que diferencia o Voto de Verdade"))}">' + "".join(itens) + "</ul>"


def migalhas_ld(itens):
    """BreadcrumbList: itens = [(nome, url ou None)]."""
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, **({"item": u} if u else {})} for i, (n, u) in enumerate(itens)]}


def carregar_dados(site):
    """Os dados em português, como estão em site/dados."""
    projetos = carregar(site, "projetos.json")
    for p in projetos:  # ementa e pontos principais ficam num arquivo por projeto
        arq = os.path.join(site, "dados", "projetos", f'{p["id"]}.json')
        if os.path.exists(arq):
            with open(arq, encoding="utf-8") as f:
                p.update(json.load(f))
    return SimpleNamespace(
        projetos=projetos, votacoes=carregar(site, "votacoes.json"), deputados=carregar(site, "deputados.json"),
        assuntos=carregar(site, "assuntos.json"), meta=carregar(site, "meta.json"),
        painel=carregar(site, "painel.json") if os.path.exists(os.path.join(site, "dados", "painel.json")) else None)


def traduzir_dados(site, D, L):
    """Cópia dos dados com os campos traduzidos por cima (site/dados/en/*). O que falta fica em português."""
    if not L.en:
        return D
    en_assuntos = carregar(site, "en/assuntos.json", True)
    en_projetos = carregar(site, "en/projetos.json", True)
    en_votacoes = carregar(site, "en/votacoes.json", True)
    en_painel = carregar(site, "en/painel.json", True)
    projetos = []
    for p in D.projetos:
        q = dict(p, **en_projetos.get(str(p["id"]), {}))
        arq = os.path.join(site, "dados", "en", "projetos", f'{p["id"]}.json')
        if os.path.exists(arq):
            with open(arq, encoding="utf-8") as f:
                q.update(json.load(f))
        projetos.append(q)
    painel = None
    if D.painel:
        painel = json.loads(json.dumps(D.painel))
        nomes = en_painel.get("assuntos", {})
        for a in painel["assuntos"]:
            a["nome"] = nomes.get(a["slug"], a["nome"])
    return SimpleNamespace(
        projetos=projetos, votacoes=[dict(v, **en_votacoes.get(str(v["id"]), {})) for v in D.votacoes], deputados=D.deputados,
        assuntos=[dict(a, **en_assuntos.get(a["slug"], {})) for a in D.assuntos], meta=D.meta, painel=painel)


def gerar_idioma(site, g, D, L, URL, doacao):
    """Todas as páginas de um idioma. Devolve o número de deputados."""
    projetos, votacoes, deputados, assuntos, meta = D.projetos, D.votacoes, D.deputados, D.assuntos, D.meta
    nome_assunto = {a["slug"]: a["nome"] for a in assuntos}
    nome_dep = {d["id"]: d for d in deputados}
    por_projeto = {}
    for v in votacoes:
        por_projeto.setdefault(v["p"], []).append(v)
    pr_por_id = {p["id"]: p for p in projetos}
    fonte_aviso = L("Assunto e resumo são feitos por inteligência artificial e podem conter erros; o texto oficial de "
                    "cada projeto está sempre disponível no site da Câmara.")
    voto_nome = {"S": L("Sim"), "N": L("Não"), "A": L("Abstenção"), "O": L("Obstrução"), "P": L("Presidia a sessão")}
    camara = L("Câmara dos Deputados")
    migalha_voce = esc(L("Você está em"))
    lang_ld = L.html

    def link_projeto(pr, raiz):
        return f'<li><a href="{raiz}projeto/{pr["id"]}/">{esc(pr["titulo"])}</a></li>'

    def votos_da_votacao(vid):
        arq = os.path.join(site, "dados", "votacoes", f"{vid}.json")
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
            votos = L("Votação de {0} ({1}): {2}.", L.data(ult["d"]), L("aprovada") if ult["ap"] else L("rejeitada"), placar_texto(L, ult["s"]))
        else:
            votos = (L("Votação secreta: o voto de cada deputado não é divulgado.") if pr["tipo"] == "secreta" else
                     L("Votação simbólica: o resultado foi anunciado sem registrar o voto de cada deputado."))
        resumo = pr.get("resumo") or pr.get("ementa") or ""
        sufixo_desc = " " + L("Votação de {0}: {1}.", L.data(ult["d"]), placar_texto(L, ult["s"])) if ult else ""
        descricao = curto(resumo, max(60, 158 - len(sufixo_desc))) + sufixo_desc
        avisos = aviso_ia(L, pr)
        assunto = nome_assunto.get(pr["a"], "")

        # votos de cada deputado da última votação nominal, agrupados (links para as páginas dos deputados)
        grupos_html, grupos_md = "", ""
        if ult:
            por_cod = {}
            for dep_id, cod, partido in votos_da_votacao(ult["id"]):
                d = nome_dep.get(dep_id)
                por_cod.setdefault(cod, []).append((d["nome"] if d else L("Deputado {0}", dep_id), dep_id, partido or (d or {}).get("partido", "")))
            partes_h, partes_m = [], []
            for cod in "SNAOP":
                lista = sorted(por_cod.get(cod, []), key=lambda x: x[0])
                if not lista:
                    continue
                partes_h.append(f'<h3>{voto_nome[cod]} ({len(lista)})</h3><p>' + ", ".join(
                    f'<a href="{raiz}deputado/{i}/">{esc(n)}</a>' + (f' ({esc(p)})' if p else "") for n, i, p in lista) + "</p>")
                partes_m.append(f"### {voto_nome[cod]} ({len(lista)})\n\n" + "; ".join(
                    f"[{n}]({URL}/{L.prefixo}deputado/{i}/)" + (f" ({p})" if p else "") for n, i, p in lista) + "\n")
            grupos_html = f'<details><summary>{L("Lista de deputados por voto")}</summary>' + "".join(partes_h) + "</details>"
            grupos_md = "\n".join(partes_m)

        # Pontos principais e texto oficial: logo depois do resumo, como no aplicativo (some sem JavaScript só se não houver nada)
        pontos = [x for x in (pr.get("pontos") or []) if x]
        link_oficial = so_https(pr.get("texto"))
        nota_oficial = L("O texto oficial está em português, como foi votado.")
        blocos_det = []
        if pontos:
            blocos_det.append(f"<div><h3>{L('Pontos principais')}</h3><ul>" + "".join(f"<li>{esc(x)}</li>" for x in pontos) + "</ul></div>")
        blocos_det.append(f'<div><h3>{L("Texto oficial ({0})", esc(pr["nome"]))}</h3>'
                          + (f'<p class="nota">{esc(nota_oficial)}</p>' if L.en else "")
                          + f'<p class="oficial"{" lang=\"pt-BR\"" if L.en else ""}>{esc(pr.get("ementa") or L("Sem ementa."))}</p>'
                          + (f'<p><a href="{esc(link_oficial)}" target="_blank" rel="noopener noreferrer">{L("Ler o texto completo no site da Câmara")}</a></p>' if link_oficial else "")
                          + "</div>")
        detalhes_html = (f'<details class="ajuda ajuda--solta"><summary>{L("Pontos principais e texto oficial")}</summary>'
                         '<div class="projeto__corpo">' + "".join(blocos_det) + "</div></details>")
        corpo = (
            '<div class="miolo pagina-projeto">'
            f'<nav class="migalhas" aria-label="{migalha_voce}"><ol><li><a href="{raiz}">{L("Assuntos")}</a></li>'
            f'<li><a href="{raiz}assunto/{pr["a"]}/">{esc(assunto)}</a></li><li aria-current="page">{esc(pr["nome"])}</li></ol></nav>'
            f'<header class="cabeca-projeto"><h1>{esc(titulo_completo(L, pr))}</h1>'
            f'<p class="cabeca-projeto__meta">{esc(pr["nome"])} · {L("última votação em {0}", L.data(pr["ultima"]))}</p></header>'
            f'<div class="resumo-projeto"><p>{esc(resumo)}</p></div>'
            + "".join(f'<p class="nota">{esc(a)}</p>' for a in avisos)
            + detalhes_html
            + f'<section class="bloco"><h2>{L("Como cada deputado votou")}</h2><p class="nota">{esc(votos)}</p>{grupos_html}</section>'
            f'<p class="nota">{L("Assunto")}: <a href="{raiz}assunto/{pr["a"]}/">{esc(assunto)}</a>. {esc(fonte_aviso)} <a href="{raiz}inteligencia-artificial/">{L("Como a inteligência artificial é usada")}</a></p>'
            + "</div>")

        md = [f"# {pr['titulo']}", "",
              f"- {L('Projeto')}: {pr['nome']}",
              f"- {L('Assunto')}: [{assunto}]({URL}/{L.prefixo}assunto/{pr['a']}/)",
              f"- {L('Última votação')}: {L.data(pr['ultima'])}",
              f"- {L('Página')}: {URL}/{L.prefixo}projeto/{pr['id']}/"]
        if pr.get("texto"):
            md.append(f"- {L('Texto oficial')}: {pr['texto']}" + (f" ({nota_oficial})" if L.en else ""))
        md += ["", f"## {L('Resumo')}", "", resumo, ""]
        md += [f"> {L('Aviso')}: {a}" for a in avisos] + ([""] if avisos else [])
        if pr.get("pontos"):
            md += [f"## {L('Pontos principais')}", ""] + [f"- {p}" for p in pr["pontos"]] + [""]
        md += [f"## {L('Votações')}", ""]
        for v in minhas:
            tipo = {"nominal": L("nominal (voto de cada deputado registrado)"), "simbolica": L("simbólica (sem o voto de cada deputado)"),
                    "secreta": L("secreta")}.get(v["t"], v["t"])
            md.append(L("- {0}: {1}, votação {2}.", L.data(v["d"]), L("aprovada") if v["ap"] else L("rejeitada"), tipo)
                      + (" " + L("Placar: {0}.", placar_texto(L, v["s"])) if v.get("s") else "") + (f" {v['desc']}" if v.get("desc") else ""))
        if grupos_md:
            md += ["", f"## {L('Como cada deputado votou')} ({L.data(ult['d'])})", "", grupos_md]
        md += ["", "---", fonte_aviso + " " + L("Como a inteligência artificial é usada: {0}. Sem nota e sem ranking.", f"{URL}/{L.prefixo}inteligencia-artificial/")]
        ld = {"@context": "https://schema.org", "@graph": [
            {"@type": "Legislation", "name": pr["titulo"], "legislationIdentifier": pr["nome"], "description": curto(resumo, 300),
             "inLanguage": lang_ld, "legislationJurisdiction": "BR", "url": f"{URL}/{L.prefixo}projeto/{pr['id']}/",
             "dateModified": pr["ultima"], **({"sameAs": pr["texto"]} if pr.get("texto") else {}),
             "about": assunto, "publisher": {"@type": "GovernmentOrganization", "name": camara}},
            migalhas_ld([(L("Assuntos"), URL + "/" + L.prefixo), (assunto, f"{URL}/{L.prefixo}assunto/{pr['a']}/"), (pr["nome"], None)])]}
        g.montar(f'projeto/{pr["id"]}', f'projeto/{pr["id"]}', titulo_projeto_seo(pr["nome"], pr["titulo"], NOME), descricao, corpo,
                 estruturados=ld, markdown="\n".join(md) + "\n")

    # ---- deputados
    n_dep = 0
    por_id_votacao = {v["id"]: v for v in votacoes}
    for d in deputados:
        arq = os.path.join(site, "dados", "deputados", f'{d["id"]}.json')
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
            nominais_txt = L("{0} votação nominal", n_vot) if n_vot == 1 else L("{0} votações nominais", n_vot)
            resumo = L("Votou em {0}, de {1} a {2}: {3} sim e {4} não.", nominais_txt, L.data(meta["de"]), L.data(meta["ate"]), total.get("S", 0), total.get("N", 0))
            resumo_curto = L("Votou em {0}: {1} sim e {2} não.", nominais_txt, total.get("S", 0), total.get("N", 0))
        else:
            resumo = resumo_curto = L("Sem voto registrado nas votações nominais do período.")
        descricao = curto(L("Veja como {0} ({1}) votou na Câmara. {2} Sem nota e sem ranking.", d["nome"], sigla, resumo_curto), 160)
        ordenados = sorted(((por_id_votacao[vid], cod) for vid, cod in votos_dep if vid in por_id_votacao),
                           key=lambda x: x[0]["d"], reverse=True)
        recentes, vistos, md_votos = [], set(), []
        for v, cod in ordenados:
            pr = pr_por_id.get(v["p"])
            if not pr:
                continue
            md_votos.append(L("- {0}: **{1}** em [{2}]({3}) ({4})", L.data(v["d"]), voto_nome[cod], pr["titulo"], f"{URL}/{L.prefixo}projeto/{pr['id']}/", pr["nome"]))
            if pr["id"] not in vistos and len(recentes) < 12:
                vistos.add(pr["id"])
                recentes.append(link_projeto(pr, "../../"))
        corpo = (
            '<div class="miolo">'
            f'<nav class="migalhas" aria-label="{migalha_voce}"><ol><li><a href="../../deputados/">{L("Deputados")}</a></li><li aria-current="page">{esc(d["nome"])}</li></ol></nav>'
            f'<header class="cabeca-dep"><div><h1>{esc(d["nome"])}</h1><p class="cabeca-dep__sub">{esc(sigla)}</p></div></header>'
            f'<section><h2>{L("Votos registrados")}</h2><p class="nota">{esc(resumo)}</p></section>'
            + (f'<section class="bloco"><h2>{L("Votações recentes")}</h2><ul>{"".join(recentes)}</ul></section>' if recentes else "")
            + "</div>")
        md = [f"# {d['nome']}", "", f"- {L('Partido e estado')}: {sigla}",
              f"- {L('Situação')}: {L('em exercício') if d.get('ex') else L('não está em exercício agora')}",
              f"- {L('Página')}: {URL}/{L.prefixo}deputado/{d['id']}/", "", f"## {L('Votos registrados')}", "", resumo, ""]
        if md_votos:
            md += [f"## {L('Como votou (votações nominais, da mais recente para a mais antiga)')}", ""] + md_votos + [""]
        md += ["---", L("Votar sim ou não numa votação não diz, sozinho, se o deputado apoia o assunto do projeto. Sem nota e sem ranking.")]
        pessoa = {"@type": "Person", "name": d["nome"],
                  **({"jobTitle": L("Deputado Federal"), "worksFor": {"@type": "GovernmentOrganization", "name": camara}} if d.get("ex") else {}),
                  **({"memberOf": {"@type": "Organization", "name": d["partido"]}} if d.get("partido") else {})}
        ld = {"@context": "https://schema.org", "@graph": [
            {"@type": "ProfilePage", "url": f"{URL}/{L.prefixo}deputado/{d['id']}/", "name": d["nome"], "inLanguage": lang_ld, "mainEntity": pessoa},
            migalhas_ld([(L("Deputados"), f"{URL}/{L.prefixo}deputados/"), (d["nome"], None)])]}
        g.montar(f'deputado/{d["id"]}', f'deputado/{d["id"]}', titulo_deputado_seo(L, d["nome"], sigla, NOME), descricao, corpo,
                 estruturados=ld, markdown="\n".join(md) + "\n")
        n_dep += 1

    # ---- assuntos
    aviso_simbolica = L("Votação simbólica: os partidos chegam a um acordo e o resultado é anunciado sem registrar o voto de cada deputado.") + " "
    for a in assuntos:
        todos = sorted((p for p in projetos if p["a"] == a["slug"] or p["s"] == a["slug"]),
                       key=lambda p: (p["ind"], p["ultima"] or ""), reverse=True)
        meus = todos[:150]
        desc_a = maiuscula(a["descricao"])
        descricao = curto(L("{0}. {1} projetos votados na Câmara dos Deputados, {2} com o voto de cada deputado. Sem nota e sem ranking.",
                            desc_a, a["n"], a["n_ind"]), 160)
        corpo = (
            '<div class="miolo">'
            f'<nav class="migalhas" aria-label="{migalha_voce}"><ol><li><a href="../../">{L("Assuntos")}</a></li><li aria-current="page">{esc(a["nome"])}</li></ol></nav>'
            f'<header class="cabeca-assunto"><h1>{esc(a["nome"])}</h1><p>{esc(desc_a)}.</p></header>'
            f'<p class="nota">{aviso_simbolica}'
            f'{L("Só nos projetos com voto de cada deputado dá para ver como cada um votou.")}</p>'
            f'<ul class="projetos">{"".join(link_projeto(p, "../../") for p in meus)}</ul></div>')
        md = [f"# {a['nome']}", "", f"{desc_a}.", "",
              L("{0} projetos votados na Câmara dos Deputados; {1} com o voto de cada deputado registrado.", a["n"], a["n_ind"]), "",
              f"## {L('Projetos')}", ""]
        md += [f"- [{p['titulo']}]({URL}/{L.prefixo}projeto/{p['id']}/) ({p['nome']}, {L.data(p['ultima'])}"
               + (", " + L("com voto de cada deputado") if p["ind"] else "") + ")" for p in todos]
        md += ["", "---", aviso_simbolica + L("Sem nota e sem ranking.")]
        ld = {"@context": "https://schema.org", "@graph": [
            {"@type": "CollectionPage", "name": f'{a["nome"]}: {NOME}', "url": f"{URL}/{L.prefixo}assunto/{a['slug']}/", "inLanguage": lang_ld,
             "description": descricao,
             "mainEntity": {"@type": "ItemList", "numberOfItems": len(todos), "itemListElement": [
                 {"@type": "ListItem", "position": i + 1, "url": f"{URL}/{L.prefixo}projeto/{p['id']}/", "name": p["titulo"]} for i, p in enumerate(meus)]}},
            migalhas_ld([(L("Assuntos"), URL + "/" + L.prefixo), (a["nome"], None)])]}
        g.montar(f'assunto/{a["slug"]}', f'assunto/{a["slug"]}', f'{a["nome"]}: {NOME}', descricao, corpo,
                 estruturados=ld, markdown="\n".join(md) + "\n")

    # ---- lista de deputados (todos, por estado) e como funciona
    por_uf = {}
    for d in sorted(deputados, key=lambda x: x["nome"]):
        por_uf.setdefault(d.get("uf") or "—", []).append(d)
    corpo = (f'<div class="miolo"><nav class="migalhas" aria-label="{migalha_voce}"><ol><li><a href="../">{L("Início")}</a></li><li aria-current="page">{L("Deputados")}</li></ol></nav>'
             f'<h1>{L("Deputados federais")}</h1><p class="nota">{L("Escolha um deputado para ver como ele votou. Sem nota e sem ranking.")}</p>'
             + "".join(f'<section><h2>{esc(uf)}</h2><ul>' + "".join(
                 f'<li><a href="../deputado/{d["id"]}/">{esc(d["nome"])}</a> ({esc(d.get("partido") or "")})</li>' for d in lista)
                 + "</ul></section>" for uf, lista in sorted(por_uf.items())) + "</div>")
    md = [f"# {L('Deputados federais')}", "", L("{0} deputados com voto registrado ou em exercício no período. Sem nota e sem ranking.", len(deputados)), ""]
    for uf, lista in sorted(por_uf.items()):
        md += [f"## {uf}", ""] + [f"- [{d['nome']}]({URL}/{L.prefixo}deputado/{d['id']}/) ({d.get('partido') or ''})" for d in lista] + [""]
    g.montar("deputados", "deputados", L("Deputados federais: {0}", NOME),
             L("Procure um deputado federal pelo nome ou pelo estado e veja como ele votou na Câmara dos Deputados. Sem nota e sem ranking."),
             corpo, markdown="\n".join(md) + "\n",
             estruturados={"@context": "https://schema.org", "@type": "CollectionPage", "name": L("Deputados federais"),
                           "url": f"{URL}/{L.prefixo}deputados/", "inLanguage": lang_ld})

    pct_simbolicas_int = round(100 * meta["simbolicas"] / meta["votacoes"])
    objetivos = [
        L("Mostrar o que cada deputado votou, em linguagem simples, sem nota e sem ranking."),
        L("Organizar os projetos por assunto, para você achar o que importa para a sua vida."),
        L("Ser neutro e apartidário, sem dizer quem votou certo ou errado."),
        L("Deixar sempre o texto oficial ao lado do resumo, e avisar quando a inteligência artificial tem dúvida."),
        L("Ser gratuito, sem anúncios e sem rastrear quem visita, com código aberto."),
    ]
    sobre = [
        (L("Versão Beta, em constante desenvolvimento"),
         L("O Voto de Verdade é uma versão beta e está em constante desenvolvimento. Pode ter erros, e o que ele mostra e a forma como funciona podem mudar. Em caso de dúvida, confira no texto oficial da Câmara. "
           "Queremos aproximar a sociedade do Congresso, com transparência e visibilidade sobre a atuação parlamentar, de forma simples e prática. Para isso, o site busca:"), objetivos),
        (L("Neutro e apartidário, sem nota e sem ranking"),
         L("O Voto de Verdade não dá nota, não faz ranking e não diz quem votou certo ou errado. Mostra o que cada deputado votou. "
           "Votar sim ou não numa votação não diz, sozinho, se o deputado apoia o assunto do projeto: muitas votações são sobre emendas, substitutivos ou pontos separados do texto.")),
        (L("De onde vêm os dados"),
         L("Do portal de Dados Abertos da Câmara dos Deputados. O site mostra {0} votações em plenário, de {1} a {2}, e é atualizado todos os dias.",
           meta["votacoes"], L.data(meta["de"]), L.data(meta["ate"]))),
        (L("Só a Câmara dos Deputados, por enquanto"),
         L("O site cobre os deputados federais. O Senado, as assembleias estaduais e as câmaras de vereadores não estão aqui.")),
        (L("Quais votações o site mostra"),
         L("Um projeto costuma passar por várias votações no plenário. Aqui entram só as que decidem sobre o projeto em si, isto é, aprovar ou rejeitar. "
           "Ficam de fora as votações de urgência (que só decidem se o projeto anda mais rápido), de requerimentos, de emendas ou destaques isolados (que votam a mudança de um trecho) e de procedimento. "
           "Por isso um projeto que foi votado muitas vezes pode aparecer com uma só votação. "
           "Às vezes a Câmara vota um substitutivo, um texto novo que troca o original. Essa votação aparece, com um aviso: o resumo foi feito a partir da ementa do projeto original, e o texto votado pode ser diferente.")),
        (L("Números e dados para baixar"),
         L("A tela Em números mostra as votações ao longo do tempo, por assunto e por resultado, quantos deputados votaram e o placar das votações nominais, com filtro por ano. "
           "Cada bloco de números e as listas de projetos, deputados e votos têm botões para baixar o que está na tela em CSV (que abre em planilha) ou em JSON, já com o filtro aplicado. "
           "Ao usar os dados, cite o Voto de Verdade e a Câmara dos Deputados.")),
        (L("Assunto e resumo são feitos por inteligência artificial"),
         L("Uma inteligência artificial lê o texto oficial de cada projeto, escolhe o assunto e escreve um resumo em linguagem simples. Ela pode errar. Quando há dúvida, o projeto mostra um aviso. "
           "Ninguém revisa os resumos antes de irem ao ar, e por enquanto o site não tem um canal para pedir correções. Se algo parecer estranho, confira no texto oficial."), None, True),
        (L("Por que nem todo projeto mostra o voto de cada deputado"),
         L("{0} das {1} votações ({2}%) foram simbólicas: os partidos chegam a um acordo e o resultado é anunciado sem registrar o voto de cada deputado.",
           meta["simbolicas"], meta["votacoes"], pct_simbolicas_int)),
        (L("Licença e uso do conteúdo"),
         L("O código do site é aberto, com licença MIT. Os textos do site e os resumos feitos por inteligência artificial podem ser copiados e usados por qualquer pessoa, inclusive em matérias, desde que citem o Voto de Verdade e o endereço votodeverdade.com.br (licença CC BY 4.0). Os dados originais são da Câmara dos Deputados, que tem as próprias regras. "
           "Pedimos que o conteúdo não seja usado para treinar modelos de inteligência artificial. Consultá-lo para responder perguntas, citando o site, é bem-vindo.")),
        (L("Quem faz e privacidade"),
         L("O Voto de Verdade é um site independente, sem ligação com a Câmara dos Deputados, com partidos ou com candidatos. Não usa cookies nem ferramentas que rastreiam quem visita.")),
    ]

    def itens_sobre(s):
        return s[2] if len(s) > 2 else None

    def com_link_ia(s):
        return len(s) > 3 and s[3]

    link_ia = L("Veja como a inteligência artificial é usada, com os números")
    corpo = (f'<div class="miolo texto-longo"><nav class="migalhas" aria-label="{migalha_voce}"><ol><li><a href="../">{L("Início")}</a></li><li aria-current="page">{L("Como o site funciona")}</li></ol></nav>'
             f'<h1>{L("Como o site funciona")}</h1>'
             + "".join(f"<h2>{esc(s[0])}</h2><p>{esc(s[1])}</p>" + (("<ul>" + "".join(f"<li>{esc(i)}</li>" for i in itens_sobre(s)) + "</ul>") if itens_sobre(s) else "")
                       + (f'<p><a href="../inteligencia-artificial/">{link_ia}</a></p>' if com_link_ia(s) else "")
                       for s in sobre)
             + "</div>")
    g.montar("sobre", "sobre", L("Como o site funciona: {0}", NOME),
             L("Neutro e apartidário, sem nota e sem ranking. De onde vêm os dados, como a inteligência artificial é usada e o que o site não faz."),
             corpo, markdown=f"# {L('Como o site funciona')}\n\n" + "\n\n".join(f"## {s[0]}\n\n{s[1]}" + (("\n\n" + "\n".join(f"- {i}" for i in itens_sobre(s))) if itens_sobre(s) else "")
                                                   + (f"\n\n[{link_ia}]({URL}/{L.prefixo}inteligencia-artificial/)" if com_link_ia(s) else "") for s in sobre) + "\n",
             estruturados={"@context": "https://schema.org", "@type": "AboutPage", "name": L("Como o site funciona"),
                           "url": f"{URL}/{L.prefixo}sobre/", "inLanguage": lang_ld})

    # ---- Em números (as colunas e barras aparecem quando o aplicativo abre; aqui ficam os textos e, em páginas próprias, as tabelas)
    pn = D.painel
    if pn:
        tp = pn["totais"]
        pa, pl, ia = pn.get("participacao") or {}, pn.get("placar") or {}, pn.get("ia") or {}

        def n_br(n):
            return L.milhar(n)

        def pct(a, b):
            if not b:
                return "0%"
            return L.decimal(f"{100 * a / b:.1f}").removesuffix(".0" if L.en else ",0") + "%"

        nomes_tipo = {"nominal": L("Nominais"), "simbolica": L("Simbólicas"), "secreta": L("Secretas")}
        votos_placar = [("S", L("Sim")), ("N", L("Não")), ("A", L("Abstenção")), ("O", L("Obstrução"))]
        faixas = [("sem_contra", L("Sem voto contrário"), L("só houve votos de um lado")), ("ampla", L("Ampla"), L("diferença de 50% ou mais")),
                  ("maioria", L("Maioria"), L("diferença de 15% a 50%")), ("apertada", L("Apertada"), L("diferença de menos de 15%"))]
        niveis = [("alta", L("Alta")), ("media", L("Média")), ("baixa", L("Baixa"))]
        nome_modelo = {"claude-sonnet-5-5": "Claude Sonnet 5.5", "claude-haiku-4-5-20251001": "Claude Haiku 4.5"}

        # Uma tabela por página própria: id -> (título, cabeçalho, linhas). Os mesmos ids e números do aplicativo.
        # Cada tabela é filha de uma tela: Em números (padrão) ou Transparência da IA.
        pai_da_tabela = {"confianca": "inteligencia-artificial"}
        nome_do_pai = {"em-numeros": L("Em números"), "inteligencia-artificial": L("Transparência da IA")}
        tabelas = {
            "por-mes": (L("Votações por mês"), [L("Mês"), L("Nominais"), L("Simbólicas"), L("Secretas")],
                        [[L.mes_ano(m["m"]), n_br(m["n"]), n_br(m["s"]), n_br(m["x"])] for m in pn["meses"]]),
            "por-assunto": (L("Votações por assunto"), [L("Assunto"), L("Nominais"), L("Simbólicas"), L("Secretas"), L("Total")],
                            [[a["nome"], n_br(a["n"]), n_br(a["s"]), n_br(a["x"]), n_br(a["n"] + a["s"] + a["x"])] for a in pn["assuntos"]]),
            "resultado": (L("Resultado por tipo de votação"), [L("Tipo"), L("Aprovadas"), L("Rejeitadas"), L("Total")],
                          [[nomes_tipo[k], n_br(r["aprovadas"]), n_br(r["rejeitadas"]), n_br(r["aprovadas"] + r["rejeitadas"])] for k, r in pn["resultado"].items()]),
        }
        if pa.get("votacoes"):
            tabelas["participacao"] = (L("Deputados que votaram, por mês"), [L("Mês"), L("Votações nominais"), L("Deputados que votaram (média)")],
                                       [[L.mes_ano(m["m"]), n_br(m["n"]), n_br(m["v"]) if m["n"] else L("sem votação nominal")] for m in pa["meses"]])
        if pl.get("nominais"):
            soma_votos = sum(pl["votos"][c] for c, _ in votos_placar)
            tabelas["placar-votos"] = (L("Votos nas votações nominais"), [L("Voto"), L("Total"), L("Parte do total")],
                                       [[nome, n_br(pl["votos"][c]), pct(pl["votos"][c], soma_votos)] for c, nome in votos_placar])
            tabelas["placar-margem"] = (L("Votações nominais por tamanho da diferença"), [L("Faixa"), L("Como é medida"), L("Votações"), L("Parte das nominais")],
                                        [[nome, det, n_br(pl["margem"][k]), pct(pl["margem"][k], pl["nominais"])] for k, nome, det in faixas])
        if ia.get("projetos"):
            tabelas["confianca"] = (L("Confiança da inteligência artificial"), [L("Confiança"), L("Assunto"), L("Resumo")],
                                    [[nome, n_br(ia["assunto"][k]), n_br(ia["resumo"][k])] for k, nome in niveis])

        def ver_tabela(id_, sobre):
            return f'<p class="numeros__tabela"><a href="{id_}/">{L("Ver como tabela")}<span class="so-leitor"> {esc(sobre)}</span></a></p>'

        pct_simbolicas = pct(tp["simbolicas"], tp["votacoes"])
        secretas_txt = L("{0} secreta", tp["secretas"]) if tp["secretas"] == 1 else L("{0} secretas", tp["secretas"])
        lead = L("{0} votações em plenário, de {1} a {2}: {3} nominais, {4} simbólicas e {5}.",
                 tp["votacoes"], L.data(pn["de"]), L.data(pn["ate"]), tp["nominais"], tp["simbolicas"], secretas_txt)
        nota = L("Atualizado em {0}. Esta página só conta e descreve: não dá nota nem compara deputados ou partidos.", L.data(pn["gerado_em"]))
        txt_part = txt_placar = txt_ia = None
        if pa.get("votacoes"):
            txt_part = L("Só nas votações nominais, que registram o voto de cada deputado. A Câmara tem {0} deputados e, em média, {1} registraram voto em cada votação nominal "
                         "(de {2} a {3}). O site não sabe o motivo de quem não aparece (falta, licença ou outro). Aqui entra só o total de cada votação, nunca quem faltou.",
                         pa["cadeiras"], n_br(pa["media"]), n_br(pa["minimo"]), n_br(pa["maximo"]))
        if pl.get("nominais"):
            txt_placar = L("Somando todas as votações nominais, quantos votos foram sim, não, abstenção ou obstrução. Votar sim ou não não diz, sozinho, se o deputado apoia o assunto do projeto: "
                           "muitas votações são sobre emendas, substitutivos ou pontos separados do texto.")
        txt_margem = L("A diferença é a distância entre sim e não, dividida pelo total de sim e não. Cada uma das {0} votações nominais cai em uma faixa.", pl.get("nominais", 0))
        if ia.get("projetos"):
            m1 = f' ({nome_modelo.get(ia["modelo"], ia["modelo"])})' if ia.get("modelo") else ""
            m2 = f' ({nome_modelo.get(ia["conferencia"], ia["conferencia"])})' if ia.get("conferencia") else ""
            txt_ia = True
            passos = [L("Um modelo{0} lê o texto oficial do projeto, escolhe o assunto, escreve o resumo e diz quanto tem de certeza.", m1),
                      L("Um segundo modelo{0} escolhe o assunto sem ver a resposta do primeiro. Se os dois discordam, a confiança no assunto cai.", m2),
                      L("Uma checagem por palavras da ementa confere se o assunto faz sentido."),
                      L("O segundo modelo confere o resumo contra o texto original. Se achar partes sem apoio no texto, o projeto mostra um aviso. Se o resumo não se sustenta, ele é descartado e a tela mostra só a ementa.")]

            def pl_(n, um, varios):
                return f"{n_br(n)} {um if n == 1 else varios}"
            projeto_s = (L("projeto"), L("projetos"))
            avisos = [L("{0} com aviso de que o assunto pode estar errado.", pl_(ia["aviso_assunto"], *projeto_s)),
                      L("{0} com aviso de que o resumo pode conter erros.", pl_(ia["aviso_resumo"], *projeto_s))]
            if ia["so_ementa"]:
                avisos.append(L("{0} sem resumo da inteligência artificial, porque ela não conseguiu resumir ou a conferência não achou apoio no texto. A tela mostra só a ementa.",
                                pl_(ia["so_ementa"], *projeto_s)))
            avisos.append(L("{0} cuja votação foi sobre um substitutivo ou emenda: o texto votado pode ser diferente da ementa.", pl_(ia["texto_pode_diferir"], *projeto_s)))
            if ia["votacao_aviso"]:
                avisos.append(L("{0} com aviso de que a classificação foi feita automaticamente e pode estar errada.", pl_(ia["votacao_aviso"], L("votação"), L("votações"))))
            limites = [L("A inteligência artificial pode errar, mesmo quando diz ter certeza."),
                       L("O texto oficial de cada projeto fica sempre ao lado do resumo. Em caso de dúvida, vale o texto oficial."),
                       L("Por enquanto o site não tem um canal para pedir correções.")]
            conf = lambda c, sem=0: " · ".join([f"{nome}: {n_br(c[k])} ({pct(c[k], sum(c.values()))})" for k, nome in niveis] + ([f"{L('Sem resumo')}: {n_br(sem)}"] if sem else []))
            ate_ia = L("Último texto gerado em {0}. O site só refaz o resumo de projetos novos ou cujo texto oficial mudou.", L.data(ia["ate"])) if ia.get("ate") else ""

        def bloco(titulo, *partes):
            return f'<section class="numeros__bloco"><h2>{esc(titulo)}</h2>' + "".join(partes) + "</section>"

        def nota_p(t):
            return f'<p class="numeros__nota">{esc(t)}</p>'

        como_funciona = L("Como o site funciona")
        migalhas_numeros = lambda atual: (f'<div class="miolo numeros"><nav class="migalhas" aria-label="{migalha_voce}"><ol><li><a href="../">{L("Início")}</a></li>'
                                          f'<li aria-current="page">{atual}</li></ol></nav>')
        corpo = (migalhas_numeros(L("Em números"))
                 + f'<h1>{L("Em números")}</h1><p class="numeros__lead">{esc(lead)}</p><p class="numeros__nota">{esc(nota)} <a href="../sobre/">{como_funciona}</a></p>'
                 + bloco(L("Votações nominais e simbólicas ao longo do tempo"),
                         nota_p(L("Na votação nominal, o voto de cada deputado fica registrado. Na simbólica, só o resultado. Meses sem votação (recesso, eleições) aparecem vazios.")),
                         ver_tabela("por-mes", L("das votações por mês")))
                 + bloco(L("Votações por assunto"),
                         nota_p(L("Cada votação conta uma vez, no assunto principal do projeto. Os assuntos são escolhidos por inteligência artificial e seguem sempre a mesma ordem, não a do tamanho.")),
                         ver_tabela("por-assunto", L("das votações por assunto")))
                 + bloco(L("Resultado das votações"),
                         nota_p(L("Cada votação termina aprovada ou rejeitada pelo plenário. Aprovar uma votação não quer dizer, sozinho, que o projeto virou lei.")),
                         nota_p(L("Nas votações simbólicas ({0} do total), os partidos chegam a um acordo antes e o resultado é apenas anunciado. Por isso a grande maioria das votações aparece como aprovada.", pct_simbolicas)),
                         ver_tabela("resultado", L("do resultado das votações")))
                 + (bloco(L("Quantos deputados votaram"), nota_p(txt_part), ver_tabela("participacao", L("da participação por mês"))) if txt_part else "")
                 + (bloco(L("Placar das votações nominais"), nota_p(txt_placar), ver_tabela("placar-votos", L("dos votos")),
                          f"<h3>{L('Votações decididas por pouco ou por muito')}</h3>", nota_p(txt_margem), ver_tabela("placar-margem", L("da diferença entre sim e não"))) if txt_placar else "")
                 + "</div>")
        md = [f"# {L('Em números')}", "", lead, "", nota, "", f"## {L('Votações nominais e simbólicas ao longo do tempo')}", ""]
        md += [f"- {L.mes_ano(m['m'])}: " + L("{0} nominais, {1} simbólicas", m["n"], m["s"]) + (", " + (L("{0} secreta", m["x"]) if m["x"] == 1 else L("{0} secretas", m["x"])) if m["x"] else "") for m in pn["meses"]]
        md += ["", f"## {L('Votações por assunto')}", ""]
        md += [f"- {a['nome']}: " + L("{0} nominais, {1} simbólicas", a["n"], a["s"]) + (", " + (L("{0} secreta", a["x"]) if a["x"] == 1 else L("{0} secretas", a["x"])) if a["x"] else "") for a in pn["assuntos"]]
        md += ["", f"## {L('Resultado das votações')}", "",
               L("Nas votações simbólicas ({0} do total), os partidos chegam a um acordo antes e o resultado é apenas anunciado. Por isso a grande maioria das votações aparece como aprovada.", pct_simbolicas), ""]
        md += [f"- {nomes_tipo[k]}: " + L("{0} aprovadas, {1} rejeitadas", r["aprovadas"], r["rejeitadas"]) for k, r in pn["resultado"].items()]
        if txt_part:
            md += ["", f"## {L('Quantos deputados votaram')}", "", txt_part]
        if txt_placar:
            md += ["", f"## {L('Placar das votações nominais')}", "", txt_placar, ""]
            md += [f"- {nome}: {n_br(pl['votos'][c])} ({pct(pl['votos'][c], soma_votos)})" for c, nome in votos_placar]
            md += ["", f"### {L('Votações decididas por pouco ou por muito')}", "", txt_margem, ""]
            md += [f"- {nome} ({det}): {pl['margem'][k]}" for k, nome, det in faixas]
        descricao_painel = L("Votações nominais e simbólicas ao longo do tempo, por assunto, resultado, participação e placar. Só números, sem nota e sem ranking.")
        g.montar("em-numeros", "em-numeros", L("Em números: votações da Câmara ao longo do tempo | {0}", NOME), descricao_painel,
                 corpo, markdown="\n".join(md) + "\n",
                 estruturados={"@context": "https://schema.org", "@type": "WebPage", "name": L("Em números"),
                               "url": f"{URL}/{L.prefixo}em-numeros/", "inLanguage": lang_ld, "dateModified": pn["gerado_em"]})

        # a página Transparência da IA (/inteligencia-artificial/)
        if txt_ia:
            fatos = [L("Escolhe o assunto de cada projeto."), L("Escreve o título e o resumo em linguagem simples e lista os pontos principais."),
                     L("Diz quanto tem de certeza e avisa quando tem dúvida.")]
            nao_faz = L("Ela não registra nem muda votos: o voto de cada deputado, a data e o resultado vêm direto dos Dados Abertos da Câmara. "
                        "Também não dá nota, não faz ranking e não compara deputados ou partidos.")
            lead_ia = L("O assunto e o resumo dos {0} projetos do site são feitos por inteligência artificial, e ninguém revisa esses textos antes de irem ao ar.", ia["projetos"])
            nota_ia = L("Atualizado em {0}. Aqui está o que ela faz, como o trabalho é conferido e onde pode errar.", L.data(pn["gerado_em"]))
            ul = lambda itens: '<ul class="numeros__fatos">' + "".join(f"<li>{esc(i)}</li>" for i in itens) + "</ul>"
            corpo_ia = (migalhas_numeros(L("Transparência da IA"))
                        + f'<h1>{L("Transparência da IA")}</h1><p class="numeros__lead">{esc(lead_ia)}</p><p class="numeros__nota">{esc(nota_ia)} <a href="../sobre/">{como_funciona}</a></p>'
                        + bloco(L("O que a inteligência artificial faz"), ul(fatos), nota_p(nao_faz))
                        + bloco(L("Como é feito"), '<ol class="numeros__passos">' + "".join(f"<li>{esc(p)}</li>" for p in passos) + "</ol>", nota_p(ate_ia) if ate_ia else "")
                        + bloco(L("Confiança de cada texto"),
                                nota_p(L("Cada assunto e cada resumo recebe uma confiança calculada por máquina, não por pessoas. Alta quer dizer que as conferências automáticas concordaram, não que o texto está certo.")),
                                nota_p(L("Assunto") + ". " + conf(ia["assunto"])), nota_p(L("Resumo") + ". " + conf(ia["resumo"], ia["so_ementa"])),
                                ver_tabela("confianca", L("da confiança")))
                        + bloco(L("Avisos que o site mostra"), ul(avisos))
                        + bloco(L("Limites e correções"), ul(limites))
                        + "</div>")
            md_ia = [f"# {L('Transparência da IA')}", "", lead_ia, "", nota_ia, "", f"## {L('O que a inteligência artificial faz')}", ""] + [f"- {f}" for f in fatos] + ["", nao_faz,
                     "", f"## {L('Como é feito')}", ""] + [f"{i}. {p}" for i, p in enumerate(passos, 1)] + ["", ate_ia, "", f"## {L('Confiança de cada texto')}", "",
                     "- " + L("Assunto") + ". " + conf(ia["assunto"]), "- " + L("Resumo") + ". " + conf(ia["resumo"], ia["so_ementa"]),
                     "", f"## {L('Avisos que o site mostra')}", ""] + [f"- {a}" for a in avisos] + ["", f"## {L('Limites e correções')}", ""] + [f"- {l}" for l in limites]
            g.montar("inteligencia-artificial", "inteligencia-artificial", L("Transparência da IA: como a inteligência artificial é usada | {0}", NOME),
                     L("O que a inteligência artificial faz no site, como o trabalho é conferido, a confiança de cada texto e onde ela pode errar."),
                     corpo_ia, markdown="\n".join(md_ia) + "\n",
                     estruturados={"@context": "https://schema.org", "@type": "WebPage", "name": L("Transparência da IA"),
                                   "url": f"{URL}/{L.prefixo}inteligencia-artificial/", "inLanguage": lang_ld, "dateModified": pn["gerado_em"]})

        # uma página para cada tabela (/em-numeros/por-mes/, /inteligencia-artificial/confianca/ e as outras)
        for id_, (titulo_t, cab, linhas) in tabelas.items():
            pai = pai_da_tabela.get(id_, "em-numeros")
            linhas_html = "".join("<tr>" + "".join((f'<td class="num">{esc(str(c))}</td>' if k else f'<th scope="row">{esc(str(c))}</th>') for k, c in enumerate(l)) + "</tr>" for l in linhas)
            cab_html = "".join(f'<th scope="col"{" class=\"num\"" if k else ""}>{esc(c)}</th>' for k, c in enumerate(cab))
            nota_t = (L("Os mesmos números do gráfico, dos {0} projetos do site. Atualizado em {1}.", ia["projetos"], L.data(pn["gerado_em"])) if pai == "inteligencia-artificial"
                      else L("Os mesmos números do gráfico, de {0} a {1}. Atualizado em {2}.", L.data(pn["de"]), L.data(pn["ate"]), L.data(pn["gerado_em"])))
            corpo_t = (f'<div class="miolo numeros"><nav class="migalhas" aria-label="{migalha_voce}"><ol><li><a href="../../">{L("Início")}</a></li>'
                       f'<li><a href="../">{esc(nome_do_pai[pai])}</a></li><li aria-current="page">{esc(titulo_t)}</li></ol></nav><h1>{esc(titulo_t)}</h1>'
                       f'<p class="numeros__nota">{esc(nota_t)}</p>'
                       '<div class="numeros__bloco"><div class="tabela-rolavel"><table class="tabela-painel">'
                       f'<caption class="so-leitor">{esc(titulo_t)}</caption><thead><tr>{cab_html}</tr></thead><tbody>{linhas_html}</tbody></table></div>'
                       f'<p class="numeros__tabela"><a href="../">{L("Voltar para {0}", esc(nome_do_pai[pai]))}</a></p></div></div>')
            md_t = [f"# {titulo_t}", "", nota_t, "",
                    "| " + " | ".join(cab) + " |", "|" + " --- |" * len(cab)] + ["| " + " | ".join(str(c) for c in l) + " |" for l in linhas]
            g.montar(f"{pai}/{id_}", f"{pai}/{id_}", L("{0}: tabela | {1}", titulo_t, NOME),
                     L("Tabela com os números do gráfico «{0}».", titulo_t),
                     corpo_t, markdown="\n".join(md_t) + "\n",
                     estruturados={"@context": "https://schema.org", "@type": "WebPage", "name": titulo_t,
                                   "url": f"{URL}/{L.prefixo}{pai}/{id_}/", "inLanguage": lang_ld, "dateModified": pn["gerado_em"]})

    # ---- apoie (só quando há um link de doação em site/config.json)
    servico_doacao = (doacao.get("servico") or "").strip() or L("serviço de pagamento")
    if so_https(doacao.get("url")):
        sv = esc(servico_doacao)
        g.montar("apoie", "apoie", L("Apoie o {0}", NOME),
                 L("Faça uma doação única, sem assinatura, para manter o Voto de Verdade no ar. Doar não muda o que o site mostra: sem nota e sem ranking."),
                 f'<div class="miolo texto-longo"><h1>{L("Apoie o Voto de Verdade")}</h1>'
                 f'<p>{L("O Voto de Verdade é gratuito e não tem anúncios. Se ele foi útil para você, pode fazer uma doação no valor que quiser. Ela é única: o {0} oferece a opção de repetir todo mês, mas só vale se você marcar. Para doar, você não precisa preencher e-mail nem mensagem.", sv)}</p>'
                 f'<p><a href="{esc(doacao["url"])}" target="_blank" rel="noopener noreferrer">{L("Fazer uma doação")}</a></p>'
                 f'<p>{L("O {0} abre em outra aba. É outro site, com regras e política de privacidade próprias. Quem mantém o Voto de Verdade recebe de lá só o que você optar por informar e não vê os dados do seu cartão. O aviso de que não usamos cookies nem rastreio vale para este site, não para o {0}.", sv)}</p>'
                 f'<h2>{L("O que a doação não muda")}</h2>'
                 f'<p>{L("O site continua neutro e apartidário, sem nota e sem ranking. Quem doa não escolhe o que aparece, não ganha destaque e não influencia os resumos. Não é doação a uma associação ou ONG: o site é mantido por uma pessoa e a doação não dá direito a abatimento de imposto.")}</p>'
                 f'<h2>{L("Para onde vai o dinheiro")}</h2>'
                 f'<p>{L("Primeiro, para cobrir os custos do site: a inteligência artificial (que classifica os projetos por assunto, escreve os títulos e os resumos em linguagem simples, lista os pontos principais e avisa quando tem dúvida) e o endereço do site (domínio). O que sobrar ajuda a pagar o trabalho de desenvolvimento e manutenção, que é feito por uma pessoa só. Doar não muda nada no site: ele continua igual e gratuito para todos.")}</p></div>',
                 markdown=f"# {L('Apoie o Voto de Verdade')}\n\n{L('Doação única, sem assinatura: {0}', doacao['url'])}\n")

    # ---- página inicial (com o endereço de compartilhamento certo e o conteúdo já escrito)
    recentes = sorted((v for v in votacoes if v["t"] == "nominal"), key=lambda v: v["d"], reverse=True)
    vistos, lista_rec = set(), []
    for v in recentes:
        pr = pr_por_id.get(v["p"])
        if pr and pr["id"] not in vistos and len(lista_rec) < 6:
            vistos.add(pr["id"])
            lista_rec.append((pr, v))
    tempo = f'<time datetime="{meta["gerado_em"]}">{L.data(meta["gerado_em"])}</time>'
    corpo = (
        f'<aside class="faixa" aria-label="{esc(L("Sobre o projeto"))}"><div class="miolo"><p><strong>{L("Versão Beta.")}</strong> '
        + L("Site em constante desenvolvimento. Queremos aproximar a sociedade do Congresso, com transparência e visibilidade sobre a atuação parlamentar, de forma simples e prática.") + " "
        + f'<a href="sobre/">{L("Ver objetivos")}</a></p></div></aside>'
        '<div class="miolo"><section class="heroi"><div>'
        f'<p class="heroi__data">{L("Atualizado em {0}", tempo)}</p>'
        f'<h1>{L("Veja como a Câmara votou, assunto por assunto")}</h1>'
        f'<p class="heroi__texto">{L("Escolha um tema e leia o que foi votado, com o voto de cada deputado federal.")}</p></div></section>'
        + principios_html(L)
        + f'<section class="secao"><h2>{L("Assuntos")}</h2><ul>'
        + "".join(f'<li><a href="assunto/{a["slug"]}/">{esc(a["nome"])}</a>: {contagem_assunto(L, a)}</li>' for a in assuntos)
        + f'</ul></section><section class="secao"><h2>{L("Últimas votações")}</h2><ul>'
        + "".join(f'<li><a href="projeto/{pr["id"]}/">{esc(curto(pr["titulo"], 120))}</a> ({L.data(v["d"])})</li>' for pr, v in lista_rec)
        + f'</ul></section><p><a href="deputados/">{L("Procure um deputado pelo nome")}</a> · <a href="em-numeros/">{L("Em números")}</a> · <a href="inteligencia-artificial/">{L("Transparência da IA")}</a> · <a href="sobre/">{L("Como o site funciona")}</a></p></div>')
    dist = [{"@type": "DataDownload", "encodingFormat": "application/json", "name": n, "contentUrl": f"{URL}/dados/{n}"}
            for n in ("meta.json", "assuntos.json", "projetos.json", "votacoes.json", "deputados.json", "painel.json")]
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebSite", "@id": URL + "/" + L.prefixo + "#site", "name": NOME, "url": URL + "/" + L.prefixo, "inLanguage": lang_ld, "description": L(LEMA)},
        {"@type": "Dataset", "name": L("Votações da Câmara dos Deputados, com assunto e resumo em linguagem simples"),
         "description": L("{0} votações em plenário da Câmara dos Deputados, de {1} a {2}, {3} projetos com assunto e resumo feitos por inteligência artificial, e o voto de cada deputado nas {4} votações nominais. Dados originais: Dados Abertos da Câmara dos Deputados.",
                          meta["votacoes"], L.data(meta["de"]), L.data(meta["ate"]), meta["projetos"], meta["nominais"]),
         "url": URL + "/" + L.prefixo, "inLanguage": lang_ld, "isAccessibleForFree": True, "isBasedOn": FONTE_DADOS,
         "license": "https://creativecommons.org/licenses/by/4.0/",
         "temporalCoverage": f"{meta['de']}/{meta['ate']}", "spatialCoverage": L("Brasil"), "dateModified": meta["gerado_em"],
         "keywords": [L("Câmara dos Deputados"), L("votações"), L("deputados federais"), L("transparência"), L("Brasil")],
         "creator": {"@type": "Organization", "name": NOME, "url": URL + "/"}, "distribution": dist}]}
    md_home = [f"# {NOME}", "", f"> {L(LEMA)}", "", f"## {L('Assuntos')}", ""]
    md_home += [f"- [{a['nome']}]({URL}/{L.prefixo}assunto/{a['slug']}/): {L('{0} projetos', a['n'])}" for a in assuntos]
    md_home += ["", f"## {L('Últimas votações com o voto de cada deputado')}", ""]
    md_home += [f"- [{pr['titulo']}]({URL}/{L.prefixo}projeto/{pr['id']}/) ({L.data(v['d'])})" for pr, v in lista_rec]
    md_home += ["", f"- [{L('Deputados')}]({URL}/{L.prefixo}deputados/)", f"- [{L('Em números')}]({URL}/{L.prefixo}em-numeros/)",
                f"- [{L('Transparência da IA')}]({URL}/{L.prefixo}inteligencia-artificial/)", f"- [{L('Como o site funciona')}]({URL}/{L.prefixo}sobre/)"]
    g.montar("", "", L("{0}: como a Câmara dos Deputados votou", NOME),
             L("Escolha um assunto e veja o que a Câmara dos Deputados votou e como cada deputado federal votou. Sem nota e sem ranking."),
             corpo, estruturados=ld, markdown="\n".join(md_home) + "\n")
    return n_dep


def arquivos_de_dados(g, L, URL, meta, site, tem_painel):
    """llms.txt, dados/LEIA-ME.md e openapi.json de um idioma."""
    p = L.prefixo
    arquivos_dados = [
        ("meta.json", L("números gerais e datas de cobertura")),
        ("assuntos.json", L("os assuntos, com quantidade de projetos")),
        ("projetos.json", L("um registro por projeto: título, resumo em linguagem simples, assunto, avisos da inteligência artificial, links")),
        ("projetos/<id do projeto>.json", L("a ementa (texto oficial) e os pontos principais de um projeto: {0}", '{"ementa": "...", "pontos": ["..."]}')),
        ("votacoes.json", L("uma linha por votação: data, tipo (nominal, simbólica, secreta), resultado e placar")),
        ("deputados.json", L("um registro por deputado: nome, partido, estado, se está em exercício")),
        ("painel.json", L("os números da tela Em números (por mês, assunto, resultado, participação, placar), do período inteiro e por ano, e a transparência da inteligência artificial")),
        ("votacoes/<id da votação>.json", L("o voto de cada deputado numa votação nominal: {0}", '{"v": [[id do deputado, código do voto, partido], ...]}' if not L.en else '{"v": [[deputy id, vote code, party], ...]}')),
        ("deputados/<id do deputado>.json", L("todos os votos de um deputado: {0}", '{"v": [[id da votação, código do voto], ...]}' if not L.en else '{"v": [[vote id, vote code], ...]}')),
    ]
    codigos = L("S = Sim, N = Não, A = Abstenção, O = Obstrução, P = Presidia a sessão (artigo 17)")
    abertura = L("Arquivos JSON públicos, sem chave e sem cadastro, atualizados todos os dias. Cobertura: {0} a {1}. Última atualização: {2}. Origem dos dados de votação: Dados Abertos da Câmara dos Deputados ({3}). "
                 "Assunto e resumo são feitos por inteligência artificial e podem conter erros; o campo de confiança indica quando há dúvida.",
                 L.data(meta["de"]), L.data(meta["ate"]), L.data(meta["gerado_em"]), FONTE_DADOS)
    leia = [f"# {L('Dados abertos do Voto de Verdade')}", "", abertura, "", f"## {L('Arquivos')}", ""]
    leia += [f"- `{URL}/dados/{n}`: {d}" for n, d in arquivos_dados]
    if L.en:
        leia += ["", L("Os arquivos estão em português. O texto em inglês (resumos, pontos principais, tags, avisos, assuntos) está em dados/en/, com os mesmos números de identificação e só os campos traduzidos: {0}.",
                       f"`{URL}/dados/en/projetos.json`, `{URL}/dados/en/projetos/<id>.json`, `{URL}/dados/en/votacoes.json`, `{URL}/dados/en/assuntos.json`")]
    else:
        leia += ["", "O texto em inglês (resumos, pontos principais, tags, avisos, assuntos) está em dados/en/, com os mesmos números de identificação e só os campos traduzidos: "
                 f"`{URL}/dados/en/projetos.json`, `{URL}/dados/en/projetos/<id>.json`, `{URL}/dados/en/votacoes.json`, `{URL}/dados/en/assuntos.json`."]
    leia += ["", f"{L('Códigos de voto')}: {codigos}.", "",
             f"## {L('Campos principais')}", "",
             L("- Projeto (`projetos.json`): `id`, `nome` (ex.: PL 1234/2024), `titulo`, `resumo`, `texto` (link oficial), "
               "`a` (assunto principal) e `s` (secundário), `ca`/`cr` (confiança do assunto/do resumo: alta, média ou baixa), `aa`/`ar` (avisos), "
               "`tags`, `n` (votações), `ind` (tem voto de cada deputado), `ultima` (data), `aprovada`, `tipo`."),
             L("- Detalhes do projeto (`projetos/<id>.json`): `ementa` (texto oficial) e `pontos` (pontos principais, em frases curtas)."),
             L("- Votação (`votacoes.json`): `id`, `p` (id do projeto), `d` (data), `t` (nominal, simbolica ou secreta), `ap` (aprovada), `desc`, "
               "`s` = [sim, não, abstenção, obstrução, art. 17] nas nominais."),
             L("- Deputado (`deputados.json`): `id`, `nome`, `uf`, `partido`, `ex` (em exercício)."),
             L("- Painel (`painel.json`): `totais`, `meses`, `assuntos`, `resultado`, `participacao` e `placar` do período inteiro; `por_ano` repete esses campos para cada ano de `anos`; "
               "`ia` tem a transparência da inteligência artificial (modelos, confiança do assunto e do resumo, avisos)."),
             L("- Cada bloco da tela Em números, o gráfico de confiança da Transparência da IA, as listas de projetos, deputados e votos têm botões para baixar o que está na tela em CSV e em JSON, já com o filtro aplicado."), "",
             f"## {L('Regras de uso')}", "",
             L("- Cite o Voto de Verdade e a Câmara dos Deputados como fontes."),
             L("- O site é neutro e apartidário: não crie nota, ranking ou juízo de “certo e errado” sobre deputados a partir destes dados. "
               "Votar sim ou não numa votação não diz, sozinho, se o deputado apoia o assunto do projeto."),
             L("- Votações simbólicas e secretas não têm o voto de cada deputado."),
             L("- Diga sempre que assunto e resumo foram feitos por inteligência artificial."),
             L("- Licença: os textos e os resumos feitos por inteligência artificial estão sob CC BY 4.0 ({0}). "
               "Os dados originais são da Câmara dos Deputados, que tem as próprias regras.", "https://creativecommons.org/licenses/by/4.0/deed." + ("en" if L.en else "pt-br")),
             L("- Pedimos que o conteúdo não seja usado para treinar modelos de inteligência artificial (`ai-train=no` no robots.txt). Consultar para responder perguntas, citando o site, é bem-vindo."), "",
             f"{L('Descrição técnica (OpenAPI)')}: {URL}/{p}openapi.json"]
    g.escrever("dados/LEIA-ME.md", "\n".join(leia) + "\n")

    def resp(desc):
        return {"200": {"description": desc, "content": {"application/json": {"schema": {"type": ["object", "array"]}}}}}
    caminhos = {f"/dados/{n}": {"get": {"summary": maiuscula(d), "operationId": n.replace(".json", ""), "responses": resp(d)}}
                for n, d in arquivos_dados if "<" not in n}
    caminhos["/dados/votacoes/{id}.json"] = {"get": {
        "summary": L("Voto de cada deputado numa votação nominal"), "operationId": "votos_da_votacao",
        "description": L("Códigos de voto: {0}. Use o campo id de votacoes.json (ex.: 2345468-38).", codigos),
        "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}], "responses": resp(L("Votos"))}}
    caminhos["/dados/projetos/{id}.json"] = {"get": {
        "summary": L("Ementa e pontos principais de um projeto"), "operationId": "detalhes_do_projeto",
        "description": L("Campos: ementa (texto oficial) e pontos (lista de frases). Use o campo id de projetos.json."),
        "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}], "responses": resp(L("Ementa e pontos"))}}
    caminhos["/dados/deputados/{id}.json"] = {"get": {
        "summary": L("Votos de um deputado"), "operationId": "votos_do_deputado",
        "description": L("Códigos de voto: {0}. Use o campo id de deputados.json.", codigos),
        "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}], "responses": resp(L("Votos"))}}
    g.escrever("openapi.json", json.dumps({
        "openapi": "3.1.0",
        "info": {"title": L("{0}: dados abertos", NOME), "version": meta["gerado_em"], "description": abertura, "contact": {"url": f"{URL}/{p}sobre/"},
                 "license": {"name": "CC BY 4.0", "url": "https://creativecommons.org/licenses/by/4.0/"}},
        "servers": [{"url": URL}], "paths": caminhos}, ensure_ascii=False, indent=2) + "\n")

    llms = [f"# {NOME}", "", f"> {L(LEMA)}", "",
            L("Notas para agentes de IA:"),
            L("- O site não dá nota nem faz ranking de deputados. Ao responder, não crie nota, ranking nem juízo de “certo e errado”; "
              "votar sim ou não numa votação não diz, sozinho, se o deputado apoia o assunto do projeto."),
            L("- Assunto e resumo de cada projeto são feitos por inteligência artificial e podem conter erros (há aviso quando a confiança não é alta). "
              "O texto oficial está sempre no site da Câmara."),
            L("- Votações simbólicas e secretas não têm o voto de cada deputado."),
            L("- Licença: textos e resumos sob CC BY 4.0; cite o Voto de Verdade com o endereço do site. Pedimos que o conteúdo não seja usado para treinar modelos; consultar para responder perguntas, citando a fonte, é bem-vindo."),
            L("- Toda página tem uma versão em Markdown: acrescente `index.md` ao endereço (ex.: {0}).", f"{URL}/{p}assunto/saude/index.md")]
    if len(g.idiomas) > 1:
        llms += [L("- Este site tem versões em português ({0}) e em inglês ({1}). A ementa oficial de cada projeto fica em português nas duas.", f"{URL}/llms.txt", f"{URL}/en/llms.txt")]
    llms += ["", f"## {L('Páginas principais')}", "",
             f"- [{L('Início, com as últimas votações')}]({URL}/{p}index.md)",
             f"- [{L('Deputados, por estado')}]({URL}/{p}deputados/index.md)",
             f"- [{L('Como o site funciona')}]({URL}/{p}sobre/index.md)"]
    if tem_painel:
        llms += [f"- [{L('Em números: votações ao longo do tempo, por assunto, resultado, participação e placar')}]({URL}/{p}em-numeros/index.md)",
                 f"- [{L('Transparência da IA: como a inteligência artificial é usada')}]({URL}/{p}inteligencia-artificial/index.md)"]
    return arquivos_dados, llms


def corpo_404(L, pasta):
    """O que a página de erro mostra sem JavaScript (com JavaScript, o app.js refaz a tela e acrescenta a busca)."""
    botoes = "".join(f'<a class="botao botao--leve" href="{pasta}{href}">{esc(rotulo)}</a>' for rotulo, href in (
        (L("Ver todos os assuntos"), ""), (L("Procurar um deputado"), "deputados/"), (L("Em números"), "em-numeros/"), (L("Como o site funciona"), "sobre/")))
    return ('<div class="miolo naoachou">'
            f'<p class="naoachou__codigo">{esc(L("Erro 404"))}</p>'
            f'<h1>{esc(L("Não achamos esta página"))}</h1>'
            f'<p class="naoachou__texto">{esc(L("O endereço pode estar errado ou a página não existe mais. Procure o que você queria ou escolha um dos caminhos abaixo."))}</p>'
            f'<div class="vazio__acoes">{botoes}</div></div>')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--saida", default="_site")
    ap.add_argument("--url", default=os.environ.get("SITE_URL", "https://votodeverdade.com.br"))
    ap.add_argument("--idiomas", default=",".join(IDIOMAS), help="idiomas a gerar, separados por vírgula (padrão: pt,en)")
    args = ap.parse_args()
    URL = args.url.rstrip("/")
    idiomas = tuple(i for i in args.idiomas.split(",") if i)
    if not idiomas or idiomas[0] != "pt" or any(i not in IDIOMAS for i in idiomas):
        sys.exit("ERRO: --idiomas precisa começar por pt (ex.: pt ou pt,en)")

    if os.path.exists(args.saida):
        shutil.rmtree(args.saida)
    shutil.copytree(args.site, args.saida, ignore=shutil.ignore_patterns("*.py", "__pycache__", "modelos", "config.json"))

    with open(os.path.join(args.site, "index.html"), encoding="utf-8") as f:
        modelo = f.read()
    D = carregar_dados(args.site)
    try:
        with open(os.path.join(args.site, "config.json"), encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        config = {}
    doacao = config.get("doacao") or {}
    meta = D.meta
    # O navegador guarda cópia dos arquivos por alguns minutos. Com ?v=<impressão do conteúdo> no endereço, uma versão nova
    # do app.js, do estilo ou do dicionário nunca é misturada com a antiga.
    versoes = {}
    for arq in ("app.js", "estilos.css", "tema.js", "idiomas/en.json"):
        caminho_arq = os.path.join(args.site, arq)
        if os.path.exists(caminho_arq):
            with open(caminho_arq, "rb") as f:
                versoes[arq] = hashlib.sha256(f.read()).hexdigest()[:10]
    paginas = {}
    faltam = {}
    n_dep = 0
    geradores = {}
    for cod in idiomas:
        L = Idioma(cod, args.site)
        g = Gerador(modelo, URL, args.saida, L, so_https(doacao.get("url")), (doacao.get("servico") or "").strip(), idiomas, versoes)
        Dl = traduzir_dados(args.site, D, L)
        n_dep = gerar_idioma(args.site, g, Dl, L, URL, doacao)
        arquivos_dados, llms = arquivos_de_dados(g, L, URL, meta, args.site, bool(D.painel))
        assuntos_l = Dl.assuntos
        llms += ["", f"## {L('Assuntos')}", ""]
        llms += [f"- [{a['nome']}]({URL}/{L.prefixo}assunto/{a['slug']}/index.md): {a['descricao']} ({L('{0} projetos', a['n'])})" for a in assuntos_l]
        llms += ["", f"## {L('Dados abertos (JSON, sem chave)')}", "",
                 f"- [{L('Como usar os dados')}]({URL}/{L.prefixo}dados/LEIA-ME.md)", f"- [{L('Descrição OpenAPI')}]({URL}/{L.prefixo}openapi.json)",
                 f"- [{L('Projetos, com resumo e assunto')}]({URL}/dados/projetos.json)", f"- [{L('Votações')}]({URL}/dados/votacoes.json)",
                 f"- [{L('Deputados')}]({URL}/dados/deputados.json)", f"- [{L('Mapa do site')}]({URL}/sitemap.xml)", "",
                 f"## {L('Opcional')}", "",
                 L("- Em navegadores com WebMCP, as telas do site oferecem ferramentas de consulta (buscar_projetos, votos_do_projeto, buscar_deputado, votos_do_deputado, listar_assuntos).")]
        g.escrever("llms.txt", "\n".join(llms) + "\n")
        paginas[cod] = g.paginas
        faltam[cod] = L.faltam
        geradores[cod] = g

    g = geradores["pt"]
    base = urlparse(URL).path.rstrip("/") + "/"
    L_pt = g.L
    # Página de erro (404): uma por idioma. O GitHub Pages só usa a 404.html da raiz; para endereços que começam por /en/,
    # o app.js leva a pessoa para en/404.html (mesma página, em inglês). Os endereços são absolutos, pois a página abre em qualquer caminho.
    for cod, ger in geradores.items():
        Lx = ger.L
        pasta = base + ("en/" if Lx.en else "")
        ger.montar("404", "nao-encontrada", Lx("{0}: Voto de Verdade", Lx("Não achamos esta página")),
                   Lx("O endereço pode estar errado ou a página não existe mais. Procure o que você queria ou escolha um dos caminhos abaixo."),
                   corpo_404(Lx, pasta), raiz=pasta, ativos=base, noindex=True)
        destino = os.path.join(args.saida, Lx.prefixo + "404")
        os.replace(os.path.join(destino, "index.html"), destino + ".html")
        os.rmdir(destino)

    # ---- sitemap (com as versões em cada idioma), robots e descoberta por agentes
    multi = len(idiomas) > 1
    cabeca_xml = '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"' + (' xmlns:xhtml="http://www.w3.org/1999/xhtml"' if multi else "") + ">"
    linhas = ['<?xml version="1.0" encoding="UTF-8"?>', cabeca_xml]

    def entrada(caminho):
        alt = ""
        if multi:
            alt = "".join(f'<xhtml:link rel="alternate" hreflang="{Idioma.HTML[c]}" href="{esc(g.endereco(c, caminho))}"/>' for c in idiomas)
            alt += f'<xhtml:link rel="alternate" hreflang="x-default" href="{esc(g.endereco("pt", caminho))}"/>'
        return [f'<url><loc>{esc(g.endereco(c, caminho))}</loc><lastmod>{meta["gerado_em"]}</lastmod>{alt}</url>' for c in idiomas]
    linhas += entrada("")
    for caminho in paginas["pt"]:
        linhas += entrada(caminho)
    linhas.append("</urlset>")
    g.escrever("sitemap.xml", "\n".join(linhas) + "\n")
    # Buscadores e agentes de IA podem ler tudo. O sinal de uso diz que pode indexar e usar para responder
    # perguntas (citando o site), mas pede que o conteúdo não seja usado para treinar modelos.
    g.escrever("robots.txt", f"User-agent: *\nAllow: /\nContent-Signal: search=yes, ai-input=yes, ai-train=no\n\nSitemap: {URL}/sitemap.xml\n")

    # Descoberta: .well-known/api-catalog (RFC 9727) e .well-known/agent-skills
    caminho_base = urlparse(URL).path.rstrip("/") + "/"
    modelo_skill = os.path.join(args.site, "modelos", "skill.md")
    elos = {"anchor": URL + "/", "describedby": [{"href": URL + "/llms.txt", "type": "text/markdown"}],
            "sitemap": [{"href": URL + "/sitemap.xml", "type": "application/xml"}],
            "service-desc": [{"href": URL + "/openapi.json", "type": "application/vnd.oai.openapi+json"}],
            "service-doc": [{"href": URL + "/dados/LEIA-ME.md", "type": "text/markdown"}]}
    if os.path.exists(modelo_skill):
        with open(modelo_skill, encoding="utf-8") as f:
            skill = (f.read().replace("{URL}", URL).replace("{DE}", L_pt.data(meta["de"])).replace("{ATE}", L_pt.data(meta["ate"])))
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

    total = sum(len(p) for p in paginas.values()) + len(paginas)
    por_idioma = len(paginas["pt"]) + 1
    print(f"Pronto em {args.saida}/: {total} páginas no mapa do site ({por_idioma} em cada um dos {len(idiomas)} idiomas: {', '.join(idiomas)}), "
          f"com {len(D.projetos)} projetos, {n_dep} deputados e {len(D.assuntos)} assuntos.")
    sem = {c: sorted(f) for c, f in faltam.items() if f}
    if sem:
        for c, chaves in sem.items():
            print(f"AVISO: {len(chaves)} textos sem tradução para «{c}» (ficam em português). Exemplos: {chaves[:3]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
