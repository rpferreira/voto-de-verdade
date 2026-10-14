#!/usr/bin/env python3
"""Testa coleta/guardar_no_repositorio.sh, o script que a rotina diária usa para guardar arquivos no repositório.

Uso (na raiz do repositório): python testes/guardar.py

Monta um repositório de mentira com um «remoto» e confere dois casos:
  1. Com outros arquivos já alterados e ainda não guardados (como site/dados no meio da rotina), o arquivo pedido
     é guardado, o remoto o recebe e os arquivos alterados continuam alterados, sem perda.
  2. Com alguém tendo mexido no remoto no meio do caminho, o script junta e guarda do mesmo jeito.
Foi o que faltou em 14/10/2026: a rotina falhou nessa etapa e o site não foi publicado.
Sai com código 1 se algo falhar.
"""
import os
import shutil
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(RAIZ, "coleta", "guardar_no_repositorio.sh")
falhas = []


def confere(ok, msg):
    print(("  ok  " if ok else "  FALHOU  ") + msg)
    if not ok:
        falhas.append(msg)


def git(cwd, *args, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f"git {' '.join(args)} falhou: {r.stderr}")
    return r.stdout.strip()


def escrever(pasta, caminho, texto):
    destino = os.path.join(pasta, caminho)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        f.write(texto)


def montar(tmp):
    remoto = os.path.join(tmp, "remoto.git")
    git(tmp, "init", "-q", "--bare", "-b", "main", remoto)
    trabalho = os.path.join(tmp, "trabalho")
    git(tmp, "clone", "-q", remoto, trabalho)
    for k, v in (("user.name", "teste"), ("user.email", "teste@example.com")):
        git(trabalho, "config", k, v)
    escrever(trabalho, "dados/traducoes_en.json", "{}\n")
    escrever(trabalho, "site/dados/meta.json", "{}\n")
    git(trabalho, "add", "-A")
    git(trabalho, "commit", "-q", "-m", "início")
    git(trabalho, "push", "-q", "origin", "HEAD:main")
    return remoto, trabalho


def rodar(trabalho):
    env = dict(os.environ, GITHUB_REF_NAME="main")
    return subprocess.run(["bash", SCRIPT, "Traduções", "dados/traducoes_en.json"], cwd=trabalho, env=env, capture_output=True, text=True)


tmp = tempfile.mkdtemp(prefix="guardar-")
try:
    print("Guardar com arquivos já alterados e ainda não guardados")
    remoto, trabalho = montar(tmp)
    escrever(trabalho, "dados/traducoes_en.json", '{"novo": 1}\n')
    escrever(trabalho, "site/dados/meta.json", '{"refeito": true}\n')
    r = rodar(trabalho)
    confere(r.returncode == 0, "o script termina bem" + ("" if r.returncode == 0 else ": " + r.stdout[-300:] + r.stderr[-300:]))
    confere('"novo"' in git(tmp, "--git-dir", remoto, "show", "main:dados/traducoes_en.json"), "o remoto recebeu o arquivo pedido")
    confere("refeito" in open(os.path.join(trabalho, "site/dados/meta.json"), encoding="utf-8").read(), "o arquivo que não era para guardar continua alterado, sem perda")
    confere("refeito" not in git(tmp, "--git-dir", remoto, "show", "main:site/dados/meta.json"), "o remoto não recebeu o arquivo que não era para guardar")

    print("Guardar quando alguém mexeu no remoto no meio do caminho")
    os.makedirs(tmp + "-2")
    remoto, trabalho = montar(tmp + "-2")
    outro = os.path.join(tmp + "-2", "outro")
    git(tmp + "-2", "clone", "-q", remoto, outro)
    for k, v in (("user.name", "outra pessoa"), ("user.email", "outra@example.com")):
        git(outro, "config", k, v)
    escrever(outro, "LEIAME.md", "mudança de outra pessoa\n")
    git(outro, "add", "-A")
    git(outro, "commit", "-q", "-m", "outra mudança")
    git(outro, "push", "-q", "origin", "HEAD:main")
    escrever(trabalho, "dados/traducoes_en.json", '{"novo": 2}\n')
    escrever(trabalho, "site/dados/meta.json", '{"refeito": true}\n')
    r = rodar(trabalho)
    confere(r.returncode == 0, "o script termina bem" + ("" if r.returncode == 0 else ": " + r.stdout[-300:] + r.stderr[-300:]))
    confere('"novo": 2' in git(tmp, "--git-dir", remoto, "show", "main:dados/traducoes_en.json"), "o remoto recebeu o arquivo pedido")
    confere("outra pessoa" in git(tmp, "--git-dir", remoto, "log", "main", "--format=%an"), "a mudança da outra pessoa continua no remoto")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(tmp + "-2", ignore_errors=True)

if falhas:
    print(f"\n{len(falhas)} falha(s).")
    sys.exit(1)
print("\nTudo certo.")
