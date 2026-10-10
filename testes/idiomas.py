#!/usr/bin/env python3
"""Confere a versão em inglês do site (português na raiz, inglês em en/).

Uso (na raiz do repositório):
    python testes/idiomas.py            # só o dicionário e os dados (não precisa de navegador)
    python testes/idiomas.py _site      # também remonta o site na pasta dada (site/gerar_paginas.py) e abre o
                                        # site em inglês num navegador de verdade

O que confere:
  1. Dicionário (site/idiomas/en.json): todo texto que o app.js e o gerar_paginas.py passam por tx()/L() tem tradução,
     os marcadores {0}, {1}… e os espaços das pontas batem com o português e não sobra tradução que ninguém usa.
  2. Dados (site/dados/en/): cada projeto e votação tem a tradução do português de agora (a impressão confere) e o
     inglês não tem números diferentes do português.
  3. Páginas (com o caminho do site): html lang, hreflang, canônica, seletor PT|EN, sitemap com as duas versões, llms.txt
     em inglês, e nenhuma chave sem tradução na geração.
  4. Navegador (com o caminho do site): telas em inglês sem texto faltando (window.__IDIOMA_FALTA__ vazio), sem
     erro no console, sem português solto (fora da ementa oficial), o seletor leva à mesma tela no outro idioma e,
     no celular, ele fica dentro do menu e o modo escuro continua fora dele.
Sai com código 1 se algo falhar.
"""
import ast
import functools
import io
import http.server
import json
import os
import re
import socketserver
import subprocess
import sys
import tempfile
import threading

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(RAIZ, "site")
sys.path.insert(0, os.path.join(RAIZ, "coleta"))
import traducoes as T  # noqa: E402
from traduzir_projetos import origem_dos_dados  # noqa: E402

falhas = []


def confere(ok, msg):
    print(("  ok  " if ok else "FALHOU ") + msg)
    if not ok:
        falhas.append(msg)


def chaves_do_app():
    with open(os.path.join(SITE, "app.js"), encoding="utf-8") as f:
        js = f.read()
    achadas = set()
    for m in re.finditer(r"\btx\(\s*\"((?:[^\"\\]|\\.)*)\"", js):
        achadas.add(json.loads('"' + m.group(1) + '"'))
    return achadas


def chaves_do_gerador():
    with open(os.path.join(SITE, "gerar_paginas.py"), encoding="utf-8") as f:
        fonte = f.read()
    arvore = ast.parse(fonte)
    chaves = set()

    def texto(no):
        if isinstance(no, ast.Constant) and isinstance(no.value, str):
            return no.value
        if isinstance(no, ast.BinOp) and isinstance(no.op, ast.Add):
            a, b = texto(no.left), texto(no.right)
            return a + b if a is not None and b is not None else None
        return None
    for no in ast.walk(arvore):
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id == "L" and no.args:
            t = texto(no.args[0])
            if t is not None:
                chaves.add(t)
        if isinstance(no, ast.Assign) and isinstance(no.targets[0], ast.Name):
            nome = no.targets[0].id
            if nome == "LEMA":
                chaves.add(ast.literal_eval(no.value))
            elif nome == "PRINCIPIOS":
                for _, titulo, desc in ast.literal_eval(no.value):
                    chaves.update([titulo, desc])
            elif nome == "TEXTOS_DO_MODELO":
                for _, t, _ in ast.literal_eval(no.value):
                    chaves.add(t)
    return chaves


def dicionario():
    print("Dicionário")
    with open(os.path.join(SITE, "idiomas", "en.json"), encoding="utf-8") as f:
        dic = json.load(f)
    usadas = chaves_do_app() | chaves_do_gerador()
    sem = sorted(usadas - set(dic))
    sobra = sorted(set(dic) - usadas)
    confere(not sem, f"todos os {len(usadas)} textos usados têm tradução" + (f" (faltam {len(sem)}, por exemplo {sem[:2]})" if sem else ""))
    confere(not sobra, "nenhuma tradução sem uso" + (f" (sobram {len(sobra)}, por exemplo {sobra[:2]})" if sobra else ""))
    ruins = []
    for k, v in dic.items():
        if not isinstance(v, str) or not v.strip():
            ruins.append(("vazio", k))
            continue
        if sorted(re.findall(r"\{\d+\}", k)) != sorted(re.findall(r"\{\d+\}", v)):
            ruins.append(("marcadores", k))
        if (k[:1].isspace(), k[-1:].isspace()) != (v[:1].isspace(), v[-1:].isspace()):
            ruins.append(("espaços nas pontas", k))
    confere(not ruins, "marcadores e espaços das pontas batem com o português" + (f" ({ruins[:2]})" if ruins else ""))
    return dic


def dados_em_ingles():
    print("Dados traduzidos")
    pasta = os.path.join(SITE, "dados")
    origem, _ = origem_dos_dados(pasta)
    trad = T.carregar(os.path.join(RAIZ, T.ARQUIVO))
    velhos = [i for i, item in origem["projetos"].items() if (trad["projetos"].get(i) or {}).get("h") != T.impressao(item)]
    velhas = [i for i, item in origem["votacoes"].items() if (trad["votacoes"].get(i) or {}).get("h") != T.impressao(item)]
    confere(not velhos, f"{len(origem['projetos'])} projetos com tradução em dia" + (f" (desatualizados ou sem tradução: {len(velhos)})" if velhos else ""))
    confere(not velhas, f"{len(origem['votacoes'])} votações com tradução em dia" + (f" (desatualizadas ou sem tradução: {len(velhas)})" if velhas else ""))
    ruins = []
    for tipo, validar in (("projetos", T.validar_projeto), ("votacoes", T.validar_votacao)):
        for i, item in origem[tipo].items():
            t = trad[tipo].get(i)
            if t and validar(item, t):
                ruins.append((tipo, i, validar(item, t)[:1]))
    confere(not ruins, "nenhuma tradução com número diferente, português sobrando ou tamanho estranho" + (f" ({ruins[:2]})" if ruins else ""))
    sobreposicao = os.path.join(pasta, "en")
    confere(os.path.isdir(sobreposicao), "site/dados/en/ existe (python site/exportar_en.py)")
    if os.path.isdir(sobreposicao):
        with open(os.path.join(sobreposicao, "projetos.json"), encoding="utf-8") as f:
            en_proj = json.load(f)
        confere(len(en_proj) >= len([1 for i in origem["projetos"] if (trad["projetos"].get(i) or {}).get("resumo")]),
                "site/dados/en/projetos.json tem todos os projetos traduzidos (rode site/exportar_en.py se faltar)")
        with open(os.path.join(sobreposicao, "assuntos.json"), encoding="utf-8") as f:
            en_ass = json.load(f)
        with open(os.path.join(pasta, "assuntos.json"), encoding="utf-8") as f:
            ass = json.load(f)
        confere(all(a["slug"] in en_ass for a in ass), "todos os assuntos têm nome e descrição em inglês")


def paginas(saida):
    print("Páginas geradas")
    proc = subprocess.run([sys.executable, os.path.join(SITE, "gerar_paginas.py"), "--saida", saida], capture_output=True, text=True)
    confere(proc.returncode == 0, "gerar_paginas.py termina sem erro" + ("" if proc.returncode == 0 else " " + proc.stderr[-300:]))
    confere("sem tradução" not in proc.stderr, "nenhum texto sem tradução na geração" + ("" if "sem tradução" not in proc.stderr else " " + proc.stderr[-300:]))

    def ler(*partes):
        with open(os.path.join(saida, *partes), encoding="utf-8") as f:
            return f.read()
    with open(os.path.join(SITE, "dados", "projetos.json"), encoding="utf-8") as f:
        projetos = json.load(f)
    pid = next(p["id"] for p in projetos if p["ind"])
    pt, en = ler("projeto", str(pid), "index.html"), ler("en", "projeto", str(pid), "index.html")
    confere('<html lang="pt-BR">' in pt and '<html lang="en">' in en, "html lang: pt-BR no português e en no inglês")
    confere(f'<link rel="canonical" href="https://votodeverdade.com.br/en/projeto/{pid}/">' in en, "página em inglês tem a própria canônica")
    for html, nome in ((pt, "português"), (en, "inglês")):
        confere(f'hreflang="pt-BR" href="https://votodeverdade.com.br/projeto/{pid}/"' in html
                and f'hreflang="en" href="https://votodeverdade.com.br/en/projeto/{pid}/"' in html
                and f'hreflang="x-default" href="https://votodeverdade.com.br/projeto/{pid}/"' in html, f"hreflang nas duas versões ({nome})")
    confere('data-idioma="en"' in pt and f'href="../../en/projeto/{pid}/"' in pt, "seletor no português leva à página em inglês")
    confere('data-idioma="pt"' in en and f'href="../../../projeto/{pid}/"' in en, "seletor no inglês leva à página em português")
    confere('class="menu-idioma"' in pt and 'class="menu-idioma"' in en, "seletor também está dentro do menu (celular)")
    confere('"lang": "en"' in en and '"lang"' not in pt, "o aplicativo sabe o idioma da página (config)")
    confere(re.search(r'src="\.\./\.\./\.\./app\.js\?v=\w+"', en) and re.search(r'href="\.\./\.\./\.\./estilos\.css\?v=\w+"', en),
            "arquivos do site em inglês apontam para a raiz, com versão no endereço (o navegador não usa cópia velha)")
    confere(re.search(r'"dic": "\w+"', en), "o aplicativo em inglês sabe a versão do dicionário")
    confere('content="https://votodeverdade.com.br/og-en.png"' in en and 'content="https://votodeverdade.com.br/og.png"' in pt
            and os.path.exists(os.path.join(saida, "og-en.png")), "prévia de compartilhamento: imagem em inglês nas páginas em inglês")
    pt404, en404 = ler("404.html"), ler("en", "404.html")
    confere('<html lang="pt-BR">' in pt404 and '<html lang="en">' in en404 and "noindex" in pt404 and "noindex" in en404,
            "página de erro (404) existe em português e em inglês, sem entrar nos buscadores")
    confere('href="/en/deputados/"' in en404 and 'href="/deputados/"' in pt404 and 'src="/app.js?v=' in en404, "página de erro usa endereços absolutos (abre em qualquer caminho)")
    confere("We could not find this page" in en404 and "Não achamos esta página" in pt404 and "Erro 404" in pt404 and "Error 404" in en404, "página de erro tem texto em cada idioma")
    confere('lang="pt-BR"' in en.split('class="oficial"')[1][:30], "a ementa oficial fica em português e marcada com lang=pt-BR")
    confere("The official text is in Portuguese" in en, "aviso de que o texto oficial está em português")
    sitemap = ler("sitemap.xml")
    confere("xmlns:xhtml" in sitemap and f"/en/projeto/{pid}/</loc>" in sitemap and 'hreflang="en"' in sitemap, "sitemap lista as duas versões com alternativas")
    confere("llms.txt" in ler("en", "llms.txt") and "# Voto de Verdade" in ler("en", "llms.txt"), "en/llms.txt existe")
    confere("Voto de Verdade open data" in ler("en", "dados", "LEIA-ME.md"), "dados abertos têm LEIA-ME em inglês")
    confere(os.path.exists(os.path.join(saida, "en", "openapi.json")), "en/openapi.json existe")
    texto_en = re.sub(r"<script.*?</script>|<style.*?</style>", "", en, flags=re.S)
    texto_en = re.sub(r"<p class=\"oficial\".*?</p>", "", texto_en, flags=re.S)
    texto_en = re.sub(r"<[^>]+>", " ", texto_en)
    sobra = [w for w in (" votação ", " deputado ", " projeto ", " resumo ", " Assuntos ", " não ") if w in " " + texto_en + " "]
    confere(not sobra, f"página de projeto em inglês sem português solto{' ' + str(sobra) if sobra else ''}")


class Quieto(http.server.SimpleHTTPRequestHandler):
    """Serve a pasta do site como o GitHub Pages: endereço que não existe devolve 404.html, com status 404."""
    def send_head(self):
        if not os.path.exists(self.translate_path(self.path)):
            with open(os.path.join(self.directory, "404.html"), "rb") as f:
                corpo = f.read()
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            return io.BytesIO(corpo)
        return super().send_head()

    def log_message(self, *a):
        pass


def navegador(saida):
    from playwright.sync_api import sync_playwright
    print("Navegador")
    socketserver.TCPServer.allow_reuse_address = True
    servidor = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(Quieto, directory=saida))
    base = f"http://127.0.0.1:{servidor.server_address[1]}"
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    with open(os.path.join(saida, "dados", "projetos.json"), encoding="utf-8") as f:
        projetos = json.load(f)
    with open(os.path.join(saida, "dados", "deputados.json"), encoding="utf-8") as f:
        deputados = json.load(f)
    with open(os.path.join(saida, "dados", "votacoes.json"), encoding="utf-8") as f:
        votacoes = json.load(f)
    with open(os.path.join(saida, "dados", "assuntos.json"), encoding="utf-8") as f:
        assuntos = json.load(f)
    nom = next(p for p in projetos if p["ind"] and p["n"] > 1)
    vot = next(v for v in votacoes if v["p"] == nom["id"] and v.get("s"))
    dep = next(d for d in deputados if d["ex"])
    sim = next(p for p in projetos if not p["ind"] and p["tipo"] == "simbolica")
    aviso = next(p for p in projetos if p["aa"])
    avisor = next(p for p in projetos if p["ar"])
    subst = next(p for p in projetos if p["subst"])
    sem_resumo = next((p for p in projetos if not p["resumo"]), None)
    rotas = ["/", "/?q=vacina", "/?q=zzzzqq", "/#/deputados", "/#/deputados?q=zzzzqq", "/#/deputados?uf=SP", f"/#/deputado/{dep['id']}",
             f"/#/deputado/{dep['id']}?v=S", "/#/deputado/1", "/#/sobre", "/#/apoie", "/#/em-numeros", "/#/em-numeros/por-mes", "/#/em-numeros/por-assunto",
             "/#/em-numeros/resultado", "/#/em-numeros/participacao", "/#/em-numeros/placar-votos", "/#/em-numeros/placar-margem", "/#/em-numeros?ano=2025",
             "/#/inteligencia-artificial", "/#/inteligencia-artificial/confianca", "/#/assunto/inexistente", "/#/projeto/999", "/#/foo/bar",
             f"/#/projeto/{nom['id']}", f"/#/projeto/{nom['id']}?votacao={vot['id']}", f"/#/projeto/{nom['id']}?votacao={vot['id']}&v=S",
             f"/#/projeto/{nom['id']}?votacao={vot['id']}&q=zzzzqq", f"/#/projeto/{sim['id']}", f"/#/projeto/{aviso['id']}", f"/#/projeto/{avisor['id']}",
             f"/#/projeto/{subst['id']}", "/#/assunto/saude?res=aprovado&cert=1", "/#/assunto/saude?q=zzzzqq&todos=1"]
    if sem_resumo:
        rotas.append(f"/#/projeto/{sem_resumo['id']}")
    rotas += [f"/#/assunto/{a['slug']}" for a in assuntos]
    # português solto: palavras que não existem em inglês; a ementa oficial (lang="pt-BR") fica de fora
    js = """() => {
      const c = document.body.cloneNode(true);
      c.querySelectorAll('[lang="pt-BR"], script, style, .oficial, .registro').forEach(e => e.remove());
      return { texto: c.innerText, falta: [...(window.__IDIOMA_FALTA__ || [])], lang: document.documentElement.lang,
               attrs: [...document.querySelectorAll('[aria-label],[title],[placeholder],[alt]')].map(e => [e.getAttribute('aria-label'), e.getAttribute('title'), e.getAttribute('placeholder'), e.getAttribute('alt')].filter(Boolean).join(' | ')).join('\\n') };
    }"""
    palavras_pt = re.compile(r"\b(não|votação|votações|deputado|deputados|projeto|projetos|assunto|resumo|inteligência|câmara|sem nota|ranking de)\b", re.I)
    with sync_playwright() as p:
        nav = p.chromium.launch()

        def nova(largura=1280, tema="light"):
            ctx = nav.new_context(viewport={"width": largura, "height": 900}, color_scheme=tema)
            pg = ctx.new_page()
            pg.erros = []
            pg.falhas = []
            pg.on("pageerror", lambda e: pg.erros.append(str(e)))
            pg.on("console", lambda m: pg.erros.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
            # Nenhum arquivo pedido pode dar erro (o app só deve pedir o que existe, por exemplo as traduções).
            # (Telas de "não achamos" pedem de propósito um arquivo de dados que não existe; aqui só contam os de tradução e o dicionário.)
            pg.on("response", lambda r: pg.falhas.append(f"{r.status} {r.url.split('/', 3)[-1]}") if r.status >= 400 and ("/dados/en/" in r.url or "/idiomas/" in r.url) else None)
            return pg

        pg = nova()
        faltas, solto, erros_tela = {}, {}, []
        for r in rotas:
            pg.goto(base + "/en" + r)
            try:
                pg.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            pg.wait_for_timeout(250)
            pg.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
            d = pg.evaluate(js)
            if d["falta"]:
                faltas[r] = d["falta"]
            ach = sorted(set(m.group(0).lower() for m in palavras_pt.finditer(d["texto"] + "\n" + d["attrs"])))
            if ach:
                solto[r] = ach
            if d["lang"] != "en":
                erros_tela.append((r, "lang " + d["lang"]))
        confere(not faltas, f"{len(rotas)} telas em inglês sem texto faltando no dicionário" + (f" {dict(list(faltas.items())[:2])}" if faltas else ""))
        confere(not solto, "nenhuma tela em inglês com português solto" + (f" {dict(list(solto.items())[:3])}" if solto else ""))
        confere(not erros_tela, "html lang=en em todas as telas" + (f" {erros_tela[:2]}" if erros_tela else ""))
        confere(not pg.erros, "telas em inglês sem erros no console " + str(pg.erros[:3]))
        confere(not pg.falhas, "telas em inglês sem arquivo pedido que não existe (404) " + str(sorted(set(pg.falhas))[:4]))

        # seletor de idioma no computador
        pg = nova()
        pg.goto(base + f"/en/projeto/{nom['id']}/")
        pg.wait_for_selector("h1", timeout=15000)
        topo = pg.locator(".topo__acoes .idioma")
        confere(topo.count() == 1 and topo.is_visible(), "computador: seletor de idioma visível no topo")
        confere(pg.locator(".topo__acoes .tema--topo").is_visible(), "computador: botão do modo escuro continua no topo")
        pg.locator(".topo__acoes .idioma a[data-idioma=pt]").click()
        pg.wait_for_url(f"{base}/projeto/{nom['id']}/", timeout=10000)
        pg.wait_for_selector("h1", timeout=15000)
        confere(pg.evaluate("document.documentElement.lang") == "pt-BR" and "Como cada deputado votou" in pg.inner_text("main"), "PT leva à mesma página em português")
        pg.locator(".topo__acoes .idioma a[data-idioma=en]").click()
        pg.wait_for_url(f"{base}/en/projeto/{nom['id']}/", timeout=10000)
        confere(True, "EN volta à mesma página em inglês")
        # rota por # : o link acompanha a tela de agora
        pg.goto(base + "/en/#/deputados?uf=SP")
        pg.wait_for_selector("h1", timeout=15000)
        href = pg.get_attribute(".topo__acoes .idioma a[data-idioma=pt]", "href")
        confere(href.endswith("/#/deputados?uf=SP") and "/en/" not in href, f"seletor acompanha a rota com # ({href})")
        pg2 = nova()
        pg2.goto(base + "/")
        pg2.wait_for_selector("h1", timeout=15000)
        pg2.locator(".topo__acoes .idioma a[data-idioma=en]").click()
        pg2.wait_for_url(f"{base}/en/", timeout=10000)
        pg2.wait_for_selector(".tiles", timeout=15000)
        confere("Pick a topic" in pg2.inner_text("main"), "da página inicial em português para a inicial em inglês")

        # celular: o seletor vai para dentro do menu; o modo escuro fica fora dele
        pg = nova(390)
        pg.goto(base + "/en/")
        pg.wait_for_selector(".tiles", timeout=15000)
        confere(not pg.locator(".topo__acoes .idioma").is_visible(), "celular: seletor não aparece solto no topo")
        confere(pg.locator(".tema--topo").is_visible() and pg.evaluate("!document.querySelector('#menu-topo').contains(document.querySelector('.tema--topo'))"),
                "celular: modo escuro fica ao lado do menu, fora dele")
        pg.click(".menu-botao")
        pg.wait_for_selector("#menu-topo .idioma", state="visible", timeout=5000)
        confere(pg.locator("#menu-topo .idioma a[data-idioma=pt]").is_visible(), "celular: seletor aparece dentro do menu")
        alvo = pg.locator("#menu-topo .idioma a[data-idioma=pt]").bounding_box()
        confere(alvo["width"] >= 24 and alvo["height"] >= 24, f"celular: alvo do seletor tem pelo menos 24px ({alvo['width']:.0f}x{alvo['height']:.0f})")
        pg.locator("#menu-topo .idioma a[data-idioma=pt]").click()
        pg.wait_for_url(f"{base}/", timeout=10000)
        confere(True, "celular: o seletor do menu leva ao português")
        pg.goto(base + "/en/")
        pg.wait_for_selector(".tiles", timeout=15000)
        confere(pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "celular: tela em inglês sem rolagem para o lado")
        for r in ("/#/sobre", "/#/em-numeros", f"/#/projeto/{nom['id']}"):
            pg.goto(base + "/en" + r)
            pg.wait_for_timeout(600)
            confere(pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), f"celular: {r} em inglês sem rolagem para o lado")
        # página de erro (404): em cada idioma, com busca e caminhos que funcionam a partir de qualquer endereço quebrado
        pg = nova()
        pg.goto(base + "/projeto/999999/")
        pg.wait_for_selector(".naoachou h1", timeout=15000)
        confere(pg.locator("h1").inner_text() == "Não achamos este projeto" and pg.evaluate("document.documentElement.lang") == "pt-BR", "404 em português: título conforme o tipo de endereço")
        hrefs = pg.evaluate("[...document.querySelectorAll('main a')].map(a => a.getAttribute('href'))")
        confere(hrefs and all(h.startswith("/") for h in hrefs), f"404 em português: os caminhos são do site, não do endereço quebrado {hrefs[:2]}")
        pg.fill(".naoachou input[type=search]", "saúde")
        pg.press(".naoachou input[type=search]", "Enter")
        pg.wait_for_url(base + "/#/?q=sa%C3%BAde", timeout=10000)
        pg.wait_for_selector(".tiles, .resultado", timeout=15000)
        confere(True, "404 em português: a busca leva aos resultados")
        pg = nova()
        pg.goto(base + "/en/deputado/1/")
        pg.wait_for_url("**/en/404.html?de=*", timeout=10000)
        pg.wait_for_selector(".naoachou h1", timeout=15000)
        confere(pg.locator("h1").inner_text() == "We could not find this deputy" and pg.evaluate("document.documentElement.lang") == "en", "404 em inglês: endereço /en/ leva à página em inglês")
        hrefs = pg.evaluate("[...document.querySelectorAll('main a')].map(a => a.getAttribute('href'))")
        confere(hrefs and all(h.startswith("/en/") for h in hrefs), f"404 em inglês: os caminhos são do site em inglês {hrefs[:2]}")
        pg.fill(".naoachou input[type=search]", "tax")
        pg.press(".naoachou input[type=search]", "Enter")
        pg.wait_for_url(base + "/en/#/?q=tax", timeout=10000)
        pg.wait_for_selector(".tiles, .resultado", timeout=15000)
        confere(True, "404 em inglês: a busca leva aos resultados em inglês")
        pg = nova(390)
        pg.goto(base + "/en/qualquer-coisa/")
        pg.wait_for_selector(".naoachou h1", timeout=15000)
        confere(pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "celular: 404 em inglês sem rolagem para o lado")
        confere(not pg.evaluate("window.__IDIOMA_FALTA__.size"), "404 em inglês sem texto faltando no dicionário")
        # modo escuro
        pg = nova(1280, "dark")
        pg.goto(base + "/en/")
        pg.wait_for_selector(".tiles", timeout=15000)
        pg.click(".topo__acoes .tema--topo")
        confere(pg.evaluate("document.documentElement.dataset.theme") == "dark", "modo escuro funciona na versão em inglês")
        nav.close()


def main():
    pasta = sys.argv[1] if len(sys.argv) > 1 else None
    dicionario()
    dados_em_ingles()
    if pasta:
        saida = os.path.abspath(pasta)
        paginas(saida)
        navegador(saida)
    print()
    if falhas:
        print(f"{len(falhas)} verificação(ões) falharam.")
        return 1
    print("Tudo certo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
