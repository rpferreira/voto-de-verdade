"""Idiomas do site: o português é o texto de origem; cada outro idioma tem um dicionário em site/idiomas/<idioma>.json.

O texto em português é a chave do dicionário. Trechos variáveis levam marcadores numerados: «{0} projetos com “{1}”».
O mesmo dicionário é lido pelo aplicativo (app.js) e pelo gerador de páginas (gerar_paginas.py).
Uma chave sem tradução não derruba nada: aparece em português e fica anotada em `faltam` (os testes exigem que fique vazia).
"""
import json
import os
import re

MESES = {
    "pt": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
}
HTML = {"pt": "pt-BR", "en": "en"}
OPEN_GRAPH = {"pt": "pt_BR", "en": "en_US"}


class Idioma:
    HTML = HTML
    OPEN_GRAPH = OPEN_GRAPH

    def __init__(self, codigo, pasta_site):
        self.codigo = codigo
        self.html = HTML[codigo]
        self.og = OPEN_GRAPH[codigo]
        self.prefixo = "" if codigo == "pt" else codigo + "/"
        self.dic = {}
        self.faltam = set()
        if codigo != "pt":
            with open(os.path.join(pasta_site, "idiomas", f"{codigo}.json"), encoding="utf-8") as f:
                self.dic = json.load(f)

    @property
    def en(self):
        return self.codigo == "en"

    def __call__(self, chave, *valores):
        texto = chave
        if self.codigo != "pt":
            if chave in self.dic:
                texto = self.dic[chave]
            else:
                self.faltam.add(chave)
        if valores:
            texto = re.sub(r"\{(\d+)\}", lambda m: str(valores[int(m.group(1))]), texto)
        return texto

    def data(self, iso):
        if not iso:
            return ""
        a, m, d = iso.split("-")
        if self.en:
            return f"{MESES['en'][int(m) - 1]} {int(d)}, {a}"
        return f"{int(d)} de {MESES['pt'][int(m) - 1]} de {a}"

    def mes_ano(self, ym):
        """«2025-03» → «março de 2025» / «March 2025»."""
        nome = MESES[self.codigo][int(ym[5:7]) - 1]
        return f"{nome} {ym[:4]}" if self.en else f"{nome} de {ym[:4]}"

    def milhar(self, n):
        return f"{n:,}" if self.en else f"{n:,}".replace(",", ".")

    def decimal(self, texto):
        """Troca o ponto decimal pela vírgula, no português."""
        return texto if self.en else texto.replace(".", ",")
