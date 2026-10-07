#!/usr/bin/env bash
# Guarda arquivos no repositório (usado pela rotina diária do GitHub).
# Uso: bash coleta/guardar_no_repositorio.sh "mensagem do commit" arquivo1 [arquivo2 ...]
# Se alguém mexeu no repositório enquanto a rotina rodava, junta as novidades e tenta de novo,
# para não perder o trabalho de uma coleta longa.
set -u
mensagem="$1"
shift
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
for arquivo in "$@"; do
  if [ -e "$arquivo" ]; then
    git add -- "$arquivo"
  fi
done
if git diff --cached --quiet; then
  echo "Nada novo para guardar."
  exit 0
fi
git commit -q -m "$mensagem"
for tentativa in 1 2 3 4 5; do
  if git pull --rebase origin "$GITHUB_REF_NAME" && git push origin "HEAD:$GITHUB_REF_NAME"; then
    echo "Guardado no repositório."
    exit 0
  fi
  echo "Não consegui enviar na tentativa $tentativa. Vou tentar de novo em 15 segundos."
  git rebase --abort 2>/dev/null || true
  sleep 15
done
echo "ERRO: não foi possível guardar os arquivos no repositório."
exit 1
