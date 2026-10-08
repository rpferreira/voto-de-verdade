#!/usr/bin/env python3
"""Monitoramento do Voto de Verdade: confere custo, dados e site, e avisa quando algo sai do normal.

Roda no GitHub no fim da atualização diária (e, só para o site, uma vez por dia em outro horário).
Usa só a biblioteca padrão do Python.

O que confere
  1. A atualização diária e a publicação terminaram bem.
  2. Dados: foram gerados hoje; a última votação não está velha demais; as contagens (votações, projetos,
     deputados, votos) não diminuíram; todo voto aponta para um deputado e uma votação que existem; todo projeto
     de votação existe; poucos projetos sem resumo; a parte com aviso de incerteza não disparou.
  3. Custo da IA: gasto da última rodada, gasto do mês e se o saldo de créditos acabou.
  4. Site no ar: página inicial, dados, mapa do site, uma página de projeto e uma de deputado, e se os dados
     publicados são os de hoje.

Como avisa
  Qualquer "erro" deixa a execução vermelha (o GitHub manda e-mail) e abre um alerta na aba Issues, que volta a
  fechar sozinho quando tudo se normaliza. "Avisos" aparecem no relatório e no resumo da execução, sem alarme.

Limites (podem ser mudados em Settings, Secrets and variables, Actions, Variables):
  LIMITE_CUSTO_RODADA (US$ 5), LIMITE_CUSTO_MES (US$ 30), LIMITE_PENDENTES (50 projetos sem resumo),
  DIAS_SEM_VOTACAO (45), LIMITE_INCERTOS (25% dos projetos com aviso de incerteza).

Uso
    python coleta/monitorar.py                        # só os arquivos do repositório
    python coleta/monitorar.py --site https://usuario.github.io/repositorio
    python coleta/monitorar.py --site URL --apenas-site
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

CODIGOS_VOTO = {"S", "N", "A", "O", "P"}


def numero(nome, padrao):
    try:
        return float(os.environ.get(nome, "") or padrao)
    except ValueError:
        return float(padrao)


class Relatorio:
    def __init__(self):
        self.erros, self.avisos, self.infos = [], [], []

    def erro(self, msg):
        self.erros.append(msg)

    def aviso(self, msg):
        self.avisos.append(msg)

    def info(self, msg):
        self.infos.append(msg)

    def texto(self):
        linhas = []
        for titulo, itens in (("Erros", self.erros), ("Avisos", self.avisos), ("Conferido", self.infos)):
            if itens:
                linhas += [f"### {titulo}", ""] + [f"- {i}" for i in itens] + [""]
        return "\n".join(linhas)


def carregar(caminho):
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# ------------------------------------------------------------------ 1. execução do dia

def checar_execucao(rel, args):
    for nome, resultado in (("A atualização diária", args.atualizar), ("A publicação do site", args.publicar)):
        if resultado and resultado not in ("success", "skipped"):
            rel.erro(f"{nome} terminou com resultado '{resultado}'." + (f" Veja o log: {args.execucao_url}" if args.execucao_url else ""))
    if args.atualizar == "success" and args.publicar == "success":
        rel.info("Atualização diária e publicação terminaram bem.")


# ------------------------------------------------------------------ 2. dados

def checar_dados(rel, raiz, hoje, anterior, args):
    dados = os.path.join(raiz, "site", "dados")
    meta = carregar(os.path.join(dados, "meta.json"))
    projetos = carregar(os.path.join(dados, "projetos.json"))
    votacoes = carregar(os.path.join(dados, "votacoes.json"))
    deputados = carregar(os.path.join(dados, "deputados.json"))
    if not all([meta, projetos, votacoes, deputados]):
        rel.erro("Faltam arquivos de dados do site ou algum não é um JSON válido (site/dados).")
        return {}
    atualizou = args.atualizar in (None, "success")

    if atualizou:
        if meta.get("gerado_em") != hoje.isoformat():
            rel.erro(f"Os dados do site não foram gerados hoje (último: {meta.get('gerado_em')}).")
        else:
            rel.info(f"Dados gerados hoje ({hoje.isoformat()}).")
    ate = meta.get("ate")
    if ate:
        dias = (hoje - date.fromisoformat(ate)).days
        if dias > numero("DIAS_SEM_VOTACAO", 45):
            rel.aviso(f"A última votação é de {ate}, há {dias} dias. Em recesso e em período de eleição é normal; fora disso, confira a coleta.")
        else:
            rel.info(f"Última votação: {ate} (há {dias} dias).")

    # contagens
    arquivos_votos = []
    pasta_vot = os.path.join(dados, "votacoes")
    if os.path.isdir(pasta_vot):
        arquivos_votos = [f for f in os.listdir(pasta_vot) if f.endswith(".json")]
    total_votos = 0
    codigos_ruins = 0
    dep_ids = {d["id"] for d in deputados}
    dep_desconhecido = 0
    for f in arquivos_votos:
        arq = carregar(os.path.join(pasta_vot, f)) or {}
        for linha in arq.get("v", []):
            total_votos += 1
            if linha[1] not in CODIGOS_VOTO:
                codigos_ruins += 1
            if linha[0] not in dep_ids:
                dep_desconhecido += 1
    contagens = {
        "votacoes": len(votacoes), "projetos": len(projetos), "deputados": len(deputados),
        "nominais": sum(1 for v in votacoes if v.get("t") == "nominal"), "votos": total_votos,
    }
    antes = (anterior or {}).get("contagens") or {}
    for chave, valor in contagens.items():
        if chave in antes and valor < antes[chave]:
            rel.erro(f"O número de {chave} diminuiu de {antes[chave]} para {valor}. Os dados só deveriam crescer.")
    rel.info("Contagens: " + ", ".join(f"{v} {k}" for k, v in contagens.items()) + ".")

    # integridade
    ids_proj = {p["id"] for p in projetos}
    sem_projeto = [v["id"] for v in votacoes if v.get("p") not in ids_proj]
    sem_arquivo = [v["id"] for v in votacoes if v.get("t") == "nominal" and f"{v['id']}.json" not in set(arquivos_votos)]
    problemas = []
    if sem_projeto:
        problemas.append(f"{len(sem_projeto)} votações apontam para um projeto que não existe (ex.: {', '.join(map(str, sem_projeto[:3]))})")
    if sem_arquivo:
        problemas.append(f"{len(sem_arquivo)} votações nominais sem o arquivo de votos (ex.: {', '.join(sem_arquivo[:3])})")
    pasta_proj = os.path.join(dados, "projetos")
    arquivos_proj = set(os.listdir(pasta_proj)) if os.path.isdir(pasta_proj) else set()
    sem_detalhe = [p["id"] for p in projetos if f"{p['id']}.json" not in arquivos_proj]
    if sem_detalhe:
        problemas.append(f"{len(sem_detalhe)} projetos sem o arquivo de ementa e pontos principais (ex.: {', '.join(map(str, sem_detalhe[:3]))})")
    if codigos_ruins:
        problemas.append(f"{codigos_ruins} votos com código desconhecido")
    if dep_desconhecido:
        problemas.append(f"{dep_desconhecido} votos de deputados que não estão na lista de deputados")
    if problemas:
        for p in problemas:
            rel.erro("Dados inconsistentes: " + p + ".")
    else:
        rel.info("Integridade: todo voto, votação e projeto se encontra.")

    # IA
    pendentes = sum(1 for p in projetos if not p.get("resumo"))
    incertos = sum(1 for p in projetos if p.get("ca") not in (None, "alta") or p.get("cr") not in (None, "alta"))
    pct = round(100 * incertos / max(len(projetos), 1), 1)
    if pendentes > numero("LIMITE_PENDENTES", 50):
        rel.aviso(f"{pendentes} projetos estão sem resumo de IA (o limite de aviso é {int(numero('LIMITE_PENDENTES', 50))}). O site mostra só a ementa.")
    else:
        rel.info(f"Projetos sem resumo de IA: {pendentes}.")
    antes_pct = (anterior or {}).get("pct_incertos")
    if antes_pct is not None and pct - antes_pct > 5:
        rel.erro(f"A parte dos projetos com aviso de incerteza saltou de {antes_pct}% para {pct}%. Pode haver problema na classificação.")
    elif pct > numero("LIMITE_INCERTOS", 25):
        rel.aviso(f"{pct}% dos projetos têm aviso de incerteza (o limite de aviso é {int(numero('LIMITE_INCERTOS', 25))}%).")
    else:
        rel.info(f"Projetos com aviso de incerteza: {pct}%.")

    # última coleta
    cache = carregar(os.path.join(raiz, "dados", "cache_v5.json")) or {}
    execucoes = cache.get("execucoes") or []
    if execucoes:
        ult = execucoes[-1]
        if ult.get("problemas"):
            rel.erro("A última coleta registrou problemas: " + "; ".join(ult["problemas"]) + ".")
        for a in ult.get("avisos") or []:
            rel.aviso(f"Coleta: {a}.")
    return {"contagens": contagens, "pendentes": pendentes, "pct_incertos": pct, "gerado_em": meta.get("gerado_em")}


# ------------------------------------------------------------------ 3. custo

def checar_custo(rel, raiz, hoje):
    historico = carregar(os.path.join(raiz, "dados", "custo.json"))
    if not historico:
        rel.info("Custo da IA: ainda sem execuções registradas.")
        return 0.0
    mes = hoje.strftime("%Y-%m")
    gasto_mes = round(sum(h.get("usd", 0) for h in historico if str(h.get("data", "")).startswith(mes)), 2)
    ultimo = historico[-1]
    limite_rodada, limite_mes = numero("LIMITE_CUSTO_RODADA", 5), numero("LIMITE_CUSTO_MES", 30)
    if ultimo.get("sem_saldo"):
        rel.erro("Os créditos da API de IA acabaram. Os projetos novos ficam sem resumo até recarregar o saldo.")
    if ultimo.get("usd", 0) > limite_rodada:
        rel.erro(f"A última rodada gastou US$ {ultimo['usd']:.2f}, acima do limite de US$ {limite_rodada:g}.")
    if gasto_mes > limite_mes:
        rel.erro(f"O gasto do mês com IA chegou a US$ {gasto_mes:.2f}, acima do limite de US$ {limite_mes:g}.")
    elif gasto_mes > 0.7 * limite_mes:
        rel.aviso(f"O gasto do mês com IA está em US$ {gasto_mes:.2f}, mais de 70% do limite de US$ {limite_mes:g}.")
    if ultimo.get("erros"):
        rel.aviso(f"{ultimo['erros']} projetos deram erro na última rodada de resumos.")
    rel.info(f"Custo da IA: US$ {ultimo.get('usd', 0):.2f} na última rodada, US$ {gasto_mes:.2f} no mês (limites: US$ {limite_rodada:g} e US$ {limite_mes:g}).")
    return gasto_mes


# ------------------------------------------------------------------ 4. site no ar

def buscar(url, tentativas=3):
    ultimo = None
    for i in range(tentativas):
        try:
            req = Request(url, headers={"User-Agent": "VotoDeVerdade-monitor/1.0"})
            with urlopen(req, timeout=30) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except HTTPError as e:
            return e.code, ""
        except (URLError, TimeoutError, OSError) as e:
            ultimo = str(e)
            time.sleep(3 * (i + 1))
    return 0, ultimo or ""


def checar_site(rel, base, hoje, esperado, args):
    base = base.rstrip("/")
    status, corpo = buscar(base + "/")
    if status != 200 or "Voto de Verdade" not in corpo:
        rel.erro(f"A página inicial do site não abriu direito (código {status}): {base}/")
        return
    rel.info(f"Página inicial no ar ({base}/).")

    # dados publicados: precisam ser os de hoje (ou os mesmos gerados nesta execução). O GitHub Pages pode levar
    # alguns minutos para mostrar o que acabou de ser publicado, então espera um pouco.
    meta_no_ar = None
    limite = time.time() + args.espera
    while True:
        st, txt = buscar(base + "/dados/meta.json")
        try:
            meta_no_ar = json.loads(txt) if st == 200 else None
        except ValueError:
            meta_no_ar = None
        ok = bool(meta_no_ar) and (
            meta_no_ar.get("gerado_em") == esperado if esperado
            else (hoje - date.fromisoformat(meta_no_ar["gerado_em"])).days <= 2
        )
        if ok or time.time() > limite:
            break
        time.sleep(20)
    if not meta_no_ar:
        rel.erro("Os dados do site (dados/meta.json) não abrem.")
    elif not ok:
        rel.erro(f"O site no ar está desatualizado: dados de {meta_no_ar.get('gerado_em')}" +
                 (f", esperado {esperado}." if esperado else "."))
    else:
        rel.info(f"Dados no ar são de {meta_no_ar['gerado_em']}.")

    st, txt = buscar(base + "/sitemap.xml")
    n = txt.count("<loc>") if st == 200 else 0
    if n < 100:
        rel.erro(f"O mapa do site (sitemap.xml) está vazio ou não abre ({n} endereços, código {st}).")
    else:
        rel.info(f"Mapa do site com {n} endereços.")

    # a pasta .well-known (catálogo da API e habilidades para agentes) começa com ponto e some do site se a
    # publicação deixar de incluir arquivos ocultos
    st, txt = buscar(base + "/.well-known/agent-skills/index.json")
    try:
        ok_wk = st == 200 and bool(json.loads(txt).get("skills"))
    except ValueError:
        ok_wk = False
    if not ok_wk:
        rel.erro(f"O catálogo para agentes (.well-known/agent-skills/index.json) não abre (código {st}).")
    else:
        rel.info("Catálogo para agentes de IA (.well-known) no ar.")

    # uma página de projeto e uma de deputado, achadas nos próprios dados no ar
    st, txt = buscar(base + "/dados/votacoes.json")
    try:
        vots = json.loads(txt) if st == 200 else []
    except ValueError:
        vots = []
    nominais = [v for v in vots if v.get("t") == "nominal"]
    if nominais:
        pid = max(nominais, key=lambda v: v["d"])["p"]
        st, txt = buscar(f"{base}/projeto/{pid}/")
        if st != 200 or "<h1" not in txt:
            rel.erro(f"A página de projeto /projeto/{pid}/ não abriu (código {st}).")
        else:
            rel.info(f"Página de projeto no ar (/projeto/{pid}/).")
        st, txt = buscar(f"{base}/dados/votacoes/{max(nominais, key=lambda v: v['d'])['id']}.json")
        try:
            votos = json.loads(txt).get("v") if st == 200 else None
        except ValueError:
            votos = None
        if not votos:
            rel.erro("O arquivo de votos da votação nominal mais recente não abre ou está vazio.")
        else:
            dep = votos[0][0]
            st, txt = buscar(f"{base}/deputado/{dep}/")
            if st != 200 or "<h1" not in txt:
                rel.erro(f"A página de deputado /deputado/{dep}/ não abriu (código {st}).")
            else:
                rel.info(f"Página de deputado no ar (/deputado/{dep}/).")
    else:
        rel.erro("Os dados no ar não têm votações nominais.")


# ------------------------------------------------------------------ alerta no GitHub (Issues)

def gh(*argumentos, entrada=None):
    r = subprocess.run(["gh", "api", *argumentos], capture_output=True, text=True, input=entrada)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip())
    return json.loads(r.stdout) if r.stdout.strip() else None


def atualizar_alerta(rel, hoje, titulo, args):
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo or not os.environ.get("GH_TOKEN"):
        print("(Sem GITHUB_REPOSITORY/GH_TOKEN: o alerta na aba Issues foi pulado.)")
        return
    try:
        abertos = gh(f"repos/{repo}/issues?state=open&labels=monitoramento&per_page=50") or []
        meu = next((i for i in abertos if i["title"] == titulo and "pull_request" not in i), None)
        assinatura = hashlib.sha1("\n".join(sorted(rel.erros)).encode("utf-8")).hexdigest()[:12]
        corpo = (f"O monitoramento achou problemas em {hoje.strftime('%d/%m/%Y')}.\n\n" + rel.texto() +
                 (f"\nLog da execução: {args.execucao_url}\n" if args.execucao_url else "") +
                 "\nEste alerta fecha sozinho quando tudo voltar ao normal.\n"
                 f"<!-- assinatura:{assinatura} -->")
        if rel.erros:
            try:
                gh(f"repos/{repo}/labels", "-f", "name=monitoramento", "-f", "color=B60205",
                   "-f", "description=Alertas automáticos do monitoramento")
            except RuntimeError:
                pass  # o marcador já existe
            if meu is None:
                gh(f"repos/{repo}/issues", "-f", f"title={titulo}", "-f", f"body={corpo}", "-f", "labels[]=monitoramento")
                print("Alerta aberto na aba Issues.")
            elif f"assinatura:{assinatura}" not in (meu.get("body") or ""):
                gh(f"repos/{repo}/issues/{meu['number']}", "-X", "PATCH", "-f", f"body={corpo}")
                gh(f"repos/{repo}/issues/{meu['number']}/comments", "-f",
                   f"body=Os problemas mudaram em {hoje.strftime('%d/%m/%Y')}:\n\n" + "\n".join(f"- {e}" for e in rel.erros))
                print("Alerta atualizado na aba Issues.")
            else:
                print("O alerta aberto já descreve estes problemas.")
        elif meu is not None:
            gh(f"repos/{repo}/issues/{meu['number']}/comments", "-f",
               f"body=Tudo voltou ao normal em {hoje.strftime('%d/%m/%Y')}. Fechando este alerta.")
            gh(f"repos/{repo}/issues/{meu['number']}", "-X", "PATCH", "-f", "state=closed")
            print("Alerta fechado: tudo normal.")
    except RuntimeError as e:
        print(f"Aviso: não consegui atualizar o alerta na aba Issues: {e}")


# ------------------------------------------------------------------ principal

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raiz", default=".", help="pasta do repositório")
    ap.add_argument("--site", default="", help="endereço do site no ar (ex.: https://usuario.github.io/repositorio)")
    ap.add_argument("--apenas-site", action="store_true", help="só confere o site no ar (sem os arquivos do repositório)")
    ap.add_argument("--atualizar", default=None, help="resultado do job de atualização (success, failure, ...)")
    ap.add_argument("--publicar", default=None, help="resultado do job de publicação")
    ap.add_argument("--execucao-url", default="", help="link do log desta execução")
    ap.add_argument("--historico", default="dados/monitor.json", help="onde guardar o histórico de conferências")
    ap.add_argument("--salvar", action="store_true", help="guarda esta conferência no histórico")
    ap.add_argument("--alerta", action="store_true", help="abre, atualiza ou fecha o alerta na aba Issues (precisa de gh e GH_TOKEN)")
    ap.add_argument("--titulo", default="Alerta do monitoramento", help="título do alerta na aba Issues")
    ap.add_argument("--hoje", default="", help="para testes: data de hoje (AAAA-MM-DD)")
    ap.add_argument("--espera", type=int, default=300, help="segundos para esperar o site publicado mostrar os dados novos")
    args = ap.parse_args()

    hoje = date.fromisoformat(args.hoje) if args.hoje else datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    raiz = args.raiz
    caminho_hist = os.path.join(raiz, args.historico)
    hist = carregar(caminho_hist) or {"historico": []}
    antes_de_hoje = [h for h in hist["historico"] if h.get("data", "") < hoje.isoformat()]
    anterior = antes_de_hoje[-1] if antes_de_hoje else None  # repetir no mesmo dia compara com o dia anterior

    rel = Relatorio()
    resumo = {}
    gasto_mes = 0.0
    if not args.apenas_site:
        checar_execucao(rel, args)
        resumo = checar_dados(rel, raiz, hoje, anterior, args)
        gasto_mes = checar_custo(rel, raiz, hoje)
    if args.site:
        esperado = None if args.apenas_site else (resumo.get("gerado_em") if args.atualizar in (None, "success") else None)
        checar_site(rel, args.site, hoje, esperado, args)

    print(f"Monitoramento de {hoje.isoformat()}: {len(rel.erros)} erro(s), {len(rel.avisos)} aviso(s).\n")
    print(rel.texto())
    destino = os.environ.get("GITHUB_STEP_SUMMARY")
    if destino:
        with open(destino, "a", encoding="utf-8") as f:
            f.write(f"## Monitoramento de {hoje.strftime('%d/%m/%Y')}\n\n" + rel.texto() + "\n")

    if args.salvar and not args.apenas_site:
        entrada = {"data": hoje.isoformat(), **resumo, "custo_mes_usd": gasto_mes,
                   "erros": rel.erros, "avisos": rel.avisos}
        lista = [h for h in hist["historico"] if h.get("data") != hoje.isoformat()] + [entrada]
        os.makedirs(os.path.dirname(caminho_hist) or ".", exist_ok=True)
        with open(caminho_hist, "w", encoding="utf-8") as f:
            json.dump({"historico": lista[-120:]}, f, ensure_ascii=False, indent=1)
            f.write("\n")

    if args.alerta:
        atualizar_alerta(rel, hoje, args.titulo, args)
    return 1 if rel.erros else 0


if __name__ == "__main__":
    sys.exit(main())
