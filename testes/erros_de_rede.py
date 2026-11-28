#!/usr/bin/env python3
"""Testa que o monitor e o resumidor repetem a consulta quando a resposta vem cortada ou a conexão cai.

Uso (na raiz do repositório): python testes/erros_de_rede.py

Sem rede e sem esperar de verdade. Em 28/11/2026 a coleta caiu com http.client.IncompleteRead porque esse erro (HTTPException)
não estava na lista de erros passageiros; coleta/monitorar.py (buscar) e coleta/resumir_projetos.py (chamar) tinham listas parecidas.
Confere, para cada um:
  1. resposta cortada (IncompleteRead) e conexão derrubada (ConnectionResetError): repete e devolve a resposta;
  2. se continuar falhando, desiste dizendo o motivo, sem derrubar o programa com um erro solto.
Sai com código 1 se algo falhar.
"""
import importlib.util
import io
import json
import os
import sys
from http.client import IncompleteRead

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "coleta"))  # resumir_projetos importa construir_banco
falhas = []


def carregar(nome):
    spec = importlib.util.spec_from_file_location(nome, os.path.join(RAIZ, "coleta", nome + ".py"))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def confere(ok, msg):
    print(("  ok  " if ok else "  FALHOU  ") + msg)
    if not ok:
        falhas.append(msg)


class Resposta(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def roteiro(modulo, passos, corpo):
    """Troca urlopen e sleep do módulo. passos: 'cortada', 'reset' ou 200, um por consulta; o último se repete."""
    chamadas = []

    def urlopen(req, timeout=None):
        passo = passos[min(len(chamadas), len(passos) - 1)]
        chamadas.append(passo)
        if passo == "cortada":
            raise IncompleteRead(b"x" * 52013)
        if passo == "reset":
            raise ConnectionResetError("Connection reset by peer")
        return Resposta(corpo)

    modulo.urlopen = urlopen
    modulo.time.sleep = lambda s: None
    return chamadas


print("Monitor (coleta/monitorar.py, buscar)")
mon = carregar("monitorar")
for passo in ("cortada", "reset"):
    chamadas = roteiro(mon, [passo, passo, 200], "Voto de Verdade".encode())
    st, corpo = mon.buscar("http://x/")
    confere(st == 200 and corpo == "Voto de Verdade" and len(chamadas) == 3, f"{passo}: repete e devolve a página ({len(chamadas)} consultas)")
chamadas = roteiro(mon, ["cortada"], b"")
st, corpo = mon.buscar("http://x/")
confere(st == 0 and "IncompleteRead" in corpo and len(chamadas) == 3, "sempre cortada: desiste com código 0 e o motivo")

print("Resumidor (coleta/resumir_projetos.py, chamar)")
res = carregar("resumir_projetos")
ok = json.dumps({"content": [{"type": "tool_use", "input": {"assunto": "saude"}}], "usage": {"input_tokens": 3, "output_tokens": 4}}).encode()
ferramenta = {"name": "resumo", "input_schema": {"type": "object"}}
for passo in ("cortada", "reset"):
    chamadas = roteiro(res, [passo, passo, 200], ok)
    dado, t_in, t_out = res.chamar("claude-sonnet-5-5", "sistema", "usuário", ferramenta, "chave")
    confere(dado == {"assunto": "saude"} and (t_in, t_out) == (3, 4) and len(chamadas) == 3, f"{passo}: repete e devolve o resultado ({len(chamadas)} consultas)")
chamadas = roteiro(res, ["cortada"], ok)
try:
    res.chamar("claude-sonnet-5-5", "sistema", "usuário", ferramenta, "chave", tentativas=3)
    confere(False, "sempre cortada: deveria desistir")
except res.ErroProjeto as e:
    confere("IncompleteRead" in str(e) and len(chamadas) == 3, f"sempre cortada: desiste com ErroProjeto e o motivo ({e})")

if falhas:
    print(f"\n{len(falhas)} falha(s).")
    sys.exit(1)
print("\nTudo certo.")
