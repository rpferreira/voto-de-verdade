#!/usr/bin/env python3
"""Confere a versão do site (regras em docs/versionamento.md).

  1. VERSION tem o formato X.Y.Z.
  2. CHANGELOG.md: versões em ordem (da mais nova para a mais antiga), sem repetição, com data ISO, e a primeira é igual a VERSION.
  3. Com a pasta do site montado: o rodapé de cada página mostra a versão de VERSION (português, inglês, 404 e páginas prontas).
  4. Com --base (no pull request): quem mexeu no código do site ou na coleta subiu VERSION para um número maior que o da base
     e acrescentou a entrada no CHANGELOG.md.

Uso:
    python testes/versao.py                              # 1 e 2
    python testes/versao.py _site                        # 1, 2 e 3
    python testes/versao.py _site --base origin/main     # 1, 2, 3 e 4
Sai com código 1 se algo falhar.
"""
import argparse
import datetime
import os
import re
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORMATO = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
# O que conta como «código do site»: muda o que o site faz. Dados, fotos e documentação ficam de fora (docs/versionamento.md, seção 3).
CODIGO_DO_SITE = ("site/", "coleta/")
FORA = ("site/dados/", "site/fotos/")

falhas = []


def confere(ok, msg):
    print(("  ok  " if ok else "FALHOU ") + msg)
    if not ok:
        falhas.append(msg)
        if os.environ.get("GITHUB_ACTIONS"):
            print("::error::" + msg)


def como_tupla(v):
    m = FORMATO.match(v or "")
    return tuple(int(x) for x in m.groups()) if m else None


def ler(nome):
    with open(os.path.join(RAIZ, nome), encoding="utf-8") as f:
        return f.read()


def versoes_do_changelog(texto):
    return re.findall(r"^## (\S+) \((\d{4}-\d{2}-\d{2})\)\s*$", texto, flags=re.M)


def mexeu_no_codigo(arquivos):
    return [a for a in arquivos if a.startswith(CODIGO_DO_SITE) and not a.startswith(FORA)]


def git(*args):
    return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True)


def estatica():
    print("VERSION e CHANGELOG.md")
    versao = ler("VERSION").strip()
    confere(como_tupla(versao) is not None, f"VERSION tem o formato X.Y.Z ({versao!r})")
    entradas = versoes_do_changelog(ler("CHANGELOG.md"))
    confere(bool(entradas), "CHANGELOG.md tem pelo menos uma versão no formato «## X.Y.Z (AAAA-MM-DD)»")
    if entradas:
        nums = [como_tupla(v) for v, _ in entradas]
        confere(None not in nums, "todas as versões do CHANGELOG.md têm o formato X.Y.Z")
        confere(None not in nums and all(a > b for a, b in zip(nums, nums[1:])), "versões do CHANGELOG.md em ordem, da mais nova para a mais antiga, sem repetir")
        confere(entradas[0][0] == versao, f"a entrada mais nova do CHANGELOG.md ({entradas[0][0]}) é a VERSION ({versao})")
        datas_ok = True
        for _, d in entradas:
            try:
                datetime.date.fromisoformat(d)
            except ValueError:
                datas_ok = False
        confere(datas_ok, "datas do CHANGELOG.md são datas de verdade")
        confere(all(a[1] >= b[1] for a, b in zip(entradas, entradas[1:])), "datas do CHANGELOG.md não andam para trás")
    return versao


def paginas(pasta, versao):
    print("Rodapé nas páginas montadas")
    candidatas = ["index.html", "en/index.html", "404.html", "en/404.html", "sobre/index.html", "en/sobre/index.html"]
    for sub in ("projeto", "deputado"):
        base = os.path.join(pasta, sub)
        if os.path.isdir(base):
            for nome in sorted(os.listdir(base))[:1]:
                candidatas.append(f"{sub}/{nome}/index.html")
    for rel in candidatas:
        caminho = os.path.join(pasta, rel)
        if not os.path.exists(caminho):
            confere(False, f"{rel} existe")
            continue
        with open(caminho, encoding="utf-8") as f:
            html = f.read()
        ingles = rel.startswith("en/")
        esperado = f"Version {versao} (beta)" if ingles else f"Versão {versao} (beta)"
        ok = f'<p class="rodape__versao">{esperado} · ' in html and "CHANGELOG.md" in html and f'<meta name="generator" content="Voto de Verdade {versao}">' in html
        confere(ok, f"{rel}: rodapé mostra «{esperado}» com link para o histórico, e a página declara a versão")


def no_pull_request(base):
    print(f"Versão em relação a {base}")
    git("fetch", "--quiet", "origin", base.split("/", 1)[-1])
    r = git("diff", "--name-only", f"{base}...HEAD")
    if r.returncode != 0:
        confere(False, f"consegui comparar com {base} ({r.stderr.strip()})")
        return
    arquivos = [a for a in r.stdout.split("\n") if a]
    codigo = mexeu_no_codigo(arquivos)
    antes = git("show", f"{base}:VERSION")
    versao = ler("VERSION").strip()
    if not codigo:
        confere(True, f"mudou só dados, fotos, testes ou documentação ({len(arquivos)} arquivos): não precisa subir a versão")
        return
    if antes.returncode != 0:
        confere(True, f"a {base} ainda não tem VERSION: esta é a primeira versão numerada ({versao})")
        return
    confere(como_tupla(antes.stdout.strip()) is not None, f"VERSION da {base} lida ({antes.stdout.strip()!r})")
    if como_tupla(antes.stdout.strip()):
        confere(como_tupla(versao) > como_tupla(antes.stdout.strip()), f"mexeu no código do site ({codigo[0]} e outros {len(codigo) - 1}): VERSION subiu de {antes.stdout.strip()} para {versao}")
    confere("CHANGELOG.md" in arquivos, "CHANGELOG.md recebeu a entrada da nova versão")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta", nargs="?")
    ap.add_argument("--base")
    args = ap.parse_args()
    versao = estatica()
    if args.pasta:
        paginas(args.pasta, versao)
    if args.base:
        no_pull_request(args.base)
    if falhas:
        print(f"\n{len(falhas)} verificação(ões) falharam.")
        return 1
    print("\nVersão em ordem.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
