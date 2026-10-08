#!/usr/bin/env python3
"""Teste de segurança do site: tenta atacar o próprio site com dados maliciosos.

Uso (na raiz do repositório):
    pip install playwright && playwright install chromium
    python testes/seguranca.py

O que faz:
  1. Copia o site para uma pasta temporária e enche os dados (títulos, resumos, nomes, assuntos, descrições)
     de código malicioso: HTML com onerror, "</script><script>", links "javascript:".
  2. Gera as páginas com esse site envenenado e abre dezenas delas, estáticas e do aplicativo,
     inclusive com endereços malformados e código na busca e nos filtros.
  3. Confere que nenhum código executou, que nenhum link perigoso chegou à tela e que o aplicativo
     não quebrou com endereço malformado.
  4. Num site normal, confere a política de segurança (CSP): sem script embutido, nenhuma violação,
     nenhuma conversa com outro endereço e nenhum cookie.
Sai com código 1 se algo falhar.
"""
import functools
import http.server
import json
import os
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading

from playwright.sync_api import sync_playwright

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
falhas = []


def confere(ok, msg):
    print(("  ok  " if ok else "FALHOU ") + msg)
    if not ok:
        falhas.append(msg)


class Quieto(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def servir(pasta):
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quieto, directory=pasta))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def gerar(site, saida):
    subprocess.run([sys.executable, os.path.join(RAIZ, "site", "gerar_paginas.py"), "--site", site, "--saida", saida],
                   check=True, stdout=subprocess.DEVNULL)


HTML = '"><img src=x onerror=window.__pwn=1>'
SCRIPT = "</script><script>window.__pwn=2</script>"


def envenenar(site):
    """Põe código malicioso em todos os campos de texto dos dados."""
    def mexer(arquivo, fn):
        caminho = os.path.join(site, "dados", arquivo)
        with open(caminho, encoding="utf-8") as f:
            d = json.load(f)
        fn(d)
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)

    def projetos(d):
        for i, x in enumerate(d[:40]):
            x["titulo"] += HTML + SCRIPT
            x["resumo"] = (x.get("resumo") or "") + HTML + SCRIPT
            x["nome"] += HTML
            x["ementa"] = (x.get("ementa") or "") + HTML
            if i % 3 == 0:
                x["texto"] = "javascript:window.__pwn=3"

    def deputados(d):
        for x in d[:40]:
            x["nome"] += HTML + SCRIPT
            x["partido"] = (x.get("partido") or "") + HTML

    def assuntos(d):
        for x in d:
            x["nome"] += HTML
            x["descricao"] = (x.get("descricao") or "") + HTML + SCRIPT

    def votacoes(d):
        for x in d[:40]:
            x["desc"] = (x.get("desc") or "") + HTML + SCRIPT

    mexer("projetos.json", projetos)
    # ementa e pontos principais ficam num arquivo por projeto: envenena esses também
    for x in json.load(open(os.path.join(site, "dados", "projetos.json"), encoding="utf-8"))[:40]:
        caminho = os.path.join(site, "dados", "projetos", f"{x['id']}.json")
        with open(caminho, encoding="utf-8") as f:
            det = json.load(f)
        det["ementa"] = (det.get("ementa") or "") + HTML + SCRIPT
        det["pontos"] = list(det.get("pontos") or []) + [HTML + SCRIPT, "javascript:window.__pwn=4"]
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(det, f, ensure_ascii=False)
    mexer("deputados.json", deputados)
    mexer("assuntos.json", assuntos)
    mexer("votacoes.json", votacoes)


def achados_na_pagina(pg):
    return pg.evaluate("""() => ({
      pwn: window.__pwn || null,
      imgx: document.querySelectorAll('img[src=x]').length,
      scr: [...document.querySelectorAll('body script')].filter(s => /__pwn/.test(s.textContent)).length,
      jsurl: [...document.querySelectorAll('a')].filter(a => /^\\s*(javascript|data|vbscript):/i.test(a.getAttribute('href') || '')).length,
    })""")


def ataque(p, base, projetos, deputados, assuntos):
    pid = [x["id"] for x in projetos[:40]]
    did = [x["id"] for x in deputados[:40]]
    urls = []
    for i in pid[:12]:
        urls += [f"/projeto/{i}/", f"/#/projeto/{i}"]
    for i in did[:8]:
        urls += [f"/deputado/{i}/", f"/#/deputado/{i}"]
    for a in assuntos[:4]:
        urls += [f"/assunto/{a['slug']}/", f"/#/assunto/{a['slug']}"]
    urls += ["/", "/#/", "/deputados/", "/#/deputados", "/sobre/"]
    img = "%3Cimg%20src=x%20onerror=window.__pwn=9%3E"
    urls += [
        f"/#/assunto/%22%3E{img}", f"/#/projeto/%22%3E{img}", "/#/deputado/<img src=x onerror=window.__pwn=9>",
        f"/#/?q={img}", f"/#/deputados?q={img}",
        f"/#/projeto/{pid[0]}?v={img}&pt=%3Cscript%3Ewindow.__pwn=9%3C/script%3E&votacao=%22%3E{img}",
        f"/#/assunto/saude?a={img}&q={img}", f"/projeto/{img}/",
    ]
    b = p.chromium.launch()
    ruins = 0
    for u in urls:
        pg = b.new_page()
        dialogos = []
        pg.on("dialog", lambda d: (dialogos.append(d.message), d.dismiss()))
        pg.goto(base + u)
        pg.wait_for_timeout(500)
        try:
            if u in ("/", "/#/") or "deputados" in u:
                pg.fill("input[type=search]", "<img src=x onerror=window.__pwn=7>")
                pg.wait_for_timeout(300)
        except Exception:
            pass
        r = achados_na_pagina(pg)
        if dialogos or r["pwn"] or r["imgx"] or r["scr"] or r["jsurl"]:
            ruins += 1
            print("   ", u, r, dialogos)
        pg.close()
    confere(ruins == 0, f"código malicioso nos dados e nos endereços não executa nem vira link perigoso ({len(urls)} páginas)")

    # endereços malformados não podem quebrar o aplicativo
    for u in ["/#/projeto/%E0%A4%A", "/#/assunto/%", "/#/deputado/%ZZ", "/#/projeto/__proto__", "/#/assunto/constructor"]:
        pg = b.new_page()
        erros = []
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto(base + u)
        pg.wait_for_timeout(400)
        titulo = pg.evaluate("() => (document.querySelector('h1') || {}).textContent || ''")
        confere(not erros and titulo.startswith("Não achamos"), f"endereço malformado {u} vira «não encontrado», sem erro")
        pg.close()
    b.close()


def normal(p, base):
    b = p.chromium.launch()
    ctx = b.new_context()
    pg = ctx.new_page()
    hosts, violacoes, erros = set(), [], []
    pg.on("request", lambda r: hosts.add(r.url.split("/")[2]))
    pg.on("console", lambda m: violacoes.append(m.text) if "Content Security Policy" in m.text or "Refused to" in m.text else None)
    pg.on("pageerror", lambda e: erros.append(str(e)))
    for u in ["/", "/#/assunto/saude", "/#/deputados", "/#/sobre", "/projeto/2611313/", "/deputado/204549/", "/#/%"]:
        pg.goto(base + u)
        pg.wait_for_timeout(500)
    pg.click("button.tema")
    confere(len(hosts) == 1, f"só fala com o próprio site (endereços: {sorted(hosts)})")
    confere(not violacoes, f"nenhuma violação da política de segurança {violacoes[:1]}")
    confere(not erros, f"nenhum erro de JavaScript {erros[:1]}")
    confere(ctx.cookies() == [], "nenhum cookie")
    for u in ["/", "/projeto/2611313/", "/deputado/204549/", "/404.html"]:
        pg.goto(base + u)
        inline = pg.evaluate("() => [...document.scripts].filter(s => !s.src && (!s.type || /javascript|module/.test(s.type))).length")
        csp = pg.evaluate("() => (document.querySelector('meta[http-equiv=Content-Security-Policy]') || {}).content || ''")
        confere(inline == 0, f"{u}: nenhum script embutido")
        confere("script-src 'self'" in csp and "'unsafe-inline'" not in csp.split("style-src")[0], f"{u}: política de segurança presente e sem script embutido")
    b.close()


def main():
    tmp = tempfile.mkdtemp(prefix="seguranca_")
    try:
        site = os.path.join(tmp, "site")
        shutil.copytree(os.path.join(RAIZ, "site"), site, ignore=shutil.ignore_patterns("fotos", "__pycache__"))
        normal_out = os.path.join(tmp, "normal")
        gerar(site, normal_out)
        envenenar(site)
        veneno_out = os.path.join(tmp, "veneno")
        gerar(site, veneno_out)
        with open(os.path.join(veneno_out, "dados", "projetos.json"), encoding="utf-8") as f:
            projetos = json.load(f)
        with open(os.path.join(veneno_out, "dados", "deputados.json"), encoding="utf-8") as f:
            deputados = json.load(f)
        with open(os.path.join(veneno_out, "dados", "assuntos.json"), encoding="utf-8") as f:
            assuntos = json.load(f)
        s1, base1 = servir(veneno_out)
        s2, base2 = servir(normal_out)
        with sync_playwright() as p:
            print("Site envenenado")
            ataque(p, base1, projetos, deputados, assuntos)
            print("Site normal")
            normal(p, base2)
        s1.shutdown()
        s2.shutdown()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if falhas:
        print(f"\n{len(falhas)} verificação(ões) falharam.")
        sys.exit(1)
    print("\nTudo certo.")


if __name__ == "__main__":
    main()
