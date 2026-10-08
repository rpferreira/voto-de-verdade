#!/usr/bin/env python3
"""Teste de fumaça do site: abre as telas principais num navegador de verdade e confere o essencial.

Uso (depois de gerar o site com site/gerar_paginas.py --saida _site):
    pip install playwright && playwright install chromium
    python testes/fumaca.py _site

Confere: início (assuntos, últimas votações, busca), assunto, projeto com o voto de cada deputado (o placar
filtra a lista), deputado, deputados por estado, páginas
prontas (título, prévia de compartilhamento), tela estreita sem rolagem para o lado e modo escuro.
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
    confere(pg.locator("h1").inner_text().startswith("Como a Câmara votou"), "título da página inicial")
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
    confere(" | Voto de Verdade" in pg.title(), "título próprio da página do projeto")
    confere(pg.locator('meta[property="og:image"]').get_attribute("content").endswith("/og.png"), "prévia de compartilhamento")
    confere(pg.locator("h1").inner_text().strip() != "", "página do projeto abre com a tela completa")
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

    print("Modo escuro")
    pg = nova(1280, "dark")
    pg.goto(base + f"/#/projeto/{com_voto['id']}")
    pg.wait_for_selector(".deputados li", timeout=15000)
    fundo = pg.evaluate("getComputedStyle(document.body).backgroundColor")
    confere(fundo.startswith("rgb(11, 16, 24)"), "fundo escuro no modo escuro")
    confere(not pg.erros, "modo escuro sem erros no console " + str(pg.erros))

    navegador.close()
servidor.shutdown()
print()
if falhas:
    print(f"{len(falhas)} verificações falharam.")
    sys.exit(1)
print("Tudo certo.")
