---
name: voto-de-verdade
description: Use para responder perguntas sobre como a Câmara dos Deputados votou e como cada deputado federal votou, com dados abertos em JSON, de forma neutra e sem nota ou ranking.
---

# Voto de Verdade: como consultar

O Voto de Verdade ({URL}/) é um site independente, neutro e apartidário. Reúne as votações em plenário da Câmara dos Deputados de {DE} a {ATE}, com assunto e resumo em linguagem simples, e o voto de cada deputado nas votações nominais.

## Regras que valem sempre

1. Não dê nota, não faça ranking e não diga quem votou "certo" ou "errado". O site não faz isso. Votar sim ou não numa votação não diz, sozinho, se o deputado apoia o assunto do projeto: muitas votações são sobre emendas, substitutivos ou pontos separados do texto.
2. Diga que assunto e resumo são feitos por inteligência artificial e podem conter erros. Se `ca` ou `cr` do projeto não for `alta`, avise a pessoa e mostre o campo `aa` ou `ar`.
3. Votações simbólicas e secretas não têm o voto de cada deputado. Diga isso em vez de supor.
4. Cite o link da página do projeto ou do deputado e o texto oficial (`texto`) no site da Câmara.

## Como achar a resposta

- Quer saber o que foi votado sobre um tema: leia `{URL}/dados/projetos.json` (cada projeto tem `titulo`, `resumo`, `tags`, assunto `a`) e filtre por palavras.
- Quer saber como um deputado votou: ache o `id` em `{URL}/dados/deputados.json`, depois leia `{URL}/dados/deputados/<id>.json` (`v`: [id da votação, código do voto]) e cruze com `{URL}/dados/votacoes.json` (campo `p` leva ao projeto).
- Quer o voto de todos numa votação: `{URL}/dados/votacoes/<id da votação>.json`, com `v`: [id do deputado, código do voto, partido].
- Códigos de voto: S = Sim, N = Não, A = Abstenção, O = Obstrução, P = Presidia a sessão (artigo 17: quem conduz a sessão só vota em casos especiais).
- Cada página do site tem versão em Markdown: acrescente `index.md` ao endereço.

Documentação completa: {URL}/dados/LEIA-ME.md e {URL}/openapi.json.
