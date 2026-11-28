#!/usr/bin/env python3
"""Testa como a coleta repete as consultas à API da Câmara quando ela cai (coleta/coletar_votacoes.py, get_url).

Uso (na raiz do repositório): python testes/coleta_repeticao.py

Sem rede e sem esperar de verdade (a função de espera é trocada por um registro). Confere:
  1. API de pé: uma consulta só, sem espera longa.
  2. 503 nas tentativas curtas e resposta depois da primeira espera longa: devolve a resposta.
  3. Erro de rede (sem resposta) tratado do mesmo jeito.
  4. Erro que não passa (404): não repete.
  5. Resposta cortada no meio (IncompleteRead) e conexão derrubada (ConnectionResetError): repete, em vez de derrubar a coleta.
  6. API fora do ar o tempo todo: desiste, e a espera total da coleta nunca passa de ORCAMENTO_ESPERA;
     depois que o orçamento acaba, as consultas seguintes fazem só as tentativas curtas.
Em 10/11 e 18/11/2026 a API da Câmara caiu e o site ficou dias sem atualizar: as três tentativas em poucos
segundos eram curtas demais. Sai com código 1 se algo falhar.
"""
import importlib.util
import io
import json
import os
import sys
from http.client import IncompleteRead
from urllib.error import HTTPError, URLError

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("coletar_votacoes", os.path.join(RAIZ, "coleta", "coletar_votacoes.py"))
col = importlib.util.module_from_spec(spec)
spec.loader.exec_module(col)
falhas = []


def confere(ok, msg):
    print(("  ok  " if ok else "  FALHOU  ") + msg)
    if not ok:
        falhas.append(msg)


class Resposta:
    status = 200

    def __init__(self, dados):
        self._dados = dados

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self._dados).encode()


def roteiro(passos):
    """Troca urlopen e sleep. passos: lista de 200, 503, 404 ou 'rede', um por consulta; o último se repete."""
    chamadas, esperas = [], []

    def urlopen(req, timeout=None):
        passo = passos[min(len(chamadas), len(passos) - 1)]
        chamadas.append(passo)
        if passo == 200:
            return Resposta({"dados": [1]})
        if passo == "rede":
            raise URLError("timed out")
        if passo == "cortada":
            raise IncompleteRead(b"x" * 52013)
        if passo == "reset":
            raise ConnectionResetError("Connection reset by peer")
        raise HTTPError(req.full_url, passo, "erro", {}, io.BytesIO(b"falha"))

    col.urlopen = urlopen
    col.time.sleep = lambda s: esperas.append(s)
    col._espera_gasta[0] = 0.0
    return chamadas, esperas


def longas(esperas):
    return [e for e in esperas if e >= 30]


print("1. API de pé")
chamadas, esperas = roteiro([200])
st, d = col.get_url("http://x/a")
confere(st == 200 and len(chamadas) == 1 and not longas(esperas), "uma consulta, sem espera longa")

print("2. 503 três vezes e depois resposta")
chamadas, esperas = roteiro([503, 503, 503, 200])
st, d = col.get_url("http://x/b")
confere(st == 200 and d == {"dados": [1]}, "devolve a resposta quando a API volta")
confere(longas(esperas) == [30], f"esperou uma vez 30 s (esperas longas: {longas(esperas)})")

print("3. Sem resposta (rede) e depois resposta")
chamadas, esperas = roteiro(["rede", "rede", "rede", "rede", 200])
st, d = col.get_url("http://x/c")
confere(st == 200 and longas(esperas) == [30, 90], f"volta depois de 30 s e 90 s (esperas longas: {longas(esperas)})")

print("4. Erro que não passa (404)")
chamadas, esperas = roteiro([404])
st, d = col.get_url("http://x/d")
confere(st == 404 and len(chamadas) == 1 and not longas(esperas), "não repete")

print("5. Resposta cortada no meio e conexão derrubada")
for passo in ("cortada", "reset"):
    chamadas, esperas = roteiro([passo, passo, passo, 200])
    st, d = col.get_url("http://x/i")
    confere(st == 200 and d == {"dados": [1]} and longas(esperas) == [30], f"{passo}: repete e devolve a resposta (esperas longas: {longas(esperas)})")
chamadas, esperas = roteiro(["cortada"])
st, d = col.get_url("http://x/j")
confere(st is None and "IncompleteRead" in d.get("_erro", ""), "se continuar cortando, desiste sem derrubar o programa e diz o motivo")

print("6. API fora do ar o tempo todo")
chamadas, esperas = roteiro([503])
st, d = col.get_url("http://x/e")
confere(st == 503 and d.get("_erro") == "falha", "desiste com o erro da API")
confere(longas(esperas) == list(col.ESPERAS_LONGAS), "a primeira consulta usa todas as esperas longas")
st, d = col.get_url("http://x/f")
st, d = col.get_url("http://x/g")
confere(sum(longas(esperas)) <= col.ORCAMENTO_ESPERA, f"espera total {sum(longas(esperas))} s, dentro de {col.ORCAMENTO_ESPERA} s")
antes = len(chamadas)
st, d = col.get_url("http://x/h")
confere(len(chamadas) - antes == 3, "sem orçamento, só as 3 tentativas curtas")

if falhas:
    print(f"\n{len(falhas)} falha(s).")
    sys.exit(1)
print("\nTudo certo.")
