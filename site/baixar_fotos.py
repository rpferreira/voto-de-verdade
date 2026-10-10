#!/usr/bin/env python3
"""Guarda a foto de cada deputado em site/fotos/<id>.jpg (só as que ainda faltam).

As fotos vêm do portal da Câmara. Guardá-las aqui evita que o navegador de quem visita o site
precise falar com outro endereço, e deixa as páginas mais rápidas.

Cada foto é reduzida para no máximo 192 px de largura (o site a mostra com 96 px; 192 px deixa nítida em tela de
alta densidade). O original da Câmara tem 354 px e pesa cerca de 28 KB; reduzida, fica com cerca de 8 KB. A redução usa
a biblioteca Pillow; se ela não estiver instalada, a foto original é guardada assim mesmo (e o aviso aparece uma vez).

Uso: python site/baixar_fotos.py [--limite 800]
     python site/baixar_fotos.py --reduzir-existentes    # reduz as fotos já guardadas (pode repetir: ignora as que já estão pequenas)
"""
import argparse
import json
import os
import sys
import time
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
URL = "https://www.camara.leg.br/internet/deputado/bandep/{}.jpg"
LARGURA_MAX = 192   # px: o dobro dos 96 px com que o site mostra a foto
QUALIDADE = 80      # JPEG
_avisou = False


def reduzir(corpo):
    """Devolve a foto (bytes de JPEG) com no máximo LARGURA_MAX px de largura. Foto já pequena ou sem Pillow: devolve igual."""
    global _avisou
    try:
        from PIL import Image
    except ImportError:
        if not _avisou:
            print("AVISO: Pillow não instalado (pip install pillow); as fotos ficam no tamanho original.", file=sys.stderr)
            _avisou = True
        return corpo
    import io
    with Image.open(io.BytesIO(corpo)) as im:
        if im.width <= LARGURA_MAX:
            return corpo  # nunca aumentamos uma foto
        im = im.convert("RGB").resize((LARGURA_MAX, round(im.height * LARGURA_MAX / im.width)), Image.LANCZOS)
        saida = io.BytesIO()
        im.save(saida, "JPEG", quality=QUALIDADE, optimize=True, progressive=True)  # sem metadados (EXIF)
    return saida.getvalue() if len(saida.getvalue()) < len(corpo) else corpo


def reduzir_existentes(pasta):
    antes = depois = n = 0
    for nome in sorted(os.listdir(pasta)):
        if not nome.endswith(".jpg"):
            continue
        caminho = os.path.join(pasta, nome)
        with open(caminho, "rb") as f:
            corpo = f.read()
        novo = reduzir(corpo)
        antes += len(corpo)
        depois += len(novo)
        if novo is not corpo and len(novo) < len(corpo):
            with open(caminho, "wb") as f:
                f.write(novo)
            n += 1
    print(f"Fotos reduzidas: {n}. De {antes / 1e6:.1f} MB para {depois / 1e6:.1f} MB.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", type=int, default=800)
    ap.add_argument("--reduzir-existentes", action="store_true", help="só reduz as fotos já guardadas, sem baixar nada")
    args = ap.parse_args()
    pasta = os.path.join(AQUI, "fotos")
    os.makedirs(pasta, exist_ok=True)
    if args.reduzir_existentes:
        reduzir_existentes(pasta)
        return 0
    with open(os.path.join(AQUI, "dados", "deputados.json"), encoding="utf-8") as f:
        deputados = json.load(f)
    baixadas = faltam = 0
    for d in deputados:
        destino = os.path.join(pasta, f'{d["id"]}.jpg')
        if os.path.exists(destino):
            continue
        faltam += 1
        if baixadas >= args.limite:
            continue
        try:
            req = urllib.request.Request(URL.format(d["id"]), headers={"User-Agent": "voto-de-verdade (site independente)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                corpo = r.read()
            if corpo[:2] != b"\xff\xd8" or len(corpo) < 1000:
                raise ValueError("não parece uma foto")
            with open(destino, "wb") as f:
                f.write(reduzir(corpo))
            baixadas += 1
        except Exception as e:  # uma foto que falha não pode derrubar a rotina
            print(f'AVISO: foto de {d["nome"]} ({d["id"]}): {e}', file=sys.stderr)
        time.sleep(0.15)
    print(f"Fotos: {baixadas} novas, {len(os.listdir(pasta))} guardadas, {faltam - baixadas} ainda faltam.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
