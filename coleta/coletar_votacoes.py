#!/usr/bin/env python3
"""Voto de Verdade: coleta de dados da Câmara dos Deputados.

Roda todo dia no GitHub (veja .github/workflows/atualizacao-diaria.yml) e também no seu computador.
O que faz:
  1. Junta as votações de plenário desde o início da legislatura (1/2/2023), guardando em cache.
  2. Classifica cada votação pelo texto da descrição (mérito, urgência, emenda, etc.).
  3. Nas votações de mérito, busca o voto de cada deputado.
  4. Descobre qual projeto foi votado e guarda a ementa e o link do texto integral.
  5. Busca a lista de deputados em exercício.
  6. Confere se algo falhou e registra a execução.

Uso (dentro da pasta dados):
  python3 ../coleta/coletar_votacoes.py --diario        rotina diária: só atualiza o cache
  python3 ../coleta/coletar_votacoes.py                 também gera as planilhas de conferência
  python3 ../coleta/coletar_votacoes.py --desde 2026-06-01   teste rápido
  python3 ../coleta/coletar_votacoes.py --atualizar     ignora o cache das janelas de datas

Só usa a biblioteca padrão do Python 3. Na primeira vez leva de 30 a 50 minutos, porque faz uma pausa
entre as consultas para não ser bloqueado. Nos dias seguintes leva poucos minutos.
Termina com erro (código 1) se algo falhar, para o GitHub avisar.

Arquivos gerados na pasta atual:
  cache_v5.json                   tudo o que veio da API (é a base do banco de dados)
  relatorio_api_camara_v5.txt     relatório da execução
  (sem --diario) amostra_classificacao_v5.csv, projetos_revisar_v5.csv, dados_merito_v5.json,
                 votos_nominais_v5.json
"""
import argparse
import csv
import json
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://dadosabertos.camara.leg.br/api/v2"
PAUSA = 0.35  # segundos entre chamadas
JANELA_DIAS = 80  # a API recusa intervalos maiores que 3 meses
MAX_PAGINAS = 100
INICIO_LEGISLATURA = date(2023, 2, 1)
CACHE = "cache_v5.json"
CATEGORIAS = ["merito", "urgencia", "emenda", "requerimento", "destaque",
              "parecer", "redacao_final", "tramitacao", "procedimento", "outros"]
linhas = []

# Regras de classificação. Vale a que aparece primeiro no texto da descrição;
# em empate, a primeira da lista. Assim "Aprovado o Parecer ... da Medida Provisória"
# vira parecer, e "Proposta de Emenda à Constituição" vira mérito (não emenda).
REGRAS = [
    ("tramitacao", r"alteração do regime de tramitação"),
    ("destaque", r"mantido o texto"),
    ("destaque", r"suprimido o texto"),
    ("procedimento", r"\brecursos?\b"),
    ("procedimento", r"\bpreferência\b"),
    ("redacao_final", r"redação final"),
    ("parecer", r"\bparecer\b"),
    ("requerimento", r"\brequerimentos?\b"),
    ("destaque", r"\bdestaques?\b"),
    ("merito", r"proposta de emenda (?:(?:à|a) constituição|constitucional)"),
    ("merito", r"subemenda substitutiva"),
    ("merito", r"\bsubstitutivo\b"),
    ("merito", r"projeto de (?:lei|decreto legislativo|resolução)"),
    ("merito", r"medida provisória"),
    ("merito", r"texto-base"),
    ("emenda", r"\bsubemendas?\b"),
    ("emenda", r"\bsubmendas?\b"),
    ("emenda", r"\bemendas?\b"),
]

TIPOS = [
    ("PEC", r"proposta de emenda (?:(?:à|a) constituição|constitucional)"),
    ("PLP", r"projeto de lei complementar"),
    ("PLV", r"projeto de lei de conversão"),
    ("PL", r"projeto de lei\b"),
    ("PDL", r"projeto de decreto legislativo"),
    ("PRC", r"projeto de resolução"),
    ("MPV", r"medida provisória"),
]


def classificar(descricao):
    d = (descricao or "").lower()
    melhor = None
    for categoria, rx in REGRAS:
        m = re.search(rx, d)
        if m and (melhor is None or m.start() < melhor[1]):
            melhor = (categoria, m.start())
    if melhor is None:
        return "outros"
    if melhor[0] == "requerimento" and "urgência" in d:
        return "urgencia"
    return melhor[0]


def extrair_materia(descricao):
    """Devolve (sigla, numero, ano) lidos do texto, ou None nos campos que faltarem."""
    d = (descricao or "").lower()
    melhor = None
    for sigla, rx in TIPOS:
        m = re.search(rx, d)
        if m and (melhor is None or m.start() < melhor[1]):
            melhor = (sigla, m.start(), m.end())
    if melhor is None:
        return None, None, None
    n = re.search(r"(?:n[ºo°]\s*)?(\d[\d\.]*)(?:-[a-z])?\s*(?:/|,?\s*de\s*)(\d{4})", d[melhor[2]:])
    if not n:
        return melhor[0], None, None
    return melhor[0], n.group(1).replace(".", ""), n.group(2)


NOMES_CATEGORIA = {
    "urgencia": "urgência", "emenda": "emenda", "requerimento": "requerimento", "destaque": "destaque",
    "parecer": "parecer", "redacao_final": "redação final", "tramitacao": "mudança de tramitação",
    "procedimento": "questão de procedimento"}

# Trechos que aparecem em votações de mérito legítimas e não indicam outro tipo de votação.
BENIGNOS = [
    r"ressalvad[oa]s? (?:o|a|os|as) destaques?", r"com exceção d[oa]s? [^.,;]*",
    r"na forma d[oa] (?:emenda|substitutivo|parecer|projeto de lei de conversão)[^.,;]*",
    r"(?:sub)?emendas? (?:substitutiva|aglutinativa)(?: global| saneadora)?",
    r"proposta de emenda (?:(?:à|a) constituição|constitucional)",
    r"parecer d[oa] relator", r"adotad[oa] pel[oa] relator[a]?[^.,;]*",
]
NIVEL = {"baixa": 0, "media": 1, "alta": 2}


def avaliar_texto(descricao):
    """Classifica pelo texto e diz o quanto confia: ("merito", "alta"|"media"|"baixa", [motivos]).
    Os motivos já vêm em português simples, para aparecerem na tela."""
    categoria = classificar(descricao)
    d = (descricao or "").lower()
    if categoria == "outros":
        return categoria, "baixa", ["a descrição da votação não foi reconhecida"]
    if categoria != "merito":
        return categoria, "alta", []
    motivos = []
    limpo = d
    for rx in BENIGNOS:
        limpo = re.sub(rx, " ", limpo)
    mencionados = []
    for cat, rx in REGRAS:
        if cat != "merito" and cat not in mencionados and re.search(rx, limpo):
            mencionados.append(cat)
    if mencionados:
        nomes = ", ".join(NOMES_CATEGORIA.get(c, c) for c in mencionados)
        motivos.append(f"o texto da votação também fala de {nomes}")
    sigla, numero, ano = extrair_materia(descricao)
    if not (sigla and numero and ano):
        motivos.append("o texto da votação não informa o número do projeto")
    return categoria, ("alta" if not motivos else "media"), motivos


def totais_do_texto(descricao):
    """(Sim, Não, Abstenção ou None) quando a descrição traz os totais, senão None."""
    m = re.search(r"Sim:\s*(\d+);\s*N[ãa]o:\s*(\d+)(?:;\s*Absten[çc][ãa]o:\s*(\d+))?", descricao or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), (int(m.group(3)) if m.group(3) else None)


def conferir_totais(descricao, lista_de_votos):
    """True/False se os totais do texto batem com os votos de cada deputado; None se o texto não traz totais."""
    t = totais_do_texto(descricao)
    if t is None:
        return None
    c = Counter(tipo for _d, tipo in lista_de_votos)
    if (c["Sim"], c["Não"]) != (t[0], t[1]):
        return False
    return t[2] is None or c["Abstenção"] == t[2]


def log(txt=""):
    print(txt)
    linhas.append(txt)


def get_url(url, tentativas=3):
    """Devolve (status, json). Em erro HTTP, o json traz {'_erro': texto da API}.
    status None = erro de rede. Repete quando a API pede calma (429) ou falha (5xx)."""
    for i in range(tentativas):
        time.sleep(PAUSA)
        req = Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "voto-de-verdade-coleta/0.5",
        })
        try:
            with urlopen(req, timeout=30) as r:
                return r.status, json.load(r)
        except HTTPError as e:
            try:
                corpo = e.read().decode("utf-8", "replace")
            except Exception:
                corpo = ""
            if e.code in (429, 500, 502, 503, 504) and i < tentativas - 1:
                time.sleep(5 * (i + 1))
                continue
            return e.code, {"_erro": corpo[:300]}
        except (URLError, TimeoutError, ValueError) as e:
            if i < tentativas - 1:
                time.sleep(3)
                continue
            return None, {"_erro": str(e)}


def get(caminho, **params):
    return get_url(BASE + caminho + ("?" + urlencode(params) if params else ""))


def data_da(v):
    return str(v.get("data") or v.get("dataHoraRegistro") or "?")[:10]


# ---------------------------------------------------------------- cache

def carregar_cache():
    cache = {}
    if os.path.exists(CACHE):
        try:
            with open(CACHE, encoding="utf-8") as f:
                cache = json.load(f)
        except (OSError, ValueError):
            print(f"   Aviso: não consegui ler {CACHE}; vou começar do zero.")
            cache = {}
    for chave in ("janelas", "votos", "props", "deputados", "detalhes", "partido_no_voto"):
        cache.setdefault(chave, {})
    cache.setdefault("recentes", [])
    cache.setdefault("deputados_atuais", [])
    cache.setdefault("execucoes", [])
    return cache


def salvar_cache(cache):
    tmp = CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, CACHE)


# ---------------------------------------------------------------- coleta

def janelas_ate(fim):
    """Janelas fixas de 80 dias a partir do início da legislatura. Fixas para o cache valer sempre."""
    saida, a = [], INICIO_LEGISLATURA
    while a <= fim:
        b = min(fim, a + timedelta(days=JANELA_DIAS - 1))
        saida.append((a, b))
        a = b + timedelta(days=1)
    return saida


def buscar_janela(a, b):
    """Votações de plenário entre a e b. Devolve (lista, ok)."""
    todas, vistos, pagina = [], set(), 1
    while True:
        st, d = get("/votacoes", dataInicio=a.isoformat(), dataFim=b.isoformat(),
                    itens=100, pagina=pagina, ordem="ASC", ordenarPor="dataHoraRegistro")
        if st != 200:
            log(f"   Janela {a} a {b} falhou na página {pagina}: HTTP {st}. {d.get('_erro', '')}")
            return [v for v in todas if v.get("siglaOrgao") == "PLEN"], False
        dados = d.get("dados", [])
        novos = 0
        for v in dados:
            if v.get("id") not in vistos:
                vistos.add(v.get("id"))
                todas.append(v)
                novos += 1
        if len(dados) < 100 or novos == 0:
            break
        pagina += 1
        if pagina > MAX_PAGINAS:
            log(f"   ATENÇÃO: janela {a} a {b} passou de {MAX_PAGINAS} páginas; pode faltar votação.")
            return [v for v in todas if v.get("siglaOrgao") == "PLEN"], False
    return [v for v in todas if v.get("siglaOrgao") == "PLEN"], True


def coletar_plenario(ini, fim, cache, atualizar):
    """Votações de plenário entre ini e fim, usando o cache das janelas já completas."""
    plen, incompletas, recentes = [], [], []
    todas = [(a, b) for a, b in janelas_ate(fim) if b >= ini]
    for i, (a, b) in enumerate(todas, 1):
        chave = f"{a}|{b}"
        if chave in cache["janelas"] and not atualizar:
            lista, ok = cache["janelas"][chave], True
        else:
            lista, ok = buscar_janela(a, b)
            # só guarda no cache se a janela é antiga e veio completa
            if ok and b < fim - timedelta(days=3):
                cache["janelas"][chave] = lista
                salvar_cache(cache)
            else:
                recentes += lista
        if not ok:
            incompletas.append(f"{a} a {b}")
        plen += lista
        print(f"   ...janela {i}/{len(todas)} ({a} a {b}): {len(plen)} votações de plenário até agora", flush=True)
    cache["recentes"] = recentes  # votações das janelas ainda abertas; o banco de dados usa junto com as janelas
    plen = [dict(v) for v in plen if data_da(v) >= ini.isoformat()]
    plen.sort(key=data_da, reverse=True)
    return plen, incompletas


def buscar_votos(ids, cache):
    """Guarda em cache os votos de cada votação: lista de [id do deputado, tipo de voto].
    Lista vazia = votação simbólica. Devolve os ids que continuaram com erro."""
    # também refaz as consultas guardadas antes de existir o partido no dia do voto
    faltam = [i for i in ids if str(i) not in cache["votos"]
              or (cache["votos"][str(i)] and str(i) not in cache["partido_no_voto"])]
    print(f"   {len(ids) - len(faltam)} já estavam em cache; faltam {len(faltam)}.", flush=True)

    def uma(vid):
        st, r = get(f"/votacoes/{vid}/votos")
        if st != 200:
            return False
        lista, partidos = [], {}
        for x in r.get("dados", []):
            dep = x.get("deputado_") or {}
            if dep.get("id") is None:
                continue
            lista.append([dep["id"], x.get("tipoVoto")])
            if dep.get("siglaPartido"):
                partidos[str(dep["id"])] = dep["siglaPartido"]  # partido informado junto com o voto
            cache["deputados"][str(dep["id"])] = [dep.get("nome"), dep.get("siglaPartido"), dep.get("siglaUf")]
        cache["votos"][str(vid)] = lista
        if lista:
            cache["partido_no_voto"][str(vid)] = partidos
        return True

    erros = []
    for i, vid in enumerate(faltam, 1):
        if not uma(vid):
            erros.append(vid)
        if i % 25 == 0 or i == len(faltam):
            salvar_cache(cache)
            print(f"   ...votos {i}/{len(faltam)}", flush=True)
    if erros:
        print(f"   Repetindo {len(erros)} consultas que deram erro...", flush=True)
        time.sleep(10)
        erros = [vid for vid in erros if not uma(vid)]
        salvar_cache(cache)
    return erros


def buscar_proposicoes(chaves, cache):
    """Procura cada projeto por tipo, número e ano. Guarda id e ementa. Devolve as chaves com erro."""
    # também refaz a busca dos que deram mais de um resultado e ainda não guardaram quais eram os candidatos
    faltam = [c for c in chaves if c not in cache["props"]
              or (cache["props"][c].get("n", 0) > 1 and "candidatos" not in cache["props"][c])]
    print(f"   {len(chaves) - len(faltam)} já estavam em cache; faltam {len(faltam)}.", flush=True)
    erros = []
    for i, chave in enumerate(faltam, 1):
        sigla, numero, ano = chave.split("|")
        st, r = get("/proposicoes", siglaTipo=sigla, numero=numero, ano=ano, itens=5)
        if st != 200:
            erros.append(chave)
        else:
            achadas = r.get("dados", [])
            if len(achadas) == 1:
                p = achadas[0]
                cache["props"][chave] = {"n": 1, "id": p.get("id"), "uri": p.get("uri"),
                                         "ementa": p.get("ementa")}
            else:
                cache["props"][chave] = {
                    "n": len(achadas),
                    "candidatos": [[x.get("id"), f"{x.get('siglaTipo')} {x.get('numero')}/{x.get('ano')}",
                                    (x.get("ementa") or "")[:120]] for x in achadas]}
        if i % 25 == 0 or i == len(faltam):
            salvar_cache(cache)
            print(f"   ...proposições {i}/{len(faltam)}", flush=True)
    return erros


# ---------------------------------------------------------------- análise

def buscar_deputados_atuais(cache):
    """Lista de deputados em exercício, com foto e e-mail. Devolve True se deu certo."""
    atuais, pagina = [], 1
    while True:
        st, r = get("/deputados", itens=100, pagina=pagina, ordem="ASC", ordenarPor="nome")
        if st != 200:
            log(f"   Lista de deputados falhou na página {pagina}: HTTP {st}")
            return False
        dados = r.get("dados", [])
        atuais += [{"id": d.get("id"), "nome": d.get("nome"), "partido": d.get("siglaPartido"),
                    "uf": d.get("siglaUf"), "foto": d.get("urlFoto"), "email": d.get("email")} for d in dados]
        if len(dados) < 100 or pagina >= 20:
            break
        pagina += 1
    cache["deputados_atuais"] = atuais
    salvar_cache(cache)
    return True


def buscar_detalhes(cache):
    """Tipo, número, ano, ementa e link do texto integral de cada projeto votado.
    Devolve quantos continuaram com erro."""
    ids = {p["id"] for p in cache["props"].values() if p.get("n") == 1 and p.get("id")}
    # também os candidatos das buscas que acharam mais de um projeto (para escolher pela data da votação)
    ids |= {x[0] for p in cache["props"].values() if p.get("n", 0) > 1 for x in p.get("candidatos", []) if x[0]}
    ids = sorted(ids)
    faltam = [i for i in ids if str(i) not in cache["detalhes"]]
    print(f"   {len(ids) - len(faltam)} projetos já tinham detalhe em cache; faltam {len(faltam)}.", flush=True)
    erros = 0
    for k, pid in enumerate(faltam, 1):
        st, r = get(f"/proposicoes/{pid}")
        if st == 200:
            d = r.get("dados", {})
            cache["detalhes"][str(pid)] = {
                "siglaTipo": d.get("siglaTipo"), "numero": d.get("numero"), "ano": d.get("ano"),
                "ementa": d.get("ementa"), "ementaDetalhada": d.get("ementaDetalhada"),
                "urlInteiroTeor": d.get("urlInteiroTeor"), "dataApresentacao": d.get("dataApresentacao")}
        else:
            erros += 1
        if k % 25 == 0 or k == len(faltam):
            salvar_cache(cache)
            print(f"   ...detalhes {k}/{len(faltam)}", flush=True)
    return erros


def curto(valor, n=300):
    return json.dumps(valor, ensure_ascii=False)[:n]


EQUIVALENTES = {"PDL": {"PDL", "PDC"}, "PDC": {"PDL", "PDC"}}


def completar_por_detalhe(merito, cache):
    """Para os projetos que a busca por tipo/número/ano não achou de forma única, tenta o detalhe
    da votação (campo proposicoesAfetadas):
      - aceita a proposição de mesmo tipo, número e ano (PDL e PDC contam como o mesmo tipo);
      - se a busca não achou nada e o detalhe aponta para uma única proposição, aceita essa
        (o texto costuma citar o número antigo, do Senado) e marca como divergente, para revisão.
    Devolve (quantos resolveu, quantos tentou)."""
    por_chave = {}
    for v in merito:
        if v.get("_chave"):
            por_chave.setdefault(v["_chave"], v)
    pendentes = [c for c, p in cache["props"].items()
                 if c in por_chave and p.get("n") != 1 and not p.get("tentou_detalhe2")]
    resolvidos = 0
    for c in pendentes:
        v = por_chave[c]
        sigla, numero, ano = c.split("|")
        st, r = get(f"/votacoes/{v['id']}")
        if st != 200:
            continue  # tenta de novo na próxima rodada
        afetadas = r.get("dados", {}).get("proposicoesAfetadas") or []
        achado = next((p for p in afetadas
                       if p.get("siglaTipo") in EQUIVALENTES.get(sigla, {sigla})
                       and str(p.get("numero")) == numero and str(p.get("ano")) == ano), None)
        divergente = False
        # a busca achou mais de um projeto: vale o único candidato que a votação afeta
        cand_ids = {x[0] for x in cache["props"][c].get("candidatos", [])}
        if achado is None and cache["props"][c].get("n", 0) > 1 and cand_ids:
            em_comum = [x for x in afetadas if x.get("id") in cand_ids]
            if len(em_comum) == 1:
                achado = em_comum[0]
        if achado is None and cache["props"][c].get("n") == 0 and len(afetadas) == 1:
            achado, divergente = afetadas[0], True
        if achado:
            cache["props"][c] = {
                "n": 1, "id": achado.get("id"), "uri": achado.get("uri"), "ementa": achado.get("ementa"),
                "via": "detalhe da votação", "divergente": divergente,
                "achada": f"{achado.get('siglaTipo')} {achado.get('numero')}/{achado.get('ano')}"}
            resolvidos += 1
        else:
            cache["props"][c]["tentou_detalhe2"] = True
            resumo = [f"{p.get('siglaTipo')} {p.get('numero')}/{p.get('ano')}" for p in afetadas[:5]]
            cands = [x[1] for x in cache["props"][c].get("candidatos", [])]
            log(f"     {c.replace('|', ' ')}: o detalhe da votação de {data_da(v)} lista {resumo or 'nada'}"
                + (f"; a busca achou {cands}" if cands else ""))
    if pendentes:
        salvar_cache(cache)
    return resolvidos, len(pendentes)


def resolver_sem_texto(merito, cache):
    """Votações cujo texto não traz tipo, número e ano: usa o detalhe da votação, só quando
    ele aponta para exatamente uma proposição. Devolve (resolvidas, tentadas)."""
    tentadas = resolvidas = 0
    for v in merito:
        if v.get("_chave"):
            continue
        chave = f"votacao|{v['id']}"
        p = cache["props"].get(chave)
        if p is None:
            st, r = get(f"/votacoes/{v['id']}")
            if st != 200:
                continue
            tentadas += 1
            afetadas = r.get("dados", {}).get("proposicoesAfetadas") or []
            if len(afetadas) == 1:
                a = afetadas[0]
                p = {"n": 1, "id": a.get("id"), "uri": a.get("uri"), "ementa": a.get("ementa"),
                     "via": "detalhe da votação"}
            else:
                p = {"n": 0, "tentou_detalhe": True, "afetadas": len(afetadas)}
            cache["props"][chave] = p
        if p.get("n") == 1:
            v["_chave"] = chave
            resolvidas += 1
    if tentadas:
        salvar_cache(cache)
    return resolvidas, tentadas


def percentil(valores, p):
    if not valores:
        return None
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados) - 1, int(p / 100 * len(ordenados)))]


def normalizar(desc):
    d = re.sub(r"\s+", " ", (desc or "").lower())
    d = re.sub(r"\d[\d\./]*", "#", d)
    return d[:90]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--atualizar", action="store_true", help="ignora o cache das janelas")
    ap.add_argument("--desde", help="data inicial AAAA-MM-DD (padrão: início da legislatura)")
    ap.add_argument("--diario", action="store_true", help="rotina diária: não gera as planilhas de conferência")
    ap.add_argument("--pasta", help="pasta onde ficam o cache e os arquivos (padrão: a pasta atual)")
    args = ap.parse_args()
    if args.pasta:
        os.makedirs(args.pasta, exist_ok=True)
        os.chdir(args.pasta)
    inicio_execucao = time.time()

    fim = date.today()
    ini = date.fromisoformat(args.desde) if args.desde else INICIO_LEGISLATURA
    if ini < INICIO_LEGISLATURA:
        ini = INICIO_LEGISLATURA
    corte_12m = (fim - timedelta(days=365)).isoformat()
    log(f"Coleta Voto de Verdade (v5) em {fim.isoformat()}")
    cache = carregar_cache()

    # 1) Votações de plenário
    log(f"\n1) Votações de plenário de {ini} a {fim}")
    plen, incompletas = coletar_plenario(ini, fim, cache, args.atualizar)
    log(f"   {len(plen)} votações de plenário.")
    if incompletas:
        log(f"   ATENÇÃO: {len(incompletas)} janela(s) não vieram completas, os números estão incompletos: "
            + "; ".join(incompletas))
    if not plen:
        log("   Nenhuma votação de plenário. Fim.")
        salvar()
        return
    log(f"   Mais antiga: {data_da(plen[-1])}. Mais recente: {data_da(plen[0])}.")

    # 2) Classificação
    for v in plen:
        v["_cat"] = classificar(v.get("descricao"))
    cont = Counter(v["_cat"] for v in plen)
    log("\n2) Classificação pelo texto da descrição (todas as votações de plenário):")
    for cat, n in cont.most_common():
        log(f"   {cat:14} {n:5}  ({100 * n / len(plen):.0f}%)")
    log("   Exemplos por categoria (para conferir se a regra acertou):")
    for cat in CATEGORIAS:
        for v in [x for x in plen if x["_cat"] == cat][:3]:
            log(f"   [{cat}] {data_da(v)} | {(v.get('descricao') or '').replace(chr(10), ' ')[:100]}")
    outros = Counter(normalizar(v.get("descricao")) for v in plen if v["_cat"] == "outros")
    if outros:
        log(f"   Descrições mais comuns em 'outros' ({sum(outros.values())} no total; números trocados por #):")
        for desc, n in outros.most_common(25):
            log(f"   {n:5}x  {desc}")

    # 3) Votos individuais nas votações de mérito
    merito = [v for v in plen if v["_cat"] == "merito"]
    log(f"\n3) Votos individuais nas {len(merito)} votações de mérito:")
    erros_votos = set(buscar_votos([v["id"] for v in merito], cache))
    for v in merito:
        sigla, numero, ano = extrair_materia(v.get("descricao"))
        v["_sigla"], v["_numero"], v["_ano"] = sigla, numero, ano
        lista = cache["votos"].get(str(v["id"]))
        v["_n_votos"] = None if lista is None else len(lista)
        # votação em que todos os registros vêm sem tipo de voto: o voto não é divulgado
        v["_secreta"] = bool(lista) and all(t is None for _d, t in lista)
    nominais = [v for v in merito if v["_n_votos"] and not v["_secreta"]]
    secretas = [v for v in merito if v["_secreta"]]
    simbolicas = [v for v in merito if v["_n_votos"] == 0]
    com_erro = [v for v in merito if v["_n_votos"] is None]
    log(f"   Com voto individual (nominais): {len(nominais)} ({100 * len(nominais) / len(merito):.0f}%)")
    log(f"   Sem voto individual (simbólicas ou sem registro): {len(simbolicas)}")
    log(f"   Com presença registrada, mas sem o voto de cada deputado (parece votação secreta): {len(secretas)}")
    for v in secretas[:5]:
        log(f"     {data_da(v)} | {(v.get('descricao') or '')[:100]}")
    log(f"   Com erro na consulta, mesmo após repetir: {len(com_erro)}"
        + ("" if not erros_votos else " (rode de novo para tentar outra vez)"))

    por_ano = defaultdict(lambda: [0, 0, 0])
    for v in merito:
        a = data_da(v)[:4]
        por_ano[a][0] += 1
        if v["_n_votos"] and not v["_secreta"]:
            por_ano[a][1] += 1
        elif v["_n_votos"] == 0 or v["_secreta"]:
            por_ano[a][2] += 1
    log("   Por ano (mérito: total / com voto individual / sem):")
    for a in sorted(por_ano):
        log(f"   {a}: {por_ano[a][0]} / {por_ano[a][1]} / {por_ano[a][2]}")
    nom_12m = sum(1 for v in nominais if data_da(v) >= corte_12m)
    log(f"   Nos últimos 12 meses: {nom_12m} votações de mérito com voto individual.")

    # 4) Projeto votado e ementa
    log("\n4) Projeto votado (tipo, número e ano lidos do texto) e ementa:")
    sem_num = [v for v in merito if not (v["_sigla"] and v["_numero"] and v["_ano"])]
    log(f"   Votações de mérito sem tipo, número e ano legíveis no texto: {len(sem_num)} de {len(merito)}")
    for v in sem_num[:5]:
        log(f"     {data_da(v)} | {(v.get('descricao') or '')[:110]}")
    for v in merito:
        v["_chave"] = (f"{v['_sigla']}|{v['_numero']}|{v['_ano']}"
                       if v["_sigla"] and v["_numero"] and v["_ano"] else None)
    chaves = sorted({v["_chave"] for v in merito if v["_chave"]})
    buscar_proposicoes(chaves, cache)
    salvar_cache(cache)
    nao_achados = sum(1 for c in chaves if cache["props"].get(c, {}).get("n") != 1)
    if nao_achados:
        print(f"   {nao_achados} projetos sem resultado único na busca; tentando pelo detalhe da votação...", flush=True)
        resolvidos, tentados = completar_por_detalhe(merito, cache)
        if tentados:
            log(f"   Pelo detalhe da votação (proposicoesAfetadas): {resolvidos} de {tentados} projetos resolvidos.")
    if sem_num:
        print(f"   {len(sem_num)} votações sem número no texto; tentando pelo detalhe da votação...", flush=True)
        res, tent = resolver_sem_texto(merito, cache)
        log(f"   Votações sem número no texto resolvidas pelo detalhe da votação: {res} de {len(sem_num)}.")
    chaves = sorted({v["_chave"] for v in merito if v["_chave"]})
    achou = Counter()
    for c in chaves:
        p = cache["props"].get(c)
        if p is None:
            achou["erro (rode de novo)"] += 1
        elif p["n"] == 1:
            achou["exatamente 1"] += 1
        elif p["n"] == 0:
            achou["nenhuma"] += 1
        else:
            achou["mais de 1"] += 1
    log(f"   Projetos diferentes votados: {len(chaves)}. Busca na API: {dict(achou)}")
    sem_unico = [c for c in chaves if c in cache["props"] and cache["props"][c]["n"] != 1]
    for c in sem_unico[:15]:
        log(f"     sem resultado único: {c.replace('|', ' ')} ({cache['props'][c]['n']} resultados)")
    if len(sem_unico) > 15:
        log(f"     ...e mais {len(sem_unico) - 15}")
    com_nominal = {v["_chave"] for v in nominais if v["_chave"]}
    log(f"   Desses projetos, {len(com_nominal)} com ao menos uma votação nominal de mérito "
        f"e {len(chaves) - len(com_nominal)} só com votações simbólicas.")

    # 4b) Deputados em exercício e detalhe dos projetos
    log("\n4b) Deputados em exercício e detalhe dos projetos votados:")
    deputados_ok = buscar_deputados_atuais(cache)
    log(f"   Deputados em exercício: {len(cache['deputados_atuais'])}" + ("" if deputados_ok else " (falhou; usando a lista anterior)"))
    erros_detalhes = buscar_detalhes(cache)
    if erros_detalhes:
        log(f"   {erros_detalhes} projetos sem detalhe por erro de consulta (rode de novo).")
    sem_url = sum(1 for d in cache["detalhes"].values() if not d.get("urlInteiroTeor"))
    log(f"   Projetos com detalhe: {len(cache['detalhes'])}; sem link do texto integral: {sem_url}")

    # 5) Votos por deputado
    log("\n5) Votos individuais por deputado (votações nominais de mérito):")
    conta, conta_12m = Counter(), Counter()
    for v in nominais:
        for dep_id, _tipo in cache["votos"][str(v["id"])]:
            conta[dep_id] += 1
            if data_da(v) >= corte_12m:
                conta_12m[dep_id] += 1
    ativos = [d for d in conta_12m]  # deputados que votaram nos últimos 12 meses
    totais = [conta[d] for d in ativos]
    if totais:
        log(f"   Deputados que votaram em alguma nominal nos últimos 12 meses: {len(ativos)}")
        log(f"   Votos individuais de cada um desde {ini}: "
            f"mínimo {min(totais)}, 10% abaixo de {percentil(totais, 10)}, "
            f"mediana {percentil(totais, 50)}, máximo {max(totais)}")
        log(f"   Deputados com menos de 20 votos individuais: {sum(1 for t in totais if t < 20)}")
    log(f"   Votos individuais registrados no total: {sum(conta.values())}")
    tipos_voto = Counter(t for v in nominais for _d, t in cache["votos"][str(v["id"])])
    log(f"   Valores de tipoVoto: {dict(tipos_voto)}")
    if tipos_voto.get(None):
        log(f"   Atenção: {tipos_voto[None]} votos sem tipo em votações nominais comuns.")

    # 6) Arquivos de conferência (só fora da rotina diária)
    if not args.diario:
        salvar_dados(merito, cache)
        n_rev = salvar_revisao(merito, cache)
        salvar_votos(nominais, cache)
        salvar_amostra(plen)
        log("\n6) Arquivos gerados: dados_merito_v5.json, votos_nominais_v5.json, amostra_classificacao_v5.csv"
            + (f", projetos_revisar_v5.csv ({n_rev} projetos)" if n_rev else ""))
        if n_rev:
            log("   projetos_revisar_v5.csv: projetos em que o texto da votação cita um número e a API aponta outro.")
            log("   No site, essas votações aparecem com o aviso de que a classificação pode estar errada.")
        log("   (As planilhas são opcionais: o projeto não depende de revisão humana. Servem só para quem quiser conferir.)")

    # 7) Conferência e registro da execução
    problemas, avisos = [], []
    if incompletas:
        problemas.append(f"{len(incompletas)} janela(s) de datas incompletas")
    if com_erro:
        problemas.append(f"{len(com_erro)} votações de mérito sem consulta de votos")
    if erros_detalhes:
        problemas.append(f"{erros_detalhes} projetos sem detalhe")
    if not deputados_ok:
        problemas.append("lista de deputados não atualizada")
    sem_projeto = sum(1 for c in chaves if cache["props"].get(c, {}).get("n") != 1)
    if sem_projeto:
        avisos.append(f"{sem_projeto} projetos sem busca única (veja o relatório)")
    registro = {"data": datetime.now().isoformat(timespec="seconds"), "votacoes_plenario": len(plen),
                "merito": len(merito), "nominais": len(nominais), "secretas": len(secretas),
                "projetos": len(chaves), "duracao_s": int(time.time() - inicio_execucao),
                "problemas": problemas, "avisos": avisos}
    anterior = cache["execucoes"][-1] if cache["execucoes"] else None
    if anterior and not args.desde and registro["merito"] < anterior.get("merito", 0):
        problemas.append(f"o número de votações de mérito caiu de {anterior['merito']} para {registro['merito']}")
    if not args.desde:
        cache["execucoes"] = (cache["execucoes"] + [registro])[-400:]
    salvar_cache(cache)
    log("\n7) Conferência: " + ("tudo certo." if not problemas else "PROBLEMAS: " + "; ".join(problemas)))
    for a in avisos:
        log(f"   Aviso: {a}")
    salvar()
    if problemas and args.diario:
        sys.exit(1)


def salvar_dados(merito, cache):
    saida = []
    for v in merito:
        p = cache["props"].get(v.get("_chave") or "", {})
        saida.append({
            "id": v.get("id"),
            "data": data_da(v),
            "descricao": v.get("descricao"),
            "aprovacao": v.get("aprovacao"),
            "tipo_materia": v.get("_sigla"),
            "numero": v.get("_numero"),
            "ano": v.get("_ano"),
            "tipo_votacao": ("secreta" if v.get("_secreta") else "nominal" if v.get("_n_votos")
                             else "simbolica" if v.get("_n_votos") == 0 else None),
            "n_votos_individuais": v.get("_n_votos"),
            "proposicao_divergente": bool(p.get("divergente")),
            "proposicao_id": p.get("id") if p.get("n") == 1 else None,
            "proposicao_ementa": p.get("ementa") if p.get("n") == 1 else None,
        })
    with open("dados_merito_v5.json", "w", encoding="utf-8") as f:
        json.dump({"gerado_em": datetime.now().isoformat(timespec="seconds"),
                   "votacoes_merito": saida}, f, ensure_ascii=False, indent=1)


def salvar_revisao(merito, cache):
    """Projetos achados por número diferente do texto da votação: uma pessoa precisa conferir."""
    vistos, linhas_csv = set(), []
    for v in sorted(merito, key=data_da, reverse=True):
        c = v.get("_chave")
        p = cache["props"].get(c or "", {})
        if c and c not in vistos and p.get("divergente"):
            vistos.add(c)
            linhas_csv.append([c.replace("|", " "), data_da(v), (v.get("descricao") or "").replace("\n", " "),
                               p.get("achada"), (p.get("ementa") or "")[:300], "", ""])
    if linhas_csv:
        with open("projetos_revisar_v5.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["numero_no_texto", "data", "descricao_da_votacao", "projeto_achado",
                        "ementa_do_projeto_achado", "confere (sim/não)", "observacao"])
            w.writerows(linhas_csv)
    return len(linhas_csv)


def salvar_votos(nominais, cache):
    ids = {str(v["id"]) for v in nominais}
    votos = {i: cache["votos"][i] for i in ids}
    deps = {str(d): cache["deputados"].get(str(d))
            for lista in votos.values() for d, _t in lista}
    with open("votos_nominais_v5.json", "w", encoding="utf-8") as f:
        json.dump({"deputados": deps, "votos": votos}, f, ensure_ascii=False)


def salvar_amostra(plen):
    random.seed(42)
    cotas = {"merito": 60, "urgencia": 25, "emenda": 25, "requerimento": 10, "destaque": 25,
             "parecer": 10, "redacao_final": 5, "tramitacao": 10, "procedimento": 15, "outros": 25}
    escolhidas = []
    for cat, n in cotas.items():
        grupo = [v for v in plen if v["_cat"] == cat]
        escolhidas += random.sample(grupo, min(n, len(grupo)))
    escolhidas.sort(key=data_da, reverse=True)
    with open("amostra_classificacao_v5.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["id", "data", "categoria_automatica", "descricao", "categoria_correta", "observacao"])
        for v in escolhidas:
            w.writerow([v.get("id"), data_da(v), v["_cat"],
                        (v.get("descricao") or "").replace("\n", " "), "", ""])


def salvar():
    with open("relatorio_api_camara_v5.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")
    print("\nRelatório salvo em relatorio_api_camara_v5.txt")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrompido. O que já foi buscado está no cache; rode de novo para continuar.")
        sys.exit(1)
