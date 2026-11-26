#!/usr/bin/env python3
"""Confere os tokens de cor, letra e forma do site. Regras completas em docs/design-system.md.

Verificação estática de site/estilos.css (não precisa de navegador):
  1. As tabelas de docs/design-system.md (cores, tamanhos de letra, raios) batem com o CSS: o documento não pode ficar diferente do código.
  2. Todo token de cor de :root tem valor no tema escuro.
  3. Nenhuma cor escrita à mão (#..., rgb(), rgba(), hsl() com número) fora das definições (--nome: valor) e do @media print.
  4. font-size só usa os tamanhos da tabela; font-family, só var(--sans); border-radius, só os valores da tabela.
  5. Contraste de pelo menos 4,5:1 nos pares de texto e fundo, nos dois temas.
Exceção rara: escrever "token-ok: motivo" num comentário na mesma linha.

Uso:
    python testes/tokens.py
Sai com código 1 se algo falhar.
"""
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = os.path.join(RAIZ, "site", "estilos.css")
DOC = os.path.join(RAIZ, "docs", "design-system.md")

# Pares (texto, fundo) que precisam de contraste de 4,5:1 nos dois temas.
PARES = [("--tinta", "--papel"), ("--tinta", "--superficie"), ("--tinta-suave", "--papel"), ("--tinta-suave", "--superficie"),
         ("--cobalto", "--papel"), ("--cobalto", "--superficie"), ("--cobalto", "--cobalto-claro"),
         ("--sobre-cobalto", "--cobalto"), ("--aviso-texto", "--aviso-fundo")]
MINIMO = 4.5

falhas = []


def confere(ok, msg):
    print(("  ok  " if ok else "FALHOU ") + msg)
    if not ok:
        falhas.append(msg)
        if os.environ.get("GITHUB_ACTIONS"):
            print("::error::" + msg)


def sem_comentarios(texto):
    """Troca os comentários por espaços, mantendo as quebras de linha (os números de linha continuam certos)."""
    return re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), texto, flags=re.S)


def bloco(texto, abertura):
    """Texto de dentro do bloco que começa em «abertura {», com as chaves aninhadas casadas."""
    i = texto.find(abertura)
    if i < 0:
        return ""
    ini = texto.index("{", i) + 1
    nivel, j = 1, ini
    while j < len(texto) and nivel:
        nivel += {"{": 1, "}": -1}.get(texto[j], 0)
        j += 1
    return texto[ini:j - 1]


def para_rgb(hexa):
    h = hexa.lstrip("#")
    if len(h) in (3, 4):
        h = "".join(c * 2 for c in h[:3])
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def luminancia(hexa):
    def canal(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(c) for c in para_rgb(hexa))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a, b):
    la, lb = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def secao_do_doc(doc, titulo):
    """Linhas do documento entre o título «titulo» (qualquer nível) e o próximo título."""
    saida, dentro = [], False
    for linha in doc.split("\n"):
        if re.match(r"#{1,6}\s", linha):
            if dentro:
                break
            dentro = titulo in linha
            continue
        if dentro:
            saida.append(linha)
    return saida


def main():
    css_bruto = open(CSS, encoding="utf-8").read()
    css = sem_comentarios(css_bruto)
    doc = open(DOC, encoding="utf-8").read()
    linhas_ok = {i for i, l in enumerate(css_bruto.split("\n"), 1) if "token-ok" in l}

    print("Tokens do site (site/estilos.css e docs/design-system.md)")
    raiz = bloco(css, ":root {")
    escuro = bloco(css, ':root[data-theme="dark"] {')
    confere(bool(raiz) and bool(escuro), "blocos :root e :root[data-theme=\"dark\"] encontrados")

    def definicoes(trecho):
        return {n: v.strip().lower() for n, v in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", trecho)}

    claro, noite = definicoes(raiz), definicoes(escuro)

    # 1a. Tabela de cores do documento x CSS
    tabela = re.findall(r"^\|\s*`(--[\w-]+)`\s*\|[^|]*\|\s*`(#[0-9a-fA-F]{3,8})`\s*\|\s*`(#[0-9a-fA-F]{3,8})`\s*\|", "\n".join(secao_do_doc(doc, "Cores")), re.M)
    confere(len(tabela) >= 10, f"tabela de cores do documento lida ({len(tabela)} tokens)")
    for token, c, e in tabela:
        confere(claro.get(token) == c.lower(), f"{token}, tema claro: documento {c}, CSS {claro.get(token)}")
        confere(noite.get(token) == e.lower(), f"{token}, tema escuro: documento {e}, CSS {noite.get(token)}")

    # 2. Todo token de cor de :root tem versão escura
    cores_claro = [n for n, v in claro.items() if re.match(r"#[0-9a-f]{3,8}$", v)]
    sem_escuro = [n for n in cores_claro if n not in noite]
    confere(not sem_escuro, f"todo token de cor de :root tem valor no tema escuro ({len(cores_claro)} tokens; sem versão escura: {sem_escuro})")
    documentados = {t for t, _, _ in tabela}
    confere(set(cores_claro) <= documentados, f"todo token de cor de :root está na tabela do documento (faltam: {sorted(set(cores_claro) - documentados)})")

    # 3. Nenhuma cor escrita à mão
    resto = css.replace(raiz, re.sub(r"[^\n]", " ", raiz)).replace(escuro, re.sub(r"[^\n]", " ", escuro))  # sem mudar as quebras de linha
    resto = re.sub(r"--[\w-]+\s*:[^;{}]*;", lambda m: re.sub(r"[^\n]", " ", m.group(0)), resto)
    impressao = bloco(resto, "@media print")
    if impressao:
        resto = resto.replace(impressao, re.sub(r"[^\n]", " ", impressao))
    achados = []
    for m in re.finditer(r"#[0-9a-fA-F]{3,8}\b|\brgba?\([^)]*\)|\bhsla?\((?!\s*var\()[^)]*\)", resto):
        linha = resto.count("\n", 0, m.start()) + 1  # «resto» tem as mesmas quebras de linha do original
        if linha in linhas_ok:
            continue
        achados.append(f"linha {linha}: {m.group(0)}")
    for a in achados[:30]:
        print("   ", a)
    confere(not achados, f"nenhuma cor escrita à mão fora das definições e da impressão ({len(achados)} achadas)")

    # 4a. Tamanhos de letra
    secao_letras = "\n".join(secao_do_doc(doc, "Tamanhos de letra"))
    escala = set(re.findall(r"^\|\s*`([\d.]+rem)`\s*\|", secao_letras, re.M))
    fluidos = {re.sub(r"\s+", " ", x) for x in re.findall(r"^\|\s*`(clamp\([^`]+\))`\s*\|", secao_letras, re.M)}
    confere(len(escala) >= 8 and len(fluidos) >= 5, f"tabelas de letras do documento lidas ({len(escala)} tamanhos, {len(fluidos)} fluidos)")
    ruins = []
    for m in re.finditer(r"(?<![-\w])font-size\s*:\s*([^;{}]+)", css):
        linha = css.count("\n", 0, m.start()) + 1
        valor = re.sub(r"\s+", " ", re.sub(r"\s*!important$", "", m.group(1).strip()))
        if linha in linhas_ok or valor == "inherit" or valor in escala or valor in fluidos:
            continue
        ruins.append(f"linha {linha}: font-size: {valor}")
    for r in ruins[:30]:
        print("   ", r)
    confere(not ruins, f"font-size só usa a escala do documento ({len(ruins)} fora dela)")
    atalhos = [f"linha {css.count(chr(10), 0, m.start()) + 1}: font: {m.group(1).strip()}" for m in re.finditer(r"(?<![-\w])font\s*:\s*([^;{}]+)", css) if m.group(1).strip() != "inherit"]
    confere(not atalhos, f"o atalho font: só aparece como «inherit» ({atalhos})")

    # 4b. Uma fonte só
    sem_fonte_face = re.sub(r"@font-face\s*\{[^}]*\}", lambda m: re.sub(r"[^\n]", " ", m.group(0)), css)
    familias = [(sem_fonte_face.count("\n", 0, m.start()) + 1, m.group(1).strip()) for m in re.finditer(r"(?<![-\w])font-family\s*:\s*([^;{}]+)", sem_fonte_face)]
    fora = [f"linha {l}: {v}" for l, v in familias if v not in ("var(--sans)", "inherit") and l not in linhas_ok and not re.match(r"^\"Atkinson Hyperlegible Next\"", v)]
    confere(not fora, f"font-family só usa var(--sans) ({fora})")

    # 4c. Raios
    secao_raios = "\n".join(secao_do_doc(doc, "Raios"))
    raios = set(re.findall(r"^\|\s*`([^`]+)`\s*\|", secao_raios, re.M))
    confere(len(raios) >= 8, f"tabela de raios do documento lida ({len(raios)} valores)")
    atomos = set()
    for r in raios:
        if r.startswith("calc("):
            atomos.add(re.sub(r"\s+", " ", r))
        else:
            atomos.update(r.split())
    ruins = []
    for m in re.finditer(r"(?<![-\w])border(?:-(?:top|bottom|start|end)-(?:left|right|start|end))?-radius\s*:\s*([^;{}]+)", css):
        linha = css.count("\n", 0, m.start()) + 1
        valor = re.sub(r"\s+", " ", re.sub(r"\s*!important$", "", m.group(1).strip()))
        if linha in linhas_ok or valor == "inherit":
            continue
        valor_calc = re.findall(r"calc\(var\(--raio\) - var\(--perto\)\)|var\([^)]*\)|[^\s]+", valor)
        if all(p in atomos for p in valor_calc):
            continue
        ruins.append(f"linha {linha}: border-radius: {valor}")
    for r in ruins[:30]:
        print("   ", r)
    confere(not ruins, f"border-radius só usa os raios do documento ({len(ruins)} fora deles)")

    # 5. Contraste nos dois temas
    for tema, tokens in (("claro", claro), ("escuro", {**claro, **noite})):
        for texto, fundo in PARES:
            a, b = tokens.get(texto), tokens.get(fundo)
            if not (a and b and a.startswith("#") and b.startswith("#")):
                confere(False, f"{tema}: {texto} sobre {fundo}: cores não encontradas")
                continue
            c = contraste(a, b)
            confere(c >= MINIMO, f"{tema}: {texto} sobre {fundo} tem contraste {c:.1f}:1 (mínimo {MINIMO}:1)")

    print()
    if falhas:
        print(f"{len(falhas)} verificação(ões) falharam.")
        sys.exit(1)
    print("Tokens dentro das regras.")


if __name__ == "__main__":
    main()
