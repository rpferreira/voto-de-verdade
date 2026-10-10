#!/usr/bin/env python3
"""Imagens de prévia (WhatsApp, X, LinkedIn, Google…) de cada deputado, de cada assunto e das páginas fixas.

Cada imagem tem 1200 x 630 pixels, no mesmo visual de site/og.png, e é feita na hora de montar o site (gerar_paginas.py),
sem custo de IA. Não vão para o repositório. Sem o Pillow instalado, `disponivel()` devolve False e o site usa o og.png de sempre.

Regras de conteúdo (as mesmas do site): só nome, partido e estado, ou o título da página. Nada de nota, placar ou ranking.
"""

import functools
import math
import os

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # sem Pillow: o site continua com a imagem geral
    Image = None

LARGURA, ALTURA = 1200, 630
MARGEM = 72
PAPEL, TINTA, SUAVE, COBALTO, COBALTO_CLARO, PONTO_CLARO = "#f5f6fa", "#0f1523", "#4a566b", "#2341d8", "#e8ecfd", "#dfe5fb"
FONTE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fontes", "atkinson-hyperlegible-next-latin-wght-normal.woff2")
ESCALA = 4  # desenhos redondos são feitos 4 vezes maiores e reduzidos, para as bordas ficarem lisas

# Os 15 pontos da marca (o mesmo desenho do ícone do site, na grade 32 x 18): (x, y, raio)
PONTOS_MARCA = [(30.10, 16.10, 1.6), (29.03, 10.70, 1.6), (25.97, 6.13, 1.6), (21.40, 3.07, 1.6), (16, 2, 1.6), (10.60, 3.07, 1.6), (6.03, 6.13, 1.6),
                (2.97, 10.70, 1.6), (1.90, 16.10, 1.6), (24.30, 16.10, 1.6), (21.87, 10.23, 1.6), (16, 7.80, 1.6), (10.13, 10.23, 1.6),
                (7.70, 16.10, 1.6), (16, 16.1, 1.8)]


def disponivel():
    return Image is not None and os.path.exists(FONTE)


@functools.lru_cache(maxsize=64)
def fonte(tamanho, peso=400):
    f = ImageFont.truetype(FONTE, tamanho)
    f.set_variation_by_axes([peso])
    return f


def quebrar(desenho, texto, f, largura, max_linhas):
    """Divide o texto em linhas que cabem na largura. Devolve (linhas, coube); se passar de max_linhas, corta a última com «…»."""
    palavras, linhas, atual = texto.split(), [], ""
    for p in palavras:
        teste = (atual + " " + p).strip()
        if desenho.textlength(teste, font=f) <= largura or not atual:
            atual = teste
        else:
            linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    if len(linhas) <= max_linhas:
        return linhas, True
    ultima = " ".join(linhas[max_linhas - 1:])
    while ultima and desenho.textlength(ultima + "…", font=f) > largura:
        ultima = ultima[:-1].rstrip()
    return linhas[: max_linhas - 1] + [ultima + "…"], False


def ajustar(desenho, texto, tamanhos, largura, max_linhas, peso=600):
    """Maior tamanho (da lista) em que o texto cabe em max_linhas; se nenhum servir, o menor, com o texto cortado.
    max_linhas pode ser um número ou uma lista com o limite de cada tamanho (os menores aceitam mais linhas)."""
    limites = max_linhas if isinstance(max_linhas, (list, tuple)) else [max_linhas] * len(tamanhos)
    for t, m in zip(tamanhos, limites):
        linhas, coube = quebrar(desenho, texto, fonte(t, peso), largura, m)
        if coube:
            return t, linhas
    return tamanhos[-1], linhas


def _marca(imagem, x, y):
    """Desenha o arco de pontos e o nome do site no canto de cima."""
    w, h = 72, 40
    camada = Image.new("RGBA", (w * ESCALA, h * ESCALA), COBALTO + "00")  # mesma cor, transparente: evita borda escura ao reduzir
    d = ImageDraw.Draw(camada)
    k = w / 32 * ESCALA
    for cx, cy, raio in PONTOS_MARCA:
        r = raio * k
        d.ellipse((cx * k - r, cy * k - r, cx * k + r, cy * k + r), fill=COBALTO)
    pequena = camada.resize((w, h), Image.LANCZOS)
    imagem.paste(pequena, (x, y), pequena)
    ImageDraw.Draw(imagem).text((x + w + 16, y + h // 2), "Voto de Verdade", font=fonte(32, 600), fill=TINTA, anchor="lm")


def _arco(imagem):
    """Arco de pontos bem claros no canto de baixo à direita, como na imagem geral do site."""
    k = 2  # desenha em dobro e reduz, para as bordas ficarem lisas
    camada = Image.new("RGBA", (LARGURA * k, ALTURA * k), PONTO_CLARO + "00")
    d = ImageDraw.Draw(camada)
    cx, cy = (LARGURA - 150) * k, (ALTURA + 40) * k
    for raio in (110, 150, 190, 230):
        n = int(math.pi * raio / 36)
        for i in range(n + 1):
            a = math.pi * i / n
            x, y = cx + math.cos(a) * raio * k, cy - math.sin(a) * raio * k
            r = 8 * k
            d.ellipse((x - r, y - r, x + r, y + r), fill=PONTO_CLARO)
    pequena = camada.resize((LARGURA, ALTURA), Image.LANCZOS)
    imagem.paste(pequena, (0, 0), pequena)


def _base():
    imagem = Image.new("RGB", (LARGURA, ALTURA), PAPEL)
    _marca(imagem, MARGEM, 56)
    return imagem


def _salvar(imagem, destino):
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    if destino.endswith(".png"):  # fundo liso e letras: PNG fica nítido e pequeno
        imagem.save(destino, "PNG", optimize=True)
    else:  # com foto: JPEG
        imagem.save(destino, "JPEG", quality=88, subsampling=0, optimize=True)


def deputado(destino, nome, sigla, foto, endereco):
    """Foto (se houver), nome e «PARTIDO · UF». O mesmo arquivo serve a todos os idiomas, por isso só tem nome e sigla."""
    imagem = _base()
    d = ImageDraw.Draw(imagem)
    x = MARGEM
    topo, base = 150, 150 + 360
    if foto and os.path.exists(foto):
        retrato = Image.open(foto).convert("RGB")
        larg, alt = 270, 360
        ratio = max(larg / retrato.width, alt / retrato.height)
        retrato = retrato.resize((round(retrato.width * ratio), round(retrato.height * ratio)), Image.LANCZOS)
        esq, sup = (retrato.width - larg) // 2, (retrato.height - alt) // 2
        retrato = retrato.crop((esq, sup, esq + larg, sup + alt))
        mascara = Image.new("L", (larg * ESCALA, alt * ESCALA), 0)
        ImageDraw.Draw(mascara).rounded_rectangle((0, 0, larg * ESCALA - 1, alt * ESCALA - 1), radius=28 * ESCALA, fill=255)
        imagem.paste(retrato, (MARGEM, topo), mascara.resize((larg, alt), Image.LANCZOS))
        x = MARGEM + larg + 56
    largura = LARGURA - MARGEM - x
    tamanho, linhas = ajustar(d, nome, (68, 60, 52, 44), largura, 3)
    f = fonte(tamanho, 600)
    passo = round(tamanho * 1.12)
    bloco = len(linhas) * passo + (16 + 40 if sigla else 0)
    y = topo + max(0, (360 - 56 - bloco) // 2)  # centrado na altura da foto, acima do endereço
    for linha in linhas:
        d.text((x, y), linha, font=f, fill=TINTA)
        y += passo
    if sigla:
        d.text((x, y + 16), sigla, font=fonte(40, 500), fill=SUAVE)
    d.text((x, base), endereco, font=fonte(28, 400), fill=SUAVE, anchor="ls")
    _salvar(imagem, destino)


def texto(destino, titulo, sub=None, destaque=None, endereco=""):  # noqa: D417
    """Página de texto: título grande, uma frase de apoio e, se houver, uma etiqueta (por exemplo, «97 projetos votados»)."""
    imagem = _base()
    _arco(imagem)
    d = ImageDraw.Draw(imagem)
    largura = 760
    tamanho, linhas = ajustar(d, titulo, (92, 80, 68, 60, 52), largura, (2, 2, 2, 3, 3))
    f = fonte(tamanho, 600)
    passo = round(tamanho * 1.1)
    y = 160
    for linha in linhas:
        d.text((MARGEM, y), linha, font=f, fill=TINTA)
        y += passo
    if sub:
        limite = 456 if destaque else 530  # a frase de apoio não pode encostar na etiqueta nem no endereço
        y += 28
        for tam in (36, 32, 28):
            passo_sub = round(tam * 1.4)
            max_l = max(1, (limite - y) // passo_sub)
            ls, coube = quebrar(d, sub, fonte(tam, 400), largura, max_l)
            if coube:
                break
        for linha in ls:
            d.text((MARGEM, y), linha, font=fonte(tam, 400), fill=SUAVE)
            y += passo_sub
    if destaque:
        fc = fonte(30, 600)
        w = d.textlength(destaque, font=fc)
        d.rounded_rectangle((MARGEM, 480, MARGEM + w + 48, 480 + 56), radius=28, fill=COBALTO_CLARO)
        d.text((MARGEM + 24, 480 + 28), destaque, font=fc, fill=COBALTO, anchor="lm")
    if endereco:
        d.text((MARGEM, 578), endereco, font=fonte(28, 400), fill=SUAVE, anchor="ls")
    _salvar(imagem, destino)
