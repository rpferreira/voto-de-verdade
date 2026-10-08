# Segurança

O Voto de Verdade é um site estático: não tem login, formulário, banco de dados no ar nem cookies.
Mesmo assim, se você achar uma falha, queremos saber.

## Como avisar

Use **Security → Report a vulnerability** neste repositório (aviso privado). Se não conseguir, abra uma
issue sem detalhes técnicos, só dizendo que quer falar de segurança, e combinamos o resto.

Vale relatar, por exemplo: código que executa a partir dos dados ou do endereço, link perigoso na tela,
segredo exposto, ou algo que quebre a promessa de não rastrear quem visita.

## O que o site garante

- Não usa cookies nem ferramentas de rastreio. A única coisa guardada no navegador é o tema (claro ou escuro).
- Não fala com outros endereços: fontes, fotos e dados são do próprio site.
- Todo texto vindo dos dados é mostrado como texto, nunca como código. Links vindos dos dados só valem se forem `https://`.
- Uma política de segurança de conteúdo (CSP) bloqueia scripts que não sejam os do próprio site.
- `testes/seguranca.py` ataca o site com dados maliciosos a cada pull request.
