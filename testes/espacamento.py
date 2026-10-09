#!/usr/bin/env python3
"""Confere as regras de espaçamento do site (grade de 8px). Regras completas em docs/espacamento.md.

Duas verificações:
  1. Estática (sempre): em site/estilos.css, margin, padding, gap, inset, top/right/bottom/left e scroll-padding
     só aceitam 0, auto, um papel (var(--junto|perto|item|grupo|bloco|respiro|margem|calha|...)) e o negativo de
     um papel (calc(-1 * var(--item))). Os componentes nunca usam a escala (var(--e-*)) direto. A própria escala precisa estar na grade (múltiplos de 8px,
     mais o meio passo de 4px) e cada papel precisa apontar para um passo dela.
     Exceção rara: escrever "espaco-ok: motivo" num comentário na mesma linha.
  2. No navegador (se der o caminho do site montado): paddings, gaps e margens verticais calculados de todos os
     elementos das telas principais têm de estar na escala, e line-height e altura, em múltiplos de 4px.

Uso:
    python testes/espacamento.py                # só a verificação estática
    python testes/espacamento.py _site          # estática + navegador (precisa de playwright)
Sai com código 1 se algo falhar.
"""
import functools
import http.server
import os
import re
import socketserver
import sys
import threading

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = os.path.join(RAIZ, "site", "estilos.css")

PROPS = (
    r"margin(?:-(?:top|right|bottom|left|block|inline|block-start|block-end|inline-start|inline-end))?"
    r"|padding(?:-(?:top|right|bottom|left|block|inline|block-start|block-end|inline-start|inline-end))?"
    r"|gap|row-gap|column-gap|top|right|bottom|left|inset(?:-block|-inline)?|scroll-padding(?:-[a-z]+)?"
)
PAPEIS = ("junto", "perto", "item", "grupo", "bloco", "respiro", "margem", "calha", "recuo-icone", "recuo-seta", "topo-fixo", "altura-topo")
PASSO = r"var\(--e-(?:meio|\d+)\)"
ROLE = rf"var\(--(?:{'|'.join(PAPEIS)})\)"
VALIDO = re.compile(rf"^(?:0|auto|inherit|initial|unset|normal|{ROLE}|calc\(-1 \* {ROLE}\))$")

falhas = []


def confere(ok, msg):
    print(("  ok  " if ok else "FALHOU ") + msg)
    if not ok:
        falhas.append(msg)


def partes(valor):
    """Separa 'var(--e-1) 0 calc(-1 * var(--e-2))' em valores, sem quebrar dentro de parênteses."""
    saida, atual, nivel = [], "", 0
    for ch in valor.strip():
        if ch == "(":
            nivel += 1
        elif ch == ")":
            nivel -= 1
        if ch.isspace() and nivel == 0:
            if atual:
                saida.append(atual)
            atual = ""
        else:
            atual += ch
    if atual:
        saida.append(atual)
    return saida


def para_px(valor):
    m = re.fullmatch(r"([\d.]+)rem", valor.strip())
    return float(m.group(1)) * 16 if m else None


def estatica():
    print("Verificação estática do CSS")
    texto = open(CSS, encoding="utf-8").read()

    # 1. A escala
    escala = {}
    for nome, valor in re.findall(r"--e-(meio|\d+)\s*:\s*([^;]+);", texto):
        escala[nome] = para_px(valor)
    confere(len(escala) >= 8, f"escala definida em :root ({len(escala)} passos)")
    for nome, px in escala.items():
        esperado = 4 if nome == "meio" else int(nome) * 8
        confere(px == esperado, f"--e-{nome} vale {px}px (esperado {esperado}px)")

    # 2. Os papéis apontam para a escala
    for papel in PAPEIS:
        valores = re.findall(rf"--{papel}\s*:\s*([^;]+);", texto)
        confere(bool(valores), f"papel --{papel} definido")
        for v in valores:
            confere(re.fullmatch(PASSO, v.strip()) is not None, f"--{papel}: {v.strip()} usa um passo da escala")

    # 3. Nenhum espaço fora da escala
    sem_comentarios = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), texto, flags=re.S)
    linhas_ok = {i for i, l in enumerate(texto.split("\n"), 1) if "espaco-ok" in l}
    ruins = []
    for m in re.finditer(rf"(?<![-\w])({PROPS})\s*:\s*([^;{{}}]+)", sem_comentarios):
        linha = sem_comentarios.count("\n", 0, m.start()) + 1
        if linha in linhas_ok:
            continue
        prop, valor = m.group(1), m.group(2).strip()
        valor = re.sub(r"\s*!important$", "", valor)
        for v in partes(valor):
            if not VALIDO.match(v):
                ruins.append(f"linha {linha}: {prop}: {valor}  ← {v}")
                break
    for r in ruins[:40]:
        print("   ", r)
    confere(not ruins, f"todo espaçamento usa a escala ({len(ruins)} fora dela)")

    # 4. Escala só dentro de :root (nas definições dos papéis); componentes usam papéis
    usados = set(re.findall(r"var\(--e-(meio|\d+)\)", sem_comentarios))
    confere(usados <= set(escala), f"todo var(--e-*) usado existe na escala ({sorted(usados - set(escala))})")
    fora_do_root = [
        i for i, l in enumerate(sem_comentarios.split("\n"), 1)
        if "var(--e-" in l and not re.match(r"\s*(--[a-z-]+|@media .*:root)", l) and ":root" not in l and i not in linhas_ok
    ]
    confere(not fora_do_root, f"componentes não usam a escala direto (linhas {fora_do_root[:10]})")

    return {n: p for n, p in escala.items()}


JS = """() => {
  const props = ['paddingTop','paddingRight','paddingBottom','paddingLeft','marginTop','marginBottom',
                 'marginLeft','marginRight','rowGap','columnGap'];
  const saida = [];
  for (const el of document.querySelectorAll('body *')) {
    if (el.closest('svg') && el.tagName !== 'svg') continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none') continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    const cls = typeof el.className === 'string' ? el.className.trim() : '';
    if (cls.includes('so-leitor') || cls.includes('pular')) continue;
    const nome = el.tagName.toLowerCase() + (cls ? '.' + cls.split(/\\s+/).join('.') : '');
    for (const p of props) {
      const v = cs[p];
      if (!v || v === 'normal' || v === 'auto') continue;
      const n = parseFloat(v);
      if (isNaN(n) || n === 0) continue;
      if ((p === 'marginLeft' || p === 'marginRight') && Math.abs(n) > 96) continue; // margin auto
      saida.push([nome, p, +n.toFixed(2)]);
    }
    const lh = parseFloat(cs.lineHeight);
    if (!isNaN(lh)) saida.push([nome, 'lineHeight', +lh.toFixed(2)]);
    const d = cs.display;
    if (d !== 'inline' && d !== 'contents' && d !== 'table-cell' && r.height >= 8 && el.tagName.toLowerCase() !== 'svg') {
      saida.push([nome, 'altura', +r.height.toFixed(2)]);
    }
  }
  return saida;
}"""

ROTAS = ["/", "/assunto/saude/", "/projeto/2611313/", "/deputados/", "/deputado/204549/", "/sobre/"]


def navegador(pasta, escala):
    from playwright.sync_api import sync_playwright

    print("Verificação no navegador (valores calculados)")
    permitidos = {p for p in escala.values()}
    permitidos |= {-p for p in permitidos}
    permitidos.add(0)

    class Quieto(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    socketserver.TCPServer.allow_reuse_address = True
    servidor = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(Quieto, directory=pasta))
    porta = servidor.server_address[1]
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    fora = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        for largura in (1280, 390):
            pg = b.new_page(viewport={"width": largura, "height": 900})
            for rota in ROTAS:
                if not os.path.exists(os.path.join(pasta, rota.strip("/"), "index.html")) and rota != "/":
                    continue
                pg.goto(f"http://127.0.0.1:{porta}{rota}")
                pg.wait_for_timeout(1200)
                for nome, prop, valor in pg.evaluate(JS):
                    if prop in ("lineHeight", "altura"):
                        ok = abs(valor / 4 - round(valor / 4)) < 0.02
                    else:
                        ok = any(abs(valor - x) < 0.02 for x in permitidos)
                    if not ok:
                        fora.setdefault((nome, prop, valor), set()).add(f"{rota}@{largura}")
        b.close()
    servidor.shutdown()
    for (nome, prop, valor), onde in sorted(fora.items())[:40]:
        print(f"    {nome} {prop}={valor}  ({', '.join(sorted(onde)[:2])})")
    confere(not fora, f"espaços calculados todos na escala; linhas e alturas em múltiplos de 4px ({len(fora)} fora)")


if __name__ == "__main__":
    escala = estatica()
    if len(sys.argv) > 1:
        navegador(os.path.abspath(sys.argv[1]), escala)
    if falhas:
        print(f"\n{len(falhas)} verificação(ões) falharam.")
        sys.exit(1)
    print("\nEspaçamento dentro das regras.")
