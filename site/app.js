/* Voto de Verdade: início, assuntos, projetos (com o voto de cada deputado), deputados e "como funciona".
   JavaScript puro, sem bibliotecas. Os dados vêm de dados/*.json (feitos por site/exportar_dados.py).
   Endereços (hash): #/   #/assunto/<slug>?q=...&todos=1   #/projeto/<id>?votacao=<id>&q=...&pt=PT&uf=GO&v=S
   #/deputados?q=...&pt=PT&uf=GO   #/deputado/<id>?q=...&a=<assunto>&v=S   #/sobre
   As páginas prontas (projeto/<id>/, deputado/<id>/, assunto/<slug>/) são feitas por site/gerar_paginas.py,
   com título e prévia próprios para Google e WhatsApp; elas abrem o mesmo aplicativo (rota inicial no bloco de configuração).
   Os filtros ficam no endereço para poder compartilhar. */
(async function () {
  "use strict";

  // Modo escuro: o site abre sempre no claro; a escolha da pessoa fica só neste navegador.
  (function () {
    const botoes = document.querySelectorAll(".tema");
    if (!botoes.length) return;
    const escuro = () => document.documentElement.dataset.theme === "dark";
    const mostrar = () => botoes.forEach((b) => b.setAttribute("aria-pressed", String(escuro())));
    botoes.forEach((b) => b.addEventListener("click", () => {
      const novo = escuro() ? "light" : "dark";
      document.documentElement.dataset.theme = novo;
      try { localStorage.setItem("tema", novo); } catch (e) { /* sem armazenamento: vale só até recarregar */ }
      mostrar();
    }));
    mostrar();
  })();

  const principal = document.getElementById("conteudo");
  const memoria = {};
  const POR_PAGINA = 30;
  // Configuração da página (raiz relativa, rota inicial e doação): vem num bloco de dados, não em script embutido.
  const CONFIG = (() => { try { return JSON.parse(document.getElementById("config").textContent) || {}; } catch (e) { return {}; } })();
  const RAIZ = CONFIG.raiz || "";
  // Idioma da página: português (padrão) ou inglês (páginas em /en/). Os endereços de página ficam dentro do idioma.
  const LANG = CONFIG.lang === "en" ? "en" : "pt";
  const LOCALE = LANG === "en" ? "en-US" : "pt-BR";
  const PAGINAS = RAIZ + (LANG === "en" ? "en/" : "");
  // Textos da tela: o próprio texto em português é a chave do dicionário (idiomas/en.json). Sem tradução, mostra o português
  // e anota a falta em window.__IDIOMA_FALTA__ (o teste testes/idiomas.py exige que fique vazio).
  let DICIONARIO = {};
  if (LANG === "en") {
    try { const r = await fetch(RAIZ + "idiomas/en.json"); if (r.ok) DICIONARIO = await r.json(); } catch (e) { console.error(e); }
  }
  const FALTAM = (window.__IDIOMA_FALTA__ = new Set());
  const tx = (chave, ...valores) => {
    let texto = chave;
    if (LANG !== "pt") {
      texto = DICIONARIO[chave];
      if (texto === undefined) { FALTAM.add(chave); texto = chave; }
    }
    return valores.length ? texto.replace(/\{(\d+)\}/g, (_, i) => valores[i]) : texto;
  };

  // ------------------------------------------------------------------ utilidades
  async function dados(nome) {
    if (memoria[nome]) return memoria[nome];
    if (window.__DADOS__ && window.__DADOS__[nome]) return (memoria[nome] = window.__DADOS__[nome]);
    const r = await fetch(RAIZ + "dados/" + nome + ".json");
    if (!r.ok) throw new Error("Não consegui carregar " + nome);
    const dado = await r.json();
    if (LANG === "en") await traduzirDados(nome, dado);
    return (memoria[nome] = dado);
  }
  // Em inglês, o texto vem de dados/en/<mesmo nome>.json, só com os campos traduzidos. O que ainda não foi traduzido fica em português.
  async function traduzirDados(nome, dado) {
    const sobrepor = (alvo, tr, campos) => { if (tr) for (const c of campos) if (tr[c] !== undefined) alvo[c] = tr[c]; };
    let en = null;
    try {
      const r = await fetch(RAIZ + "dados/en/" + nome + ".json");
      if (r.ok) en = await r.json();
    } catch (e) { /* sem tradução: fica em português */ }
    if (!en) return;
    if (nome === "assuntos") for (const a of dado) sobrepor(a, en[a.slug], ["nome", "descricao"]);
    else if (nome === "projetos") for (const p of dado) sobrepor(p, en[p.id], ["titulo", "resumo", "tags", "aa", "ar"]);
    else if (nome === "votacoes") for (const v of dado) sobrepor(v, en[v.id], ["desc", "av"]);
    else if (nome.startsWith("projetos/")) sobrepor(dado, en, ["pontos"]);
  }

  const semAcento = (t) => (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const formato = new Intl.DateTimeFormat(LOCALE, { day: "numeric", month: "long", year: "numeric" });
  const data = (iso) => (iso ? formato.format(new Date(iso + "T12:00:00")) : "");
  const num = (n) => n.toLocaleString(LOCALE);
  const plural = (n, um, varios) => `${num(n)} ${n === 1 ? um : varios}`;

  function h(tag, attrs, ...filhos) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === false || v == null) continue;
      if (k === "class") el.className = v;
      else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
      else if (v === true) el.setAttribute(k, "");
      else el.setAttribute(k, v);
    }
    for (const f of filhos.flat()) {
      if (f == null || f === false) continue;
      el.append(f.nodeType ? f : document.createTextNode(String(f)));
    }
    return el;
  }

  // Endereço com "%" malformado (por exemplo #/assunto/%) não pode derrubar o roteador: vira "não encontrado".
  const decodificar = (t) => { try { return decodeURIComponent(t); } catch (e) { return t; } };
  // Só aceitamos link https que venha dos dados; qualquer outro esquema (javascript:, data:…) é ignorado.
  const soHttps = (u) => (typeof u === "string" && /^https:\/\//i.test(u) ? u : null);

  function lerRota() {
    const hash = location.hash;
    let bruto = hash.replace(/^#\/?/, "");
    // Nas páginas prontas (projeto/123/) o endereço não tem "#": a rota vem da própria página.
    if (!hash && CONFIG.rota) bruto = CONFIG.rota;
    const [caminho, consulta = ""] = bruto.split("?");
    return { partes: caminho.split("/").filter(Boolean).map(decodificar), p: new URLSearchParams(consulta) };
  }

  function gravarEndereco(caminho, params) {
    const s = params.toString();
    history.replaceState(null, "", "#/" + caminho + (s ? "?" + s : ""));
  }

  function limparParams(obj) {
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(obj)) if (v) p.set(k, v);
    return p;
  }

  const anunciar = (el, texto) => { el.textContent = texto; };
  const comEspera = (campo, fn) => {
    let espera;
    campo.addEventListener("input", () => { clearTimeout(espera); espera = setTimeout(fn, 180); });
  };

  // Botão "Compartilhar": usa o menu do celular ou copia o endereço da página pronta.
  function botaoCompartilhar(caminho, titulo) {
    if (!/^https?:$/.test(location.protocol)) return null;
    const url = new URL(PAGINAS + caminho + "/", location.href).href;
    const botao = h("button", { type: "button", class: "botao botao--leve botao--pequeno" }, tx("Compartilhar"));
    const aviso = h("span", { class: "so-leitor", role: "status" });
    botao.addEventListener("click", async () => {
      try {
        if (navigator.share) { await navigator.share({ title: titulo, url }); return; }
      } catch (e) { if (e && e.name === "AbortError") return; }
      let texto;
      try { await navigator.clipboard.writeText(url); texto = tx("Link copiado"); } catch (e) { texto = tx("Copie o endereço na barra do navegador"); }
      botao.textContent = texto; anunciar(aviso, texto);
      setTimeout(() => { botao.textContent = tx("Compartilhar"); anunciar(aviso, ""); }, 2500);
    });
    return h("span", {}, botao, aviso);
  }

  // ------------------------------------------------------------------ busca
  let indiceProjetos = null;
  async function projetosComTexto() {
    if (indiceProjetos) return indiceProjetos;
    const lista = await dados("projetos");
    for (const p of lista) p._t = semAcento([p.titulo, p.resumo, p.nome, (p.tags || []).join(" ")].join(" "));
    return (indiceProjetos = lista);
  }
  // "pl4952" vale como "pl 4952". Termos de até 3 letras só casam no começo de uma palavra ("ia" não acha "previdência").
  const termos = (q) => semAcento(q).replace(/([a-z])(\d)/g, "$1 $2").split(/\s+/).filter((t) => t.length > 1);
  const casa = (texto, ts) => ts.every((t) => (t.length <= 3 ? texto.startsWith(t) || texto.includes(" " + t) || new RegExp("[^a-z0-9]" + t.replace(/[^a-z0-9]/g, "\\$&")).test(texto) : texto.includes(t)));

  let indiceVot = null;
  async function indiceVotacoes() {
    if (indiceVot) return indiceVot;
    const lista = await dados("votacoes");
    const porProjeto = {}, porId = {};
    for (const v of lista) { (porProjeto[v.p] = porProjeto[v.p] || []).push(v); porId[v.id] = v; }
    return (indiceVot = { lista, porProjeto, porId });
  }

  // ------------------------------------------------------------------ cores e ícones dos assuntos
  const HUES = {
    "saude": 165, "educacao": 38, "impostos-e-economia": 205, "seguranca-publica": 255, "meio-ambiente": 125,
    "trabalho-e-direitos": 18, "infraestrutura-e-transporte": 55, "tecnologia-e-comunicacao": 188,
    "administracao-publica-e-congresso": 275, "cultura-esporte-e-turismo": 330, "relacoes-internacionais-e-defesa": 228,
    "agropecuaria-e-campo": 85, "outros": 215,
  };
  const ICONES = {
    "saude": "M9 3h6v6h6v6h-6v6H9v-6H3V9h6z",
    "educacao": "M2 5h7a3 3 0 0 1 3 3v12a2 2 0 0 0-2-2H2z|M22 5h-7a3 3 0 0 0-3 3v12a2 2 0 0 1 2-2h8z",
    "impostos-e-economia": "M3 20h18|M6 20v-7|M11 20V5|M16 20v-10|M21 20V8",
    "seguranca-publica": "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z",
    "meio-ambiente": "M5 19c0-9 5-14 15-14 0 10-5 15-14 15|M5 19c2-5 5-8 9-10",
    "trabalho-e-direitos": "M3 8h18v12H3z|M9 8V5h6v3|M3 13h18",
    "infraestrutura-e-transporte": "M8 3L4 21|M16 3l4 18|M12 4v3|M12 11v3|M12 18v3",
    "tecnologia-e-comunicacao": "M7 7h10v10H7z|M10 3v4|M14 3v4|M10 17v4|M14 17v4|M3 10h4|M3 14h4|M17 10h4|M17 14h4",
    "administracao-publica-e-congresso": "M3 10l9-6 9 6|M5 10v8|M9.5 10v8|M14.5 10v8|M19 10v8|M3 21h18",
    "cultura-esporte-e-turismo": "M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z",
    "relacoes-internacionais-e-defesa": "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z|M3 12h18|M12 3c3 3 3 15 0 18|M12 3c-3 3-3 15 0 18",
    "agropecuaria-e-campo": "M12 21V9|M12 9c0-3-2-5-5-5 0 3 2 5 5 5z|M12 14c0-3 2-5 5-5 0 3-2 5-5 5z",
    "outros": "M5 12h.01|M12 12h.01|M19 12h.01",
    // Ícones dos pontos fortes na tela inicial
    "p-neutro": "M12 4v16|M7 20h10|M5 8h14|M5 8l-3 6a3.5 3.5 0 0 0 6 0z|M19 8l-3 6a3.5 3.5 0 0 0 6 0z",
    "p-sem-nota": "M5 20v-6|M10 20V8|M15 20v-9|M20 20V5|M3 3l18 18",
    "p-votado": "M4 4h16v16H4z|M8 12l3 3 5-6",
    "v-busca": "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14z|M21 21l-5-5",
    "v-filtro": "M3 5h18l-7 8v6l-4-2v-4z",
    "v-urna": "M3 13h18v7H3z|M8 13l1-9h6l1 9|M9 17h6",
    "v-mapa": "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z|M15.5 8.5l-2 5-5 2 2-5z",
    "v-erro": "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z|M12 7v6|M12 16h.01",
    "v-pessoa": "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8z|M4 21c0-4.4 3.6-8 8-8s8 3.6 8 8",
    "p-sem-rastreio": "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z|M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z|M3 3l18 18",
  };
  const SVGNS = "http://www.w3.org/2000/svg";
  function svg(tag, attrs) {
    const el = document.createElementNS(SVGNS, tag);
    for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
    return el;
  }
  function icone(slug) {
    const s = svg("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "1.8", "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true", class: "icone" });
    for (const d of (ICONES[slug] || ICONES.outros).split("|")) s.append(svg("path", { d }));
    return s;
  }
  // Estado vazio: quando não há nada para mostrar, explica por quê e oferece o próximo passo.
  function estadoVazio({ icone: ic, titulo, texto, acoes = [], pagina = false }) {
    return h("div", { class: "vazio" + (pagina ? " vazio--pagina" : "") },
      h("span", { class: "vazio__icone" }, icone(ic)),
      h("div", { class: "vazio__corpo" },
        h("p", { class: "vazio__titulo" }, titulo),
        texto ? h("p", { class: "vazio__texto" }, texto) : null,
        acoes.length ? h("div", { class: "vazio__acoes" }, acoes.map((a) => a.href
          ? h("a", { class: "botao botao--leve", href: a.href }, a.rotulo)
          : h("button", { type: "button", class: "botao botao--leve", onclick: a.onclick }, a.rotulo))) : null));
  }

  // O título de um projeto é cortado em 200 letras; na página do projeto mostramos a primeira frase inteira.
  function tituloCompleto(pr) {
    if (!pr.titulo.endsWith("…") || !pr.resumo) return pr.titulo;
    const base = pr.titulo.slice(0, -1).trimEnd();
    if (!pr.resumo.startsWith(base)) return pr.titulo;
    const m = /[.!?](?=\s|$)/.exec(pr.resumo.slice(base.length));
    const inteiro = m ? pr.resumo.slice(0, base.length + m.index + 1) : pr.resumo;
    return inteiro.length <= 400 ? inteiro : pr.titulo;
  }

  const estiloAssunto = (slug) => `--h:${HUES[slug] ?? 215}${slug === "outros" ? ";--sat:0.25" : ""}`;

  // ------------------------------------------------------------------ votos
  const VOTO = {
    S: { nome: tx("Sim") }, N: { nome: tx("Não") }, A: { nome: tx("Abstenção") }, O: { nome: tx("Obstrução") }, P: { nome: tx("Presidia a sessão") },
  };
  const ORDEM_VOTO = ["S", "N", "A", "O", "P"];
  const NOME_VOTO = Object.fromEntries(ORDEM_VOTO.map((c) => [c, VOTO[c].nome]));
  const fichaVoto = (cod) => h("span", { class: "voto voto--" + cod }, VOTO[cod].nome);

  // Números do placar; cada um é um botão que mostra só os deputados com aquele voto.
  function placarVotos(total, aoEscolher) {
    const itens = ORDEM_VOTO.filter((c) => total[c]).map((c) => {
      const conteudo = [h("span", { class: "placar__nome" }, c === "P" ? tx("Presidia") : VOTO[c].nome), h("span", { class: "placar__num" }, num(total[c]))];
      return h("li", {}, aoEscolher
        ? h("button", { type: "button", class: "placar__item placar__item--" + c, "aria-pressed": "false", "data-voto": c, onclick: () => aoEscolher(c) }, conteudo)
        : h("div", { class: "placar__item placar__item--" + c }, conteudo));
    });
    const lista = h("ul", { class: "placar" }, itens);
    lista.marcar = (cod) => lista.querySelectorAll("button[data-voto]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.voto === cod)));
    return lista;
  }

  // ------------------------------------------------------------------ pedaços reaproveitados
  const TIPO_SEM = { secreta: tx("Votação secreta"), simbolica: tx("Votação simbólica, sem o voto de cada deputado") };

  function primeiroNominal(votacoes, pr) {
    const nominais = (votacoes.porProjeto[pr.id] || []).filter((x) => x.t === "nominal").sort((x, y) => (x.d < y.d ? -1 : 1));
    return nominais[nominais.length - 1];
  }

  // Uma linha da lista de projetos: leva à página do projeto, que já mostra os votos.
  function linhaProjeto(pr, votacoes, opc) {
    opc = opc || {};
    const incerto = (pr.ca && pr.ca !== "alta") || (pr.cr && pr.cr !== "alta");
    const v = opc.votacao || primeiroNominal(votacoes, pr);
    let placar = null;
    if (v && v.s) {
      const soma = v.s.reduce((a, b) => a + b, 0), outros = v.s[2] + v.s[3] + v.s[4];
      placar = h("span", { class: "mini-placar" },
        h("span", { class: "barra-voto", "aria-hidden": "true" },
          ORDEM_VOTO.map((c, i) => (v.s[i] ? h("i", { class: "seg-" + c, style: `width:${(v.s[i] / soma) * 100}%` }) : null))),
        h("span", {}, tx("{0} sim · {1} não{2}", num(v.s[0]), num(v.s[1]), outros ? ` · ${num(outros)} ${outros === 1 ? tx("outro") : tx("outros")}` : "")));
    }
    const resultado = (v ? v.ap : pr.aprovada) ? tx("Votação aprovada") : tx("Votação rejeitada");
    const sem = !v ? TIPO_SEM[pr.tipo] || TIPO_SEM.simbolica : null;
    const href = "#/projeto/" + pr.id + (opc.votacao ? "?votacao=" + encodeURIComponent(opc.votacao.id) : "");
    return h("li", {}, h("a", { class: "proj", href },
      h("span", { class: "proj__titulo" }, pr.titulo),
      h("span", { class: "proj__meta" },
        h("span", {}, data(v ? v.d : pr.ultima)), h("span", {}, resultado), sem && h("span", {}, sem),
        opc.assunto && h("span", {}, opc.assunto),
        incerto && h("span", { class: "selo-aviso" }, tx("Classificação incerta"))),
      placar));
  }

  const descCurta = (t, max) => {
    t = (t || "").replace(/\s+/g, " ");
    max = max || 80;
    if (t.length <= max) return t;
    const c = t.slice(0, max - 1), i = c.lastIndexOf(" ");
    return c.slice(0, i > max / 2 ? i : max - 1) + "…";
  };

  // Resumo, avisos, pontos principais e texto oficial de um projeto.
  function blocosProjeto(pr) {
    const avisos = [];
    if (pr.aa) avisos.push(h("p", {}, pr.aa));
    if (pr.ar) avisos.push(h("p", {}, pr.ar));
    return {
      resumo: pr.resumo
        ? h("div", {}, h("span", { class: "rotulo-ia" }, tx("Resumo feito por inteligência artificial. "), h("a", { href: "#/inteligencia-artificial" }, tx("Como é usada"))), h("p", {}, pr.resumo))
        : h("p", {}, tx("Ainda não há resumo deste projeto. Leia o texto oficial abaixo.")),
      avisos: avisos.length ? h("div", { class: "cartao-aviso" }, h("strong", {}, tx("Atenção")), avisos) : null,
      substitutivo: pr.subst
        ? h("p", { class: "nota-neutra" }, tx("O resumo foi feito a partir da ementa do projeto original. Esta votação foi sobre um substitutivo ou emenda, e o texto votado pode ser diferente."))
        : null,
      pontos: pr.pontos && pr.pontos.length ? h("div", {}, h("h3", {}, tx("Pontos principais")), h("ul", {}, pr.pontos.map((x) => h("li", {}, x)))) : null,
      oficial: h("div", {}, h("h3", {}, tx("Texto oficial ({0})", pr.nome)), h("p", { class: "oficial" }, pr.ementa || (pr.ementa === null ? tx("Não consegui carregar a ementa agora. O texto completo está no site da Câmara.") : tx("Sem ementa."))),
        LANG === "en" && pr.ementa ? h("p", { class: "nota" }, tx("O texto oficial está em português, como foi votado.")) : null,
        soHttps(pr.texto) ? h("p", {}, h("a", { href: soHttps(pr.texto), target: "_blank", rel: "noopener noreferrer" }, tx("Ler o texto completo no site da Câmara"))) : null),
    };
  }

  // O título da página é a primeira frase do resumo; aqui vai só o resto, para não repetir.
  function resumoSemRepetir(pr) {
    if (!pr.resumo) return blocosProjeto(pr).resumo;
    const titulo = tituloCompleto(pr);
    const cortado = titulo.endsWith("…");
    const base = cortado ? titulo.slice(0, -1).trimEnd() : titulo;
    let resto = pr.resumo.startsWith(base) ? pr.resumo.slice(base.length).trim() : pr.resumo;
    if (cortado && resto && pr.resumo.startsWith(base)) resto = "… " + resto;
    return h("div", {}, h("span", { class: "rotulo-ia" }, tx("Título e resumo feitos por inteligência artificial. "), h("a", { href: "#/inteligencia-artificial" }, tx("Como é usada"))), resto ? h("p", {}, resto) : null);
  }

  // ------------------------------------------------------------------ tela inicial
  function destaquesInicio(projetos, vots) {
    const existe = new Set(projetos.map((p) => p.id));
    const nominais = vots.lista.filter((v) => v.t === "nominal" && v.s && existe.has(v.p));
    const unicos = (lista, n) => {
      const vistos = new Set(), saida = [];
      for (const v of lista) { if (vistos.has(v.p)) continue; vistos.add(v.p); saida.push(v); if (saida.length === n) break; }
      return saida;
    };
    const margem = (v) => Math.abs(v.s[0] - v.s[1]) / (v.s[0] + v.s[1]);
    const maisRecente = (a, b) => (a.d < b.d ? 1 : a.d > b.d ? -1 : a.id < b.id ? 1 : -1);
    const recentes = unicos(nominais.slice().sort(maisRecente), 5);
    // As cinco mais apertadas, mostradas da mais recente para a mais antiga.
    const apertadas = unicos(nominais.filter((v) => v.s[0] + v.s[1] >= 100 && margem(v) < 0.15).sort((a, b) => margem(a) - margem(b)), 5).sort(maisRecente);
    return { recentes, apertadas };
  }

  function cartaoTile(a, n, rotulo, q) {
    return h("li", {}, h("a", { class: "tile", style: estiloAssunto(a.slug), href: "#/assunto/" + a.slug + q },
      h("span", { class: "tile__icone" }, icone(a.slug)),
      h("span", { class: "tile__nome" }, a.nome),
      h("span", { class: "tile__desc" }, a.descricao),
      !rotulo && a.n_ind != null
        ? h("span", { class: "tile__num" }, h("b", {}, num(a.n_ind)), tx(" {0} com voto de cada deputado", a.n_ind === 1 ? tx("projeto") : tx("projetos")))
        : h("span", { class: "tile__num" }, h("b", {}, num(n)), ` ${n === 1 ? tx("projeto") : tx("projetos")}${rotulo ? " " + rotulo : ""}`),
      !rotulo && a.n_ind != null ? h("span", { class: "tile__sub" }, tx("{0} no total, contando os de votação simbólica", num(n))) : null));
  }

  async function telaInicio(p) {
    const [assuntos, meta] = await Promise.all([dados("assuntos"), dados("meta")]);
    const nomes = Object.fromEntries(assuntos.map((x) => [x.slug, x.nome]));
    const estado = { q: p.get("q") || "" };
    let limiteBusca = 8;

    // Sugestão no próprio campo: os assuntos com mais projetos na base.
    const TERMO_CURTO = { "impostos-e-economia": tx("impostos"), "trabalho-e-direitos": tx("trabalho"), "seguranca-publica": tx("segurança pública"), "administracao-publica-e-congresso": tx("servidores públicos"), "relacoes-internacionais-e-defesa": tx("acordos internacionais") };
    const sugestoes = assuntos.filter((x) => x.slug !== "outros").sort((x, y) => y.n - x.n).slice(0, 3)
      .map((x) => TERMO_CURTO[x.slug] || x.nome.toLowerCase()).join(", ") + "…";
    const campoBusca = h("input", {
      id: "busca", type: "search", name: "q", autocomplete: "off", spellcheck: "false",
      placeholder: sugestoes, value: estado.q, enterkeyhint: "search",
    });
    const estadoTxt = h("p", { class: "estado so-leitor", role: "status", "aria-live": "polite" });
    const resultados = h("div", {});
    const destaques = h("div", {});
    const principios = h("ul", { class: "principios", "aria-label": tx("O que diferencia o Voto de Verdade") },
      [["p-neutro", tx("Neutro e apartidário"), tx("Sem ligação com partidos, candidatos ou a Câmara.")],
       ["p-sem-nota", tx("Sem nota e sem ranking"), tx("Não dizemos quem votou certo ou errado.")],
       ["p-votado", tx("Só o que foi votado"), tx("O voto de cada deputado, dos dados oficiais.")],
       ["p-sem-rastreio", tx("Sem cookies nem rastreio"), tx("Não usamos ferramentas que rastreiam quem visita.")]]
        .map(([ic, t, d]) => h("li", {}, h("span", { class: "principios__icone" }, icone(ic)), h("strong", {}, t), h("span", { class: "principios__desc" }, d))));

    principal.replaceChildren(
      h("aside", { class: "faixa", "aria-label": tx("Sobre o projeto") }, h("div", { class: "miolo" }, h("p", {},
        h("strong", {}, tx("Versão Beta. ")),
        tx("Site em constante desenvolvimento. Queremos aproximar a sociedade do Congresso, com transparência e visibilidade sobre a atuação parlamentar, de forma simples e prática. "),
        h("a", { href: "#/sobre" }, tx("Ver objetivos"))))),
      h("div", { class: "miolo" },
      h("section", { class: "heroi", "aria-labelledby": "titulo-inicio" },
        h("div", { class: "heroi__topo" },
          h("p", { class: "heroi__data" }, tx("Atualizado em "), h("time", { datetime: meta.gerado_em }, data(meta.gerado_em))),
          h("h1", { id: "titulo-inicio", tabindex: "-1" }, tx("Veja como a Câmara votou, assunto por assunto"))),
        h("div", { class: "heroi__lado" },
          h("p", { class: "heroi__texto" }, tx("Escolha um tema e leia o que foi votado, com o voto de cada deputado federal.")),
          h("form", { class: "heroi__busca", role: "search", "aria-label": tx("Procurar assunto ou projeto"), onsubmit: (e) => e.preventDefault() },
            h("label", { for: "busca", class: "so-leitor" }, tx("Procure por um tema ou palavra")), campoBusca),
          h("p", { class: "heroi__link" }, tx("Já sabe quem? "), h("a", { href: "#/deputados" }, tx("Procure um deputado pelo nome")), tx(". Ou veja "), h("a", { href: "#/em-numeros" }, tx("os números das votações")), "."))),
      principios, estadoTxt, resultados, destaques,
      h("p", { class: "confianca" },
        tx("Dados oficiais da Câmara dos Deputados, de {0} a {1}. Assunto e resumo são feitos por inteligência artificial e podem errar; avisamos quando há dúvida. ", data(meta.de), data(meta.ate)),
        h("a", { href: "#/sobre" }, tx("Como o site funciona")), " · ", h("a", { href: "#/inteligencia-artificial" }, tx("Transparência da IA")))));
    document.title = tx("Voto de Verdade: como a Câmara dos Deputados votou");

    let versao = 0;
    async function atualizar(reiniciar) {
      if (reiniciar) limiteBusca = 8;
      const minha = ++versao;
      estado.q = campoBusca.value.trim();
      gravarEndereco("", limparParams({ q: estado.q }));
      const ts = termos(estado.q);
      const porNome = (x, y) => (x.slug === "outros") - (y.slug === "outros") || x.nome.localeCompare(y.nome, LOCALE);

      if (!ts.length) {
        const dica = estado.q.length === 1 ? h("p", { class: "nota" }, tx("Escreva pelo menos duas letras para buscar.")) : null;
        resultados.replaceChildren(...[dica, h("section", { class: "secao", "aria-labelledby": "t-assuntos" },
          h("h2", { id: "t-assuntos" }, tx("Assuntos")),
          h("ul", { class: "tiles" }, assuntos.slice().sort(porNome).map((a) => cartaoTile(a, a.n, null, ""))))].filter(Boolean));
        destaques.hidden = false; principios.hidden = false;
        anunciar(estadoTxt, "");
        return;
      }

      destaques.hidden = true; principios.hidden = true;
      anunciar(estadoTxt, tx("Procurando…"));
      let todos, vots;
      try { [todos, vots] = await Promise.all([projetosComTexto(), indiceVotacoes()]); } catch (e) {
        resultados.replaceChildren(estadoVazio({ icone: "v-erro", titulo: tx("Não foi possível carregar a busca"), texto: tx("Verifique sua conexão e tente de novo."), acoes: [{ rotulo: tx("Tentar de novo"), onclick: () => atualizar(true) }] }));
        return;
      }
      if (minha !== versao) return;

      const achados = todos.filter((pr) => casa(pr._t, ts)).sort((x, y) => (Number(y.ind) - Number(x.ind)) || (y.ultima > x.ultima ? 1 : y.ultima < x.ultima ? -1 : y.id - x.id));
      const contagem = {};
      for (const pr of achados) { contagem[pr.a] = (contagem[pr.a] || 0) + 1; if (pr.s) contagem[pr.s] = (contagem[pr.s] || 0) + 1; }
      const q = "?q=" + encodeURIComponent(estado.q);
      const tiles = assuntos
        .filter((a) => contagem[a.slug] || casa(semAcento(a.nome + " " + a.descricao), ts))
        .sort((x, y) => (contagem[y.slug] || 0) - (contagem[x.slug] || 0) || porNome(x, y));

      const blocos = [];
      if (achados.length) {
        const mostrados = achados.slice(0, limiteBusca);
        blocos.push(h("section", { class: "secao", "aria-labelledby": "t-projetos" },
          h("h2", { id: "t-projetos" }, tx("Projetos"), h("small", {}, tx("{0} com “{1}”", num(achados.length), estado.q))),
          h("p", { class: "secao__intro" }, tx("Os que têm o voto de cada deputado aparecem primeiro.")),
          h("ul", { class: "projetos" }, mostrados.map((pr) => linhaProjeto(pr, vots, { assunto: nomes[pr.a] }))),
          achados.length > mostrados.length
            ? h("div", { class: "mais" }, h("button", { type: "button", class: "botao botao--leve", onclick: () => { limiteBusca += 10; atualizar(false); } },
                tx("Mostrar mais {0} projetos", Math.min(10, achados.length - mostrados.length))))
            : null));
      }
      if (tiles.length) {
        blocos.push(h("section", { class: "secao", "aria-labelledby": "t-assuntos" },
          h("h2", { id: "t-assuntos" }, tx("Assuntos")),
          h("ul", { class: "tiles" }, tiles.map((a) => contagem[a.slug] ? cartaoTile(a, contagem[a.slug], tx("com “{0}”", estado.q), q) : cartaoTile(a, a.n, null, "")))));
      }
      if (!blocos.length) {
        blocos.push(estadoVazio({
          icone: "v-busca", titulo: tx("Nada encontrado com “{0}”", estado.q),
          texto: tx("A busca olha o título, o resumo e o assunto dos projetos votados. Tente uma palavra mais simples, como “saúde”, “imposto” ou “escola”. Para achar um deputado, procure pelo nome na lista de deputados."),
          acoes: [
            { rotulo: tx("Limpar a busca"), onclick: () => { campoBusca.value = ""; atualizar(true); campoBusca.focus(); } },
            { rotulo: tx("Procurar um deputado"), href: "#/deputados" }] }));
      }
      resultados.replaceChildren(...blocos);
      anunciar(estadoTxt, achados.length ? tx("{0} com “{1}”", plural(achados.length, tx("projeto"), tx("projetos")), estado.q) : tx("Nada encontrado com “{0}”.", estado.q));
    }
    comEspera(campoBusca, () => atualizar(true));
    await atualizar(true);

    // Últimas votações e votações apertadas: chegam depois, sem atrasar o resto.
    (async () => {
      try {
        const [projetos, vots] = await Promise.all([projetosComTexto(), indiceVotacoes()]);
        const porId = Object.fromEntries(projetos.map((x) => [x.id, x]));
        const { recentes, apertadas } = destaquesInicio(projetos, vots);
        if (!recentes.length) return;
        const lista = (vs) => h("ul", { class: "projetos lista-home" }, vs.map((v) => linhaProjeto(porId[v.p], vots, { votacao: v })));
        destaques.replaceChildren(h("div", { class: "duas-colunas" },
          h("section", { class: "secao", "aria-labelledby": "t-recentes" },
            h("h2", { id: "t-recentes" }, tx("Últimas votações")),
            h("p", { class: "secao__intro" }, tx("As mais recentes em que cada deputado votou.")),
            lista(recentes)),
          apertadas.length
            ? h("section", { class: "secao", "aria-labelledby": "t-apertadas" },
                h("h2", { id: "t-apertadas" }, tx("Decididas por pouco")),
                h("p", { class: "secao__intro" }, tx("Votações em que sim e não ficaram a menos de 15% de diferença.")),
                lista(apertadas))
            : null));
      } catch (e) { console.error(e); }
    })();
    return document.getElementById("titulo-inicio");
  }

  // ------------------------------------------------------------------ exportar (CSV e JSON)
  // Cada bloco com números oferece os mesmos dados da tabela em CSV (abre em planilha) e em JSON.
  const FONTE_DADOS = tx("Voto de Verdade (votodeverdade.com.br), a partir dos Dados Abertos da Câmara dos Deputados");
  const csvCelula = (v) => {
    let t = v === null || v === undefined ? "" : String(v);
    if (typeof v === "string" && /^[=+\-@\t\r]/.test(t)) t = "'" + t; // planilhas tratariam o texto como fórmula
    return /[",;\r\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t;
  };
  const paraCsv = (colunas, registros) => "\uFEFF" + [colunas.map((c) => csvCelula(c[1])).join(",")]
    .concat(registros.map((r) => colunas.map((c) => csvCelula(r[c[0]])).join(","))).join("\r\n") + "\r\n";
  function baixarArquivo(nome, texto, tipo) {
    const url = URL.createObjectURL(new Blob([texto], { type: tipo }));
    const a = h("a", { href: url, download: nome });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }
  // pegar() devolve { titulo, colunas: [[chave, rótulo]...], registros, filtros, gerado_em } no momento do clique (vale o filtro que está na tela).
  function botoesExportar(arquivo, pegar, sobre) {
    const exportar = (formato) => {
      const d = pegar();
      const base = `voto-de-verdade-${arquivo}` + (d.filtros && d.filtros.ano ? "-" + d.filtros.ano : "");
      if (formato === "csv") baixarArquivo(base + ".csv", paraCsv(d.colunas, d.registros), "text/csv;charset=utf-8");
      else baixarArquivo(base + ".json", JSON.stringify({ titulo: d.titulo, fonte: FONTE_DADOS, licenca: tx("CC BY 4.0: cite o Voto de Verdade"), gerado_em: d.gerado_em, filtros: d.filtros || {}, ...(LANG === "pt" ? {} : { campos: Object.fromEntries(d.colunas.map((c) => [c[0], c[1]])) }), dados: d.registros }, null, 2) + "\n", "application/json");
    };
    const botao = (formato, rotulo) => h("button", { type: "button", class: "exportar__botao", onclick: () => exportar(formato) },
      h("span", { class: "so-leitor" }, tx("Baixar ")), rotulo, sobre ? h("span", { class: "so-leitor" }, " " + sobre) : null);
    return h("span", { class: "exportar", role: "group", "aria-label": tx("Baixar estes números") },
      h("span", { class: "exportar__rotulo", "aria-hidden": "true" }, tx("Baixar")), botao("csv", "CSV"), botao("json", "JSON"));
  }

  // ------------------------------------------------------------------ painel
  // Só descreve: conta votações. Não ordena pessoas, não dá nota e não compara partidos.
  const MES = new Intl.DateTimeFormat(LOCALE, { month: "long", year: "numeric" });
  const mesPorExtenso = (m) => MES.format(new Date(m + "-15T12:00:00"));
  const MES_CURTO = new Intl.DateTimeFormat(LOCALE, { month: "short" });
  const pct1 = (a, b) => (b ? (100 * a / b).toLocaleString(LOCALE, { maximumFractionDigits: 1 }) : "0") + "%";
  const rotuloVotacoes = (n) => plural(n, tx("votação"), tx("votações"));

  const ROTULOS_TIPO = { nominal: tx("Nominais"), simbolica: tx("Simbólicas"), secreta: tx("Secretas") };
  const NOME_MODELO = { "claude-sonnet-5-5": "Claude Sonnet 5.5", "claude-haiku-4-5-20251001": "Claude Haiku 4.5" };
  const nomeModelo = (id) => NOME_MODELO[id] || id || "";
  const VOTOS_PLACAR = [["S", "sim", tx("Sim")], ["N", "nao", tx("Não")], ["A", "abstencao", tx("Abstenção")], ["O", "obstrucao", tx("Obstrução")]];
  // Diferença entre sim e não, dividida pelo total de sim e não (o mesmo corte de 15% da home, em «Decididas por pouco»).
  const FAIXAS_PLACAR = [
    ["sem_contra", tx("Sem voto contrário"), tx("só houve votos de um lado")],
    ["ampla", tx("Ampla"), tx("diferença de 50% ou mais")],
    ["maioria", tx("Maioria"), tx("diferença de 15% a 50%")],
    ["apertada", tx("Apertada"), tx("diferença de menos de 15%")],
  ];
  const NIVEIS_IA = [["alta", tx("Alta")], ["media", tx("Média")], ["baixa", tx("Baixa")]];
  const somaDe = (obj, chaves) => chaves.reduce((a, k) => a + (obj[k] || 0), 0);
  const pctNum = (a, b) => (b ? Math.round((1000 * a) / b) / 10 : 0);
  const fmtPct = (v) => v.toLocaleString(LOCALE, { maximumFractionDigits: 1 }) + "%";
  // Os números do período inteiro ou de um ano: o que a tela mostra e o que as tabelas e os arquivos baixados trazem.
  const visao = (pn, ano) => (ano && pn.por_ano && pn.por_ano[ano] ? Object.assign({}, pn, pn.por_ano[ano]) : pn);

  const AVISOS_IA = (ia) => [
    ["assunto_pode_estar_errado", tx("Projetos com aviso de que o assunto pode estar errado"), ia.aviso_assunto, [tx("projeto"), tx("projetos")], tx("com aviso de que o assunto pode estar errado.")],
    ["resumo_pode_ter_erros", tx("Projetos com aviso de que o resumo pode conter erros"), ia.aviso_resumo, [tx("projeto"), tx("projetos")], tx("com aviso de que o resumo pode conter erros.")],
    ia.so_ementa ? ["sem_resumo", tx("Projetos sem resumo da inteligência artificial (a tela mostra só a ementa)"), ia.so_ementa, [tx("projeto"), tx("projetos")], tx("sem resumo da inteligência artificial, porque ela não conseguiu resumir ou a conferência não achou apoio no texto. A tela mostra só a ementa.")] : null,
    ["texto_pode_diferir", tx("Projetos cuja votação foi sobre substitutivo ou emenda (o texto votado pode ser diferente da ementa)"), ia.texto_pode_diferir, [tx("projeto"), tx("projetos")], tx("cuja votação foi sobre um substitutivo ou emenda: o texto votado pode ser diferente da ementa.")],
    ia.votacao_aviso ? ["classificacao_automatica", tx("Votações com aviso de que a classificação foi feita automaticamente e pode estar errada"), ia.votacao_aviso, [tx("votação"), tx("votações")], tx("com aviso de que a classificação foi feita automaticamente e pode estar errada.")] : null,
  ].filter(Boolean);
  const FUNCOES_IA = [tx("Escolhe o assunto de cada projeto."), tx("Escreve o título e o resumo em linguagem simples e lista os pontos principais."), tx("Diz quanto tem de certeza e avisa quando tem dúvida.")];
  const LIMITES_IA = [tx("A inteligência artificial pode errar, mesmo quando diz ter certeza."), tx("O texto oficial de cada projeto fica sempre ao lado do resumo. Em caso de dúvida, vale o texto oficial."), tx("Por enquanto o site não tem um canal para pedir correções.")];
  // m1 e m2: « (nome do modelo)» já formatado, ou vazio.
  const PASSOS_IA = (ia, m1, m2) => [
    [tx("Escolha do assunto e resumo"), ia.modelo, tx("Um modelo{0} lê o texto oficial do projeto, escolhe o assunto, escreve o resumo e diz quanto tem de certeza.", m1)],
    [tx("Segunda leitura do assunto"), ia.conferencia, tx("Um segundo modelo{0} escolhe o assunto sem ver a resposta do primeiro. Se os dois discordam, a confiança no assunto cai.", m2)],
    [tx("Checagem por palavras"), "", tx("Uma checagem por palavras da ementa confere se o assunto faz sentido.")],
    [tx("Conferência do resumo"), ia.conferencia, tx("O segundo modelo{0} confere o resumo contra o texto original. Se achar partes sem apoio no texto, o projeto mostra um aviso. Se o resumo não se sustenta, ele é descartado e a tela mostra só a ementa.", m2)],
  ];


  // Cada bloco tem a sua tabela numa página própria (#/em-numeros/<id> ou #/inteligencia-artificial/<id>).
  // colunas: [chave, rótulo, formatador opcional (valor, registro)]; registros(visao) traz os valores puros (os que vão para o CSV e o JSON).
  const TABELAS_NUMEROS = {
    "por-mes": {
      titulo: tx("Votações por mês"),
      colunas: [["mes", tx("Mês"), mesPorExtenso], ["nominais", tx("Nominais")], ["simbolicas", tx("Simbólicas")], ["secretas", tx("Secretas")]],
      registros: (v) => v.meses.map((m) => ({ mes: m.m, nominais: m.n, simbolicas: m.s, secretas: m.x })),
    },
    "por-assunto": {
      titulo: tx("Votações por assunto"),
      colunas: [["assunto", tx("Assunto")], ["nominais", tx("Nominais")], ["simbolicas", tx("Simbólicas")], ["secretas", tx("Secretas")], ["total", tx("Total")]],
      registros: (v) => v.assuntos.map((a) => ({ assunto: a.nome, nominais: a.n, simbolicas: a.s, secretas: a.x, total: a.n + a.s + a.x })),
    },
    "resultado": {
      titulo: tx("Resultado por tipo de votação"),
      colunas: [["tipo", tx("Tipo"), (k) => ROTULOS_TIPO[k] || k], ["aprovadas", tx("Aprovadas")], ["rejeitadas", tx("Rejeitadas")], ["total", tx("Total")]],
      registros: (v) => ["nominal", "simbolica", "secreta"].map((k) => { const r = v.resultado[k] || { aprovadas: 0, rejeitadas: 0 }; return { tipo: k, aprovadas: r.aprovadas, rejeitadas: r.rejeitadas, total: r.aprovadas + r.rejeitadas }; }),
    },
    "participacao": {
      titulo: tx("Deputados que votaram, por mês"),
      colunas: [["mes", tx("Mês"), mesPorExtenso], ["votacoes_nominais", tx("Votações nominais")], ["deputados_que_votaram_media", tx("Deputados que votaram (média)"), (x) => (x === null ? tx("sem votação nominal") : num(x))]],
      registros: (v) => v.participacao.meses.map((m) => ({ mes: m.m, votacoes_nominais: m.n, deputados_que_votaram_media: m.n ? m.v : null })),
    },
    "placar-votos": {
      titulo: tx("Votos nas votações nominais"),
      colunas: [["voto", tx("Voto")], ["total", tx("Total")], ["percentual", tx("Parte do total"), fmtPct]],
      registros: (v) => { const soma = somaDe(v.placar.votos, VOTOS_PLACAR.map((x) => x[0])); return VOTOS_PLACAR.map(([c, , nome]) => ({ voto: nome, total: v.placar.votos[c], percentual: pctNum(v.placar.votos[c], soma) })); },
    },
    "placar-margem": {
      titulo: tx("Votações nominais por tamanho da diferença"),
      colunas: [["faixa", tx("Faixa")], ["como_e_medida", tx("Como é medida")], ["votacoes", tx("Votações")], ["percentual", tx("Parte das nominais"), fmtPct]],
      registros: (v) => FAIXAS_PLACAR.map(([k, nome, det]) => ({ faixa: nome, como_e_medida: det, votacoes: v.placar.margem[k], percentual: pctNum(v.placar.margem[k], v.placar.nominais) })),
    },
    "confianca": {
      pai: "ia", titulo: tx("Confiança da inteligência artificial"),
      colunas: [["confianca", tx("Confiança")], ["assunto", tx("Assunto")], ["resumo", tx("Resumo")]],
      registros: (v) => NIVEIS_IA.map(([k, nome]) => ({ confianca: nome, assunto: v.ia.assunto[k], resumo: v.ia.resumo[k] })),
      nota: (pn) => tx("Os mesmos números do gráfico, dos {0} projetos do site. Atualizado em {1}.", num(pn.ia.projetos), data(pn.gerado_em)),
    },
  };
  // De qual tela cada tabela faz parte: o endereço e o «Voltar para» seguem daí.
  const PAIS_TABELA = { numeros: { nome: tx("Em números"), rota: "#/em-numeros" }, ia: { nome: tx("Transparência da IA"), rota: "#/inteligencia-artificial" } };
  const paiDaTabela = (id) => PAIS_TABELA[(TABELAS_NUMEROS[id] || {}).pai || "numeros"];
  const consultaAno = (ano) => (ano ? "?ano=" + ano : "");

  // Link «Ver como tabela» e os botões de baixar CSV e JSON do bloco. v é a visão (o ano escolhido), pn o painel inteiro.
  function acoesDoBloco(id, sobre, pn, v, ano) {
    const def = TABELAS_NUMEROS[id];
    const doIa = def.pai === "ia";
    const link = def.semPagina ? null : h("a", { href: paiDaTabela(id).rota + "/" + id + (doIa ? "" : consultaAno(ano)) }, tx("Ver como tabela"), sobre ? h("span", { class: "so-leitor" }, " " + sobre) : null);
    const exportar = botoesExportar(id, () => ({
      titulo: def.titulo, colunas: def.colunas, registros: def.registros(v), gerado_em: pn.gerado_em, filtros: ano && !doIa ? { ano: Number(ano) } : {},
    }), sobre);
    return h("p", { class: "numeros__acoes" }, link, exportar);
  }

  async function telaTabelaNumeros(id, pai, p) {
    const def = Object.prototype.hasOwnProperty.call(TABELAS_NUMEROS, id) ? TABELAS_NUMEROS[id] : null;
    if (!def || def.semPagina || (def.pai || "numeros") !== pai) return telaNaoEncontrada();
    const mae = PAIS_TABELA[pai];
    const pn = await dados("painel");
    const ano = pai === "numeros" && p && pn.anos && pn.anos.includes(p.get("ano")) ? p.get("ano") : "";
    const v = visao(pn, ano);
    const nota = def.nota ? def.nota(pn) : ano
      ? tx("Os mesmos números do gráfico, de {0}, de {1} a {2}. Atualizado em {3}.", ano, data(v.de), data(v.ate), data(pn.gerado_em))
      : tx("Os mesmos números do gráfico, de {0} a {1}. Atualizado em {2}.", data(v.de), data(v.ate), data(pn.gerado_em));
    const fmt = (c, r) => (c[2] ? c[2](r[c[0]], r) : typeof r[c[0]] === "number" ? num(r[c[0]]) : r[c[0]]);
    principal.replaceChildren(h("div", { class: "miolo numeros" },
      h("nav", { class: "migalhas", "aria-label": tx("Você está em") }, h("ol", {},
        h("li", {}, h("a", { href: "#/" }, tx("Início"))), h("li", {}, h("a", { href: mae.rota + consultaAno(ano) }, mae.nome)), h("li", { "aria-current": "page" }, def.titulo))),
      h("h1", { id: "titulo-painel", tabindex: "-1" }, def.titulo),
      h("p", { class: "numeros__nota" }, nota),
      h("div", { class: "numeros__bloco" },
        h("div", { class: "tabela-rolavel" },
          h("table", { class: "tabela-painel" },
            h("caption", { class: "so-leitor" }, def.titulo),
            h("thead", {}, h("tr", {}, def.colunas.map((c, k) => h("th", { scope: "col", class: k && typeof def.registros(v)[0][c[0]] === "number" ? "num" : null }, c[1])))),
            h("tbody", {}, def.registros(v).map((r) => h("tr", {}, def.colunas.map((c, k) => (k ? h("td", { class: typeof r[c[0]] === "number" || r[c[0]] === null && k ? "num" : null }, fmt(c, r)) : h("th", { scope: "row" }, fmt(c, r))))))))),
        h("p", { class: "numeros__acoes" }, h("a", { href: mae.rota + consultaAno(ano) }, tx("Voltar para {0}", mae.nome)), botoesExportar(id, () => ({ titulo: def.titulo, colunas: def.colunas, registros: def.registros(v), gerado_em: pn.gerado_em, filtros: ano ? { ano: Number(ano) } : {} }))))));
    document.title = tx("{0}: tabela | Voto de Verdade", def.titulo);
    return document.getElementById("titulo-painel");
  }

  const legendaDoPainel = (itens) => h("ul", { class: "pn-legenda", "aria-label": tx("Legenda") },
    itens.map(([cor, texto]) => h("li", {}, h("span", { class: "pn-chip pn-chip--" + cor, "aria-hidden": "true" }), texto)));

  const dicaVotacoes = (m) => [
    h("span", {}, h("span", { class: "pn-chip pn-chip--nominal", "aria-hidden": "true" }), tx("Nominais: {0}", num(m.n))),
    h("span", {}, h("span", { class: "pn-chip pn-chip--simbolica", "aria-hidden": "true" }), tx("Simbólicas: {0}", num(m.s))),
    m.x ? h("span", {}, tx("Secretas: {0}", num(m.x))) : null,
  ];

  // opc: series ([[campo, textura]...]), topo e passo do eixo (opcionais), aria (o que o gráfico mostra) e dica (linhas do balão de cada mês).
  function graficoMeses(meses, opc) {
    const o = Object.assign({ series: [["n", "nominal"], ["s", "simbolica"], ["x", "secreta"]], dica: dicaVotacoes, aria: tx("o número de votações nominais e simbólicas em cada mês") }, opc || {});
    const maior = Math.max(1, ...meses.map((m) => o.series.reduce((a, [k]) => a + m[k], 0)));
    const passo = o.passo || (maior <= 30 ? 10 : maior <= 80 ? 20 : 50);
    const topo = o.topo || Math.ceil(maior / passo) * passo;
    const marcas = [];
    for (let v = topo; v >= 0; v -= passo) marcas.push(v);

    const dica = h("div", { class: "pn-dica", role: "presentation", hidden: true });
    const colunas = h("div", { class: "pn-colunas" });
    colunas.style.setProperty("--n", meses.length);
    colunas.style.setProperty("--topo", topo);
    const eixoX = h("div", { class: "pn-eixo-x", "aria-hidden": "true" });
    eixoX.style.setProperty("--n", meses.length);
    meses.forEach((m, i) => {
      const col = h("div", { class: "pn-col" });
      for (const [k, cls] of o.series) {
        if (!m[k]) continue;
        const seg = h("span", { class: "pn-seg pn-seg--" + cls });
        seg.style.setProperty("--v", m[k]);
        col.append(seg);
      }
      const mostrar = () => {
        dica.replaceChildren(h("strong", {}, mesPorExtenso(m.m)), ...o.dica(m));
        dica.hidden = false;
        const area = colunas.getBoundingClientRect();
        const c = col.getBoundingClientRect();
        const largura = dica.offsetWidth;
        const centro = c.left - area.left + c.width / 2;
        dica.style.left = Math.max(0, Math.min(area.width - largura, centro - largura / 2)) + "px";
      };
      col.addEventListener("pointerenter", mostrar);
      col.addEventListener("pointerdown", mostrar);
      colunas.append(col);
      // O ano aparece no primeiro mês do período e a cada janeiro (ou no primeiro mês de cada ano com votações).
      const primeiroDoAno = i === 0 || m.m.slice(0, 4) !== meses[i - 1].m.slice(0, 4);
      // Com até 12 meses (um ano só), cada coluna leva o nome do mês; com mais, só o ano no primeiro mês de cada ano.
      if (meses.length <= 12) {
        const nome = MES_CURTO.format(new Date(m.m + "-15T12:00:00")).replace(".", "");
        eixoX.append(h("span", { class: "pn-rotulo-x pn-rotulo-x--mes" }, h("span", { class: "pn-mes-longo" }, nome), h("span", { class: "pn-mes-curto", "aria-hidden": "true" }, nome.charAt(0).toUpperCase())));
      } else eixoX.append(h("span", { class: "pn-rotulo-x" }, primeiroDoAno ? m.m.slice(0, 4) : ""));
    });
    colunas.addEventListener("pointerleave", () => { dica.hidden = true; });
    document.addEventListener("pointerdown", (e) => { if (!colunas.contains(e.target)) dica.hidden = true; });

    return h("div", { class: "pn-grafico", role: "img",
      "aria-label": tx("Gráfico de colunas com {0}, de {1} a {2}. Os mesmos números estão numa tabela, no link abaixo do gráfico.", o.aria, mesPorExtenso(meses[0].m), mesPorExtenso(meses[meses.length - 1].m)) },
      h("div", { class: "pn-eixo-y", "aria-hidden": "true" }, marcas.map((v) => h("span", {}, num(v)))),
      h("div", { class: "pn-area" },
        h("div", { class: "pn-grades", "aria-hidden": "true" }, marcas.map(() => h("span", {}))),
        colunas, dica),
      h("span", {}), eixoX);
  }

  function linhaBarras(nome, partes, total, maximo, cls) {
    const trilho = h("div", { class: "pn-trilho" });
    const barra = h("div", { class: "pn-barra" });
    barra.style.setProperty("--t", total);
    barra.style.setProperty("--max", maximo);
    for (const [valor, tipo] of partes) {
      if (!valor) continue;
      const seg = h("span", { class: "pn-seg pn-seg--" + tipo });
      seg.style.setProperty("--v", valor);
      barra.append(seg);
    }
    trilho.append(barra);
    return h("li", { class: "pn-linha" + (cls ? " " + cls : "") }, h("span", { class: "pn-nome" }, nome), trilho);
  }

  async function telaPainel(p) {
    const pn = await dados("painel");
    let ano = pn.anos && pn.anos.includes(p && p.get("ano")) ? p.get("ano") : "";
    const rotulos = ROTULOS_TIPO;

    const seletorAno = h("select", { id: "ano-n", "aria-controls": "numeros-area" },
      h("option", { value: "" }, tx("Todos os anos")), ...(pn.anos || []).map((a) => h("option", { value: a }, a)));
    seletorAno.value = ano;
    const area = h("div", { class: "numeros__area", id: "numeros-area" });

    function desenhar() {
      const v = visao(pn, ano);
      const t = v.totais;
      const pa = v.participacao, pl = v.placar;
      const maiorAssunto = Math.max(1, ...v.assuntos.map((a) => a.n + a.s + a.x));

      const blocoMeses = h("section", { class: "numeros__bloco", "aria-labelledby": "pn-t1" },
        h("h2", { id: "pn-t1" }, tx("Votações nominais e simbólicas ao longo do tempo")),
        h("p", { class: "numeros__nota" }, tx("Na votação nominal, o voto de cada deputado fica registrado. Na simbólica, só o resultado. Meses sem votação (recesso, eleições) aparecem vazios.")),
        legendaDoPainel([["nominal", tx("Nominais")], ["simbolica", tx("Simbólicas")]]),
        graficoMeses(v.meses),
        t.secretas ? h("p", { class: "numeros__nota" }, tx("Há também {0}, mostrada na tabela.", plural(t.secretas, tx("votação secreta"), tx("votações secretas")))) : null,
        acoesDoBloco("por-mes", tx("das votações por mês"), pn, v, ano));

      const blocoAssuntos = h("section", { class: "numeros__bloco", "aria-labelledby": "pn-t2" },
        h("h2", { id: "pn-t2" }, tx("Votações por assunto")),
        h("p", { class: "numeros__nota" }, tx("Cada votação conta uma vez, no assunto principal do projeto. Os assuntos são escolhidos por inteligência artificial e seguem sempre a mesma ordem, não a do tamanho.")),
        legendaDoPainel([["nominal", tx("Nominais")], ["simbolica", tx("Simbólicas")]]),
        h("ul", { class: "pn-linhas", "aria-label": tx("Votações por assunto") }, v.assuntos.map((a) => {
          const total = a.n + a.s + a.x;
          const li = linhaBarras(a.nome, [[a.n, "nominal"], [a.s, "simbolica"], [a.x, "secreta"]], total, maiorAssunto);
          li.append(h("span", { class: "pn-total" }, num(total), h("span", { class: "so-leitor" }, tx(" votações: {0} nominais e {1} simbólicas", num(a.n), num(a.s)))));
          return li;
        })),
        acoesDoBloco("por-assunto", tx("das votações por assunto"), pn, v, ano));

      const blocoResultado = h("section", { class: "numeros__bloco", "aria-labelledby": "pn-t3" },
        h("h2", { id: "pn-t3" }, tx("Resultado das votações")),
        h("p", { class: "numeros__nota" }, tx("Cada votação termina aprovada ou rejeitada pelo plenário. Aprovar uma votação não quer dizer, sozinho, que o projeto virou lei.")),
        h("p", { class: "numeros__nota" }, tx("Nas votações simbólicas ({0} do total), os partidos chegam a um acordo antes e o resultado é apenas anunciado. Por isso a grande maioria das votações aparece como aprovada.", pct1(t.simbolicas, t.votacoes))),
        legendaDoPainel([["aprovada", tx("Aprovadas")], ["rejeitada", tx("Rejeitadas")]]),
        h("ul", { class: "pn-linhas pn-linhas--resultado", "aria-label": tx("Resultado por tipo de votação") },
          ["nominal", "simbolica", "secreta"].filter((k) => v.resultado[k] && v.resultado[k].aprovadas + v.resultado[k].rejeitadas > 0).map((k) => {
            const r = v.resultado[k];
            const total = r.aprovadas + r.rejeitadas;
            const li = linhaBarras(rotulos[k], [[r.aprovadas, "aprovada"], [r.rejeitadas, "rejeitada"]], total, total);
            li.append(h("span", { class: "pn-total" }, tx("{0} aprovadas ({1}) · {2} rejeitadas ({3})", num(r.aprovadas), pct1(r.aprovadas, total), num(r.rejeitadas), pct1(r.rejeitadas, total))));
            return li;
          })),
        acoesDoBloco("resultado", tx("do resultado das votações"), pn, v, ano));

      const blocoParticipacao = pa && pa.votacoes ? h("section", { class: "numeros__bloco", "aria-labelledby": "pn-t4" },
        h("h2", { id: "pn-t4" }, tx("Quantos deputados votaram")),
        h("p", { class: "numeros__nota" }, tx("Só nas votações nominais, que registram o voto de cada deputado. A Câmara tem {0} deputados e, em média, {1} registraram voto em cada votação nominal (de {2} a {3}). O site não sabe o motivo de quem não aparece (falta, licença ou outro). Aqui entra só o total de cada votação, nunca quem faltou.", num(pa.cadeiras), num(pa.media), num(pa.minimo), num(pa.maximo))),
        legendaDoPainel([["nominal", tx("Deputados que votaram (média do mês)")]]),
        graficoMeses(pa.meses, {
          series: [["v", "nominal"]], topo: 600, passo: 100, aria: tx("a média de deputados que votaram nas votações nominais de cada mês"),
          dica: (m) => (m.n ? [
            h("span", {}, tx("Votações nominais: {0}", num(m.n))),
            h("span", {}, h("span", { class: "pn-chip pn-chip--nominal", "aria-hidden": "true" }), tx("Votaram, em média: {0}", num(m.v)))] : [h("span", {}, tx("Sem votação nominal"))]),
        }),
        acoesDoBloco("participacao", tx("da participação por mês"), pn, v, ano)) : null;

      const somaVotos = pl && pl.votos ? somaDe(pl.votos, VOTOS_PLACAR.map((x) => x[0])) : 0;
      const maiorFaixa = pl && pl.margem ? Math.max(1, ...FAIXAS_PLACAR.map(([k]) => pl.margem[k])) : 1;
      const linhaPlacar = () => {
        const li = linhaBarras(tx("Todas as votações nominais"), VOTOS_PLACAR.map(([c, cls]) => [pl.votos[c], cls]), somaVotos, somaVotos);
        li.append(h("span", { class: "pn-total" }, VOTOS_PLACAR.map(([c, , nome]) => `${nome}: ${num(pl.votos[c])} (${pct1(pl.votos[c], somaVotos)})`).join(" · ")));
        return li;
      };
      const blocoPlacar = pl && pl.nominais ? h("section", { class: "numeros__bloco", "aria-labelledby": "pn-t5" },
        h("h2", { id: "pn-t5" }, tx("Placar das votações nominais")),
        h("p", { class: "numeros__nota" }, tx("Somando todas as votações nominais, quantos votos foram sim, não, abstenção ou obstrução. Votar sim ou não não diz, sozinho, se o deputado apoia o assunto do projeto: muitas votações são sobre emendas, substitutivos ou pontos separados do texto.")),
        legendaDoPainel(VOTOS_PLACAR.map(([, cls, nome]) => [cls, nome])),
        h("ul", { class: "pn-linhas pn-linhas--resultado", "aria-label": tx("Votos nas votações nominais") }, linhaPlacar()),
        acoesDoBloco("placar-votos", tx("dos votos"), pn, v, ano),
        h("h3", {}, tx("Votações decididas por pouco ou por muito")),
        h("p", { class: "numeros__nota" }, tx("A diferença é a distância entre sim e não, dividida pelo total de sim e não. Cada uma das {0} votações nominais cai em uma faixa.", num(pl.nominais))),
        h("ul", { class: "pn-linhas", "aria-label": tx("Votações nominais por diferença entre sim e não") }, FAIXAS_PLACAR.map(([k, nome, det]) => {
          const li = linhaBarras(h("span", {}, nome, h("span", { class: "pn-detalhe" }, det)), [[pl.margem[k], "faixa"]], pl.margem[k], maiorFaixa);
          li.append(h("span", { class: "pn-total" }, num(pl.margem[k]), h("span", { class: "so-leitor" }, tx(" votações ({0})", pct1(pl.margem[k], pl.nominais)))));
          return li;
        })),
        acoesDoBloco("placar-margem", tx("da diferença entre sim e não"), pn, v, ano)) : null;

      area.replaceChildren(
        h("p", { class: "numeros__lead" },
          tx("{0} em plenário, de {1} a {2}: {3} nominais, {4} simbólicas", rotuloVotacoes(t.votacoes), data(v.de), data(v.ate), num(t.nominais), num(t.simbolicas)) + (t.secretas ? tx(" e {0} secreta.", num(t.secretas)) : ".")),
        h("p", { class: "numeros__nota" }, tx("Atualizado em {0}. Esta página só conta e descreve: não dá nota nem compara deputados ou partidos. ", data(pn.gerado_em)), h("a", { href: "#/sobre" }, tx("Como o site funciona"))),
        blocoMeses, blocoAssuntos, blocoResultado, blocoParticipacao, blocoPlacar);
      gravarEndereco("em-numeros", limparParams({ ano }));
    }

    seletorAno.addEventListener("change", () => { ano = seletorAno.value; desenhar(); });
    principal.replaceChildren(h("div", { class: "miolo numeros" },
      h("nav", { class: "migalhas", "aria-label": tx("Você está em") }, h("ol", {}, h("li", {}, h("a", { href: "#/" }, tx("Início"))), h("li", { "aria-current": "page" }, tx("Em números")))),
      h("h1", { id: "titulo-painel", tabindex: "-1" }, tx("Em números")),
      pn.anos && pn.anos.length > 1 ? h("div", { class: "campo numeros__filtro" }, h("label", { for: "ano-n" }, tx("Ano")), seletorAno) : null,
      area));
    desenhar();
    document.title = tx("Em números: votações da Câmara ao longo do tempo | Voto de Verdade");
    return document.getElementById("titulo-painel");
  }

  // ------------------------------------------------------------------ transparência da IA
  // Mostra como a inteligência artificial é usada no site e o que as conferências automáticas encontraram.
  async function telaIA() {
    const pn = await dados("painel");
    const ia = pn.ia || {};
    const m1 = ia.modelo ? ` (${nomeModelo(ia.modelo)})` : "";
    const m2 = ia.conferencia ? ` (${nomeModelo(ia.conferencia)})` : "";
    const linhaConfianca = (nome, c, sem) => {
      const total = somaDe(c, NIVEIS_IA.map((x) => x[0]));
      const li = linhaBarras(nome, NIVEIS_IA.map(([k]) => [c[k], k]), total, total);
      li.append(h("span", { class: "pn-total" }, NIVEIS_IA.map(([k, rotulo]) => `${rotulo}: ${num(c[k])} (${pct1(c[k], total)})`).concat(sem ? [tx("Sem resumo: {0}", num(sem))] : []).join(" · ")));
      return li;
    };
    const bloco = (id, titulo, ...filhos) => h("section", { class: "numeros__bloco", "aria-labelledby": id }, h("h2", { id }, titulo), ...filhos);
    const lista = (itens) => h("ul", { class: "numeros__fatos" }, ...itens.filter(Boolean).map((t) => h("li", {}, t)));
    const acoes = (id, sobre) => acoesDoBloco(id, sobre, pn, pn, "");
    const passos = ia.projetos ? PASSOS_IA(ia, m1, m2).map(([, , texto]) => texto) : [];

    principal.replaceChildren(h("div", { class: "miolo numeros" },
      h("nav", { class: "migalhas", "aria-label": tx("Você está em") }, h("ol", {}, h("li", {}, h("a", { href: "#/" }, tx("Início"))), h("li", { "aria-current": "page" }, tx("Transparência da IA")))),
      h("h1", { id: "titulo-ia", tabindex: "-1" }, tx("Transparência da IA")),
      h("p", { class: "numeros__lead" }, ia.projetos
        ? tx("O assunto e o resumo dos {0} projetos do site são feitos por inteligência artificial, e ninguém revisa esses textos antes de irem ao ar.", num(ia.projetos))
        : tx("O assunto e o resumo dos projetos do site são feitos por inteligência artificial, e ninguém revisa esses textos antes de irem ao ar.")),
      h("p", { class: "numeros__nota" }, tx("Atualizado em {0}. Aqui está o que ela faz, como o trabalho é conferido e onde pode errar. ", data(pn.gerado_em)), h("a", { href: "#/sobre" }, tx("Como o site funciona"))),
      bloco("ia-t1", tx("O que a inteligência artificial faz"),
        lista(FUNCOES_IA),
        h("p", { class: "numeros__nota" }, tx("Ela não registra nem muda votos: o voto de cada deputado, a data e o resultado vêm direto dos Dados Abertos da Câmara. Também não dá nota, não faz ranking e não compara deputados ou partidos."))),
      ia.projetos ? bloco("ia-t2", tx("Como é feito"),
        h("ol", { class: "numeros__passos" }, ...passos.map((t) => h("li", {}, t))),
        ia.ate ? h("p", { class: "numeros__nota" }, tx("Último texto gerado em {0}. O site só refaz o resumo de projetos novos ou cujo texto oficial mudou.", data(ia.ate))) : null) : null,
      ia.projetos ? bloco("ia-t3", tx("Confiança de cada texto"),
        h("p", { class: "numeros__nota" }, tx("Cada assunto e cada resumo recebe uma confiança calculada por máquina, não por pessoas. Alta quer dizer que as conferências automáticas concordaram, não que o texto está certo.")),
        legendaDoPainel(NIVEIS_IA.map(([k, nome]) => [k, nome])),
        h("ul", { class: "pn-linhas pn-linhas--resultado", "aria-label": tx("Confiança do assunto e do resumo") }, linhaConfianca(tx("Assunto"), ia.assunto), linhaConfianca(tx("Resumo"), ia.resumo, ia.so_ementa)),
        acoes("confianca", tx("da confiança"))) : null,
      ia.projetos ? bloco("ia-t4", tx("Avisos que o site mostra"),
        lista(AVISOS_IA(ia).map(([, , n, [um, varios], resto]) => `${plural(n, um, varios)} ${resto}`))) : null,
      bloco("ia-t5", tx("Limites e correções"), lista(LIMITES_IA))));
    document.title = tx("Transparência da IA: como a inteligência artificial é usada | Voto de Verdade");
    return document.getElementById("titulo-ia");
  }

  // ------------------------------------------------------------------ como o site funciona
  const OBJETIVOS = [
    tx("Mostrar o que cada deputado votou, em linguagem simples, sem nota e sem ranking."),
    tx("Organizar os projetos por assunto, para você achar o que importa para a sua vida."),
    tx("Ser neutro e apartidário, sem dizer quem votou certo ou errado."),
    tx("Deixar sempre o texto oficial ao lado do resumo, e avisar quando a inteligência artificial tem dúvida."),
    tx("Ser gratuito, sem anúncios e sem rastrear quem visita, com código aberto."),
  ];
  async function telaSobre() {
    const meta = await dados("meta");
    const pct = Math.round((meta.simbolicas / meta.votacoes) * 100);
    principal.replaceChildren(h("div", { class: "miolo texto-longo" },
      h("nav", { class: "migalhas", "aria-label": tx("Você está em") }, h("ol", {}, h("li", {}, h("a", { href: "#/" }, tx("Início"))), h("li", { "aria-current": "page" }, tx("Como o site funciona")))),
      h("h1", { id: "titulo-sobre", tabindex: "-1" }, tx("Como o site funciona")),
      h("h2", {}, tx("Versão Beta, em constante desenvolvimento")),
      h("p", {}, tx("O Voto de Verdade é uma versão beta e está em constante desenvolvimento. Pode ter erros, e o que ele mostra e a forma como funciona podem mudar. Em caso de dúvida, confira no texto oficial da Câmara.")),
      h("p", {}, tx("Queremos aproximar a sociedade do Congresso, com transparência e visibilidade sobre a atuação parlamentar, de forma simples e prática. Para isso, o site busca:")),
      h("ul", {}, ...OBJETIVOS.map((o) => h("li", {}, o))),
      h("h2", {}, tx("Neutro e apartidário, sem nota e sem ranking")),
      h("p", {}, tx("Não dá nota, não faz ranking e não diz quem votou certo ou errado. Mostra o que cada deputado votou. Votar sim ou não numa votação não diz, sozinho, se o deputado apoia o assunto do projeto: muitas votações são sobre emendas, substitutivos ou pontos separados do texto.")),
      h("h2", {}, tx("De onde vêm os dados")),
      h("p", {}, tx("Do portal de Dados Abertos da Câmara dos Deputados. O site mostra {0} votações em plenário, de {1} a {2}, e é atualizado todos os dias. Quando a Câmara não vota (recesso, período de eleições), não há novidades.", num(meta.votacoes), data(meta.de), data(meta.ate))),
      h("h2", {}, tx("Só a Câmara dos Deputados, por enquanto")),
      h("p", {}, tx("O site cobre os deputados federais. O Senado, as assembleias estaduais e as câmaras de vereadores não estão aqui.")),
      h("h2", {}, tx("Quais votações o site mostra")),
      h("p", {}, tx("Um projeto costuma passar por várias votações no plenário. Aqui entram só as que decidem sobre o projeto em si, isto é, aprovar ou rejeitar. Ficam de fora as votações de urgência (que só decidem se o projeto anda mais rápido), de requerimentos, de emendas ou destaques isolados (que votam a mudança de um trecho) e de procedimento. Por isso um projeto que foi votado muitas vezes pode aparecer com uma só votação.")),
      h("p", {}, tx("Às vezes a Câmara vota um substitutivo, um texto novo que troca o original. Essa votação aparece, com um aviso: o resumo foi feito a partir da ementa do projeto original, e o texto votado pode ser diferente.")),
      h("h2", {}, tx("Números e dados para baixar")),
      h("p", {}, tx("A tela "), h("a", { href: "#/em-numeros" }, tx("Em números")), tx(" mostra as votações ao longo do tempo, por assunto e por resultado, quantos deputados votaram e o placar das votações nominais, com filtro por ano. Cada bloco de números e as listas de projetos, deputados e votos têm botões para baixar o que está na tela em CSV (que abre em planilha) ou em JSON, já com o filtro aplicado. Ao usar os dados, cite o Voto de Verdade e a Câmara dos Deputados.")),
      h("h2", {}, tx("Assunto e resumo são feitos por inteligência artificial")),
      h("p", {}, tx("Uma inteligência artificial lê o texto oficial de cada projeto, escolhe o assunto e escreve um resumo em linguagem simples. Ela pode errar. Quando a classificação ou o resumo têm dúvida, o projeto mostra um aviso. O texto oficial fica sempre ao lado.")),
      h("p", {}, tx("Ninguém revisa os resumos antes de irem ao ar, e por enquanto o site não tem um canal para pedir correções. Se algo parecer estranho, confira no texto oficial.")),
      h("p", {}, h("a", { href: "#/inteligencia-artificial" }, tx("Veja como a inteligência artificial é usada, com os números"))),
      h("h2", {}, tx("Por que nem todo projeto mostra o voto de cada deputado")),
      h("p", {}, tx("{0} das {1} votações ({2}%) foram simbólicas: os partidos chegam a um acordo e o resultado é anunciado sem registrar o voto de cada deputado. Nesses casos não há como saber como cada um votou. Só as {3} votações nominais têm o voto de cada deputado.", num(meta.simbolicas), num(meta.votacoes), pct, num(meta.nominais))),
      h("h2", {}, tx("O que significa “presidia a sessão”")),
      h("p", {}, tx("Quem conduz a sessão só vota em situações previstas no regimento (artigo 17). Nos dados da Câmara, o voto de quem presidia aparece com esse registro, e não como sim ou não.")),
      h("h2", {}, tx("Licença e uso do conteúdo")),
      h("p", {}, tx("O código do site é aberto, com licença MIT. Os textos do site e os resumos feitos por inteligência artificial podem ser copiados e usados por qualquer pessoa, inclusive em matérias, desde que citem o Voto de Verdade e o endereço votodeverdade.com.br (licença CC BY 4.0). Os dados originais são da Câmara dos Deputados, que tem as próprias regras. Pedimos que o conteúdo não seja usado para treinar modelos de inteligência artificial. Consultá-lo para responder perguntas, citando o site, é bem-vindo.")),
      h("h2", {}, tx("Quem faz e privacidade")),
      h("p", {}, tx("O Voto de Verdade é um site independente, sem ligação com a Câmara dos Deputados, com partidos ou com candidatos. Não usa cookies nem ferramentas que rastreiam quem visita. Se você escolher o modo escuro, só o seu navegador guarda essa escolha.")),
      h("p", {}, h("a", { href: "#/" }, tx("Voltar ao início")))));
    document.title = tx("Como o site funciona: Voto de Verdade");
    return document.getElementById("titulo-sobre");
  }

  // ------------------------------------------------------------------ página do assunto
  async function telaAssunto(slug, p) {
    const [assuntos, projetos, votacoes, metaDados] = await Promise.all([dados("assuntos"), projetosComTexto(), indiceVotacoes(), dados("meta")]);
    const a = assuntos.find((x) => x.slug === slug);
    if (!a) return telaNaoEncontrada("assunto");
    const base = projetos.filter((x) => x.a === slug || x.s === slug);
    const nInd = base.filter((x) => x.ind).length;
    const anosAssunto = [...new Set(base.map((x) => (x.ultima || "").slice(0, 4)))].filter(Boolean).sort().reverse();

    const estado = {
      q: p.get("q") || "", todos: p.get("todos") === "1" || !nInd,
      ord: p.get("ord") === "antiga" ? "antiga" : "recente",
      res: ["aprovado", "rejeitado"].includes(p.get("res")) ? p.get("res") : "", cert: p.get("cert") === "1",
      ano: anosAssunto.includes(p.get("ano")) ? p.get("ano") : "",
    };
    let limite = Math.min(600, Math.max(POR_PAGINA, parseInt(p.get("n"), 10) || 0));

    const maisFiltros = h("details", { class: "ajuda mais-filtros" });
    const campoBusca = h("input", { id: "busca-a", type: "search", autocomplete: "off", spellcheck: "false", value: estado.q, placeholder: tx("uma palavra do projeto"), enterkeyhint: "search" });
    const seletorOrd = h("select", { id: "ord-a" }, h("option", { value: "recente" }, tx("Mais recentes primeiro")), h("option", { value: "antiga" }, tx("Mais antigos primeiro")));
    const seletorRes = h("select", { id: "res-a" }, h("option", { value: "" }, tx("Todos")), h("option", { value: "aprovado" }, tx("Só aprovados")), h("option", { value: "rejeitado" }, tx("Só rejeitados")));
    seletorOrd.value = estado.ord; seletorRes.value = estado.res;
    const seletorAno = h("select", { id: "ano-a" }, h("option", { value: "" }, tx("Todos os anos")), ...anosAssunto.map((x) => h("option", { value: x }, x)));
    seletorAno.value = estado.ano;
    let listaAtual = [];
    const exportarLista = botoesExportar("projetos-" + slug, () => ({
      titulo: tx("Projetos de {0}", a.nome), gerado_em: metaDados.gerado_em,
      filtros: { assunto: slug, busca: estado.q || undefined, ano: estado.ano ? Number(estado.ano) : undefined, resultado: estado.res || undefined, so_com_voto_de_cada_deputado: estado.todos ? undefined : true, esconder_com_aviso: estado.cert || undefined },
      colunas: [["id", tx("Código")], ["projeto", tx("Projeto")], ["titulo", tx("Título")], ["assunto", tx("Assunto")], ["data_da_ultima_votacao", tx("Data da última votação")], ["resultado", tx("Resultado")],
        ["tipo_de_votacao", tx("Tipo de votação")], ["voto_de_cada_deputado_registrado", tx("Voto de cada deputado registrado")], ["confianca_do_assunto", tx("Confiança do assunto")],
        ["confianca_do_resumo", tx("Confiança do resumo")], ["resumo", tx("Resumo feito por inteligência artificial")], ["texto_oficial", tx("Texto oficial")]],
      registros: listaAtual.map((x) => ({ id: x.id, projeto: x.nome, titulo: x.titulo, assunto: a.nome, data_da_ultima_votacao: x.ultima, resultado: x.aprovada ? tx("aprovada") : tx("rejeitada"),
        tipo_de_votacao: x.tipo, voto_de_cada_deputado_registrado: !!x.ind, confianca_do_assunto: x.ca, confianca_do_resumo: x.cr || null, resumo: x.resumo || null, texto_oficial: x.texto || null })),
    }), tx("dos projetos desta lista"));
    const caixaCert = h("input", { type: "checkbox", id: "cert-a" }); caixaCert.checked = estado.cert;
    const abaInd = h("button", { type: "button", class: "aba", id: "aba-ind" });
    const abaTodos = h("button", { type: "button", class: "aba", id: "aba-todos" });
    const estadoTxt = h("p", { class: "estado", role: "status", "aria-live": "polite" });
    const lista = h("ul", { class: "projetos" });
    const maisBox = h("div", { class: "mais" });
    const vazio = h("div", { class: "vazio" });

    maisFiltros.append(
      h("summary", {}, tx("Mais filtros")),
      h("div", { class: "filtros__linha filtros__linha--3" },
        h("div", { class: "campo" }, h("label", { for: "res-a" }, tx("Resultado da votação")), seletorRes),
        h("div", { class: "campo" }, h("label", { for: "ano-a" }, tx("Ano da última votação")), seletorAno),
        h("div", { class: "campo" }, h("label", { for: "ord-a" }, tx("Ordem")), seletorOrd)),
      h("label", { class: "marcar", for: "cert-a" }, caixaCert, h("span", {}, tx("Esconder projetos com aviso de possível erro"))));
    maisFiltros.open = !!(estado.ano || estado.res || estado.cert);
    principal.replaceChildren(h("div", { class: "miolo" },
      h("nav", { class: "migalhas", "aria-label": tx("Você está em") },
        h("ol", {}, h("li", {}, h("a", { href: "#/" }, tx("Assuntos"))), h("li", { "aria-current": "page" }, a.nome))),
      h("header", { class: "cabeca-assunto cabeca-assunto--cor", style: estiloAssunto(slug) },
        h("span", { class: "cabeca-assunto__icone" }, icone(slug)),
        h("div", {},
          h("h1", { id: "titulo-assunto", tabindex: "-1" }, a.nome),
          h("p", {}, a.descricao.charAt(0).toUpperCase() + a.descricao.slice(1) + "."))),
      h("p", { class: "guia-votacao" },
        h("strong", {}, tx("Votação simbólica: ")), tx("os partidos chegam a um acordo e o resultado é anunciado sem registrar o voto de cada deputado. Por isso só os projetos da aba “Com voto de cada deputado” mostram como cada um votou; “Todos os projetos” inclui também os votados de forma simbólica ou secreta.")),
      h("div", { class: "abas", role: "group", "aria-label": tx("Quais projetos mostrar") }, abaInd, abaTodos),
      h("form", { class: "filtros filtros--compacto", role: "search", "aria-label": tx("Procurar em {0}", a.nome), onsubmit: (e) => e.preventDefault() },
        h("div", { class: "campo" }, h("label", { for: "busca-a" }, tx("Procurar neste assunto")), campoBusca),
        maisFiltros,
      ),
      estadoTxt, h("div", { class: "lista-acoes" }, exportarLista), lista, vazio, maisBox,
      h("div", { class: "mais" }, botaoCompartilhar("assunto/" + slug, tx("{0}: Voto de Verdade", a.nome)))));
    document.title = tx("{0}: Voto de Verdade", a.nome);

    function atualizar(reiniciar) {
      if (reiniciar) limite = POR_PAGINA;
      estado.q = campoBusca.value.trim(); estado.ord = seletorOrd.value; estado.res = seletorRes.value; estado.cert = caixaCert.checked; estado.ano = seletorAno.value;
      gravarEndereco("assunto/" + slug, limparParams({
        q: estado.q, todos: estado.todos && nInd ? "1" : "", ord: estado.ord === "recente" ? "" : estado.ord, res: estado.res, cert: estado.cert ? "1" : "", ano: estado.ano,
        n: limite > POR_PAGINA ? String(limite) : "" }));

      const ts = termos(estado.q);
      const comFiltros = base.filter((x) =>
        (!ts.length || casa(x._t, ts)) && (!estado.res || (estado.res === "aprovado") === x.aprovada) && (!estado.ano || (x.ultima || "").slice(0, 4) === estado.ano) &&
        (!estado.cert || ((x.ca === "alta") && (!x.cr || x.cr === "alta"))));
      const nIndF = comFiltros.filter((x) => x.ind).length;
      abaInd.textContent = tx("Com voto de cada deputado ({0})", num(nIndF));
      abaTodos.textContent = tx("Todos os projetos ({0})", num(comFiltros.length));
      abaInd.setAttribute("aria-pressed", String(!estado.todos)); abaTodos.setAttribute("aria-pressed", String(estado.todos));
      abaInd.disabled = !nInd;

      const r = (estado.todos ? comFiltros : comFiltros.filter((x) => x.ind)).slice();
      r.sort((x, y) => (estado.ord === "recente" ? (y.ultima > x.ultima ? 1 : -1) : (x.ultima > y.ultima ? 1 : -1)) || y.id - x.id);
      listaAtual = r;
      const mostrados = r.slice(0, limite);
      lista.replaceChildren(...mostrados.map((x) => linhaProjeto(x, votacoes)));
      anunciar(estadoTxt, r.length ? plural(r.length, tx("projeto"), tx("projetos")) : "");
      vazio.replaceChildren();
      if (!r.length) {
        const acoes = [];
        if (!estado.todos && comFiltros.length) {
          acoes.push({ rotulo: tx("Ver os {0} projetos, inclusive os sem voto de cada deputado", num(comFiltros.length)), onclick: () => { estado.todos = true; atualizar(true); } });
        }
        if (estado.q || estado.res || estado.cert || estado.ano) {
          acoes.push({ rotulo: tx("Limpar a busca e os filtros"), onclick: () => { campoBusca.value = ""; estado.q = ""; estado.res = ""; estado.cert = false; estado.ano = ""; seletorRes.value = ""; seletorAno.value = ""; caixaCert.checked = false; atualizar(true); } });
        }
        vazio.append(estadoVazio({
          icone: "v-filtro", titulo: tx("Nenhum projeto com esses filtros"),
          texto: !estado.todos && comFiltros.length ? tx("Nenhum dos projetos com o voto de cada deputado combina com a busca. Os outros foram votados de forma simbólica ou secreta.") : tx("Tire algum filtro ou escreva outra palavra."),
          acoes }));
      }
      maisBox.replaceChildren();
      if (r.length > mostrados.length) {
        maisBox.append(h("button", { type: "button", class: "botao botao--leve", onclick: () => { limite += POR_PAGINA; atualizar(false); } },
          tx("Mostrar mais {0} projetos", Math.min(POR_PAGINA, r.length - mostrados.length))));
      }
    }

    comEspera(campoBusca, () => atualizar(true));
    for (const el of [seletorOrd, seletorRes, seletorAno, caixaCert]) el.addEventListener("change", () => atualizar(true));
    abaInd.addEventListener("click", () => { estado.todos = false; atualizar(true); });
    abaTodos.addEventListener("click", () => { estado.todos = true; atualizar(true); });
    atualizar(false);
    return document.getElementById("titulo-assunto");
  }

  // ------------------------------------------------------------------ painel "como cada deputado votou"
  let contadorPainel = 0;
  function painelVotos(v, opc) {
    opc = opc || {};
    const n = ++contadorPainel;
    const raiz = h("div", { class: "painel" }, h("p", { class: "nota" }, tx("Carregando os votos…")));
    montar().catch((e) => {
      console.error(e);
      raiz.replaceChildren(h("p", { class: "nota" }, tx("Não foi possível carregar os votos desta votação. Recarregue a página e tente de novo.")));
    });
    return raiz;

    async function montar() {
      const [deputados, arq] = await Promise.all([dados("deputados"), dados("votacoes/" + v.id)]);
      const porId = Object.fromEntries(deputados.map((d) => [d.id, d]));
      const linhas = arq.v.map(([did, cod, partido]) => {
        const d = porId[did] || { nome: tx("Deputado {0}", did), uf: "" };
        return { id: did, nome: d.nome, uf: d.uf || "", partido: partido || d.partido || "", cod, _t: semAcento(d.nome) };
      });
      const total = {}; for (const l of linhas) total[l.cod] = (total[l.cod] || 0) + 1;
      const nTotal = linhas.length;
      const partidos = [...new Set(linhas.map((l) => l.partido))].filter(Boolean).sort((a, b) => a.localeCompare(b, LOCALE));
      const ufs = [...new Set(linhas.map((l) => l.uf))].filter(Boolean).sort();
      const p = opc.p || new URLSearchParams();
      const estado = {
        q: p.get("q") || "", pt: partidos.includes(p.get("pt")) ? p.get("pt") : "", uf: ufs.includes(p.get("uf")) ? p.get("uf") : "",
        v: VOTO[p.get("v")] ? p.get("v") : "",
      };
      let limite = 60;
      const id = (x) => `${x}-${n}`;

      const placar = placarVotos(total, (cod) => { selV.value = selV.value === cod ? "" : cod; atualizar(true); });
      const meta = await dados("meta");
      let linhasAtuais = linhas;
      const exportarVotosDeps = botoesExportar("votos-" + v.id, () => ({
        titulo: opc.titulo || tx("Votos de cada deputado na votação {0}", v.id), gerado_em: meta.gerado_em,
        filtros: { votacao: v.id, busca: estado.q || undefined, partido: estado.pt || undefined, uf: estado.uf || undefined, voto: estado.v ? VOTO[estado.v].nome : undefined },
        colunas: [["deputado_id", tx("Código do deputado")], ["deputado", tx("Deputado")], ["partido", tx("Partido na data")], ["uf", tx("UF")], ["voto", tx("Voto")]],
        registros: linhasAtuais.map((l) => ({ deputado_id: l.id, deputado: l.nome, partido: l.partido || null, uf: l.uf || null, voto: VOTO[l.cod].nome })),
      }), tx("dos votos desta lista"));

      const campoQ = h("input", { id: id("q"), type: "search", autocomplete: "off", spellcheck: "false", value: estado.q, placeholder: tx("nome do deputado"), enterkeyhint: "search" });
      const selPt = h("select", { id: id("pt") }, h("option", { value: "" }, tx("Todos")), partidos.map((x) => h("option", { value: x }, x)));
      const selUf = h("select", { id: id("uf") }, h("option", { value: "" }, tx("Todos")), ufs.map((x) => h("option", { value: x }, x)));
      const selV = h("select", { id: id("v") }, h("option", { value: "" }, tx("Todos")), ORDEM_VOTO.filter((c) => total[c]).map((c) => h("option", { value: c }, VOTO[c].nome)));
      selPt.value = estado.pt; selUf.value = estado.uf; selV.value = estado.v;
      const limpar = h("button", { type: "button", class: "botao botao--leve botao--pequeno" }, tx("Limpar filtros"));
      const estadoTxt = h("p", { class: "estado", role: "status", "aria-live": "polite" });
      const lista = h("ul", { class: "deputados" });
      const vazioLista = h("div", {});
      const maisBox = h("div", { class: "mais" });

      const filtros = h("form", { class: "filtros filtros--compacto", role: "search", "aria-label": tx("Filtrar os votos"), onsubmit: (e) => e.preventDefault() },
        h("div", { class: "filtros__linha filtros__linha--4" },
          h("div", { class: "campo campo--nome" }, h("label", { for: id("q") }, tx("Deputado")), campoQ),
          h("div", { class: "campo" }, h("label", { for: id("pt") }, tx("Partido")), selPt),
          h("div", { class: "campo" }, h("label", { for: id("uf") }, tx("Estado")), selUf),
          h("div", { class: "campo campo--so-desktop" }, h("label", { for: id("v") }, tx("Voto")), selV)),
        h("div", { class: "filtros__rodape" }, limpar));

      const ajudaVotos = h("details", { class: "ajuda ajuda--solta" },
        h("summary", {}, tx("O que significam abstenção, obstrução e “presidia a sessão”?")),
        h("ul", {},
          h("li", {}, tx("Abstenção: o deputado esteve presente e escolheu não votar nem sim nem não.")),
          h("li", {}, tx("Obstrução: o deputado ou seu partido age para atrasar ou impedir a votação, em geral não votando.")),
          h("li", {}, tx("Presidia a sessão: quem conduz a sessão só vota em situações previstas no regimento (artigo 17). O registro aparece assim nos dados da Câmara."))));

      raiz.replaceChildren(
        h("div", { class: "painel-topo" },
          h("div", { class: "painel-placar" },
            placar,
            h("p", { class: "nota" }, tx("{0} voto; quem faltou não aparece. Toque em um número para ver só esses deputados.", plural(nTotal, tx("deputado registrou"), tx("deputados registraram")))),
            total.P ? h("p", { class: "nota" }, tx("“Presidia a sessão”: quem conduz a sessão só vota em casos especiais. Nesses casos o registro aparece assim, e não como sim ou não.")) : null)),
        opc.descricao || null,
        h("div", { class: "bloco" }, filtros, estadoTxt, h("div", { class: "lista-acoes" }, exportarVotosDeps), lista, vazioLista, maisBox, ajudaVotos));

      function filtrar() {
        const ts = termos(estado.q);
        return linhas.filter((l) =>
          (!ts.length || casa(l._t, ts)) && (!estado.pt || l.partido === estado.pt) && (!estado.uf || l.uf === estado.uf) && (!estado.v || l.cod === estado.v));
      }

      function atualizar(reiniciar) {
        if (reiniciar) limite = 60;
        estado.q = campoQ.value.trim(); estado.pt = selPt.value; estado.uf = selUf.value; estado.v = selV.value;
        if (opc.gravar) opc.gravar(limparParams({ q: estado.q, pt: estado.pt, uf: estado.uf, v: estado.v }));
        const filtrando = !!(estado.q || estado.pt || estado.uf || estado.v);
        const r = filtrar().sort((a, b) => a.nome.localeCompare(b.nome, LOCALE));
        linhasAtuais = r;
        const mostrados = r.slice(0, limite);
        placar.marcar(estado.v);
        lista.replaceChildren(...mostrados.map((l) => h("li", { class: "deputado" },
          h("a", { class: "deputado__nome", href: "#/deputado/" + l.id }, l.nome),
          h("span", { class: "deputado__sub" }, [l.partido, l.uf].filter(Boolean).join(" · ")),
          fichaVoto(l.cod))));
        anunciar(estadoTxt, r.length
          ? `${plural(r.length, tx("deputado"), tx("deputados"))}${r.length !== nTotal ? tx(" de {0}", num(nTotal)) : ""}`
          : tx("Nenhum deputado com esses filtros. Tire algum filtro ou escreva outro nome."));
        vazioLista.replaceChildren(...(r.length ? [] : [estadoVazio({
          icone: "v-filtro", titulo: tx("Nenhum deputado com esses filtros"),
          texto: tx("Nesta votação, ninguém combina com a busca, o partido, o estado e o voto escolhidos. Tire algum filtro ou escreva outro nome."),
          acoes: [{ rotulo: tx("Limpar filtros"), onclick: () => limpar.click() }] })]));
        limpar.hidden = !filtrando;
        maisBox.replaceChildren();
        if (r.length > mostrados.length) {
          maisBox.append(h("button", { type: "button", class: "botao botao--leve", onclick: () => { limite += 60; atualizar(false); } },
            tx("Mostrar mais {0} deputados", Math.min(60, r.length - mostrados.length))));
        }
      }
      comEspera(campoQ, () => atualizar(true));
      for (const el of [selPt, selUf, selV]) el.addEventListener("change", () => atualizar(true));
      limpar.addEventListener("click", () => { campoQ.value = ""; selPt.value = ""; selUf.value = ""; selV.value = ""; atualizar(true); campoQ.focus(); });
      atualizar(true);
    }
  }

  // ------------------------------------------------------------------ página do projeto (com os votos)
  async function telaProjeto(id, p) {
    const [vots, projetos, assuntos] = await Promise.all([indiceVotacoes(), dados("projetos"), dados("assuntos")]);
    const base = projetos.find((x) => String(x.id) === String(id));
    if (!base) return telaNaoEncontrada("projeto");
    // ementa e pontos principais ficam num arquivo por projeto; se não carregar, a página abre sem eles
    const detalhes = await dados("projetos/" + base.id).catch(() => null);
    const pr = { ...base, ementa: detalhes ? detalhes.ementa || "" : null, pontos: detalhes ? detalhes.pontos || [] : [] };
    const assunto = assuntos.find((x) => x.slug === pr.a);
    const minhas = (vots.porProjeto[pr.id] || []).slice().sort((x, y) => (x.d < y.d ? -1 : x.d > y.d ? 1 : 0));
    const nominais = minhas.filter((x) => x.t === "nominal");
    let atual = nominais.find((x) => x.id === p.get("votacao")) || nominais[nominais.length - 1];

    const caixa = h("div", { class: "votos-projeto" });
    const mostrar = (v) => {
      atual = v;
      const params = new URLSearchParams(p);
      params.set("votacao", v.id);
      caixa.replaceChildren(...[
        h("p", { class: "nota" }, tx("{0} · Resultado: {1}", data(v.d), v.ap ? tx("aprovada") : tx("rejeitada"))),
        v.c !== "alta" && v.av ? h("div", { class: "cartao-aviso" }, h("strong", {}, tx("Atenção")), h("p", {}, v.av)) : null,
        painelVotos(v, { titulo: tx("Votos de cada deputado em {0} (votação de {1})", pr.nome, data(v.d)), descricao: h("p", { class: "nota registro" }, tx("Registro oficial da votação: {0}", v.desc)), p: params, gravar: (q) => { q.set("votacao", v.id); gravarEndereco("projeto/" + pr.id, q); } })].filter(Boolean));
    };

    const secaoVotos = h("section", { class: "bloco", "aria-labelledby": "votos-titulo" }, h("h2", { id: "votos-titulo" }, tx("Como cada deputado votou")));
    if (nominais.length) {
      if (nominais.length > 1) {
        const sel = h("select", { id: "sel-votacao" },
          nominais.slice().reverse().map((v) => h("option", { value: v.id }, `${data(v.d)}: ${descCurta(v.desc)}`)));
        sel.value = atual.id;
        sel.addEventListener("change", () => { const novo = nominais.find((v) => v.id === sel.value); p = new URLSearchParams(); mostrar(novo); gravarEndereco("projeto/" + pr.id, new URLSearchParams({ votacao: novo.id })); });
        secaoVotos.append(h("div", { class: "campo campo--largo" }, h("label", { for: "sel-votacao" }, tx("Este projeto teve {0} votações com o voto de cada deputado. Escolha uma:", nominais.length)), sel));
      }
      secaoVotos.append(caixa);
    } else {
      const secreta = minhas.some((x) => x.t === "secreta");
      secaoVotos.append(estadoVazio(secreta
        ? { icone: "v-urna", titulo: tx("Votação secreta"), texto: tx("Votação secreta: o voto de cada deputado não é divulgado.") }
        : { icone: "v-urna", titulo: tx("Votação simbólica, sem voto individual"), texto: tx("Votação simbólica: os partidos chegaram a um acordo e o resultado foi anunciado sem registrar o voto de cada deputado. Por isso não há como mostrar como cada um votou.") }));
      secaoVotos.append(h("ul", { class: "lista-simples" }, minhas.map((v) => h("li", {}, `${data(v.d)} · ${v.ap ? tx("Aprovada") : tx("Rejeitada")}. ${v.desc}`))));
    }
    const partes = blocosProjeto(pr);
    const outrasSimbolicas = nominais.length ? minhas.filter((x) => x.t !== "nominal") : [];

    principal.replaceChildren(h("div", { class: "miolo pagina-projeto" },
      h("nav", { class: "migalhas", "aria-label": tx("Você está em") },
        h("ol", {},
          h("li", {}, h("a", { href: "#/" }, tx("Assuntos"))),
          assunto ? h("li", {}, h("a", { href: "#/assunto/" + assunto.slug }, assunto.nome)) : null,
          h("li", { "aria-current": "page" }, pr.nome))),
      h("header", { class: "cabeca-projeto" },
        h("h1", { id: "titulo-projeto", tabindex: "-1" }, tituloCompleto(pr)),
        h("p", { class: "cabeca-projeto__meta" }, tx("{0} · última votação em {1}", pr.nome, data(pr.ultima))),
        h("div", { class: "cabeca-projeto__acoes" }, botaoCompartilhar("projeto/" + pr.id, tx("{0} | Voto de Verdade", descCurta(pr.titulo, 90))))),
      h("div", { class: "resumo-projeto" }, resumoSemRepetir(pr), partes.avisos, partes.substitutivo),
      h("details", { class: "ajuda ajuda--solta" },
        h("summary", {}, tx("Pontos principais e texto oficial")),
        h("div", { class: "projeto__corpo" }, partes.pontos, partes.oficial)),
      secaoVotos,
      outrasSimbolicas.length ? h("p", { class: "nota" }, tx("Este projeto também teve {0}, sem o voto de cada deputado.", outrasSimbolicas.length === 1 ? tx("uma votação simbólica") : tx("{0} votações simbólicas", outrasSimbolicas.length))) : null));
    if (nominais.length) mostrar(atual);
    {
      const base = `${pr.nome}: ${descCurta(pr.titulo, 60 - String(pr.nome).length - 2)}`;
      document.title = base.length + 17 <= 62 ? tx("{0} | Voto de Verdade", base) : base;
    }
    return document.getElementById("titulo-projeto");
  }

  // Endereço antigo de uma votação: abre a página do projeto, já nessa votação.
  async function telaVotacao(id, p) {
    const vots = await indiceVotacoes();
    const v = vots.porId[id];
    if (!v) return telaNaoEncontrada("votacao");
    const q = new URLSearchParams(p); q.set("votacao", id);
    history.replaceState(null, "", `#/projeto/${v.p}?${q}`);
    return telaProjeto(String(v.p), q);
  }

  // ------------------------------------------------------------------ deputados (busca) e página do deputado
  // A foto fica guardada aqui (fotos/<id>.jpg). Se faltar, some: o navegador de quem visita nunca fala com outro endereço.
  const fotoDeputado = (id) => h("img", {
    class: "foto-dep", src: `${RAIZ}fotos/${id}.jpg`, alt: "", width: "100", height: "133", loading: "lazy", referrerpolicy: "no-referrer",
    onerror: (e) => e.target.remove(),
  });

  async function telaDeputados(p) {
    const [deputados, metaDeps] = await Promise.all([dados("deputados"), dados("meta")]);
    for (const d of deputados) d._t = semAcento(d.nome);
    const partidos = [...new Set(deputados.map((d) => d.partido))].filter(Boolean).sort((a, b) => a.localeCompare(b, LOCALE));
    const ufs = [...new Set(deputados.map((d) => d.uf))].filter(Boolean).sort();
    const estado = { q: p.get("q") || "", pt: partidos.includes(p.get("pt")) ? p.get("pt") : "", uf: ufs.includes(p.get("uf")) ? p.get("uf") : "", ex: p.get("ex") === "1" };
    let limite = 60;

    const campoQ = h("input", { id: "busca-d", type: "search", autocomplete: "off", spellcheck: "false", value: estado.q, placeholder: tx("nome do deputado"), enterkeyhint: "search" });
    const selPt = h("select", { id: "dep-pt" }, h("option", { value: "" }, tx("Todos os partidos")), partidos.map((x) => h("option", { value: x }, x)));
    selPt.value = estado.pt;
    const chips = ufs.map((u) => h("li", {}, h("button", { type: "button", class: "chip-uf", "aria-pressed": "false", "data-uf": u, onclick: () => { estado.uf = estado.uf === u ? "" : u; atualizar(true); } }, u)));
    const caixaEx = h("input", { type: "checkbox", id: "dep-ex" }); caixaEx.checked = estado.ex;
    const estadoTxt = h("p", { class: "estado", role: "status", "aria-live": "polite" });
    let depsAtuais = deputados;
    const exportarDeps = botoesExportar("deputados", () => ({
      titulo: tx("Deputados federais"), gerado_em: metaDeps.gerado_em,
      filtros: { busca: estado.q || undefined, partido: estado.pt || undefined, uf: estado.uf || undefined, so_em_exercicio: estado.ex || undefined },
      colunas: [["id", tx("Código na Câmara")], ["nome", tx("Nome")], ["partido", tx("Partido")], ["uf", tx("UF")], ["em_exercicio", tx("Em exercício agora")]],
      registros: depsAtuais.map((d) => ({ id: d.id, nome: d.nome, partido: d.partido || null, uf: d.uf || null, em_exercicio: !!d.ex })),
    }), tx("dos deputados desta lista"));
    const lista = h("ul", { class: "lista-dep" });
    const vazio = h("div", {});
    const maisBox = h("div", { class: "mais" });

    principal.replaceChildren(h("div", { class: "miolo" },
      h("section", { class: "abertura", "aria-labelledby": "titulo-deputados" },
        h("h1", { id: "titulo-deputados", tabindex: "-1" }, tx("Procure um deputado federal")),
        h("p", { class: "abertura__texto" }, tx("Veja como cada deputado votou nas votações nominais, as únicas em que o voto de cada um fica registrado. Sem nota e sem ranking."))),
      h("form", { class: "filtros", role: "search", "aria-label": tx("Procurar deputado"), onsubmit: (e) => e.preventDefault() },
        h("div", {}, h("p", { class: "rotulo", id: "rotulo-uf" }, tx("Deputados do seu estado")), h("ul", { class: "chips-uf", "aria-labelledby": "rotulo-uf" }, chips)),
        h("div", { class: "filtros__linha" },
          h("div", { class: "campo" }, h("label", { for: "busca-d" }, tx("Nome")), campoQ),
          h("div", { class: "campo" }, h("label", { for: "dep-pt" }, tx("Partido")), selPt)),
        h("label", { class: "marcar", for: "dep-ex" }, caixaEx, h("span", {}, tx("Só quem está em exercício agora"),
          h("small", {}, tx("Deixe desligado para ver também quem já deixou o cargo ou foi suplente no período."))))),
      estadoTxt, h("div", { class: "lista-acoes" }, exportarDeps), lista, vazio, maisBox));
    document.title = tx("Deputados: Voto de Verdade");

    function atualizar(reiniciar) {
      if (reiniciar) limite = 60;
      estado.q = campoQ.value.trim(); estado.pt = selPt.value; estado.ex = caixaEx.checked;
      gravarEndereco("deputados", limparParams({ q: estado.q, pt: estado.pt, uf: estado.uf, ex: estado.ex ? "1" : "" }));
      for (const b of principal.querySelectorAll(".chip-uf")) b.setAttribute("aria-pressed", String(b.dataset.uf === estado.uf));
      const ts = termos(estado.q);
      const r = deputados.filter((d) => (!ts.length || casa(d._t, ts)) && (!estado.pt || d.partido === estado.pt) && (!estado.uf || d.uf === estado.uf) && (!estado.ex || d.ex));
      depsAtuais = r;
      const mostrados = r.slice(0, limite);
      lista.replaceChildren(...mostrados.map((d) => h("li", {}, h("a", { class: "linha-dep", href: "#/deputado/" + d.id },
        h("span", { class: "linha-dep__nome" }, d.nome),
        h("span", { class: "linha-dep__sub" }, [d.partido, d.uf].filter(Boolean).join(" · ") + (d.ex ? "" : tx(" · fora do exercício agora")))))));
      anunciar(estadoTxt, r.length ? `${plural(r.length, tx("deputado"), tx("deputados"))}${r.length !== deputados.length ? tx(" de {0}", num(deputados.length)) : ""}`
        : tx("Nenhum deputado com esses filtros. Confira a grafia do nome ou tire algum filtro."));
      vazio.replaceChildren(...(r.length ? [] : [estadoVazio({
        icone: "v-pessoa", titulo: tx("Nenhum deputado com esses filtros"),
        texto: estado.ex ? tx("Confira a grafia do nome ou tire algum filtro. Quem já deixou o cargo só aparece se você desligar “Só quem está em exercício agora”.") : tx("Confira a grafia do nome ou tire algum filtro. A busca ignora acentos e letras maiúsculas."),
        acoes: [{ rotulo: tx("Limpar filtros"), onclick: () => { campoQ.value = ""; selPt.value = ""; caixaEx.checked = false; estado.uf = ""; atualizar(true); campoQ.focus(); } }] })]));
      maisBox.replaceChildren();
      if (r.length > mostrados.length) {
        maisBox.append(h("button", { type: "button", class: "botao botao--leve", onclick: () => { limite += 60; atualizar(false); } },
          tx("Mostrar mais {0} deputados", Math.min(60, r.length - mostrados.length))));
      }
    }
    comEspera(campoQ, () => atualizar(true));
    for (const el of [selPt, caixaEx]) el.addEventListener("change", () => atualizar(true));
    atualizar(true);
    return document.getElementById("titulo-deputados");
  }

  async function telaDeputado(id, p) {
    const [deputados, vots, projetos, assuntos] = await Promise.all([dados("deputados"), indiceVotacoes(), dados("projetos"), dados("assuntos")]);
    const dep = deputados.find((d) => String(d.id) === id);
    if (!dep) return telaNaoEncontrada("deputado");
    let arq;
    try { arq = await dados("deputados/" + id); } catch (e) { arq = { v: [], pt: [] }; }
    const meta = await dados("meta");
    const prPorId = Object.fromEntries(projetos.map((x) => [x.id, x]));
    const nomeAssunto = Object.fromEntries(assuntos.map((x) => [x.slug, x.nome]));

    const votos = [];
    for (const [vid, cod] of arq.v) {
      const v = vots.porId[vid]; if (!v) continue;
      const pr = prPorId[v.p]; if (!pr) continue;
      votos.push({ v, pr, cod, _t: semAcento([pr.titulo, pr.nome, v.desc].join(" ")) });
    }
    const total = {}; for (const x of votos) total[x.cod] = (total[x.cod] || 0) + 1;

    const porAssunto = {};
    for (const x of votos) {
      const t = (porAssunto[x.pr.a] ||= { S: 0, N: 0, O: 0, n: 0 });
      t.n++; if (x.cod === "S" || x.cod === "N") t[x.cod]++; else t.O++;
    }
    const slugs = Object.keys(porAssunto).sort((a, b) => (a === "outros") - (b === "outros") || nomeAssunto[a].localeCompare(nomeAssunto[b], LOCALE));

    const anosDep = [...new Set(votos.map((x) => x.v.d.slice(0, 4)))].sort().reverse();
    const estado = {
      q: p.get("q") || "", a: porAssunto[p.get("a")] ? p.get("a") : "", v: VOTO[p.get("v")] ? p.get("v") : "", ord: p.get("ord") === "antiga" ? "antiga" : "recente",
      ano: anosDep.includes(p.get("ano")) ? p.get("ano") : "",
    };
    let limite = 30;

    const campoQ = h("input", { id: "busca-v", type: "search", autocomplete: "off", spellcheck: "false", value: estado.q, placeholder: tx("uma palavra do projeto"), enterkeyhint: "search" });
    const selA = h("select", { id: "dep-a" }, h("option", { value: "" }, tx("Todos os assuntos")), slugs.map((x) => h("option", { value: x }, nomeAssunto[x])));
    const selV = h("select", { id: "dep-v" }, h("option", { value: "" }, tx("Todos os votos")), ORDEM_VOTO.filter((c) => total[c]).map((c) => h("option", { value: c }, VOTO[c].nome)));
    const selOrd = h("select", { id: "dep-ord" }, h("option", { value: "recente" }, tx("Mais recentes primeiro")), h("option", { value: "antiga" }, tx("Mais antigas primeiro")));
    const selAnoDep = h("select", { id: "dep-ano" }, h("option", { value: "" }, tx("Todos os anos")), ...anosDep.map((x) => h("option", { value: x }, x)));
    selA.value = estado.a; selV.value = estado.v; selOrd.value = estado.ord; selAnoDep.value = estado.ano;
    let votosAtuais = [];
    const exportarVotos = botoesExportar("votos-" + dep.id, () => ({
      titulo: tx("Votos de {0} nas votações nominais", dep.nome), gerado_em: meta.gerado_em,
      filtros: { deputado: dep.nome, busca: estado.q || undefined, assunto: estado.a ? nomeAssunto[estado.a] : undefined, voto: estado.v ? VOTO[estado.v].nome : undefined, ano: estado.ano ? Number(estado.ano) : undefined },
      colunas: [["data", tx("Data")], ["votacao", tx("Código da votação")], ["projeto", tx("Projeto")], ["titulo", tx("Título")], ["assunto", tx("Assunto")], ["voto", tx("Voto")], ["resultado_da_votacao", tx("Resultado da votação")]],
      registros: votosAtuais.map(({ v, pr, cod }) => ({ data: v.d, votacao: v.id, projeto: pr.nome, titulo: pr.titulo, assunto: nomeAssunto[pr.a] || null, voto: VOTO[cod].nome, resultado_da_votacao: v.ap ? tx("aprovada") : tx("rejeitada") })),
    }), tx("dos votos desta lista"));
    const limpar = h("button", { type: "button", class: "botao botao--leve botao--pequeno", id: "limpar-d" }, tx("Limpar filtros"));
    const estadoTxt = h("p", { class: "estado", role: "status", "aria-live": "polite" });
    const tabelaBox = h("div", { class: "tabela-rolavel", tabindex: "0", role: "region", "aria-label": tx("Votos por assunto") });
    const lista = h("ul", { class: "votos-dep" });
    const vazioLista = h("div", {});
    const maisBox = h("div", { class: "mais" });

    const partidoAgora = [dep.partido, dep.uf].filter(Boolean).join(" · ");
    const historico = arq.pt && arq.pt.length > 1 ? tx("Nas votações, apareceu nos partidos: {0} (do mais antigo ao mais recente).", arq.pt.join(", ")) : null;

    const temVotos = votos.length > 0;
    const placar = placarVotos(total, (cod) => { selV.value = selV.value === cod ? "" : cod; atualizar(true); });

    const maisOpcoes = h("details", { class: "ajuda mais-filtros" },
      h("summary", {}, tx("Mais opções")),
      h("div", { class: "filtros__linha" },
        h("div", { class: "campo campo--curto" }, h("label", { for: "dep-ano" }, tx("Ano")), selAnoDep),
        h("div", { class: "campo campo--curto" }, h("label", { for: "dep-ord" }, tx("Ordem")), selOrd)));
    maisOpcoes.open = !!estado.ano;
    const conteudo = h("div", { class: "miolo" },
      h("nav", { class: "migalhas", "aria-label": tx("Você está em") },
        h("ol", {}, h("li", {}, h("a", { href: "#/deputados" }, tx("Deputados"))), h("li", { "aria-current": "page" }, dep.nome))),
      h("header", { class: "cabeca-dep" },
        fotoDeputado(dep.id),
        h("div", {},
          h("h1", { id: "titulo-deputado", tabindex: "-1" }, dep.nome),
          h("p", { class: "cabeca-dep__sub" }, partidoAgora, dep.ex ? "" : tx(" · não está em exercício agora")),
          historico ? h("p", { class: "nota" }, historico) : null,
          h("p", { class: "cabeca-projeto__acoes", style: "margin-top:1rem" }, botaoCompartilhar("deputado/" + dep.id, tx("{0}: Voto de Verdade", dep.nome))))),
      temVotos
        ? h("section", { "aria-labelledby": "resumo-dep" },
            h("h2", { id: "resumo-dep" }, tx("Votos registrados")),
            placar,
            h("p", { class: "nota" }, tx("{0} com voto registrado, de {1} a {2}. Votações simbólicas e votações em que o deputado faltou não aparecem. Toque em um número para ver só aquele voto.", plural(votos.length, tx("votação nominal"), tx("votações nominais")), data(meta.de), data(meta.ate))),
            total.P ? h("p", { class: "nota" }, tx("“Presidia a sessão”: quem conduz a sessão só vota em casos especiais. Nesses casos o registro aparece assim, e não como sim ou não.")) : null)
        : estadoVazio({
            icone: "v-urna", titulo: tx("Sem voto registrado nas votações nominais"),
            texto: tx("Não há voto deste deputado nas votações nominais do período. Isso pode acontecer com quem assumiu o mandato há pouco tempo ou não esteve nas votações em que o voto de cada um fica registrado."),
            acoes: [{ rotulo: tx("Procurar outro deputado"), href: "#/deputados" }] }));

    if (temVotos) {
      conteudo.append(
        h("section", { class: "bloco", "aria-labelledby": "lista-dep" },
          h("h2", { id: "lista-dep" }, tx("Como votou")),
          h("form", { class: "filtros filtros--compacto", role: "search", "aria-label": tx("Filtrar os votos de {0}", dep.nome), onsubmit: (e) => e.preventDefault() },
            h("div", { class: "filtros__linha filtros__linha--3" },
              h("div", { class: "campo" }, h("label", { for: "busca-v" }, tx("Procurar nos projetos")), campoQ),
              h("div", { class: "campo" }, h("label", { for: "dep-a" }, tx("Assunto")), selA),
              h("div", { class: "campo" }, h("label", { for: "dep-v" }, tx("Voto")), selV)),
            maisOpcoes,
            h("div", { class: "filtros__rodape" }, limpar)),
          estadoTxt, h("div", { class: "lista-acoes" }, exportarVotos), lista, vazioLista, maisBox,
          h("details", { class: "ajuda ajuda--solta" },
            h("summary", {}, tx("Ver os votos por assunto")),
            h("p", { class: "nota" }, tx("Conta pelo assunto principal de cada projeto. Escolha um assunto para ver só os votos nele.")),
            tabelaBox),
          h("p", { class: "nota" }, tx("Votar sim ou não não diz, sozinho, se o deputado apoia o assunto do projeto: muitas votações são sobre emendas ou pontos separados do texto. Abra o projeto para ler o que foi votado."))));
    }
    principal.replaceChildren(conteudo);
    {
      const sigla = [dep.partido, dep.uf].filter(Boolean).join(" · ");
      let t = dep.nome;
      for (const parte of [sigla ? ` (${sigla})` : "", tx(": votos na Câmara"), " | Voto de Verdade"]) if (t.length + parte.length <= 60) t += parte;
      document.title = t;
    }

    function desenharTabela() {
      tabelaBox.replaceChildren(h("table", { class: "tabela-partidos" },
        h("caption", { class: "so-leitor" }, tx("Votos por assunto")),
        h("thead", {}, h("tr", {}, h("th", { scope: "col" }, tx("Assunto")), h("th", { scope: "col", class: "num" }, tx("Sim")), h("th", { scope: "col", class: "num" }, tx("Não")),
          h("th", { scope: "col", class: "num" }, tx("Outros")), h("th", { scope: "col", class: "num" }, tx("Total")))),
        h("tbody", {}, slugs.map((sl) => {
          const t = porAssunto[sl], ativo = estado.a === sl;
          return h("tr", { class: ativo ? "ativa" : null },
            h("th", { scope: "row" },
              h("button", { type: "button", class: "escolha-assunto", "aria-pressed": ativo ? "true" : "false", onclick: () => { selA.value = ativo ? "" : sl; atualizar(true); } }, nomeAssunto[sl]),
              h("span", { class: "barra-voto barra-voto--fina", "aria-hidden": "true" },
                h("i", { class: "seg-S", style: `width:${(t.S / t.n) * 100}%` }), h("i", { class: "seg-N", style: `width:${(t.N / t.n) * 100}%` }), h("i", { class: "seg-O", style: `width:${(t.O / t.n) * 100}%` }))),
            h("td", { class: "num" }, t.S), h("td", { class: "num" }, t.N), h("td", { class: "num" }, t.O), h("td", { class: "num" }, t.n));
        }))));
    }

    function atualizar(reiniciar) {
      if (reiniciar) limite = 30;
      estado.q = campoQ.value.trim(); estado.a = selA.value; estado.v = selV.value; estado.ord = selOrd.value; estado.ano = selAnoDep.value;
      gravarEndereco("deputado/" + id, limparParams({ q: estado.q, a: estado.a, v: estado.v, ano: estado.ano, ord: estado.ord === "recente" ? "" : estado.ord }));
      desenharTabela();
      placar.marcar(estado.v);
      const ts = termos(estado.q);
      const r = votos.filter((x) => (!ts.length || casa(x._t, ts)) && (!estado.a || x.pr.a === estado.a) && (!estado.v || x.cod === estado.v) && (!estado.ano || x.v.d.startsWith(estado.ano)));
      votosAtuais = r;
      r.sort((x, y) => (estado.ord === "recente" ? (y.v.d > x.v.d ? 1 : y.v.d < x.v.d ? -1 : 0) : (x.v.d > y.v.d ? 1 : x.v.d < y.v.d ? -1 : 0)) || (x.v.id < y.v.id ? -1 : 1));
      const mostrados = r.slice(0, limite);
      lista.replaceChildren(...mostrados.map(({ v, pr, cod }) => h("li", {},
        h("a", { class: "voto-dep", href: "#/projeto/" + pr.id + "?votacao=" + encodeURIComponent(v.id) },
          h("span", { class: "voto-dep__titulo" }, pr.titulo),
          h("span", { class: "voto-dep__meta" }, `${pr.nome} · ${data(v.d)} · ${nomeAssunto[pr.a] || ""}`),
          fichaVoto(cod)))));
      anunciar(estadoTxt, r.length ? `${plural(r.length, tx("votação"), tx("votações"))}${r.length !== votos.length ? tx(" de {0}", num(votos.length)) : ""}`
        : tx("Nenhuma votação com esses filtros. Tire algum filtro ou use outra palavra."));
      vazioLista.replaceChildren(...(r.length ? [] : [estadoVazio({
        icone: "v-filtro", titulo: tx("Nenhuma votação com esses filtros"),
        texto: tx("{0} não tem voto registrado com essa combinação de palavra, assunto e voto. Tire algum filtro ou use outra palavra.", dep.nome),
        acoes: [{ rotulo: tx("Limpar filtros"), onclick: () => limpar.click() }] })]));
      limpar.hidden = !(estado.q || estado.a || estado.v || estado.ano);
      maisBox.replaceChildren();
      if (r.length > mostrados.length) {
        maisBox.append(h("button", { type: "button", class: "botao botao--leve", onclick: () => { limite += 30; atualizar(false); } },
          tx("Mostrar mais {0} votações", Math.min(30, r.length - mostrados.length))));
      }
    }
    if (temVotos) {
      comEspera(campoQ, () => atualizar(true));
      for (const el of [selA, selV, selOrd, selAnoDep]) el.addEventListener("change", () => atualizar(true));
      limpar.addEventListener("click", () => { campoQ.value = ""; selA.value = ""; selV.value = ""; selAnoDep.value = ""; atualizar(true); campoQ.focus(); });
      atualizar(true);
    }
    return document.getElementById("titulo-deputado");
  }

  // ------------------------------------------------------------------ apoie (doação única, por serviço de terceiros)
  function telaApoie() {
    const servico = CONFIG.servico || tx("serviço de pagamento");
    principal.replaceChildren(h("div", { class: "miolo texto-longo" },
      h("nav", { class: "migalhas", "aria-label": tx("Você está em") }, h("ol", {}, h("li", {}, h("a", { href: "#/" }, tx("Início"))), h("li", { "aria-current": "page" }, tx("Apoie")))),
      h("h1", { id: "titulo-apoie", tabindex: "-1" }, tx("Apoie o Voto de Verdade")),
      h("p", {}, tx("O Voto de Verdade é gratuito e não tem anúncios. Se ele foi útil para você, pode fazer uma doação no valor que quiser. Ela é única: o {0} oferece a opção de repetir todo mês, mas só vale se você marcar. Para doar, você não precisa preencher e-mail nem mensagem.", servico)),
      h("p", { class: "apoie__acao" },
        h("a", { class: "botao", href: soHttps(CONFIG.doacao), target: "_blank", rel: "noopener noreferrer" }, tx("Fazer uma doação"))),
      h("p", { class: "nota" }, tx("O {0} abre em outra aba. É outro site, com regras e política de privacidade próprias. Quem mantém o Voto de Verdade recebe de lá só o que você optar por informar e não vê os dados do seu cartão. O aviso de que não usamos cookies nem rastreio vale para este site, não para o {1}.", servico, servico)),
      h("h2", {}, tx("O que a doação não muda")),
      h("p", {}, tx("O site continua neutro e apartidário, sem nota e sem ranking. Quem doa não escolhe o que aparece, não ganha destaque e não influencia os resumos. Não é doação a uma associação ou ONG: o site é mantido por uma pessoa e a doação não dá direito a abatimento de imposto.")),
      h("h2", {}, tx("Para onde vai o dinheiro")),
      h("p", {}, tx("Primeiro, para cobrir os custos do site: a inteligência artificial (que classifica os projetos por assunto, escreve os títulos e os resumos em linguagem simples, lista os pontos principais e avisa quando tem dúvida) e o endereço do site (domínio). O que sobrar ajuda a pagar o trabalho de desenvolvimento e manutenção, que é feito por uma pessoa só. Doar não muda nada no site: ele continua igual e gratuito para todos.")),
      h("p", {}, h("a", { href: "#/" }, tx("Voltar ao início")))));
    document.title = tx("Apoie o Voto de Verdade");
    return document.getElementById("titulo-apoie");
  }

  const NAO_ENCONTRADA = {
    projeto: { titulo: tx("Não achamos este projeto"), texto: tx("O número pode estar errado, ou este projeto não teve votação de mérito no plenário desde 1º de fevereiro de 2023. Só esses projetos estão aqui."), acoes: [{ rotulo: tx("Buscar um projeto ou ver os assuntos"), href: "#/" }, { rotulo: tx("Procurar um deputado"), href: "#/deputados" }] },
    assunto: { titulo: tx("Não achamos este assunto"), texto: tx("O endereço pode estar errado. Os assuntos disponíveis estão na página inicial."), acoes: [{ rotulo: tx("Ver todos os assuntos"), href: "#/" }] },
    deputado: { titulo: tx("Não achamos este deputado"), texto: tx("O endereço pode estar errado, ou a pessoa não foi deputada federal no período coberto (desde 1º de fevereiro de 2023). Procure pelo nome na lista."), acoes: [{ rotulo: tx("Procurar um deputado"), href: "#/deputados" }] },
    votacao: { titulo: tx("Não achamos esta votação"), texto: tx("O endereço pode estar errado. Procure o projeto pelo assunto ou por uma palavra."), acoes: [{ rotulo: tx("Buscar um projeto"), href: "#/" }] },
    pagina: { titulo: tx("Não achamos esta página"), texto: tx("O endereço pode estar errado ou a página não existe mais."), acoes: [{ rotulo: tx("Ver todos os assuntos"), href: "#/" }, { rotulo: tx("Procurar um deputado"), href: "#/deputados" }, { rotulo: tx("Como o site funciona"), href: "#/sobre" }] },
  };
  function telaNaoEncontrada(tipo = "pagina") {
    const t = NAO_ENCONTRADA[tipo] || NAO_ENCONTRADA.pagina;
    principal.replaceChildren(h("div", { class: "miolo" },
      h("h1", { id: "titulo-nao", tabindex: "-1" }, t.titulo),
      estadoVazio({ icone: "v-mapa", titulo: tx("Nada aqui"), texto: t.texto, acoes: t.acoes, pagina: true })));
    document.title = tx("{0}: Voto de Verdade", t.titulo);
    return document.getElementById("titulo-nao");
  }

  // ------------------------------------------------------------------ rotas
  // O link do outro idioma leva à mesma tela: o endereço da versão pronta, ou a raiz do outro idioma com a rota (#/...) de agora.
  function ajustarTrocaDeIdioma() {
    for (const a of document.querySelectorAll("a[data-idioma]")) {
      const raiz = new URL(RAIZ + (a.dataset.idioma === "en" ? "en/" : ""), location.href).href;
      a.href = raiz + (location.hash ? "" : CONFIG.rota ? CONFIG.rota + "/" : "") + location.hash;
    }
  }

  async function rotear(moverFoco) {
    ajustarTrocaDeIdioma();
    if (location.hash === "#conteudo") { principal.focus(); return; }
    const { partes, p } = lerRota();
    const emDeputados = partes[0] === "deputados" || partes[0] === "deputado";
    const emPainel = partes[0] === "em-numeros";
    const emIa = partes[0] === "inteligencia-artificial";
    const emAssuntos = !emDeputados && !emPainel && !emIa;
    for (const [id, ativo] of [["nav-assuntos", emAssuntos], ["nav-deputados", emDeputados], ["nav-numeros", emPainel], ["nav-ia", emIa], ["menu-assuntos", emAssuntos], ["menu-deputados", emDeputados], ["menu-numeros", emPainel], ["menu-ia", emIa]]) {
      const a = document.getElementById(id);
      if (!a) continue;
      if (ativo) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    }
    let titulo;
    try {
      if (!partes.length) titulo = await telaInicio(p);
      else if (partes[0] === "assunto" && partes[1]) titulo = await telaAssunto(partes[1], p);
      else if (partes[0] === "projeto" && partes[1]) titulo = await telaProjeto(partes[1], p);
      else if (partes[0] === "votacao" && partes[1]) titulo = await telaVotacao(partes[1], p);
      else if (partes[0] === "sobre") titulo = await telaSobre();
      else if (partes[0] === "em-numeros") titulo = partes[1] ? await telaTabelaNumeros(partes[1], "numeros", p) : await telaPainel(p);
      else if (partes[0] === "inteligencia-artificial") titulo = partes[1] ? await telaTabelaNumeros(partes[1], "ia", p) : await telaIA();
      else if (partes[0] === "apoie" && soHttps(CONFIG.doacao)) titulo = telaApoie();
      else if (partes[0] === "deputados") titulo = await telaDeputados(p);
      else if (partes[0] === "deputado" && partes[1]) titulo = await telaDeputado(partes[1], p);
      else titulo = telaNaoEncontrada();
    } catch (e) {
      console.error(e);
      principal.replaceChildren(h("div", { class: "miolo" },
        h("h1", { tabindex: "-1", id: "titulo-erro" }, tx("Não foi possível carregar os dados")),
        estadoVazio({ icone: "v-erro", titulo: tx("Algo impediu a página de carregar"), texto: tx("Verifique sua conexão e tente de novo. Se continuar assim, volte mais tarde: o problema pode estar no site."),
          acoes: [{ rotulo: tx("Tentar de novo"), onclick: () => location.reload() }, { rotulo: tx("Ir para o início"), href: "#/" }], pagina: true })));
      titulo = document.getElementById("titulo-erro");
    }
    if (moverFoco && titulo) {
      titulo.focus({ preventScroll: true });
      const voltou = !clicou && posicoes[location.hash] != null;
      window.scrollTo(0, voltou ? posicoes[location.hash] : 0);
    }
    clicou = false;
  }

  // ------------------------------------------------------------------ ferramentas para agentes de IA (WebMCP)
  // Em navegadores com WebMCP, um agente pode consultar os dados sem mexer na tela. Todas só leem.
  (function ferramentasParaAgentes() {
    const mc = document.modelContext;
    if (!mc || typeof mc.registerTool !== "function") return;
    const AVISO = tx("Assunto e resumo são feitos por inteligência artificial e podem conter erros. O site não dá nota nem faz ranking de deputados; votar sim ou não numa votação não diz, sozinho, se o deputado apoia o assunto.");
    const pagina = (caminho) => new URL(PAGINAS + caminho + "/", location.href).href;
    const lim = (n, padrao) => Math.max(1, Math.min(50, Number.isFinite(n) ? n : padrao));
    const avisos = (p) => [(p.ca && p.ca !== "alta") ? (p.aa || tx("Dúvida da inteligência artificial sobre o assunto.")) : null,
                           (p.cr && p.cr !== "alta") ? (p.ar || tx("Dúvida da inteligência artificial sobre o resumo.")) : null].filter(Boolean);
    const registrar = (def) => {
      try {
        const r = mc.registerTool({ ...def, annotations: { readOnlyHint: true, untrustedContentHint: false } });
        if (r && r.catch) r.catch((e) => console.warn("WebMCP:", e));
      } catch (e) { console.warn("WebMCP:", e); }
    };

    registrar({
      name: "listar_assuntos",
      description: tx("Lista os assuntos em que os projetos votados na Câmara dos Deputados estão organizados, com a quantidade de projetos de cada um."),
      inputSchema: { type: "object", properties: {} },
      async execute() {
        const lista = await dados("assuntos");
        return { assuntos: lista.map((x) => ({ slug: x.slug, nome: x.nome, descricao: x.descricao, projetos: x.n, com_voto_de_cada_deputado: x.n_ind, pagina: pagina("assunto/" + x.slug) })), aviso: AVISO };
      },
    });

    registrar({
      name: "buscar_projetos",
      description: tx("Procura projetos votados na Câmara dos Deputados por palavras do título, resumo ou tema. Devolve os mais recentes primeiro."),
      inputSchema: {
        type: "object",
        properties: {
          consulta: { type: "string", description: tx("Palavras para procurar, por exemplo: aposentadoria, aluguel, vacina.") },
          assunto: { type: "string", description: tx("Opcional. Slug do assunto, como saude ou educacao (veja listar_assuntos).") },
          so_com_voto_de_cada_deputado: { type: "boolean", description: tx("Opcional. Se verdadeiro, só projetos em que o voto de cada deputado foi registrado.") },
          limite: { type: "number", description: tx("Quantos projetos devolver, de 1 a 50. Padrão 10.") },
        },
      },
      async execute({ consulta = "", assunto = "", so_com_voto_de_cada_deputado = false, limite } = {}) {
        const todos = await projetosComTexto();
        const ts = termos(consulta);
        const achados = todos.filter((p) => (!ts.length || casa(p._t, ts)) && (!assunto || p.a === assunto || p.s === assunto) && (!so_com_voto_de_cada_deputado || p.ind))
          .sort((x, y) => (y.ultima > x.ultima ? 1 : -1));
        return {
          total: achados.length,
          projetos: achados.slice(0, lim(limite, 10)).map((p) => ({
            id: p.id, nome: p.nome, titulo: p.titulo, resumo: p.resumo, assunto: p.a, ultima_votacao: p.ultima, aprovada: p.aprovada,
            tem_voto_de_cada_deputado: p.ind, tipo_de_votacao: p.tipo, avisos: avisos(p), pagina: pagina("projeto/" + p.id), texto_oficial: p.texto || null })),
          aviso: AVISO,
        };
      },
    });

    registrar({
      name: "votos_do_projeto",
      description: tx("Mostra o placar e como cada deputado votou num projeto (votação nominal). Se o projeto só teve votação simbólica ou secreta, explica que não há voto individual."),
      inputSchema: {
        type: "object",
        properties: {
          projeto_id: { type: "string", description: tx("O id do projeto, como vem em buscar_projetos.") },
          votacao_id: { type: "string", description: tx("Opcional. Id de uma votação específica; sem ele, usa a mais recente com voto de cada deputado.") },
          voto: { type: "string", enum: ["S", "N", "A", "O", "P"], description: tx("Opcional. Só os deputados com este voto: S sim, N não, A abstenção, O obstrução, P presidia a sessão.") },
        },
        required: ["projeto_id"],
      },
      async execute({ projeto_id, votacao_id, voto } = {}, { signal } = {}) {
        const [todos, vots, deputados] = await Promise.all([projetosComTexto(), indiceVotacoes(), dados("deputados")]);
        const p = todos.find((x) => String(x.id) === String(projeto_id));
        if (!p) return { error: tx("Projeto {0} não encontrado. Use buscar_projetos para achar o id.", projeto_id) };
        const minhas = (vots.porProjeto[p.id] || []).slice().sort((x, y) => (x.d < y.d ? -1 : 1));
        const nominais = minhas.filter((v) => v.t === "nominal");
        const v = votacao_id ? minhas.find((x) => x.id === votacao_id) : nominais[nominais.length - 1];
        if (!v || v.t !== "nominal") {
          return { projeto: p.titulo, pagina: pagina("projeto/" + p.id),
            observacao: tx("Este projeto não teve votação nominal: na votação simbólica ou secreta o voto de cada deputado não é registrado."),
            votacoes: minhas.map((x) => ({ id: x.id, data: x.d, tipo: x.t, aprovada: x.ap })) };
        }
        const r = await fetch(RAIZ + "dados/votacoes/" + v.id + ".json", { signal });
        if (!r.ok) return { error: tx("Não consegui carregar os votos desta votação.") };
        const arq = await r.json();
        const nomes = Object.fromEntries(deputados.map((d) => [d.id, d]));
        const NOME = NOME_VOTO;
        const grupos = {};
        for (const [did, cod, partido] of arq.v) {
          if (voto && cod !== voto) continue;
          (grupos[NOME[cod]] = grupos[NOME[cod]] || []).push(`${(nomes[did] || {}).nome || tx("Deputado {0}", did)} (${partido || (nomes[did] || {}).partido || "?"}-${(nomes[did] || {}).uf || "?"})`);
        }
        for (const k in grupos) grupos[k].sort((x, y) => x.localeCompare(y, LOCALE));
        return { projeto: p.titulo, votacao: { id: v.id, data: v.d, aprovada: v.ap, descricao: v.desc },
          placar: { sim: v.s[0], nao: v.s[1], abstencao: v.s[2], obstrucao: v.s[3], presidia_a_sessao: v.s[4] },
          deputados_por_voto: grupos, outras_votacoes: nominais.filter((x) => x.id !== v.id).map((x) => ({ id: x.id, data: x.d })), pagina: pagina("projeto/" + p.id), aviso: AVISO };
      },
    });

    registrar({
      name: "buscar_deputado",
      description: tx("Procura deputados federais pelo nome, partido ou estado e devolve o id para usar em votos_do_deputado."),
      inputSchema: {
        type: "object",
        properties: {
          nome: { type: "string", description: tx("Parte do nome do deputado.") },
          uf: { type: "string", description: tx("Opcional. Sigla do estado, como GO ou SP.") },
          partido: { type: "string", description: tx("Opcional. Sigla do partido.") },
          limite: { type: "number", description: tx("Quantos devolver, de 1 a 50. Padrão 10.") },
        },
      },
      async execute({ nome = "", uf = "", partido = "", limite } = {}) {
        const lista = await dados("deputados");
        const ts = termos(nome);
        const achados = lista.filter((d) => (!ts.length || casa(semAcento(d.nome), ts)) && (!uf || d.uf === uf.toUpperCase()) && (!partido || semAcento(d.partido) === semAcento(partido)));
        return { total: achados.length, deputados: achados.slice(0, lim(limite, 10)).map((d) => ({ id: d.id, nome: d.nome, partido: d.partido, uf: d.uf, em_exercicio: d.ex, pagina: pagina("deputado/" + d.id) })) };
      },
    });

    registrar({
      name: "votos_do_deputado",
      description: tx("Mostra como um deputado federal votou nas votações nominais, da mais recente para a mais antiga, sem nota e sem ranking."),
      inputSchema: {
        type: "object",
        properties: {
          deputado_id: { type: "number", description: tx("O id do deputado, como vem em buscar_deputado.") },
          consulta: { type: "string", description: tx("Opcional. Palavras para filtrar os projetos.") },
          voto: { type: "string", enum: ["S", "N", "A", "O", "P"], description: tx("Opcional. Só votos deste tipo.") },
          limite: { type: "number", description: tx("Quantos votos devolver, de 1 a 50. Padrão 20.") },
        },
        required: ["deputado_id"],
      },
      async execute({ deputado_id, consulta = "", voto, limite } = {}, { signal } = {}) {
        const [lista, vots, todos] = await Promise.all([dados("deputados"), indiceVotacoes(), projetosComTexto()]);
        const d = lista.find((x) => x.id === Number(deputado_id));
        if (!d) return { error: tx("Deputado {0} não encontrado. Use buscar_deputado para achar o id.", deputado_id) };
        const r = await fetch(RAIZ + "dados/deputados/" + d.id + ".json", { signal });
        if (!r.ok) return { error: tx("Este deputado não tem voto registrado nas votações nominais do período.") };
        const arq = await r.json();
        const porId = Object.fromEntries(todos.map((p) => [p.id, p]));
        const NOME = NOME_VOTO;
        const ts = termos(consulta);
        const itens = arq.v.map(([vid, cod]) => ({ v: vots.porId[vid], cod })).filter((x) => x.v && porId[x.v.p])
          .filter((x) => (!voto || x.cod === voto) && (!ts.length || casa(porId[x.v.p]._t, ts)))
          .sort((x, y) => (y.v.d > x.v.d ? 1 : -1));
        return { deputado: { id: d.id, nome: d.nome, partido: d.partido, uf: d.uf, em_exercicio: d.ex, pagina: pagina("deputado/" + d.id) },
          total_de_votos: itens.length,
          votos: itens.slice(0, lim(limite, 20)).map((x) => ({ data: x.v.d, voto: NOME[x.cod], projeto_id: x.v.p, projeto: porId[x.v.p].nome, titulo: porId[x.v.p].titulo, pagina: pagina("projeto/" + x.v.p) })),
          aviso: AVISO };
      },
    });
  })();

  // Rodapé com a data dos dados, em qualquer página.
  dados("meta").then((meta) => {
    document.getElementById("rodape-dados").textContent =
      tx("Dados da Câmara dos Deputados (Dados Abertos), de {0} a {1}. Atualizado em {2}.", data(meta.de), data(meta.ate), data(meta.gerado_em));
  }).catch(() => {});

  // Nas páginas prontas (projeto/<id>/, deputado/<id>/...), um link do aplicativo abre o site na raiz, com o endereço limpo.
  if (CONFIG.rota) {
    document.addEventListener("click", (e) => {
      const a = e.target.closest && e.target.closest('a[href^="#/"]');
      if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      location.assign(new URL(PAGINAS, location.href).href + a.getAttribute("href"));
    });
  }

  // Voltar com o botão do navegador devolve a pessoa ao ponto da lista onde estava.
  if ("scrollRestoration" in history) history.scrollRestoration = "manual";
  const posicoes = {};
  let clicou = false, temporizador;
  document.addEventListener("click", (e) => {
    if (e.target.closest && e.target.closest('a[href^="#/"]')) { posicoes[location.hash] = window.scrollY; clicou = true; }
  }, true);
  window.addEventListener("scroll", () => { clearTimeout(temporizador); temporizador = setTimeout(() => { posicoes[location.hash] = window.scrollY; }, 120); }, { passive: true });
  // O aviso do selo "beta" e o menu do celular são popovers nativos: fecham sozinhos ao tocar fora, mas não ao seguir um link de dentro.
  document.querySelectorAll("[popover]").forEach((pop) => pop.addEventListener("click", (e) => { if (e.target.closest("a")) pop.hidePopover(); }));
  window.addEventListener("hashchange", () => rotear(true));
  rotear(false);
})();
