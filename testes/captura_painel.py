#!/usr/bin/env python3
"""Tira uma foto (PNG) da tela "Em números" do site montado, para ver como ficou a cada atualização.

Uso (depois de montar o site com python site/gerar_paginas.py --saida _site):
    python testes/captura_painel.py _site painel/ultima-geracao.png
    python testes/captura_painel.py _site saida.png --largura 390 --escuro

Precisa do Playwright (pip install -r testes/requirements.txt && playwright install chromium).
"""
import argparse
import functools
import http.server
import os
import sys
import threading

from playwright.sync_api import sync_playwright


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("site")
    ap.add_argument("saida")
    ap.add_argument("--largura", type=int, default=1100)
    ap.add_argument("--escuro", action="store_true")
    args = ap.parse_args()

    class Quieto(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quieto, directory=args.site))
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{servidor.server_address[1]}"

    os.makedirs(os.path.dirname(os.path.abspath(args.saida)), exist_ok=True)
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page(viewport={"width": args.largura, "height": 900}, device_scale_factor=2 if args.largura < 600 else 1)
        erros = []
        pagina.on("pageerror", lambda e: erros.append(str(e)))
        pagina.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
        if args.escuro:
            pagina.add_init_script("try{localStorage.setItem('tema','dark')}catch(e){}")
        pagina.goto(base + "/em-numeros/")
        pagina.wait_for_selector(".pn-colunas", timeout=15000)
        pagina.wait_for_selector(".pn-linhas", timeout=15000)
        pagina.wait_for_timeout(500)
        pagina.screenshot(path=args.saida, full_page=True)
        navegador.close()
    servidor.shutdown()
    if erros:
        print("ERRO no console da página:", erros, file=sys.stderr)
        return 1
    print(f"Foto do painel salva em {args.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
