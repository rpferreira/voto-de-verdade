#!/usr/bin/env python3
"""Números do painel (tela "Em números"): votações simbólicas × nominais ao longo do tempo, por assunto, o resultado,
a participação, o placar e como a inteligência artificial é usada.

Só conta e descreve. Não ordena pessoas, não dá nota e não compara partidos.
Roda sozinho a cada atualização diária (o exportar_dados.py chama montar_painel) e também pode ser
rodado à mão a partir dos arquivos que o site já lê:

    python3 site/painel.py                 # lê site/dados/*.json e escreve site/dados/painel.json

Arquivo gerado (painel.json):
    gerado_em, de, ate           quando foi feito e o período coberto
    totais                       votações, nominais, simbolicas, secretas, aprovadas, rejeitadas
    meses                        uma linha por mês do período (meses sem votação entram com zero):
                                 m = "AAAA-MM", n = nominais, s = simbólicas, x = secretas
    assuntos                     uma linha por assunto, na ordem fixa dos assuntos do site (não por tamanho):
                                 slug, nome, n, s, x. Cada votação conta no assunto principal do projeto
    resultado                    por tipo de votação (nominal, simbolica, secreta): aprovadas e rejeitadas
    participacao                 só nominais: cadeiras (513), votacoes, media/minimo/maximo de deputados que registraram
                                 voto (sim, não, abstenção ou obstrução) e, por mês com nominal, m, n (votações) e v (média)
    placar                       só nominais: votos (S, N, A, O somados) e margem: quantas votações ficaram em cada faixa
                                 de diferença entre sim e não (sem_contra, ampla, maioria, apertada)
    anos, por_ano                os anos com votação e, para cada um, os mesmos campos de cima (de, ate, totais, meses, assuntos,
                                 resultado, participacao, placar), para o filtro por ano da tela
    ia                           transparência: projetos, modelos, datas, confiança do assunto e do resumo, avisos mostrados
Nada aqui ordena ou compara pessoas ou partidos: são só totais da Câmara inteira.
"""
import json
import os
import sys

TIPOS = ("nominal", "simbolica", "secreta")
CADEIRAS = 513
# Faixas da diferença entre sim e não, em relação a sim + não. O limite de 15% é o mesmo da home («Decididas por pouco»).
LIMITE_APERTADA = 0.15
LIMITE_AMPLA = 0.5
CHAVE = {"nominal": "n", "simbolica": "s", "secreta": "x"}


def _meses(de, ate):
    """Todos os meses de «AAAA-MM-DD» a «AAAA-MM-DD», inclusive, sem pular nenhum."""
    ano, mes = int(de[:4]), int(de[5:7])
    fim = (int(ate[:4]), int(ate[5:7]))
    while (ano, mes) <= fim:
        yield f"{ano:04d}-{mes:02d}"
        mes += 1
        if mes == 13:
            ano, mes = ano + 1, 1


def _faixa(sim, nao):
    if sim == 0 or nao == 0:
        return "sem_contra"
    margem = abs(sim - nao) / (sim + nao)
    if margem < LIMITE_APERTADA:
        return "apertada"
    return "ampla" if margem >= LIMITE_AMPLA else "maioria"


def _participacao_e_placar(votacoes, meses):
    """Só as votações nominais (a simbólica não registra o voto de cada deputado). Cada votação traz s = [S, N, A, O, P]."""
    nominais = [v for v in votacoes if v["t"] == "nominal" and v.get("s")]
    por_mes = {}
    votos = {"S": 0, "N": 0, "A": 0, "O": 0}
    margem = {"sem_contra": 0, "ampla": 0, "maioria": 0, "apertada": 0}
    presentes = []
    for v in nominais:
        sim, nao, abst, obs = v["s"][:4]  # o quinto (presidia a sessão) não entra na conta
        votaram = sim + nao + abst + obs
        presentes.append(votaram)
        mes = por_mes.setdefault(v["d"][:7], [])
        mes.append(votaram)
        for c, n in zip("SNAO", (sim, nao, abst, obs)):
            votos[c] += n
        margem[_faixa(sim, nao)] += 1
    participacao = {
        "cadeiras": CADEIRAS, "votacoes": len(nominais),
        "media": round(sum(presentes) / len(presentes)) if presentes else 0,
        "minimo": min(presentes) if presentes else 0, "maximo": max(presentes) if presentes else 0,
        "meses": [{"m": m["m"], "n": len(por_mes[m["m"]]), "v": round(sum(por_mes[m["m"]]) / len(por_mes[m["m"]]))} if m["m"] in por_mes
                  else {"m": m["m"], "n": 0, "v": 0} for m in meses],
    }
    return participacao, {"nominais": len(nominais), "votos": votos, "margem": margem}


def _contar(valores, chaves):
    return {k: sum(1 for x in valores if x == k) for k in chaves}


def _ia(votacoes, projetos, resumos):
    """Como a IA é usada: só contagens. Os modelos e a data vêm do resumos.json (feito por coleta/resumir_projetos.py)."""
    ia = {
        "projetos": len(projetos),
        "assunto": _contar([p.get("ca") for p in projetos], ("alta", "media", "baixa")),
        "resumo": _contar([p.get("cr") for p in projetos], ("alta", "media", "baixa")),
        "aviso_assunto": sum(1 for p in projetos if p.get("aa")),
        "aviso_resumo": sum(1 for p in projetos if p.get("ar")),
        "so_ementa": sum(1 for p in projetos if not p.get("cr")),
        "texto_pode_diferir": sum(1 for p in projetos if p.get("subst")),
        "votacoes": len(votacoes),
        "votacao_aviso": sum(1 for v in votacoes if v.get("av")),
        "modelo": None, "conferencia": None, "de": None, "ate": None, "conferencia_apontou": None,
    }
    if resumos:
        itens = list(resumos.values())
        mais_comum = lambda chave: max(set(x.get(chave) for x in itens), key=lambda m: sum(1 for x in itens if x.get(chave) == m))
        ia["modelo"], ia["conferencia"] = mais_comum("modelo"), mais_comum("conferencia")
        datas = [x["gerado_em"] for x in itens if x.get("gerado_em")]
        ia["de"], ia["ate"] = (min(datas), max(datas)) if datas else (None, None)
        ia["conferencia_apontou"] = sum(1 for x in itens if x.get("conferencia_obs"))
    return ia


def _numeros(votacoes, assunto_do_projeto, assuntos, meses_de=None, meses_ate=None):
    """Os números de um conjunto de votações (o período inteiro ou um ano): totais, meses, assuntos, resultado, participação e placar.
    meses_de e meses_ate (opcionais) alargam a lista de meses: um ano mostra janeiro a dezembro, sem pular nenhum."""
    de, ate = min(v["d"] for v in votacoes), max(v["d"] for v in votacoes)
    meses = {m: {"m": m, "n": 0, "s": 0, "x": 0} for m in _meses(meses_de or de, meses_ate or ate)}
    por_assunto = {a["slug"]: {"slug": a["slug"], "nome": a["nome"], "n": 0, "s": 0, "x": 0} for a in assuntos}
    resultado = {t: {"aprovadas": 0, "rejeitadas": 0} for t in TIPOS}
    for v in votacoes:
        k = CHAVE[v["t"]]
        meses[v["d"][:7]][k] += 1
        slug = assunto_do_projeto.get(v["p"])
        if slug in por_assunto:
            por_assunto[slug][k] += 1
        resultado[v["t"]]["aprovadas" if v["ap"] else "rejeitadas"] += 1
    totais = {
        "votacoes": len(votacoes),
        "nominais": sum(1 for v in votacoes if v["t"] == "nominal"),
        "simbolicas": sum(1 for v in votacoes if v["t"] == "simbolica"),
        "secretas": sum(1 for v in votacoes if v["t"] == "secreta"),
        "aprovadas": sum(r["aprovadas"] for r in resultado.values()),
        "rejeitadas": sum(r["rejeitadas"] for r in resultado.values()),
    }
    lista_meses = list(meses.values())
    participacao, placar = _participacao_e_placar(votacoes, lista_meses)
    return {
        "de": de, "ate": ate,
        "totais": totais,
        "meses": lista_meses,
        "assuntos": [a for a in por_assunto.values() if a["n"] + a["s"] + a["x"] > 0],
        "resultado": resultado,
        "participacao": participacao,
        "placar": placar,
    }


def montar_painel(votacoes, projetos, assuntos, gerado_em, resumos=None):
    """votacoes: lista de {id, p, d, t, ap, s}; projetos: lista de {id, a, ca, cr...}; vazio se não houver votação.
    assuntos: lista de {slug, nome} na ordem do site; resumos: o dados/resumos.json (opcional, só para os modelos e a data da IA).
    O período inteiro fica na raiz; cada ano, com os mesmos campos, em por_ano (para o filtro por ano da tela)."""
    assunto_do_projeto = {p["id"]: p["a"] for p in projetos}
    votacoes = [v for v in votacoes if v["t"] in TIPOS]
    if not votacoes:
        return {"gerado_em": gerado_em, "de": None, "ate": None, "totais": {}, "meses": [], "assuntos": [], "resultado": {},
                "participacao": {}, "placar": {}, "anos": [], "por_ano": {}, "ia": {}}
    painel = {"gerado_em": gerado_em}
    painel.update(_numeros(votacoes, assunto_do_projeto, assuntos))
    anos = sorted({v["d"][:4] for v in votacoes})
    painel["anos"] = anos
    ultimo = max(v["d"] for v in votacoes)
    # Cada ano mostra janeiro a dezembro; no último ano, vai só até o mês da última votação (os meses seguintes ainda não aconteceram).
    painel["por_ano"] = {ano: _numeros([v for v in votacoes if v["d"][:4] == ano], assunto_do_projeto, assuntos,
                                       f"{ano}-01-01", ultimo if ano == ultimo[:4] else f"{ano}-12-31") for ano in anos}
    painel["ia"] = _ia(votacoes, projetos, resumos)
    return painel


def main():
    pasta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados")
    if len(sys.argv) > 1:
        pasta = sys.argv[1]

    def ler(nome):
        with open(os.path.join(pasta, nome), encoding="utf-8") as f:
            return json.load(f)

    meta = ler("meta.json")
    caminho_resumos = os.path.join(os.path.dirname(os.path.abspath(pasta)), "..", "dados", "resumos.json")
    resumos = json.load(open(caminho_resumos, encoding="utf-8")) if os.path.exists(caminho_resumos) else None
    painel = montar_painel(ler("votacoes.json"), ler("projetos.json"), ler("assuntos.json"), meta["gerado_em"], resumos)
    caminho = os.path.join(pasta, "painel.json")
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(painel, f, ensure_ascii=False, separators=(",", ":"))
    print(f"   {caminho}: {os.path.getsize(caminho) / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
