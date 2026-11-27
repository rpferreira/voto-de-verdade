#!/usr/bin/env python3
"""Confere os módulos JavaScript do site (app.js e site/js/*.js). Não precisa de navegador.

  1. No código-fonte (site/): todo import é relativo, termina em .js, aponta para um arquivo que existe e não leva ?v= (quem põe é o gerador).
  2. Nenhum módulo fica sem uso (todo arquivo de site/js/ é alcançado a partir do app.js) e não há import circular.
  3. No site montado (_site/): todo import leva o mesmo ?v= do app.js, e esse é o ?v= que cada página põe no <script type="module">.
     Assim um app.js novo nunca abre um módulo velho guardado pelo navegador.
  4. Cada página carrega o app.js como módulo e avisa o navegador dos módulos (modulepreload), com o mesmo ?v=.

Uso:
    python testes/modulos.py [_site]
Sai com código 1 se algo falhar.
"""
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(RAIZ, "site")
SAIDA = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(RAIZ, "_site")

# from "./x.js", import "./x.js" e import("./x.js"); qualquer coisa que não seja relativa aparece em IMPORT_QUALQUER.
IMPORT_RELATIVO = re.compile(r"""\b(?:from|import)\s*\(?\s*(["'])(\.{1,2}/[^"']+?\.js)(\?v=[0-9a-f]+)?\1""")
IMPORT_QUALQUER = re.compile(r"""\b(?:from|import)\s*\(?\s*(["'])([^"']+)\1""")

falhas = []


def confere(ok, msg):
    print(("  ok  " if ok else "FALHOU ") + msg)
    if not ok:
        falhas.append(msg)
        if os.environ.get("GITHUB_ACTIONS"):
            print("::error::" + msg)


def ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        return f.read()


def modulos_de(pasta):
    achados = ["app.js"]
    for raiz, _, nomes in os.walk(os.path.join(pasta, "js")):
        achados += [os.path.relpath(os.path.join(raiz, n), pasta).replace(os.sep, "/") for n in nomes if n.endswith(".js")]
    return sorted(achados)


def importa(pasta, rel):
    """(alvo normalizado, ?v= ou None) de cada import relativo do arquivo; e os imports que não são relativos."""
    texto = ler(os.path.join(pasta, rel))
    relativos = [(os.path.normpath(os.path.join(os.path.dirname(rel), m.group(2))).replace(os.sep, "/"), m.group(3)) for m in IMPORT_RELATIVO.finditer(texto)]
    outros = [m.group(2) for m in IMPORT_QUALQUER.finditer(texto) if not m.group(2).startswith(("./", "../"))]
    return relativos, outros


def main():
    print("== Código-fonte (site/)")
    fonte = modulos_de(SITE)
    grafo = {}
    for rel in fonte:
        relativos, outros = importa(SITE, rel)
        grafo[rel] = [alvo for alvo, _ in relativos]
        confere(not outros, f"{rel}: só imports relativos" + (f" (achei {outros})" if outros else ""))
        confere(all(v is None for _, v in relativos), f"{rel}: sem ?v= no código-fonte (o gerador põe)")
        faltam = [alvo for alvo in grafo[rel] if not os.path.exists(os.path.join(SITE, alvo))]
        confere(not faltam, f"{rel}: todo import aponta para um arquivo que existe" + (f" (faltam {faltam})" if faltam else ""))

    alcancados, pilha = set(), ["app.js"]
    while pilha:
        atual = pilha.pop()
        if atual in alcancados:
            continue
        alcancados.add(atual)
        pilha += grafo.get(atual, [])
    soltos = sorted(set(fonte) - alcancados)
    confere(not soltos, "todo módulo de site/js/ é usado a partir do app.js" + (f" (sem uso: {soltos})" if soltos else ""))

    def tem_ciclo(no, caminho):
        if no in caminho:
            return True
        return any(tem_ciclo(alvo, caminho | {no}) for alvo in grafo.get(no, []))
    confere(not tem_ciclo("app.js", frozenset()), "nenhum import circular")

    print("== Site montado (" + os.path.basename(SAIDA) + "/)")
    if not os.path.isdir(SAIDA):
        confere(False, f"{SAIDA} não existe: rode python site/gerar_paginas.py --saida _site antes")
        return
    montados = modulos_de(SAIDA)
    confere(montados == fonte, "os mesmos arquivos de módulo foram copiados para o site montado")
    codigos = set()
    for rel in montados:
        relativos, _ = importa(SAIDA, rel)
        for alvo, v in relativos:
            codigos.add(v)
            confere(v is not None, f"{rel}: import de {alvo} leva ?v=")
    confere(len(codigos) == 1 and None not in codigos, "todos os imports levam o mesmo ?v=" + (f" (achei {sorted(map(str, codigos))})" if len(codigos) != 1 else ""))
    codigo = next(iter(codigos)) if len(codigos) == 1 else None

    sem_modulo, sem_preload, v_errado, total = [], [], [], 0
    for raiz, _, nomes in os.walk(SAIDA):
        for nome in nomes:
            if not nome.endswith(".html"):
                continue
            caminho = os.path.join(raiz, nome)
            pagina = ler(caminho)
            m = re.search(r'<script type="module" src="([^"]*app\.js)(\?v=[0-9a-f]+)?"></script>', pagina)
            if "app.js" not in pagina:
                continue
            total += 1
            rel = os.path.relpath(caminho, SAIDA)
            if not m:
                sem_modulo.append(rel)
                continue
            if m.group(2) != codigo:
                v_errado.append(rel)
            preloads = set(re.findall(r'<link rel="modulepreload" href="([^"]+)">', pagina))
            # o modulepreload usa o mesmo prefixo do app.js (../ nas páginas de dentro) e o mesmo ?v=
            prefixo = m.group(1)[: -len("app.js")]  # "", "../", "../../" ou "/" (404)
            esperados = {prefixo + x + (codigo or "") for x in fonte if x != "app.js"}
            if preloads != esperados:
                sem_preload.append(rel)
    confere(total > 0, f"achei páginas que carregam o app.js ({total})")
    confere(not sem_modulo, "toda página carrega o app.js com type=\"module\"" + (f" (falha em {sem_modulo[:3]})" if sem_modulo else ""))
    confere(not v_errado, "o ?v= do app.js é o mesmo dos imports em toda página" + (f" (falha em {v_errado[:3]})" if v_errado else ""))
    confere(not sem_preload, "toda página avisa os módulos com modulepreload e o mesmo ?v=" + (f" (falha em {sem_preload[:3]})" if sem_preload else ""))


main()
if falhas:
    print(f"\n{len(falhas)} verificação(ões) falharam.")
    sys.exit(1)
print("\nTudo certo com os módulos.")
