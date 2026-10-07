#!/usr/bin/env python3
"""Voto de Verdade: constrói o banco de dados (SQLite) a partir do cache da coleta.

O banco é sempre refeito do zero, a partir de duas fontes que ficam no repositório:
  dados/cache_v5.json   o que veio da API da Câmara (a coleta atualiza todo dia)
  dados/resumos.json    assunto, resumo e revisão de cada projeto (preenchido na etapa dos resumos)
Por isso o arquivo .db pode ser apagado e refeito quando quiser.

Uso (na raiz do repositório):
  python3 coleta/construir_banco.py
  python3 coleta/construir_banco.py --cache dados/cache_v5.json --saida dados/voto_de_verdade.db

Formato do resumos.json (todas as chaves são opcionais):
  {"<id do projeto na Câmara>": {"assunto": "Saúde", "assunto_secundario": null,
                                 "confianca_assunto": "alta", "resumo": "...",
                                 "pontos_chave": ["..."], "tags": ["..."]}}

Não há revisão humana neste projeto. Por isso cada votação e cada assunto leva uma "confiança"
(alta, media ou baixa) e, quando não é alta, um aviso em português simples para aparecer na tela:
"A classificação desta votação foi feita automaticamente e pode estar errada: ..."
"""
import argparse
import json
import os
import sqlite3
import sys
from collections import Counter

import coletar_votacoes as col

ASSUNTOS = ["Saúde", "Educação", "Impostos e Economia", "Segurança Pública", "Meio Ambiente",
            "Trabalho e Direitos", "Infraestrutura e Transporte", "Tecnologia e Comunicação", "Outros"]

ESQUEMA = """
CREATE TABLE deputados (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    partido TEXT,
    uf TEXT,
    foto_url TEXT,
    email TEXT,
    em_exercicio INTEGER NOT NULL
);
CREATE TABLE projetos (
    id INTEGER PRIMARY KEY,
    tipo TEXT,
    numero INTEGER,
    ano INTEGER,
    ementa TEXT,
    url_texto_integral TEXT,
    assunto TEXT,
    assunto_secundario TEXT,
    confianca_assunto TEXT,
    aviso_assunto TEXT,
    resumo TEXT,
    pontos_chave TEXT,
    tags TEXT,
    achado_por_numero_diferente INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE votacoes (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    projeto_id INTEGER REFERENCES projetos(id),
    descricao TEXT,
    aprovacao INTEGER,
    tipo_votacao TEXT NOT NULL,
    confianca TEXT NOT NULL,
    aviso TEXT,
    n_sim INTEGER, n_nao INTEGER, n_abstencao INTEGER, n_obstrucao INTEGER, n_outros INTEGER
);
CREATE TABLE votos (
    votacao_id TEXT NOT NULL REFERENCES votacoes(id),
    deputado_id INTEGER NOT NULL REFERENCES deputados(id),
    voto TEXT NOT NULL,
    partido TEXT,
    PRIMARY KEY (votacao_id, deputado_id)
);
CREATE TABLE execucoes (
    data TEXT PRIMARY KEY,
    votacoes_plenario INTEGER, merito INTEGER, nominais INTEGER, secretas INTEGER, projetos INTEGER,
    duracao_s INTEGER, problemas TEXT, avisos TEXT
);
CREATE INDEX votacoes_projeto ON votacoes(projeto_id);
CREATE INDEX votos_deputado ON votos(deputado_id);
CREATE INDEX projetos_assunto ON projetos(assunto);
"""


def foto_padrao(dep_id):
    return f"https://www.camara.leg.br/internet/deputado/bandep/{dep_id}.jpg"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="dados/cache_v5.json")
    ap.add_argument("--resumos", default="dados/resumos.json")
    ap.add_argument("--saida", default="dados/voto_de_verdade.db")
    args = ap.parse_args()

    with open(args.cache, encoding="utf-8") as f:
        cache = json.load(f)
    resumos = {}
    if os.path.exists(args.resumos):
        with open(args.resumos, encoding="utf-8") as f:
            resumos = json.load(f)

    # votações de plenário: janelas fechadas + janelas ainda abertas
    plen = {}
    for lista in list(cache.get("janelas", {}).values()) + [cache.get("recentes", [])]:
        for v in lista:
            plen[v["id"]] = v

    votacoes, projetos_usados, incertas = [], {}, []
    for v in plen.values():
        desc = v.get("descricao")
        if col.classificar(desc) != "merito":
            continue
        sigla, numero, ano = col.extrair_materia(desc)
        chave = f"{sigla}|{numero}|{ano}" if sigla and numero and ano else f"votacao|{v['id']}"
        p = cache["props"].get(chave) or {}
        projeto_id = p.get("id") if p.get("n") == 1 else None
        if projeto_id:
            projetos_usados.setdefault(projeto_id, bool(p.get("divergente")))
        lista = cache["votos"].get(str(v["id"]))
        if lista is None:
            continue  # votos ainda não consultados: entra no próximo dia
        if not lista:
            tipo = "simbolica"
        elif all(t is None for _d, t in lista):
            tipo = "secreta"
        else:
            tipo = "nominal"
        # confiança: vale a menor entre o texto, a ligação com o projeto e a conferência dos totais
        _cat, conf, motivos = col.avaliar_texto(desc)
        motivos = list(motivos)
        if projeto_id is None:
            conf, motivos = "baixa", motivos + ["não foi possível identificar o projeto votado"]
        elif p.get("divergente"):
            conf = min(conf, "baixa", key=col.NIVEL.get)
            motivos.append("o número citado na votação não existe como projeto da Câmara, e usamos o projeto que a Câmara indica")
        elif chave.startswith("votacao|"):
            conf = min(conf, "media", key=col.NIVEL.get)
            motivos.append("usamos o projeto que a Câmara indica, porque o texto da votação não cita o número")
        if tipo == "nominal" and col.conferir_totais(desc, lista) is False:
            conf = min(conf, "baixa", key=col.NIVEL.get)
            motivos.append("os totais de votos do texto não batem com os votos de cada deputado")
        aviso = None
        if conf != "alta":
            aviso = "A classificação desta votação foi feita automaticamente e pode estar errada: " + "; ".join(motivos) + "."
            incertas.append((conf, col.data_da(v), projeto_id, desc, motivos))
        contagem = Counter(t for _d, t in lista if t is not None) if tipo == "nominal" else Counter()
        principais = {"Sim", "Não", "Abstenção", "Obstrução"}
        votacoes.append({
            "id": v["id"], "data": col.data_da(v), "projeto_id": projeto_id, "descricao": desc,
            "aprovacao": v.get("aprovacao"), "tipo": tipo, "confianca": conf, "aviso": aviso, "lista": lista if tipo == "nominal" else [],
            "n": (contagem["Sim"], contagem["Não"], contagem["Abstenção"], contagem["Obstrução"],
                  sum(c for t, c in contagem.items() if t not in principais)) if tipo == "nominal"
                 else (None,) * 5})

    if os.path.exists(args.saida):
        os.remove(args.saida)
    con = sqlite3.connect(args.saida)
    con.executescript(ESQUEMA)

    # deputados: em exercício + todos os que aparecem em algum voto
    atuais = {d["id"]: d for d in cache.get("deputados_atuais", [])}
    vistos = {int(i): d for i, d in cache.get("deputados", {}).items()}
    ids_com_voto = {dep for vt in votacoes for dep, _t in vt["lista"]}
    for dep_id in sorted(set(atuais) | ids_com_voto):
        a = atuais.get(dep_id)
        nome, partido, uf = (vistos.get(dep_id) or [None, None, None])
        if a:
            nome, partido, uf = a["nome"], a["partido"], a["uf"]
        con.execute("INSERT INTO deputados VALUES (?,?,?,?,?,?,?)",
                    (dep_id, nome or f"Deputado {dep_id}", partido, uf,
                     (a or {}).get("foto") or foto_padrao(dep_id), (a or {}).get("email"),
                     1 if a else 0))

    # projetos
    for pid, divergente in sorted(projetos_usados.items()):
        d = cache.get("detalhes", {}).get(str(pid), {})
        r = resumos.get(str(pid), {})
        assunto = r.get("assunto")
        if assunto is not None and assunto not in ASSUNTOS:
            print(f"Aviso: assunto desconhecido no projeto {pid}: {assunto!r}", file=sys.stderr)
        conf_assunto = None
        aviso_assunto = None
        if assunto is not None:
            conf_assunto = r.get("confianca_assunto") if r.get("confianca_assunto") in col.NIVEL else "media"
            if conf_assunto != "alta":
                aviso_assunto = ("O assunto e o resumo deste projeto foram feitos por inteligência artificial "
                                 "e a classificação pode estar errada.")
        con.execute("INSERT INTO projetos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (pid, d.get("siglaTipo"), d.get("numero"), d.get("ano"), d.get("ementa"),
                     d.get("urlInteiroTeor"), assunto, r.get("assunto_secundario"), conf_assunto, aviso_assunto,
                     r.get("resumo"),
                     json.dumps(r.get("pontos_chave"), ensure_ascii=False) if r.get("pontos_chave") else None,
                     json.dumps(r.get("tags"), ensure_ascii=False) if r.get("tags") else None,
                     1 if divergente else 0))

    # votações e votos
    for vt in votacoes:
        con.execute("INSERT INTO votacoes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (vt["id"], vt["data"], vt["projeto_id"], vt["descricao"], vt["aprovacao"], vt["tipo"],
                     vt["confianca"], vt["aviso"], *vt["n"]))
        part = cache.get("partido_no_voto", {}).get(str(vt["id"]), {})
        con.executemany("INSERT OR IGNORE INTO votos VALUES (?,?,?,?)",
                        [(vt["id"], dep, voto, part.get(str(dep))) for dep, voto in vt["lista"] if voto is not None])

    # execuções
    for e in cache.get("execucoes", []):
        con.execute("INSERT OR REPLACE INTO execucoes VALUES (?,?,?,?,?,?,?,?,?)",
                    (e["data"], e.get("votacoes_plenario"), e.get("merito"), e.get("nominais"),
                     e.get("secretas"), e.get("projetos"), e.get("duracao_s"),
                     json.dumps(e.get("problemas"), ensure_ascii=False),
                     json.dumps(e.get("avisos"), ensure_ascii=False)))
    con.commit()

    # conferência
    erros = con.execute("PRAGMA foreign_key_check").fetchall()
    n = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
         for t in ("deputados", "projetos", "votacoes", "votos", "execucoes")}
    sem_projeto = con.execute("SELECT COUNT(*) FROM votacoes WHERE projeto_id IS NULL").fetchone()[0]
    sem_assunto = con.execute("SELECT COUNT(*) FROM projetos WHERE assunto IS NULL").fetchone()[0]
    por_tipo = dict(con.execute("SELECT tipo_votacao, COUNT(*) FROM votacoes GROUP BY 1").fetchall())
    sem_partido = con.execute("SELECT COUNT(*) FROM votos WHERE partido IS NULL").fetchone()[0]
    por_conf = dict(con.execute("SELECT confianca, COUNT(*) FROM votacoes GROUP BY 1").fetchall())
    con.close()
    print(f"Banco criado em {args.saida}: {n}")
    print(f"Votações por tipo: {por_tipo}. Votações sem projeto: {sem_projeto}. Projetos sem assunto: {sem_assunto}.")
    print(f"Votações por confiança da classificação: {por_conf} (as que não são 'alta' aparecem com aviso na tela).")
    print(f"Votos sem o partido do dia do voto: {sem_partido} (esperado: 0 depois da primeira rodada completa).")
    if incertas:
        motivos_cont = Counter(m for _c, _d, _p, _t, ms in incertas for m in ms)
        print("\nMotivos das votações com confiança média ou baixa (uma votação pode ter mais de um):")
        for m, n_m in motivos_cont.most_common():
            print(f"   {n_m:3d}x  {m}")
        print("\nVotações com confiança baixa (data | projeto | texto | motivos):")
        baixas = [i for i in incertas if i[0] == "baixa"]
        for conf_i, data_i, pid_i, desc_i, ms_i in sorted(baixas, key=lambda i: i[1])[:60]:
            texto = " ".join((desc_i or "").split())[:110]
            print(f"   {data_i} | {pid_i or 'sem projeto'} | {texto} | {'; '.join(ms_i)[:160]}")
        if len(baixas) > 60:
            print(f"   ... e mais {len(baixas) - 60}.")
        print()
    if erros:
        print(f"ERRO: {len(erros)} referências quebradas no banco.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
