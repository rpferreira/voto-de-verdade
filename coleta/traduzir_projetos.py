#!/usr/bin/env python3
"""Voto de Verdade: tradução para o inglês do que o site mostra de cada projeto e de cada votação.

O que é traduzido: resumo, pontos principais, tags e avisos de cada projeto; descrição e aviso de cada votação.
A ementa oficial não é traduzida (o site a mostra em português, com um aviso). Nomes de assuntos e textos de tela
ficam em site/idiomas/en.json (feitos à mão).

Lê o português já exportado em site/dados/ e escreve dados/traducoes_en.json. Só traduz o que é novo ou mudou.

Uso (na raiz do repositório):
  ANTHROPIC_API_KEY=... python3 coleta/traduzir_projetos.py                  rotina diária: traduz o que falta (via API)
  python3 coleta/traduzir_projetos.py --limite 5                              teste com 5 itens
  python3 coleta/traduzir_projetos.py --lotes pasta [--tamanho 40]            só prepara lotes de entrada (carga inicial, sem API)
  python3 coleta/traduzir_projetos.py --importar saida1.json saida2.json      confere e guarda lotes já traduzidos
  python3 coleta/traduzir_projetos.py --conferir                              diz quantos itens faltam e valida o que existe

Sem a chave, a rotina avisa e termina sem erro (o site mostra o português nos itens ainda sem tradução).
Só usa a biblioteca padrão do Python 3.
"""
import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import traducoes as T  # noqa: E402
from resumir_projetos import Contas, ErroFatal, ErroProjeto, PRECOS, chamar, registrar_custo  # noqa: E402

import resumir_projetos as _r  # noqa: E402

MODELO = os.environ.get("MODELO_TRADUCAO", "claude-sonnet-5-5")
_r.PRECOS.setdefault(MODELO, (2.0, 10.0))

CAMPOS_PROJETO = ("resumo", "pontos", "tags", "aviso_assunto", "aviso_resumo")
CAMPOS_VOTACAO = ("descricao", "aviso")

FERRAMENTA_PROJETOS = {
    "name": "registrar_traducoes",
    "description": "Registra a tradução para o inglês de cada projeto.",
    "input_schema": {
        "type": "object",
        "properties": {"itens": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "resumo": {"type": ["string", "null"]},
                "pontos": {"type": "array", "items": {"type": "string"}},
                "tags": {"type": "array", "items": {"type": "string"}},
                "aviso_assunto": {"type": ["string", "null"]},
                "aviso_resumo": {"type": ["string", "null"]},
            },
            "required": ["id", "resumo", "pontos", "tags", "aviso_assunto", "aviso_resumo"],
            "additionalProperties": False}}},
        "required": ["itens"],
        "additionalProperties": False,
    },
}
FERRAMENTA_VOTACOES = {
    "name": "registrar_traducoes",
    "description": "Registra a tradução para o inglês de cada votação.",
    "input_schema": {
        "type": "object",
        "properties": {"itens": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "descricao": {"type": ["string", "null"]}, "aviso": {"type": ["string", "null"]}},
            "required": ["id", "descricao", "aviso"],
            "additionalProperties": False}}},
        "required": ["itens"],
        "additionalProperties": False,
    },
}
TIPOS = {
    "projetos": {"campos": CAMPOS_PROJETO, "ferramenta": FERRAMENTA_PROJETOS, "validar": T.validar_projeto},
    "votacoes": {"campos": CAMPOS_VOTACAO, "ferramenta": FERRAMENTA_VOTACOES, "validar": T.validar_votacao},
}


def ler(pasta, nome):
    with open(os.path.join(pasta, nome), encoding="utf-8") as f:
        return json.load(f)


def origem_dos_dados(pasta):
    """Texto em português de cada item: {'projetos': {id: {...}}, 'votacoes': {id: {...}}} e a ementa de cada projeto (só contexto)."""
    projetos = ler(pasta, "projetos.json")
    itens, ementas = {}, {}
    for p in projetos:
        pid = str(p["id"])
        try:
            det = ler(os.path.join(pasta, "projetos"), f"{pid}.json")
        except OSError:
            det = {}
        item = {"resumo": p.get("resumo") or None, "pontos": det.get("pontos") or [], "tags": p.get("tags") or [],
                "aviso_assunto": p.get("aa") or None, "aviso_resumo": p.get("ar") or None}
        ementas[pid] = det.get("ementa") or ""
        if item["resumo"] or item["pontos"] or item["tags"] or item["aviso_assunto"] or item["aviso_resumo"]:
            itens[pid] = item
    votacoes = {}
    for v in ler(pasta, "votacoes.json"):
        item = {"descricao": v.get("desc") or None, "aviso": v.get("av") or None}
        if item["descricao"] or item["aviso"]:
            votacoes[str(v["id"])] = item
    return {"projetos": itens, "votacoes": votacoes}, ementas


def pendentes(origem, dado):
    """{tipo: [ids]} de itens sem tradução ou com o português mudado."""
    saida = {}
    for tipo, itens in origem.items():
        saida[tipo] = [i for i, item in itens.items() if (dado[tipo].get(i) or {}).get("h") != T.impressao(item)]
        saida[tipo].sort(key=lambda x: (len(x), x), reverse=True)  # os mais novos (ids maiores) primeiro
    return saida


def guardar(dado, tipo, id_, origem_item, trad):
    campos = TIPOS[tipo]["campos"]
    dado[tipo][id_] = {"h": T.impressao(origem_item), **{c: trad.get(c) for c in campos if trad.get(c) not in (None, "", [])}}


# ---------------------------------------------------------------- carga inicial: lotes em arquivos

def preparar_lotes(origem, ementas, dado, pasta, tamanho):
    os.makedirs(pasta, exist_ok=True)
    pend = pendentes(origem, dado)
    with open(os.path.join(pasta, "REGRAS.md"), "w", encoding="utf-8") as f:
        f.write(T.SISTEMA)
    n = 0
    for tipo, ids in pend.items():
        for i in range(0, len(ids), tamanho):
            parte = ids[i:i + tamanho]
            n += 1
            itens = {}
            for id_ in parte:
                itens[id_] = dict(origem[tipo][id_])
                if tipo == "projetos":
                    itens[id_]["_contexto_ementa_nao_traduzir"] = (ementas.get(id_) or "")[:500]
            nome = f"entrada_{tipo[:4]}_{n:03d}.json"
            with open(os.path.join(pasta, nome), "w", encoding="utf-8") as f:
                json.dump({"tipo": tipo, "itens": itens}, f, ensure_ascii=False, indent=1)
    print(f"{n} lotes em {pasta}/ ({sum(len(v) for v in pend.values())} itens): " + ", ".join(f"{t}: {len(v)}" for t, v in pend.items()))


def importar(origem, dado, arquivos, rejeitados_em):
    ok, ruins = 0, {}
    for arq in arquivos:
        with open(arq, encoding="utf-8") as f:
            lote = json.load(f)
        tipo = lote.get("tipo")
        if tipo not in TIPOS:
            print(f"{arq}: tipo desconhecido {tipo!r}", file=sys.stderr)
            continue
        for id_, trad in (lote.get("itens") or {}).items():
            o = origem[tipo].get(str(id_))
            if o is None:
                ruins.setdefault(arq, []).append((id_, ["id que não existe na origem"]))
                continue
            problemas = TIPOS[tipo]["validar"](o, trad)
            if problemas:
                ruins.setdefault(arq, []).append((id_, problemas))
                continue
            guardar(dado, tipo, str(id_), o, trad)
            ok += 1
    nruins = sum(len(v) for v in ruins.values())
    print(f"Guardados: {ok}. Rejeitados: {nruins}.")
    if ruins:
        with open(rejeitados_em, "w", encoding="utf-8") as f:
            json.dump({a: [{"id": i, "problemas": p} for i, p in lista] for a, lista in ruins.items()}, f, ensure_ascii=False, indent=1)
        for a, lista in ruins.items():
            for i, p in lista[:8]:
                print(f"   {os.path.basename(a)} #{i}: {'; '.join(p)}")
        print(f"Lista completa em {rejeitados_em}")
    return ok, nruins


def conferir(origem, dado):
    pend = pendentes(origem, dado)
    for tipo in origem:
        print(f"{tipo}: {len(origem[tipo])} itens, {len(pend[tipo])} sem tradução em dia.")
    problemas = 0
    for tipo in origem:
        for id_, trad in dado[tipo].items():
            o = origem[tipo].get(id_)
            if o is None or trad.get("h") != T.impressao(o):
                continue
            p = TIPOS[tipo]["validar"](o, trad)
            if p:
                problemas += 1
                print(f"   {tipo} {id_}: {'; '.join(p)}")
    print(f"Traduções com problema: {problemas}.")
    return sum(len(v) for v in pend.values()), problemas


# ---------------------------------------------------------------- rotina diária: via API

def traduzir_lote(tipo, ids, origem, ementas, chave, contas):
    itens = []
    for id_ in ids:
        item = {"id": id_, **origem[tipo][id_]}
        if tipo == "projetos":
            item["contexto_ementa_oficial_nao_traduzir"] = (ementas.get(id_) or "")[:500]
        itens.append(item)
    usuario = ("Translate these items into English following the rules. Return one entry per input item, with the same id.\n\n"
               + json.dumps(itens, ensure_ascii=False, indent=1))
    resp, ent, sai = chamar(MODELO, T.SISTEMA, usuario, TIPOS[tipo]["ferramenta"], chave, max_tokens=8000)
    contas.somar(MODELO, ent, sai)
    saida = {}
    for r in resp.get("itens") or []:
        if isinstance(r, dict) and str(r.get("id")) in ids:
            saida[str(r["id"])] = r
    return saida


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dados", default="site/dados", help="pasta do português exportado")
    ap.add_argument("--traducoes", default=T.ARQUIVO)
    ap.add_argument("--custo", default="dados/custo.json")
    ap.add_argument("--limite", type=int, default=400, help="máximo de itens nesta execução")
    ap.add_argument("--lote", type=int, default=8, help="itens por chamada da API")
    ap.add_argument("--paralelo", type=int, default=4)
    ap.add_argument("--tempo-max", type=float, default=40, help="minutos; depois disso não começa lotes novos")
    ap.add_argument("--lotes", metavar="PASTA", help="só prepara arquivos de entrada para tradução fora da API")
    ap.add_argument("--tamanho", type=int, default=40)
    ap.add_argument("--importar", nargs="+", metavar="ARQUIVO")
    ap.add_argument("--rejeitados", default="rejeitados.json")
    ap.add_argument("--conferir", action="store_true")
    args = ap.parse_args()

    origem, ementas = origem_dos_dados(args.dados)
    dado = T.carregar(args.traducoes)
    if args.lotes:
        preparar_lotes(origem, ementas, dado, args.lotes, args.tamanho)
        return 0
    if args.importar:
        ok, _ = importar(origem, dado, args.importar, args.rejeitados)
        if ok:
            T.salvar(dado, args.traducoes)
        return 0
    if args.conferir:
        faltam, problemas = conferir(origem, dado)
        return 1 if problemas else 0

    chave = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    pend = pendentes(origem, dado)
    total = sum(len(v) for v in pend.values())
    print(f"Itens a traduzir: {total} ({', '.join(f'{t}: {len(v)}' for t, v in pend.items())}).")
    if not total:
        return 0
    if not chave:
        print("Aviso: a chave ANTHROPIC_API_KEY não está configurada. A tradução para o inglês foi pulada.")
        return 0

    contas, trava = Contas(), threading.Lock()
    estado = {"feitos": 0, "erros": [], "fatal": None, "rejeitados": 0}
    inicio = time.time()

    def tarefa(args_):
        tipo, ids = args_
        if estado["fatal"]:
            return
        try:
            saida = traduzir_lote(tipo, ids, origem, ementas, chave, contas)
        except ErroFatal as ex:
            estado["fatal"] = str(ex)
            return
        except Exception as ex:
            with trava:
                estado["erros"].append((tipo, ids[0], f"{type(ex).__name__}: {ex}"))
            return
        with trava:
            for id_ in ids:
                trad = saida.get(id_)
                problemas = TIPOS[tipo]["validar"](origem[tipo][id_], trad) if trad else ["sem resposta"]
                if problemas:
                    estado["rejeitados"] += 1
                    estado["erros"].append((tipo, id_, "; ".join(problemas)))
                    continue
                guardar(dado, tipo, id_, origem[tipo][id_], trad)
                estado["feitos"] += 1
            T.salvar(dado, args.traducoes)

    lotes, restante = [], args.limite
    for tipo in ("projetos", "votacoes"):
        ids = pend[tipo][:restante]
        restante -= len(ids)
        lotes += [(tipo, ids[i:i + args.lote]) for i in range(0, len(ids), args.lote)]
    with ThreadPoolExecutor(max_workers=max(1, args.paralelo)) as pool:
        for i in range(0, len(lotes), args.paralelo * 2):
            if estado["fatal"] or (time.time() - inicio) / 60 > args.tempo_max:
                break
            list(pool.map(tarefa, lotes[i:i + args.paralelo * 2]))
    T.salvar(dado, args.traducoes)

    gasto = contas.custo()
    print(f"Traduzidos: {estado['feitos']}. Com problema (ficam para a próxima vez): {len(estado['erros'])}. Gasto estimado: US$ {gasto:.2f}.")
    for tipo, id_, msg in estado["erros"][:10]:
        print(f"   {tipo} {id_}: {msg}")
    registrar_custo(args.custo, gasto, contas, {"feitos": estado["feitos"], "erros": estado["erros"]}, False, tarefa="traducao")
    if estado["fatal"]:
        if "saldo de créditos" in estado["fatal"]:
            print(f"AVISO: {estado['fatal']}\n       O que falta fica em português no site em inglês até haver saldo.")
            return 0
        print(f"ERRO: {estado['fatal']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
