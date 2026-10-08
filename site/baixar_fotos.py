#!/usr/bin/env python3
"""Guarda a foto de cada deputado em site/fotos/<id>.jpg (só as que ainda faltam).

As fotos vêm do portal da Câmara. Guardá-las aqui evita que o navegador de quem visita o site
precise falar com outro endereço, e deixa as páginas mais rápidas.
Uso: python site/baixar_fotos.py [--limite 800]
"""
import argparse
import json
import os
import sys
import time
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
URL = "https://www.camara.leg.br/internet/deputado/bandep/{}.jpg"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", type=int, default=800)
    args = ap.parse_args()
    pasta = os.path.join(AQUI, "fotos")
    os.makedirs(pasta, exist_ok=True)
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
                f.write(corpo)
            baixadas += 1
        except Exception as e:  # uma foto que falha não pode derrubar a rotina
            print(f'AVISO: foto de {d["nome"]} ({d["id"]}): {e}', file=sys.stderr)
        time.sleep(0.15)
    print(f"Fotos: {baixadas} novas, {len(os.listdir(pasta))} guardadas, {faltam - baixadas} ainda faltam.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
