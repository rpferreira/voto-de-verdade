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
import datetime
import functools
import http.server
import json
import os
import re
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
        if os.environ.get("GITHUB_ACTIONS"):
            print("::error::" + msg.replace("\n", " "))  # aparece na aba da verificação, sem precisar abrir o registro


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

    def com_tema(pg, tema):
        """O site abre sempre no modo claro (mesmo com o aparelho no escuro); o escuro vem da escolha guardada de quem visita."""
        if tema == "dark":
            pg.add_init_script("try { localStorage.setItem('tema', 'dark'); } catch (e) {}")
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
    confere(pg.locator(".numeros__bloco").count() == 5, "cinco blocos: tempo, assunto, resultado, participação e placar")
    confere(pg.locator("table").count() == 0, "as tabelas não ficam na tela dos gráficos")
    links = pg.locator(".numeros__acoes > a").evaluate_all("els => els.map(a => a.getAttribute('href'))")
    esperados = ["por-mes", "por-assunto", "resultado", "participacao", "placar-votos", "placar-margem"]
    confere(links == ["#/em-numeros/" + e for e in esperados], f"cada gráfico tem o seu «Ver como tabela» ({len(links)} links)")
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
    confere(soma_coluna(pg, 2) == painel["placar"]["nominais"] == painel["totais"]["nominais"], "tabela das faixas soma as votações nominais")
    pg.goto(base + "/#/inteligencia-artificial/confianca")
    pg.wait_for_selector("table", timeout=15000)
    confere(pg.locator(".migalhas a").nth(1).inner_text() == "Transparência da IA", "tabela de confiança é filha da página Transparência da IA")
    confere(pg.locator("text=Voltar para Transparência da IA").count() == 1, "tabela de confiança volta para Transparência da IA")
    confere(soma_coluna(pg, 1) == painel["ia"]["projetos"] == soma_coluna(pg, 2) + painel["ia"]["so_ementa"], "tabela de confiança soma os projetos (o resumo descartado fica de fora)")
    pg.goto(base + "/#/em-numeros/participacao")
    pg.wait_for_selector("table", timeout=15000)
    confere(soma_coluna(pg, 1) == painel["totais"]["nominais"], "tabela de participação soma as votações nominais")
    # filtro por ano
    pg = nova(1280, "light")
    pg.goto(base + "/#/em-numeros")
    pg.wait_for_selector(".pn-colunas", timeout=15000)
    anos = painel["anos"]
    confere(pg.locator("#ano-n option").count() == len(anos) + 1, f"filtro de ano: todos os anos e mais {len(anos)} anos")
    ano = anos[2]
    do_ano = painel["por_ano"][ano]
    pg.select_option("#ano-n", ano)
    confere(pg.locator(".numeros__lead").inner_text().startswith(f"{do_ano['totais']['votacoes']} votações"), f"filtro de ano: o total passa a ser o de {ano} ({do_ano['totais']['votacoes']})")
    confere(pg.evaluate("location.hash") == f"#/em-numeros?ano={ano}", "filtro de ano: o ano vai para o endereço")
    confere(pg.locator(".pn-grafico").first.locator(".pn-col").count() == len(do_ano["meses"]), f"filtro de ano: o gráfico mostra os {len(do_ano['meses'])} meses de {ano}")
    confere(pg.locator('.numeros__acoes > a[href$="por-mes?ano=%s"]' % ano).count() == 1, "filtro de ano: «Ver como tabela» leva o ano junto")
    confere(pg.locator(".numeros__bloco").count() == 5 and pg.locator("#ano-n").input_value() == ano, "filtro de ano: os cinco blocos continuam e o filtro fica no ano")
    pg.goto(base + f"/#/em-numeros?ano={ano}")
    pg.reload()
    pg.wait_for_selector(".pn-colunas", timeout=15000)
    confere(pg.locator("#ano-n").input_value() == ano, "filtro de ano: abrir o endereço com o ano já traz o filtro marcado")
    pg.locator('.numeros__acoes > a[href$="por-mes?ano=%s"]' % ano).click()
    pg.wait_for_selector("table", timeout=15000)
    confere(soma_coluna(pg) == do_ano["totais"]["votacoes"], f"filtro de ano: a tabela por mês de {ano} soma {do_ano['totais']['votacoes']}")
    confere(pg.locator(".migalhas a").nth(1).get_attribute("href") == f"#/em-numeros?ano={ano}", "filtro de ano: a migalha volta para Em números no mesmo ano")
    # exportar CSV e JSON
    with pg.expect_download() as d:
        pg.locator("button:has-text('Baixar CSV')").first.click()
    arq = d.value
    texto = open(arq.path(), encoding="utf-8-sig").read()
    linhas = texto.strip().splitlines()
    confere(arq.suggested_filename == f"voto-de-verdade-por-mes-{ano}.csv", f"exportar: nome do arquivo CSV ({arq.suggested_filename})")
    confere(linhas[0] == "Mês,Nominais,Simbólicas,Secretas" and len(linhas) == 1 + len(do_ano["meses"]), "exportar: CSV com cabeçalho e uma linha por mês")
    confere(sum(int(c) for l in linhas[1:] for c in l.split(",")[1:]) == do_ano["totais"]["votacoes"], "exportar: o CSV soma o total do ano")
    confere(open(arq.path(), "rb").read(3) == b"\xef\xbb\xbf", "exportar: CSV com marca UTF-8 para abrir certo na planilha")
    with pg.expect_download() as d:
        pg.locator("button:has-text('Baixar JSON')").first.click()
    dj = json.load(open(d.value.path(), encoding="utf-8"))
    confere(d.value.suggested_filename == f"voto-de-verdade-por-mes-{ano}.json" and dj["filtros"] == {"ano": int(ano)} and len(dj["dados"]) == len(do_ano["meses"]), "exportar: JSON com o filtro e os dados do ano")
    confere(dj["dados"][0].keys() == {"mes": 0, "nominais": 0, "simbolicas": 0, "secretas": 0}.keys() and "fonte" in dj and dj["gerado_em"] == painel["gerado_em"], "exportar: JSON traz fonte, data e as chaves dos dados")
    pg.goto(base + f"/#/em-numeros?ano={ano}")
    pg.wait_for_selector(".pn-colunas", timeout=15000)
    confere(pg.locator(".exportar").count() == 6, "exportar: cada um dos seis gráficos tem os botões de CSV e JSON")
    with pg.expect_download() as d:
        pg.locator("#pn-t5 ~ .numeros__acoes button:has-text('Baixar CSV')").first.click()
    t_votos = open(d.value.path(), encoding="utf-8-sig").read().strip().splitlines()
    confere(d.value.suggested_filename == f"voto-de-verdade-placar-votos-{ano}.csv" and sum(int(l.split(",")[1]) for l in t_votos[1:]) == sum(do_ano["placar"]["votos"].values()), "exportar: o CSV do placar soma os votos do ano")
    confere(not pg.erros, "filtro de ano e exportação sem erros no console " + str(pg.erros))

    pg.goto(base + "/#/inteligencia-artificial")
    pg.wait_for_selector("#titulo-ia", timeout=15000)
    confere(pg.locator("h1").inner_text() == "Transparência da IA", "página Transparência da IA abre")
    confere(pg.locator(".numeros__passos li").count() == 4, "inteligência artificial: quatro passos de como é feito")
    confere("não tem um canal para pedir correções" in pg.locator("main, #principal, body").first.inner_text(), "inteligência artificial: diz que ainda não há canal de correções")
    confere(pg.locator(".numeros__acoes > a").evaluate_all("els => els.map(a => a.getAttribute('href'))") == ["#/inteligencia-artificial/confianca"], "inteligência artificial: só a confiança tem «Ver como tabela»")
    confere(pg.locator(".exportar").count() == 1, "inteligência artificial: CSV e JSON só no bloco «Confiança»")
    confere(pg.locator('[aria-labelledby="ia-t1"] .exportar, [aria-labelledby="ia-t2"] .exportar, [aria-labelledby="ia-t4"] .exportar, [aria-labelledby="ia-t5"] .exportar, [aria-labelledby="ia-t1"] .numeros__acoes, [aria-labelledby="ia-t2"] .numeros__acoes, [aria-labelledby="ia-t4"] .numeros__acoes, [aria-labelledby="ia-t5"] .numeros__acoes').count() == 0, "inteligência artificial: «O que faz», «Como é feito», «Avisos» e «Limites» sem tabela nem exportação")
    confere(pg.locator("#ano-n").count() == 0, "inteligência artificial: sem filtro de ano (não depende do ano da votação)")
    with pg.expect_download() as d:
        pg.locator("#ia-t3 ~ .numeros__acoes button:has-text('Baixar CSV')").click()
    t_ia = open(d.value.path(), encoding="utf-8-sig").read().strip().splitlines()
    confere(d.value.suggested_filename == "voto-de-verdade-confianca.csv" and t_ia[0] == "Confiança,Assunto,Resumo" and sum(int(l.split(",")[1]) for l in t_ia[1:]) == painel["ia"]["projetos"], "inteligência artificial: o CSV da confiança soma os projetos")
    with pg.expect_download() as d:
        pg.locator("#ia-t3 ~ .numeros__acoes button:has-text('Baixar JSON')").click()
    confere(len(json.load(open(d.value.path(), encoding="utf-8"))["dados"]) == 3, "inteligência artificial: o JSON da confiança traz os três níveis")
    confere(pg.locator("#nav-ia").get_attribute("aria-current") == "page", "menu marca Transparência da IA como a página atual")
    pg.goto(base + "/#/inteligencia-artificial/em-numeros")
    pg.wait_for_selector("h1", timeout=15000)
    confere("Não achamos" in pg.locator("h1").inner_text(), "tabela que não é da IA não abre em /inteligencia-artificial/")
    pg.goto(base + "/#/em-numeros/nao-existe")
    pg.wait_for_selector("h1", timeout=15000)
    confere("Não achamos" in pg.locator("h1").inner_text(), "tabela que não existe mostra «não achamos»")
    confere(not pg.erros, "tabelas do Em números sem erros no console " + str(pg.erros))
    for largura in (320, 390):
        for rota in ("", "/por-mes", "/placar-margem", "?ano=2025"):
            pg = nova(largura, "light")
            pg.goto(base + "/#/em-numeros" + rota)
            pg.wait_for_selector(".pn-colunas, table", timeout=15000)
            confere(sem_rolagem_lateral(pg), f"Em números{rota} sem rolagem para o lado a {largura} px")

    print("Filtro por ano e exportação nas outras telas")
    def baixar_csv(pagina, seletor):
        with pagina.expect_download() as d:
            pagina.locator(seletor).first.click()
        return d.value, open(d.value.path(), encoding="utf-8-sig").read().strip().splitlines()

    # assunto: filtro por ano e exportar
    slug = max(assuntos, key=lambda a: a["n"])["slug"]
    base_a = [p for p in projetos if p["a"] == slug or p["s"] == slug]
    ano_a = sorted({p["ultima"][:4] for p in base_a})[-2]
    esperados_a = [p for p in base_a if p["ultima"][:4] == ano_a]
    pg = nova(1280, "light")
    pg.goto(base + f"/#/assunto/{slug}?todos=1&ano={ano_a}")
    pg.wait_for_selector(".projetos li", timeout=15000)
    confere(pg.locator("#ano-a").input_value() == ano_a and pg.locator("details.mais-filtros").evaluate("e => e.open"), "assunto: o ano do endereço vem marcado e os filtros abertos")
    confere(pg.locator(".estado").inner_text().startswith(str(len(esperados_a)) + " projeto"), f"assunto: filtro por {ano_a} mostra {len(esperados_a)} projetos")
    arq, linhas = baixar_csv(pg, "button:has-text('Baixar CSV')")
    confere(arq.suggested_filename == f"voto-de-verdade-projetos-{slug}-{ano_a}.csv" and len(linhas) >= 1 + len(esperados_a), f"assunto: o CSV traz os {len(esperados_a)} projetos do ano ({arq.suggested_filename})")
    confere(linhas[0].startswith("Código,Projeto,Título,Assunto,Data da última votação"), "assunto: cabeçalho do CSV")
    confere(not pg.erros, "assunto com filtro de ano sem erros no console " + str(pg.erros))

    # deputados: exportar a lista
    pg = nova(1280, "light")
    pg.goto(base + "/#/deputados")
    pg.wait_for_selector(".lista-dep li", timeout=15000)
    arq, linhas = baixar_csv(pg, "button:has-text('Baixar CSV')")
    confere(arq.suggested_filename == "voto-de-verdade-deputados.csv" and len(linhas) == 1 + len(deputados), f"deputados: o CSV traz todos os {len(deputados)} deputados")
    pg.fill("#busca-d", deputados[0]["nome"].split()[0])
    pg.wait_for_timeout(600)
    arq, linhas = baixar_csv(pg, "button:has-text('Baixar CSV')")
    confere(0 < len(linhas) - 1 < len(deputados), "deputados: o CSV respeita a busca da tela")

    # deputado: filtro por ano e exportar
    with open(os.path.join(pasta, "dados", "votacoes.json"), encoding="utf-8") as f:
        data_da = {v["id"]: v["d"] for v in json.load(f)}
    achou = None
    for d in deputados:
        caminho = os.path.join(pasta, "dados", "deputados", f"{d['id']}.json")
        if os.path.exists(caminho):
            v = json.load(open(caminho, encoding="utf-8"))["v"]
            if len(v) >= 40:
                achou = (d, v)
                break
    dep, votos_dep = achou
    ano_d = sorted({data_da[vid][:4] for vid, _ in votos_dep if vid in data_da})[-1]
    n_ano = sum(1 for vid, _ in votos_dep if vid in data_da and data_da[vid][:4] == ano_d)
    pg = nova(1280, "light")
    pg.goto(base + f"/#/deputado/{dep['id']}?ano={ano_d}")
    pg.wait_for_selector(".votos-dep li", timeout=15000)
    confere(pg.locator("#dep-ano").input_value() == ano_d, "deputado: o ano do endereço vem marcado")
    confere(pg.locator(".estado").inner_text().startswith(f"{n_ano} votaç"), f"deputado: filtro por {ano_d} mostra {n_ano} votações")
    arq, linhas = baixar_csv(pg, "button:has-text('Baixar CSV')")
    confere(arq.suggested_filename == f"voto-de-verdade-votos-{dep['id']}-{ano_d}.csv" and len(linhas) == 1 + n_ano, f"deputado: o CSV traz as {n_ano} votações do ano")
    confere(all(l.split(",")[0].startswith(ano_d) for l in linhas[1:]), "deputado: todas as linhas do CSV são do ano escolhido")
    pg.locator("#limpar-d").click()
    confere(pg.locator("#dep-ano").input_value() == "", "deputado: Limpar filtros também limpa o ano")

    # projeto: exportar os votos de cada deputado
    pg = nova(1280, "light")
    pg.goto(base + f"/#/projeto/{com_voto['id']}")
    pg.wait_for_selector(".deputados .deputado", timeout=15000)
    arq, linhas = baixar_csv(pg, ".votos-projeto button:has-text('Baixar CSV')")
    confere(arq.suggested_filename.startswith("voto-de-verdade-votos-") and linhas[0] == "Código do deputado,Deputado,Partido na data,UF,Voto" and len(linhas) > 100, "projeto: o CSV dos votos traz um deputado por linha")
    confere(not pg.erros, "projeto, deputado e deputados sem erros no console " + str(pg.erros))

    print("Campos com o texto inteiro à vista")
    # O valor escolhido (e o texto de exemplo) de cada campo tem de caber; antes, "Mais recentes primeiro" aparecia cortado.
    medir = """async () => {
      const c = document.createElement('canvas').getContext('2d'), cortados = [];
      const largura = async (el, texto) => { const cs = getComputedStyle(el); c.font = cs.fontWeight + ' ' + cs.fontSize + ' ' + cs.fontFamily; await document.fonts.load(c.font, texto); return [c.measureText(texto).width, el.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight)]; };
      for (const s of document.querySelectorAll('select')) {
        if (!s.offsetParent || s.id === 'sel-votacao') continue;   // escondido, ou a lista de votações (rótulo longo, já abreviado com …)
        const [w, d] = await largura(s, s.options[s.selectedIndex].text); if (w > d + 1) cortados.push(s.id + ': ' + s.options[s.selectedIndex].text);
      }
      for (const i of document.querySelectorAll('input[type=search]')) {
        if (!i.offsetParent || !i.placeholder) continue;
        const [w, d] = await largura(i, i.placeholder); if (w > d + 1) cortados.push(i.id + ' (exemplo): ' + i.placeholder);
      }
      return cortados;
    }"""
    for largura in (390, 1024, 1280):
        pg = nova(largura)
        for rota in ["/", "/#/assunto/saude", f"/#/projeto/{com_voto['id']}", f"/#/deputado/{dep['id']}", "/#/deputados"]:
            pg.goto(base + rota)
            pg.wait_for_timeout(700)
            pg.evaluate("document.fonts.ready")
            pg.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
            if rota.startswith("/#/deputado/"):  # com o assunto de nome mais longo escolhido
                pg.evaluate("(() => { const s = document.querySelector('#dep-a'); if (s) { s.value = [...s.options].sort((a, b) => b.text.length - a.text.length)[0].value; } })()")
            corte = pg.evaluate(medir)
            confere(not corte, f"campos sem texto cortado em {rota} ({largura}px)" + (f" {corte}" if corte else ""))

    print("Caixas de marcar alinhadas com o texto")
    for largura in (390, 1280):
        pg = nova(largura)
        for rota in ["/#/assunto/saude", "/#/deputados"]:
            pg.goto(base + rota)
            pg.wait_for_selector(".marcar", state="attached", timeout=15000)
            pg.evaluate("document.fonts.ready")
            pg.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
            desvios = pg.evaluate("""() => [...document.querySelectorAll('.marcar')].filter(l => l.offsetParent).map(l => {
              const i = l.querySelector('input').getBoundingClientRect(), r = document.createRange();
              r.selectNodeContents(l.querySelector('span')); const t = r.getClientRects()[0];
              return Math.abs((i.top + i.height / 2) - (t.top + t.height / 2)); })""")
            confere(bool(desvios) and max(desvios) <= 2, f"caixa de marcar centrada na primeira linha em {rota} ({largura}px) {desvios}")

    print("Faixa de uso de IA discreta")
    # Já aconteceu de outra regra (".resumo-projeto p") anular o estilo da faixa: ela voltava a 18px, colada no resumo.
    for largura in (390, 1280):
        pg = nova(largura)
        pg.goto(base + f"/#/projeto/{com_voto['id']}")
        pg.wait_for_selector(".rotulo-ia", timeout=15000)
        info = pg.evaluate("""() => [...document.querySelectorAll('.rotulo-ia')].map(e => { const n = e.nextElementSibling;
          return [parseFloat(getComputedStyle(e).fontSize), n ? Math.round(n.getBoundingClientRect().top - e.getBoundingClientRect().bottom) : 99]; })""")
        confere(bool(info) and all(f == 12 and g == 8 for f, g in info), f"faixa de IA com fonte 12px e 8px de respiro do resumo ({largura}px) {info}")

    print("Contagem colada na caixa de filtros")
    medir_dist = """() => [...document.querySelectorAll('.estado')].filter(e => e.offsetParent && e.previousElementSibling && e.previousElementSibling.classList.contains('filtros'))
              .map(e => Math.round(e.getBoundingClientRect().top - e.previousElementSibling.getBoundingClientRect().bottom))"""
    for largura in (390, 1280):
        for rota in ["/#/assunto/saude", "/#/assunto/saude?todos=1", "/#/deputados", f"/#/deputado/{dep['id']}", f"/#/projeto/{com_voto['id']}"]:
            pg = nova(largura)  # página nova a cada rota: ao trocar só o # a tela anterior ainda poderia contar
            pg.goto(base + rota)
            try:  # a página monta a lista aos poucos: espera a contagem aparecer ao lado da caixa
                pg.wait_for_function("(" + medir_dist + ")().length > 0", polling=100, timeout=15000)
            except Exception:
                pass
            dist = pg.evaluate(medir_dist)
            confere(bool(dist) and max(dist) <= 4, f"contagem a no máximo 4px da caixa de filtros em {rota} ({largura}px) {dist}")
            pg.context.close()  # páginas abertas em segundo plano ficam lentas para montar a tela

    print("Cabeçalho e menu (aparência)")
    # Mede o que já saiu torto: links colados no computador, itens do menu sem divisória ou com cantos que não acompanham a caixa,
    # texto ilegível no item da página atual.
    cabecalho_js = """() => {
      const cx = document.createElement('canvas').getContext('2d');
      const rgb = (cor) => { cx.clearRect(0, 0, 1, 1); cx.fillStyle = '#000'; cx.fillStyle = cor; cx.fillRect(0, 0, 1, 1); const d = cx.getImageData(0, 0, 1, 1).data; return [d[0], d[1], d[2], d[3] / 255]; };
      const lum = ([r, g, b]) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
      const fundo = (el) => { let e = el; while (e) { const c = rgb(getComputedStyle(e).backgroundColor); if (c[3] > 0.9) return c; e = e.parentElement; } return [255, 255, 255, 1]; };
      const mistura = (topo, base) => topo[3] >= 1 ? topo : [0, 1, 2].map((i) => topo[i] * topo[3] + base[i] * (1 - topo[3]));
      const contraste = (el) => { const base = fundo(el.parentElement), c = rgb(getComputedStyle(el).backgroundColor), f = c[3] > 0 ? mistura(c, base) : base;
        const t = rgb(getComputedStyle(el).color), a = lum(f), b = lum(t); return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05); };
      const r = (el) => el.getBoundingClientRect();
      const topo = document.querySelector('.topo'), saida = { topoAltura: Math.round(r(topo).height), rolagem: document.documentElement.scrollWidth - window.innerWidth };
      const links = [...document.querySelectorAll('.topo__acoes > nav a')].filter((a) => a.offsetParent);
      saida.nav = links.length;
      saida.espacoEntreLinks = links.slice(1).map((a, i) => Math.round(r(a).left - r(links[i]).right));
      saida.paddingLinks = links.map((a) => parseFloat(getComputedStyle(a).paddingLeft));
      const atual = links.find((a) => a.getAttribute('aria-current') === 'page'); saida.contrasteAtualTopo = atual ? contraste(atual) : null;
      const menu = document.querySelector('#menu-topo');
      if (menu && menu.matches(':popover-open')) {
        const itens = [...menu.querySelectorAll('li > a')], cm = getComputedStyle(menu);
        saida.menuItens = itens.length;
        saida.alturaItens = itens.map((a) => Math.round(r(a).height));
        saida.divisorias = [...menu.querySelectorAll('ul > li + li')].map((li) => getComputedStyle(li).boxShadow !== 'none');
        saida.raioCaixa = parseFloat(cm.borderTopLeftRadius); saida.respiroCaixa = parseFloat(cm.paddingLeft);
        saida.raioItens = itens.map((a) => parseFloat(getComputedStyle(a).borderTopLeftRadius));
        saida.dentro = r(menu).left >= 0 && r(menu).right <= window.innerWidth;
        const cur = itens.find((a) => a.getAttribute('aria-current') === 'page'); saida.contrasteAtualMenu = cur ? contraste(cur) : null;
      }
      return saida;
    }"""
    for caminho, nome in (("/", "PT"), ("/en/", "EN")):
        for tema in ("light", "dark"):
            pg = com_tema(nova(1280, tema), tema)
            pg.goto(base + caminho)
            pg.wait_for_selector(".topo nav a", timeout=15000)
            m = pg.evaluate(cabecalho_js)
            rot = f"{nome} computador {tema}"
            confere(m["nav"] >= 4 and all(e >= 8 for e in m["espacoEntreLinks"]), f"{rot}: links do topo com respiro entre si {m['espacoEntreLinks']}")
            confere(all(x >= 16 for x in m["paddingLinks"]), f"{rot}: links do topo com 16px de folga lateral {sorted(set(m['paddingLinks']))}")
            confere(m["topoAltura"] <= 80 and m["rolagem"] <= 1, f"{rot}: topo em uma linha, sem rolagem lateral (altura {m['topoAltura']}px)")
            confere(m["contrasteAtualTopo"] is not None and m["contrasteAtualTopo"] >= 4.5, f"{rot}: item atual legível, contraste {m['contrasteAtualTopo'] and round(m['contrasteAtualTopo'], 1)}")
            pg.context.close()
            pg = com_tema(nova(390, tema), tema)
            pg.goto(base + caminho)
            pg.wait_for_selector(".menu-botao", state="visible", timeout=15000)
            pg.click(".menu-botao")
            pg.wait_for_function("document.querySelector('#menu-topo').matches(':popover-open')", polling=100, timeout=15000)
            m = pg.evaluate(cabecalho_js)
            rot = f"{nome} celular {tema}"
            confere(m["nav"] == 0 and m["rolagem"] <= 1, f"{rot}: links saem do topo e vão para o menu, sem rolagem lateral")
            confere(m["menuItens"] >= 4 and all(h >= 48 for h in m["alturaItens"]), f"{rot}: itens do menu com 48px ou mais {m['alturaItens']}")
            confere(m["divisorias"] and all(m["divisorias"]), f"{rot}: divisória discreta entre os itens do menu")
            confere(all(abs(x - (m["raioCaixa"] - m["respiroCaixa"])) <= 1 for x in m["raioItens"]), f"{rot}: cantos dos itens acompanham a caixa (caixa {m['raioCaixa']}px, respiro {m['respiroCaixa']}px, itens {sorted(set(m['raioItens']))})")
            confere(m["dentro"], f"{rot}: menu cabe na tela")
            confere(m["contrasteAtualMenu"] is not None and m["contrasteAtualMenu"] >= 4.5, f"{rot}: item atual do menu legível, contraste {m['contrasteAtualMenu'] and round(m['contrasteAtualMenu'], 1)}")
            pg.context.close()

    print("Primeira visita leve (tela inicial)")
    # O arquivo dos destaques é feito pelo mesmo script da exportação diária; se ficar velho, a tela inicial mostraria votações erradas.
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site"))
    import destaques as destaques_inicio
    import novos
    with open(os.path.join(pasta, "dados", "destaques.json"), encoding="utf-8") as f:
        confere(json.load(f) == json.loads(json.dumps(destaques_inicio.montar_destaques(json.load(open(os.path.join(pasta, "dados", "votacoes.json"), encoding="utf-8")), projetos, novos.datas(novos.carregar())))), "destaques.json confere com projetos.json, votacoes.json e primeira_vez.json (não está velho)")
    # A tela inicial mostra 10 votações em destaque e não pode baixar projetos.json e votacoes.json (cerca de 156 KB
    # comprimidos) antes de a pessoa buscar: os destaques vêm prontos em dados/destaques.json.
    for caminho, nome in (("/", "PT"), ("/en/", "EN")):
        pg = nova(390)
        baixados = []
        pg.on("request", lambda r: baixados.append(r.url.split("?")[0].split("/dados/")[-1]) if "/dados/" in r.url else None)
        pg.goto(base + caminho)
        pg.wait_for_selector("#t-recentes", timeout=15000)
        pg.wait_for_selector("#t-apertadas", timeout=15000)
        pg.wait_for_timeout(500)
        confere(pg.locator("#t-recentes ~ ul > li").count() == 5 and pg.locator("#t-apertadas ~ ul > li").count() == 5, f"{nome}: tela inicial mostra 5 últimas votações e 5 decididas por pouco")
        confere("projetos.json" not in baixados and "votacoes.json" not in baixados, f"{nome}: tela inicial sem baixar projetos.json nem votacoes.json {baixados}")
        confere("destaques.json" in baixados, f"{nome}: destaques vêm de dados/destaques.json")
        if nome == "EN":
            confere("en/destaques.json" in baixados, "EN: títulos em inglês dos destaques vêm de dados/en/destaques.json")
            primeiro = pg.locator("#t-recentes ~ ul > li .proj__titulo").first.inner_text()
            confere(not primeiro.startswith("O projeto") and not primeiro.startswith("Muda "), f"EN: título do primeiro destaque em inglês ({primeiro[:50]})")
        pg.fill("#busca", "vacina" if nome == "PT" else "treaty")
        pg.wait_for_selector("#t-projetos", timeout=15000)
        confere("projetos.json" in baixados and "votacoes.json" in baixados, f"{nome}: a busca baixa projetos.json e votacoes.json só quando é usada")
        pg.context.close()

    print("Lista de deputados parece clicável")
    # Cada deputado da busca tem de parecer um link: cartão com borda e seta à direita (antes era só texto solto, sem pista de clique).
    for largura in (390, 1280):
        for tema in ("light", "dark"):
            pg = com_tema(nova(largura, tema), tema)
            pg.goto(base + "/#/deputados")
            pg.wait_for_selector(".linha-dep", timeout=15000)
            m = pg.evaluate("""() => { const a = document.querySelector('.linha-dep'), cs = getComputedStyle(a), seta = getComputedStyle(a, '::after'), r = a.getBoundingClientRect();
              return { link: a.tagName === 'A' && a.getAttribute('href').startsWith('#/deputado/'), altura: Math.round(r.height), borda: cs.boxShadow !== 'none',
                       fundo: getComputedStyle(a).backgroundColor, seta: parseFloat(seta.width) >= 16 && seta.content !== 'none' && seta.backgroundColor !== 'rgba(0, 0, 0, 0)' }; }""")
            rot = f"{largura}px {tema}"
            confere(m["link"] and m["altura"] >= 48, f"deputado da lista é link com área de toque de 48px ou mais ({rot}, {m['altura']}px)")
            confere(m["borda"] and m["fundo"] != "rgba(0, 0, 0, 0)", f"deputado da lista tem cara de cartão: borda e fundo ({rot})")
            confere(m["seta"], f"deputado da lista tem seta à direita ({rot})")
            pg.context.close()

    print("Fotos dos deputados leves")
    # A foto é mostrada com 96 px de largura: guardamos no máximo 192 px (nítida em tela de alta densidade), ~8 KB cada.
    def tamanho_jpeg(caminho):
        with open(caminho, "rb") as f:
            d = f.read()
        i = 2
        while i < len(d):
            if d[i] != 0xFF:
                i += 1
                continue
            marca = d[i + 1]
            if marca in (0xC0, 0xC1, 0xC2):  # início do quadro: altura e largura
                return int.from_bytes(d[i + 7:i + 9], "big"), int.from_bytes(d[i + 5:i + 7], "big")
            i += 2 + int.from_bytes(d[i + 2:i + 4], "big")
        return 0, 0
    pasta_fotos = os.path.join(pasta, "fotos")
    arquivos = sorted(os.listdir(pasta_fotos))
    medidas = [(a, tamanho_jpeg(os.path.join(pasta_fotos, a)), os.path.getsize(os.path.join(pasta_fotos, a))) for a in arquivos]
    largas = [a for a, (l, _), _ in medidas if l > 192]
    pesadas = [(a, t // 1024) for a, _, t in medidas if t > 24 * 1024]
    pequenas = [a for a, (l, _), _ in medidas if l < 96]
    confere(len(arquivos) >= 600 and not largas, f"{len(arquivos)} fotos, nenhuma com mais de 192 px de largura {largas[:3]}")
    confere(not pesadas, f"nenhuma foto com mais de 24 KB {pesadas[:3]}")
    confere(not pequenas, f"nenhuma foto menor que os 96 px mostrados {pequenas[:3]}")
    confere(sum(t for _, _, t in medidas) < 8 * 1024 * 1024, f"fotos somam {sum(t for _, _, t in medidas) / 1e6:.1f} MB (limite: 8 MB)")
    pg = nova(390)
    pg.goto(base + f"/#/deputado/{dep['id']}")
    pg.wait_for_selector("img.foto-dep", timeout=15000)
    pg.wait_for_function("document.querySelector('img.foto-dep').complete && document.querySelector('img.foto-dep').naturalWidth > 0", polling=100, timeout=15000)
    confere(pg.evaluate("document.querySelector('img.foto-dep').naturalWidth") >= 96, "foto do deputado carrega e não é menor que o espaço em que aparece")
    pg.context.close()

    print("Situações em destaque (pílula)")
    # "Fora do exercício agora" e "votação simbólica/secreta" são informações que mudam como o dado é lido: ficam em pílula, não em texto solto.
    fora = next(d for d in deputados if not d["ex"])
    em_exercicio = next(d for d in deputados if d["ex"])
    for caminho, nome in (("", "PT"), ("/en", "EN")):
        pg = nova(390)
        pg.goto(base + f"{caminho}/#/deputados?q={fora['nome'].split()[0]}")
        pg.wait_for_selector(".linha-dep", timeout=15000)
        pill = pg.locator(f".linha-dep[href='#/deputado/{fora['id']}'] .selo-aviso")
        confere(pill.count() == 1 and pill.inner_text() == ("Fora do exercício agora" if nome == "PT" else "Not in office now"), f"{nome}: deputado fora do exercício aparece com pílula na lista")
        pg.goto(base + f"{caminho}/#/deputados?q={em_exercicio['nome'].split()[0]}")
        pg.wait_for_selector(".linha-dep", timeout=15000)
        confere(pg.locator(f".linha-dep[href='#/deputado/{em_exercicio['id']}'] .selo-aviso").count() == 0, f"{nome}: deputado em exercício não tem pílula")
        pg.goto(base + f"{caminho}/#/deputado/{fora['id']}")
        pg.wait_for_selector(".cabeca-dep", timeout=15000)
        confere(pg.locator(".cabeca-dep .selo-aviso").count() == 1 and pg.locator(".cabeca-dep .selo-aviso").inner_text() == ("Fora do exercício agora" if nome == "PT" else "Not in office now"), f"{nome}: página do deputado fora do exercício tem pílula no cabeçalho")
        pg.context.close()
    pg = nova(390)
    pg.goto(base + "/#/assunto/saude?todos=1")
    pg.wait_for_selector("ul.projetos .proj", timeout=15000)
    simbolicas = pg.locator(".proj__meta .selo-info")
    confere(simbolicas.count() > 0 and simbolicas.first.evaluate("e => getComputedStyle(e).borderRadius") != "0px", "votação simbólica ou secreta aparece em pílula nas listas de projetos")
    pg.context.close()

    print("Etiqueta «Novo» nas últimas votações")
    # Regras: só vale para projetos que entraram no site depois de o registro começar, só em «Últimas votações» da tela inicial,
    # e some depois de DIAS_COMO_NOVO dias. O registro (site/novos.py) começa com todos os projetos de hoje como «já existia».
    reg = novos.atualizar(None, [1, 2], "2026-01-01")
    confere(reg == {"desde": "2026-01-01", "projetos": {"1": None, "2": None}} and novos.datas(reg) == {}, "registro novo: todos os projetos existentes valem «já existia» (nada vira Novo de uma vez)")
    reg2 = novos.atualizar(reg, [1, 2, 3], "2026-01-05")
    confere(novos.datas(reg2) == {"3": "2026-01-05"} and novos.atualizar(reg2, [1, 2, 3], "2026-02-01") == reg2, "projeto que chega depois recebe a data de entrada, e só na primeira vez")
    prazo_js = re.search(r"const DIAS_COMO_NOVO = (\d+);", open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site", "app.js"), encoding="utf-8").read())
    confere(prazo_js and int(prazo_js.group(1)) == novos.DIAS_COMO_NOVO, f"prazo da etiqueta igual no aplicativo e em site/novos.py ({novos.DIAS_COMO_NOVO} dias)")
    hoje_utc = datetime.datetime.now(datetime.timezone.utc).date()

    def dias_atras(n):
        return (hoje_utc - datetime.timedelta(days=n)).isoformat()

    for caminho, nome, esperado in (("/", "PT", "novo"), ("/en/", "EN", "new")):
        for tema in ("light", "dark"):
            pg = com_tema(nova(390, tema), tema)
            def adulterar(rota):
                resp = rota.fetch()
                d = json.loads(resp.text())
                for lista, datas_ in ((d["recentes"], [dias_atras(0), dias_atras(6), dias_atras(8), None, dias_atras(1)]), (d["apertadas"], [dias_atras(0)] * 5)):
                    for it, quando in zip(lista, datas_):
                        if quando:
                            it["p"]["inc"] = quando
                        else:
                            it["p"].pop("inc", None)
                rota.fulfill(response=resp, body=json.dumps(d))
            pg.route("**/dados/destaques.json", adulterar)
            pg.goto(base + caminho)
            pg.wait_for_selector("#t-recentes ~ ul > li", timeout=15000)
            etiquetas = pg.locator("#t-recentes ~ ul > li .selo-novo")
            # a etiqueta vem logo depois da data, na mesma linha
            depois_da_data = pg.evaluate("""() => { const e = document.querySelector('#t-recentes ~ ul .selo-novo'), ant = e.previousElementSibling, r1 = ant.getBoundingClientRect(), r2 = e.getBoundingClientRect();
              return /\\d{4}/.test(ant.textContent) && r2.left >= r1.right && Math.abs((r1.top + r1.height / 2) - (r2.top + r2.height / 2)) < 4; }""")
            confere(depois_da_data, f"{nome} {tema}: «Novo» fica logo depois da data, na mesma linha")
            confere(etiquetas.count() == 3 and etiquetas.first.inner_text().lower() == esperado, f"{nome} {tema}: 3 de 5 últimas votações com «Novo» (hoje, 6 dias e 1 dia); 8 dias e sem data ficam sem")
            confere(pg.locator("#t-apertadas ~ ul .selo-novo").count() == 0, f"{nome} {tema}: «Decididas por pouco» nunca mostra «Novo»")
            contraste = pg.evaluate("""() => { const e = document.querySelector('.selo-novo'), cs = getComputedStyle(e);
              const rgb = (c) => c.match(/[\\d.]+/g).slice(0, 3).map(Number); const lum = ([r, g, b]) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
              const a = lum(rgb(cs.color)), b = lum(rgb(cs.backgroundColor)); return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05); }""")
            confere(contraste >= 4.5, f"{nome} {tema}: «Novo» legível, contraste {contraste:.1f}")
            pg.context.close()
    pg = nova(390)
    pg.goto(base + "/")
    pg.wait_for_selector("#t-recentes ~ ul > li", timeout=15000)
    confere(pg.locator(".selo-novo").count() == 0, "com os dados de hoje (nenhum projeto entrou depois do registro começar) não há «Novo»")
    pg.goto(base + "/#/assunto/saude?todos=1")
    pg.wait_for_selector("ul.projetos .proj", timeout=15000)
    pg.context.close()

    print("Versão no rodapé")
    versao_site = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "VERSION"), encoding="utf-8").read().strip()
    for caminho, nome, esperado in (("/", "PT", f"Versão {versao_site} (beta)"), ("/en/", "EN", f"Version {versao_site} (beta)")):
        for largura in (390, 1280):
            pg = nova(largura)
            pg.goto(base + caminho)
            pg.wait_for_selector(".rodape__versao", state="attached", timeout=15000)
            texto = pg.locator(".rodape__versao").inner_text()
            visivel = pg.evaluate("(() => { const e = document.querySelector('.rodape__versao'), r = e.getBoundingClientRect(); return r.width > 0 && r.right <= window.innerWidth && e.scrollWidth <= e.clientWidth + 1; })()")
            confere(texto.startswith(esperado) and visivel, f"{nome} {largura}px: rodapé mostra «{esperado}», sem passar da tela")
            link = pg.locator(".rodape__versao a").get_attribute("href")
            confere(link.startswith("https://github.com/") and link.endswith("/CHANGELOG.md"), f"{nome} {largura}px: versão leva ao histórico de mudanças")
            pg.context.close()

    print("Licença publicada")
    raiz_repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    api = navegador.new_context().request
    for arq in ("LICENSE", "LICENSE-CONTEUDO.md"):
        r = api.get(base + "/" + arq)
        confere(r.ok and r.text() == open(os.path.join(raiz_repo, arq), encoding="utf-8").read(), f"/{arq} é servido igual ao do repositório")
    confere("MIT License" in api.get(base + "/LICENSE").text(), "/LICENSE é a licença MIT")
    for caminho, nome, titulo, rotulo in (("/", "PT", "Licença e uso do conteúdo", "Licença"), ("/en/", "EN", "License and use of the content", "License")):
        for largura in (390, 1280):
            pg = nova(largura)
            pg.goto(base + caminho)
            pg.wait_for_selector(".rodape", state="attached", timeout=15000)
            link = pg.locator(f'.rodape a:text-is("{rotulo}")')
            confere(link.count() == 1, f"{nome} {largura}px: rodapé tem o link «{rotulo}»")
            link.click()
            pg.wait_for_selector("h1", timeout=15000)
            confere(pg.locator("h1").inner_text() == titulo and pg.url.rstrip("/").endswith("licenca"), f"{nome} {largura}px: o link leva à página de licença")
            confere(pg.locator('link[rel="license"]').get_attribute("href") == "https://creativecommons.org/licenses/by/4.0/", f"{nome}: a página declara a licença do conteúdo")
            textos = pg.locator("main").inner_text()
            confere("CC BY 4.0" in textos and "MIT" in textos and "LICENSE" in textos, f"{nome} {largura}px: a página fala de MIT, CC BY 4.0 e dos arquivos de licença")
            estouro = pg.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
            confere(not estouro, f"{nome} {largura}px: a página de licença não rola para o lado")
            pg.context.close()
        pg = nova(390)
        pg.goto(base + caminho + "licenca/")
        pg.wait_for_selector("#titulo-licenca", timeout=15000)
        confere(pg.locator("h1").inner_text() == titulo and pg.locator("main li a").count() == 4, f"{nome}: a página pronta licenca/ continua certa depois que o aplicativo abre")
        sem = navegador.new_context(java_script_enabled=False).new_page()
        sem.goto(base + caminho + "licenca/")
        confere(sem.locator("h1").inner_text() == titulo and sem.locator("main li a").count() == 4, f"{nome}: licenca/ tem o conteúdo sem JavaScript")
        sem.context.close()
        pg.context.close()
        pg = nova(390)
        pg.goto(base + caminho + "#/sobre")
        pg.wait_for_selector("#titulo-sobre", timeout=15000)
        confere(pg.locator('main a[href="#/licenca"]').count() == 1, f"{nome}: «Como o site funciona» leva à licença completa")
        pg.context.close()

    print("Em números sem JavaScript (páginas prontas)")
    sem_js = navegador.new_context(java_script_enabled=False).new_page()
    sem_js.goto(base + "/em-numeros/")
    confere(sem_js.locator("h1").inner_text() == "Em números", "Em números tem conteúdo sem JavaScript")
    confere(sem_js.locator("table").count() == 0, "Em números pronto: tabelas ficam em páginas próprias")
    confere(sem_js.locator('a[href$="/"]:has-text("Ver como tabela")').count() == len(esperados), "Em números pronto: um link de tabela para cada gráfico")
    for e in esperados:
        sem_js.goto(f"{base}/em-numeros/{e}/")
        confere(sem_js.locator("table tbody tr").count() > 0 and sem_js.locator("h1").inner_text() != "", f"/em-numeros/{e}/ pronta com a tabela")
    sem_js.goto(f"{base}/inteligencia-artificial/")
    confere(sem_js.locator("h1").inner_text() == "Transparência da IA" and sem_js.locator("ol.numeros__passos li").count() == 4, "Transparência da IA tem conteúdo sem JavaScript")
    sem_js.goto(f"{base}/inteligencia-artificial/confianca/")
    confere(sem_js.locator("table tbody tr").count() == 3 and sem_js.locator('a:has-text("Voltar para Transparência da IA")').count() == 1, "/inteligencia-artificial/confianca/ pronta com a tabela")
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
