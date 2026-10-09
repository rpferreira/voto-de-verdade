#!/usr/bin/env python3
"""Teste de fumaça do site: abre as telas principais num navegador de verdade e confere o essencial.

Uso (depois de gerar o site com site/gerar_paginas.py --saida _site):
    pip install playwright && playwright install chromium
    python testes/fumaca.py _site

Confere: início (assuntos, últimas votações, busca), assunto, projeto com o voto de cada deputado (o placar
filtra a lista), deputado, deputados por estado, páginas
prontas (título, prévia de compartilhamento), buscadores e agentes de IA (conteúdo sem JavaScript, dados estruturados,
llms.txt, ferramentas WebMCP), tela estreita sem rolagem para o lado e modo escuro.
Sai com código 1 se algo falhar.
"""
import functools
import http.server
import json
import os
import socketserver
import sys
import threading

from playwright.sync_api import sync_playwright

pasta = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "_site")
falhas = []


def confere(ok, msg):
    print(("  ok  " if ok else "FALHOU ") + msg)
    if not ok:
        falhas.append(msg)


class Quieto(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


socketserver.TCPServer.allow_reuse_address = True
servidor = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(Quieto, directory=pasta))
porta = servidor.server_address[1]
threading.Thread(target=servidor.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{porta}"

with open(os.path.join(pasta, "dados", "projetos.json"), encoding="utf-8") as f:
    projetos = json.load(f)
com_voto = next(p for p in projetos if p["ind"])
with open(os.path.join(pasta, "dados", "deputados.json"), encoding="utf-8") as f:
    deputados = json.load(f)
with open(os.path.join(pasta, "dados", "assuntos.json"), encoding="utf-8") as f:
    assuntos = json.load(f)

with sync_playwright() as p:
    navegador = p.chromium.launch()

    def nova(largura=1280, tema="light"):
        ctx = navegador.new_context(viewport={"width": largura, "height": 900}, color_scheme=tema)
        pg = ctx.new_page()
        pg.erros = []
        pg.on("pageerror", lambda e: pg.erros.append(str(e)))
        pg.on("console", lambda m: pg.erros.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
        return pg

    def sem_rolagem_lateral(pg):
        return pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")

    print("Início")
    pg = nova()
    pg.goto(base + "/")
    pg.wait_for_selector("#t-recentes", timeout=15000)
    confere(pg.locator("h1").inner_text().startswith("Veja como a Câmara votou"), "título da página inicial")
    confere(pg.locator(".tiles > li").count() == len(assuntos), f"{len(assuntos)} assuntos na tela inicial")
    confere(pg.locator("#t-recentes").count() == 1, "seção de últimas votações")
    pg.fill("#busca", "vacina")
    pg.wait_for_selector("#t-projetos", timeout=15000)
    confere(pg.locator(".projetos .proj").count() > 0, "busca “vacina” acha projetos")
    confere(pg.locator(".tiles > li").count() > 0, "busca “vacina” acha assuntos")
    confere(not pg.erros, "início sem erros no console " + str(pg.erros))

    print("Assunto")
    pg.goto(base + "/#/assunto/saude")
    pg.wait_for_selector(".proj", timeout=15000)
    confere(pg.locator(".proj").count() > 0, "lista de projetos do assunto saúde")

    print("Projeto e voto de cada deputado")
    pg.goto(base + f"/#/projeto/{com_voto['id']}")
    pg.wait_for_selector(".placar__item", timeout=15000)
    pg.wait_for_selector(".deputados li", timeout=15000)
    soma = sum(int(t.replace(".", "")) for t in pg.locator(".placar__num").all_inner_texts())
    confere(soma > 100, f"placar soma os deputados que votaram ({soma})")
    primeiro = pg.locator("button.placar__item").first
    n_primeiro = int(primeiro.locator(".placar__num").inner_text().replace(".", ""))
    primeiro.click()
    pg.wait_for_timeout(300)
    confere(primeiro.get_attribute("aria-pressed") == "true", "botão do placar fica marcado")
    confere(pg.locator(".painel .estado").inner_text().startswith(f"{n_primeiro:,}".replace(",", ".")), "contagem da lista bate com o número clicado")
    confere(not pg.erros, "projeto sem erros no console " + str(pg.erros))
    pg.locator("a.deputado__nome").first.click()
    pg.wait_for_selector(".cabeca-dep h1", timeout=15000)
    confere(pg.locator(".placar__item").count() > 0, "página do deputado mostra o placar")
    pg.go_back()
    pg.wait_for_selector(".deputados li", timeout=15000)
    confere(pg.locator("h1").inner_text() != "", "voltar para o projeto funciona")

    print("Deputados por estado")
    pg.goto(base + "/#/deputados")
    pg.wait_for_selector(".chip-uf", timeout=15000)
    pg.locator('.chip-uf[data-uf="GO"]').click()
    pg.wait_for_timeout(300)
    confere("de 6" in pg.locator(".estado").inner_text(), "atalho por estado filtra a lista")

    print("Páginas prontas (compartilhar)")
    pg = nova()
    pg.goto(f"{base}/projeto/{com_voto['id']}/")
    pg.wait_for_selector(".deputados li", timeout=15000)
    confere(com_voto["nome"] in pg.title() and len(pg.title()) <= 62, "título próprio da página do projeto (com o número do projeto, até ~60 caracteres)")
    confere(pg.locator('meta[property="og:image"]').get_attribute("content").endswith("/og.png"), "prévia de compartilhamento")
    confere(pg.locator("h1").inner_text().strip() != "", "página do projeto abre com a tela completa")
    with open(os.path.join(pasta, "dados", "projetos", f"{com_voto['id']}.json"), encoding="utf-8") as f:
        detalhe = json.load(f)
    pg.wait_for_selector(".oficial", state="attached", timeout=15000)
    confere(" ".join(pg.locator(".oficial").first.text_content().split()) == detalhe["ementa"], "ementa do projeto vem do arquivo próprio (projetos/<id>.json)")
    confere(not any(k in projetos[0] for k in ("ementa", "pontos")), "projetos.json (lista) não carrega ementa nem pontos principais")
    confere(os.path.getsize(os.path.join(pasta, "dados", "projetos.json")) < 900_000, "projetos.json abaixo de 900 KB")
    dep = deputados[0]
    pg.goto(f"{base}/deputado/{dep['id']}/")
    pg.wait_for_selector(".cabeca-dep h1", timeout=15000)
    confere(dep["nome"] in pg.title(), "título próprio da página do deputado")
    pg.goto(f"{base}/assunto/{assuntos[0]['slug']}/")
    pg.wait_for_selector(".proj", timeout=15000)
    confere(assuntos[0]["nome"] in pg.title(), "título próprio da página do assunto")
    pg.goto(f"{base}/projeto/{com_voto['id']}/")
    pg.wait_for_selector(".deputados li", timeout=15000)
    pg.locator("a.marca").click()
    pg.wait_for_selector(".tiles", timeout=15000)
    confere(pg.url.split("#")[0].rstrip("/").endswith(f":{porta}"), "logotipo leva ao início")
    confere(not pg.erros, "páginas prontas sem erros no console " + str(pg.erros))

    print("Sitemap")
    r = pg.request.get(base + "/sitemap.xml")
    confere(r.ok and r.text().count("<loc>") > 1000, "sitemap com todas as páginas")

    print("Celular (390 px)")
    pg = nova(390)
    for rota in ["/", f"/#/projeto/{com_voto['id']}", f"/#/deputado/{dep['id']}", "/#/deputados", "/#/assunto/saude"]:
        pg.goto(base + rota)
        pg.wait_for_timeout(1200)
        confere(sem_rolagem_lateral(pg), f"sem rolagem para o lado em {rota}")
    confere(not pg.erros, "celular sem erros no console " + str(pg.erros))

    print("Reflow a 320 px (WCAG 1.4.10, zoom de 400%)")
    pg = nova(320)
    for rota in ["/", f"/#/projeto/{com_voto['id']}", f"/#/deputado/{dep['id']}", "/#/deputados", "/#/assunto/saude", "/#/sobre"]:
        pg.goto(base + rota)
        pg.wait_for_timeout(1000)
        confere(sem_rolagem_lateral(pg), f"sem rolagem para o lado a 320 px em {rota}")

    print("Modo escuro")
    pg = nova(1280, "dark")
    pg.goto(base + f"/#/projeto/{com_voto['id']}")
    pg.wait_for_selector(".deputados li", timeout=15000)
    fundo = pg.evaluate("getComputedStyle(document.body).backgroundColor")
    confere(fundo.startswith("rgb(245, 246, 250)"), "abre no modo claro mesmo com o aparelho no escuro")
    pg.locator(".tema:visible").first.click()
    fundo = pg.evaluate("getComputedStyle(document.body).backgroundColor")
    confere(fundo.startswith("rgb(11, 16, 24)"), "fundo escuro depois de escolher o modo escuro")
    confere(not pg.erros, "modo escuro sem erros no console " + str(pg.erros))

    print("Botão de modo escuro")
    pg = nova(1280, "light")
    pg.goto(base + "/")
    pg.wait_for_selector(".tiles", timeout=15000)
    pg.locator(".tema:visible").first.click()
    confere(pg.evaluate("getComputedStyle(document.body).backgroundColor").startswith("rgb(11, 16, 24)"), "botão liga o modo escuro")
    pg.reload()
    pg.wait_for_selector(".tiles", timeout=15000)
    confere(pg.evaluate("getComputedStyle(document.body).backgroundColor").startswith("rgb(11, 16, 24)"), "escolha continua depois de recarregar")
    pg.locator(".tema:visible").first.click()
    confere(pg.evaluate("getComputedStyle(document.body).backgroundColor").startswith("rgb(245, 246, 250)"), "botão volta ao modo claro")

    print("Em números")
    with open(os.path.join(pasta, "dados", "painel.json"), encoding="utf-8") as f:
        painel = json.load(f)
    pg = nova(1280, "light")
    pg.goto(base + "/#/em-numeros")
    pg.wait_for_selector(".pn-colunas", timeout=15000)
    confere(pg.locator("h1").inner_text() == "Em números", "tela Em números abre")
    confere(pg.locator(".numeros__bloco").count() == 6, "seis blocos: tempo, assunto, resultado, participação, placar e inteligência artificial")
    confere(pg.locator("table").count() == 0, "as tabelas não ficam na tela dos gráficos")
    links = pg.locator(".numeros__tabela a").evaluate_all("els => els.map(a => a.getAttribute('href'))")
    esperados = ["por-mes", "por-assunto", "resultado", "participacao", "placar-votos", "placar-margem", "ia-confianca"]
    confere(links == ["#/em-numeros/" + e for e in esperados], f"cada gráfico tem o seu «Ver como tabela» ({len(links)} links)")
    confere(pg.locator(".numeros__passos li").count() == 4, "inteligência artificial: quatro passos de como é feito")
    confere("não tem um canal para pedir correções" in pg.locator("#pn-t6").locator("xpath=..").inner_text(), "inteligência artificial: diz que ainda não há canal de correções")
    pg.locator(".pn-col").nth(5).hover()
    confere(pg.locator(".pn-dica:visible").count() == 1, "passar o mouse numa coluna mostra os números do mês")
    pg.locator("#pn-t4 ~ .pn-grafico .pn-col").nth(8).hover()
    confere("Votaram, em média" in pg.locator(".pn-dica:visible").inner_text(), "participação: o balão do mês mostra a média de deputados que votaram")
    confere(not pg.erros, "Em números sem erros no console " + str(pg.erros))

    def soma_coluna(pagina, coluna=None):
        return pagina.evaluate("(c) => [...document.querySelectorAll('tbody tr')].reduce((t, tr) => t + (c === null ? [...tr.querySelectorAll('td')].reduce((x, td) => x + Number(td.textContent.replace(/[.]/g, '')), 0) : Number(tr.children[c].textContent.replace(/[.]/g, ''))), 0)", coluna)

    total = painel["totais"]["votacoes"]
    pg.locator('a[href="#/em-numeros/por-mes"]').click()
    pg.wait_for_selector("table", timeout=15000)
    confere(pg.locator("h1").inner_text() == "Votações por mês" and pg.evaluate("location.hash") == "#/em-numeros/por-mes", "«Ver como tabela» abre a tabela numa página própria")
    confere(pg.locator(".pn-colunas").count() == 0, "a página da tabela não repete o gráfico")
    confere(soma_coluna(pg) == total, f"tabela por mês soma o total das votações ({soma_coluna(pg)} de {total})")
    pg.locator("text=Voltar para Em números").click()
    pg.wait_for_selector(".pn-colunas", timeout=15000)
    confere(pg.locator("h1").inner_text() == "Em números", "«Voltar para Em números» volta à tela dos gráficos")
    pg.goto(base + "/#/em-numeros/por-assunto")
    pg.wait_for_selector("table", timeout=15000)
    confere(soma_coluna(pg, 4) == total, f"tabela por assunto soma o total das votações ({soma_coluna(pg, 4)} de {total})")
    pg.goto(base + "/#/em-numeros/placar-votos")
    pg.wait_for_selector("table", timeout=15000)
    votos = painel["placar"]["votos"]
    confere(soma_coluna(pg, 1) == sum(votos.values()), "tabela dos votos soma sim, não, abstenção e obstrução")
    pg.goto(base + "/#/em-numeros/placar-margem")
    pg.wait_for_selector("table", timeout=15000)
    confere(soma_coluna(pg, 1) == painel["placar"]["nominais"] == painel["totais"]["nominais"], "tabela das faixas soma as votações nominais")
    pg.goto(base + "/#/em-numeros/ia-confianca")
    pg.wait_for_selector("table", timeout=15000)
    confere(soma_coluna(pg, 1) == painel["ia"]["projetos"] == soma_coluna(pg, 2) + painel["ia"]["so_ementa"], "tabela de confiança soma os projetos (o resumo descartado fica de fora)")
    pg.goto(base + "/#/em-numeros/participacao")
    pg.wait_for_selector("table", timeout=15000)
    confere(soma_coluna(pg, 1) == painel["totais"]["nominais"], "tabela de participação soma as votações nominais")
    pg.goto(base + "/#/em-numeros/nao-existe")
    pg.wait_for_selector("h1", timeout=15000)
    confere("Não achamos" in pg.locator("h1").inner_text(), "tabela que não existe mostra «não achamos»")
    confere(not pg.erros, "tabelas do Em números sem erros no console " + str(pg.erros))
    for largura in (320, 390):
        for rota in ("", "/por-mes", "/placar-margem"):
            pg = nova(largura, "light")
            pg.goto(base + "/#/em-numeros" + rota)
            pg.wait_for_selector(".pn-colunas, table", timeout=15000)
            confere(sem_rolagem_lateral(pg), f"Em números{rota} sem rolagem para o lado a {largura} px")

    print("Em números sem JavaScript (páginas prontas)")
    sem_js = navegador.new_context(java_script_enabled=False).new_page()
    sem_js.goto(base + "/em-numeros/")
    confere(sem_js.locator("h1").inner_text() == "Em números", "Em números tem conteúdo sem JavaScript")
    confere(sem_js.locator("table").count() == 0, "Em números pronto: tabelas ficam em páginas próprias")
    confere(sem_js.locator('a[href$="/"]:has-text("Ver como tabela")').count() == len(esperados), "Em números pronto: um link de tabela para cada gráfico")
    for e in esperados:
        sem_js.goto(f"{base}/em-numeros/{e}/")
        confere(sem_js.locator("table tbody tr").count() > 0 and sem_js.locator("h1").inner_text() != "", f"/em-numeros/{e}/ pronta com a tabela")
    sem_js.goto(f"{base}/em-numeros/por-mes/")
    confere(sem_js.locator('a:has-text("Voltar para Em números")').get_attribute("href") == "../", "página da tabela volta para Em números")

    print("Buscadores e agentes de IA")
    sem_js = navegador.new_context(java_script_enabled=False).new_page()
    sem_js.goto(base + "/")
    confere(sem_js.locator("h1").inner_text().startswith("Veja como a Câmara votou"), "início tem conteúdo sem JavaScript")
    confere(sem_js.locator('a[href^="assunto/"]').count() == len(assuntos), "início sem JavaScript leva a todos os assuntos")
    sem_js.goto(f"{base}/projeto/{com_voto['id']}/")
    confere(sem_js.locator("h1").inner_text().strip() != "" and sem_js.locator('a[href*="deputado/"]').count() > 100,
            "projeto sem JavaScript lista os deputados com link")
    for rota in ["/", f"/projeto/{com_voto['id']}/", f"/deputado/{dep['id']}/", f"/assunto/{assuntos[0]['slug']}/", "/deputados/", "/sobre/"]:
        sem_js.goto(base + rota)
        blocos = sem_js.locator('script[type="application/ld+json"]').all_inner_texts()
        try:
            ok = bool(blocos) and all(json.loads(b) for b in blocos)
        except ValueError:
            ok = False
        confere(ok, f"dados estruturados válidos em {rota}")
    for arq in ["llms.txt", "openapi.json", "robots.txt", "sitemap.xml", "dados/LEIA-ME.md", "index.md", f"projeto/{com_voto['id']}/index.md"]:
        r = sem_js.request.get(f"{base}/{arq}")
        confere(r.ok and len(r.text()) > 50, f"{arq} existe")
    confere("Content-Signal" in sem_js.request.get(base + "/robots.txt").text(), "robots.txt libera busca e uso por agentes")
    confere(json.loads(sem_js.request.get(base + "/openapi.json").text())["openapi"].startswith("3."), "openapi.json válido")
    pg = nova()
    pg.add_init_script("window.__ferr=[]; document.modelContext={registerTool(t){window.__ferr.push(t.name);return Promise.resolve()}};")
    pg.goto(base + "/")
    pg.wait_for_selector(".tiles", timeout=15000)
    nomes = pg.evaluate("window.__ferr")
    confere(set(nomes) == {"listar_assuntos", "buscar_projetos", "votos_do_projeto", "buscar_deputado", "votos_do_deputado"}, f"ferramentas WebMCP registradas {nomes}")

    navegador.close()
servidor.shutdown()
print()
if falhas:
    print(f"{len(falhas)} verificações falharam.")
    sys.exit(1)
print("Tudo certo.")
