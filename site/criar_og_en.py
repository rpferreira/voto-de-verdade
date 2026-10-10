#!/usr/bin/env python3
"""Cria site/og-en.png, a imagem de prévia (WhatsApp, Google…) das páginas em inglês.

Parte de site/og.png (em português): apaga a legenda e escreve a legenda em inglês com a mesma fonte do site,
mantendo o título "Voto de Verdade" e o desenho dos deputados. Precisa do Playwright (testes/requirements.txt).
Só precisa rodar de novo se a legenda ou o og.png mudarem.

    python3 site/criar_og_en.py
"""
import base64
import os
import tempfile

from playwright.sync_api import sync_playwright

SITE = os.path.dirname(os.path.abspath(__file__))
FUNDO = "rgb(245,246,250)"
LEGENDA = ["How the Chamber voted,", "and how each deputy voted."]
RODAPE = "No grades, no rankings."


def dados(caminho):
    with open(os.path.join(SITE, caminho), "rb") as f:
        return base64.b64encode(f.read()).decode()


def main():
    html = f"""<!doctype html><meta charset="utf-8"><style>
@font-face {{ font-family: Atkinson; src: url(data:font/woff2;base64,{dados("fontes/atkinson-hyperlegible-next-latin-wght-normal.woff2")}) format("woff2"); font-weight: 200 800; }}
html, body {{ margin: 0; width: 1200px; height: 630px; overflow: hidden; background: {FUNDO}; font-family: Atkinson, sans-serif; }}
img {{ position: absolute; left: 0; top: 0; }}
.apaga {{ position: absolute; left: 0; top: 405px; width: 620px; height: 225px; background: {FUNDO}; }}
.legenda {{ position: absolute; left: 72px; top: 421px; margin: 0; font-size: 32px; line-height: 47px; font-weight: 400; color: rgb(74,84,110); }}
.rodape {{ position: absolute; left: 72px; top: 538px; margin: 0; font-size: 24px; line-height: 36px; font-weight: 400; color: rgb(74,84,110); }}
</style>
<img src="data:image/png;base64,{dados("og.png")}" width="1200" height="630" alt="">
<div class="apaga"></div>
<p class="legenda">{"<br>".join(LEGENDA)}</p>
<p class="rodape">{RODAPE}</p>"""
    with tempfile.TemporaryDirectory() as pasta:
        arq = os.path.join(pasta, "og.html")
        with open(arq, "w", encoding="utf-8") as f:
            f.write(html)
        with sync_playwright() as p:
            nav = p.chromium.launch()
            pg = nav.new_page(viewport={"width": 1200, "height": 630})
            pg.goto("file://" + arq)
            pg.wait_for_timeout(300)
            pg.screenshot(path=os.path.join(SITE, "og-en.png"))
            nav.close()
    print("Criado site/og-en.png")


if __name__ == "__main__":
    main()
