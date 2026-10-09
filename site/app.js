/* Voto de Verdade: início, assuntos, projetos (com o voto de cada deputado), deputados e "como funciona".
   JavaScript puro, sem bibliotecas. Os dados vêm de dados/*.json (feitos por site/exportar_dados.py).
   Endereços (hash): #/   #/assunto/<slug>?q=...&todos=1   #/projeto/<id>?votacao=<id>&q=...&pt=PT&uf=GO&v=S
   #/deputados?q=...&pt=PT&uf=GO   #/deputado/<id>?q=...&a=<assunto>&v=S   #/sobre
   As páginas prontas (projeto/<id>/, deputado/<id>/, assunto/<slug>/) são feitas por site/gerar_paginas.py,
   com título e prévia próprios para Google e WhatsApp; elas abrem o mesmo aplicativo (rota inicial no bloco de configuração).
   Os filtros ficam no endereço para poder compartilhar. */
(function () {
  "use strict";

  // Modo escuro: segue o aparelho até a pessoa escolher; a escolha fica só neste navegador.
  (function () {
    const botoes = document.querySelectorAll(".tema");
    if (!botoes.length) return;
    const sistema = window.matchMedia("(prefers-color-scheme: dark)");
    const escuro = () => (document.documentElement.dataset.theme ? document.documentElement.dataset.theme === "dark" : sistema.matches);
    const mostrar = () => botoes.forEach((b) => b.setAttribute("aria-pressed", String(escuro())));
    botoes.forEach((b) => b.addEventListener("click", () => {
      const novo = escuro() ? "light" : "dark";
      document.documentElement.dataset.theme = novo;
      try { localStorage.setItem("tema", novo); } catch (e) { /* sem armazenamento: vale só até recarregar */ }
      mostrar();
    }));
    sistema.addEventListener("change", mostrar);
    mostrar();
  })();

  const principal = document.getElementById("conteudo");
  const memoria = {};
  const POR_PAGINA = 30;
  // Configuração da página (raiz relativa, rota inicial e doação): vem num bloco de dados, não em script embutido.
  const CONFIG = (() => { try { return JSON.parse(document.getElementById("config").textContent) || {}; } catch (e) { return {}; } })();
  const RAIZ = CONFIG.raiz || "";

  // ------------------------------------------------------------------ utilidades
  async function dados(nome) {
    if (memoria[nome]) return memoria[nome];
    if (window.__DADOS__ && window.__DADOS__[nome]) return (memoria[nome] = window.__DADOS__[nome]);
    const r = await fetch(RAIZ + "dados/" + nome + ".json");
    if (!r.ok) throw new Error("Não consegui carregar " + nome);
    return (memoria[nome] = await r.json());
  }

  const semAcento = (t) => (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const formato = new Intl.DateTimeFormat("pt-BR", { day: "numeric", month: "long", year: "numeric" });
  const data = (iso) => (iso ? formato.format(new Date(iso + "T12:00:00")) : "");
  const num = (n) => n.toLocaleString("pt-BR");
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
    const url = new URL(RAIZ + caminho + "/", location.href).href;
    const botao = h("button", { type: "button", class: "botao botao--leve botao--pequeno" }, "Compartilhar");
    const aviso = h("span", { class: "so-leitor", role: "status" });
    botao.addEventListener("click", async () => {
      try {
        if (navigator.share) { await navigator.share({ title: titulo, url }); return; }
      } catch (e) { if (e && e.name === "AbortError") return; }
      let texto;
      try { await navigator.clipboard.writeText(url); texto = "Link copiado"; } catch (e) { texto = "Copie o endereço na barra do navegador"; }
      botao.textContent = texto; anunciar(aviso, texto);
      setTimeout(() => { botao.textContent = "Compartilhar"; anunciar(aviso, ""); }, 2500);
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
    S: { nome: "Sim" }, N: { nome: "Não" }, A: { nome: "Abstenção" }, O: { nome: "Obstrução" }, P: { nome: "Presidia a sessão" },
  };
  const ORDEM_VOTO = ["S", "N", "A", "O", "P"];
  const fichaVoto = (cod) => h("span", { class: "voto voto--" + cod }, VOTO[cod].nome);

  // Números do placar; cada um é um botão que mostra só os deputados com aquele voto.
  function placarVotos(total, aoEscolher) {
    const itens = ORDEM_VOTO.filter((c) => total[c]).map((c) => {
      const conteudo = [h("span", { class: "placar__nome" }, c === "P" ? "Presidia" : VOTO[c].nome), h("span", { class: "placar__num" }, num(total[c]))];
      return h("li", {}, aoEscolher
        ? h("button", { type: "button", class: "placar__item placar__item--" + c, "aria-pressed": "false", "data-voto": c, onclick: () => aoEscolher(c) }, conteudo)
        : h("div", { class: "placar__item placar__item--" + c }, conteudo));
    });
    const lista = h("ul", { class: "placar" }, itens);
    lista.marcar = (cod) => lista.querySelectorAll("button[data-voto]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.voto === cod)));
    return lista;
  }

  // ------------------------------------------------------------------ pedaços reaproveitados
  const TIPO_SEM = { secreta: "Votação secreta", simbolica: "Votação simbólica, sem o voto de cada deputado" };

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
        h("span", {}, `${num(v.s[0])} sim · ${num(v.s[1])} não${outros ? ` · ${num(outros)} ${outros === 1 ? "outro" : "outros"}` : ""}`));
    }
    const resultado = v ? (v.ap ? "Votação aprovada" : "Votação rejeitada") : (pr.aprovada ? "Votação aprovada" : "Votação rejeitada");
    const sem = !v ? TIPO_SEM[pr.tipo] || TIPO_SEM.simbolica : null;
    const href = "#/projeto/" + pr.id + (opc.votacao ? "?votacao=" + encodeURIComponent(opc.votacao.id) : "");
    return h("li", {}, h("a", { class: "proj", href },
      h("span", { class: "proj__titulo" }, pr.titulo),
      h("span", { class: "proj__meta" },
        h("span", {}, data(v ? v.d : pr.ultima)), h("span", {}, resultado), sem && h("span", {}, sem),
        opc.assunto && h("span", {}, opc.assunto),
        incerto && h("span", { class: "selo-aviso" }, "Classificação incerta")),
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
        ? h("div", {}, h("span", { class: "rotulo-ia" }, "Resumo feito por inteligência artificial"), h("p", {}, pr.resumo))
        : h("p", {}, "Ainda não há resumo deste projeto. Leia o texto oficial abaixo."),
      avisos: avisos.length ? h("div", { class: "cartao-aviso" }, h("strong", {}, "Atenção"), avisos) : null,
      substitutivo: pr.subst
        ? h("p", { class: "nota-neutra" }, "O resumo foi feito a partir da ementa do projeto original. Esta votação foi sobre um substitutivo ou emenda, e o texto votado pode ser diferente.")
        : null,
      pontos: pr.pontos && pr.pontos.length ? h("div", {}, h("h3", {}, "Pontos principais"), h("ul", {}, pr.pontos.map((x) => h("li", {}, x)))) : null,
      oficial: h("div", {}, h("h3", {}, `Texto oficial (${pr.nome})`), h("p", { class: "oficial" }, pr.ementa || (pr.ementa === null ? "Não consegui carregar a ementa agora. O texto completo está no site da Câmara." : "Sem ementa.")),
        soHttps(pr.texto) ? h("p", {}, h("a", { href: soHttps(pr.texto), target: "_blank", rel: "noopener noreferrer" }, "Ler o texto completo no site da Câmara")) : null),
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
    return h("div", {}, h("span", { class: "rotulo-ia" }, "Título e resumo feitos por inteligência artificial"), resto ? h("p", {}, resto) : null);
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
        ? h("span", { class: "tile__num" }, h("b", {}, num(a.n_ind)), ` ${a.n_ind === 1 ? "projeto" : "projetos"} com voto de cada deputado`)
        : h("span", { class: "tile__num" }, h("b", {}, num(n)), ` ${n === 1 ? "projeto" : "projetos"}${rotulo ? " " + rotulo : ""}`),
      !rotulo && a.n_ind != null ? h("span", { class: "tile__sub" }, `${num(n)} no total, contando os de votação simbólica`) : null));
  }

  async function telaInicio(p) {
    const [assuntos, meta] = await Promise.all([dados("assuntos"), dados("meta")]);
    const nomes = Object.fromEntries(assuntos.map((x) => [x.slug, x.nome]));
    const estado = { q: p.get("q") || "" };
    let limiteBusca = 8;

    // Sugestão no próprio campo: os assuntos com mais projetos na base.
    const TERMO_CURTO = { "impostos-e-economia": "impostos", "trabalho-e-direitos": "trabalho", "seguranca-publica": "segurança pública", "administracao-publica-e-congresso": "servidores públicos", "relacoes-internacionais-e-defesa": "acordos internacionais" };
    const sugestoes = assuntos.filter((x) => x.slug !== "outros").sort((x, y) => y.n - x.n).slice(0, 3)
      .map((x) => TERMO_CURTO[x.slug] || x.nome.toLowerCase()).join(", ") + "…";
    const campoBusca = h("input", {
      id: "busca", type: "search", name: "q", autocomplete: "off", spellcheck: "false",
      placeholder: sugestoes, value: estado.q, enterkeyhint: "search",
    });
    const estadoTxt = h("p", { class: "estado so-leitor", role: "status", "aria-live": "polite" });
    const resultados = h("div", {});
    const destaques = h("div", {});
    const principios = h("ul", { class: "principios", "aria-label": "O que diferencia o Voto de Verdade" },
      [["p-neutro", "Neutro e apartidário", "Sem ligação com partidos, candidatos ou a Câmara."],
       ["p-sem-nota", "Sem nota e sem ranking", "Não dizemos quem votou certo ou errado."],
       ["p-votado", "Só o que foi votado", "O voto de cada deputado, dos dados oficiais."],
       ["p-sem-rastreio", "Sem cookies nem rastreio", "Não usamos ferramentas que rastreiam quem visita."]]
        .map(([ic, t, d]) => h("li", {}, h("span", { class: "principios__icone" }, icone(ic)), h("strong", {}, t), h("span", { class: "principios__desc" }, d))));

    principal.replaceChildren(
      h("aside", { class: "faixa", "aria-label": "Sobre o projeto" }, h("div", { class: "miolo" }, h("p", {},
        h("strong", {}, "Em beta, em desenvolvimento. "),
        "Nossa meta é aproximar a sociedade do Congresso: transparência e visibilidade para você acompanhar, de forma simples e prática, como seus parlamentares agem. ",
        h("a", { href: "#/sobre" }, "Ver objetivos")))),
      h("div", { class: "miolo" },
      h("section", { class: "heroi", "aria-labelledby": "titulo-inicio" },
        h("h1", { id: "titulo-inicio", tabindex: "-1" }, "Veja como a Câmara votou, assunto por assunto"),
        h("div", { class: "heroi__lado" },
          h("p", { class: "heroi__texto" }, "Escolha um tema e leia o que foi votado, com o voto de cada deputado federal."),
          h("form", { class: "heroi__busca", role: "search", "aria-label": "Procurar assunto ou projeto", onsubmit: (e) => e.preventDefault() },
            h("label", { for: "busca", class: "so-leitor" }, "Procure por um tema ou palavra"), campoBusca),
          h("p", { class: "heroi__link" }, "Já sabe quem? ", h("a", { href: "#/deputados" }, "Procure um deputado pelo nome")))),
      principios, estadoTxt, resultados, destaques,
      h("p", { class: "confianca" },
        `Dados oficiais da Câmara dos Deputados, de ${data(meta.de)} a ${data(meta.ate)}. Assunto e resumo são feitos por inteligência artificial e podem errar; avisamos quando há dúvida. `,
        h("a", { href: "#/sobre" }, "Como o site funciona"))));
    document.title = "Voto de Verdade: como a Câmara dos Deputados votou";

    let versao = 0;
    async function atualizar(reiniciar) {
      if (reiniciar) limiteBusca = 8;
      const minha = ++versao;
      estado.q = campoBusca.value.trim();
      gravarEndereco("", limparParams({ q: estado.q }));
      const ts = termos(estado.q);
      const porNome = (x, y) => (x.nome === "Outros") - (y.nome === "Outros") || x.nome.localeCompare(y.nome, "pt-BR");

      if (!ts.length) {
        const dica = estado.q.length === 1 ? h("p", { class: "nota" }, "Escreva pelo menos duas letras para buscar.") : null;
        resultados.replaceChildren(...[dica, h("section", { class: "secao", "aria-labelledby": "t-assuntos" },
          h("h2", { id: "t-assuntos" }, "Assuntos"),
          h("ul", { class: "tiles" }, assuntos.slice().sort(porNome).map((a) => cartaoTile(a, a.n, null, ""))))].filter(Boolean));
        destaques.hidden = false; principios.hidden = false;
        anunciar(estadoTxt, "");
        return;
      }

      destaques.hidden = true; principios.hidden = true;
      anunciar(estadoTxt, "Procurando…");
      let todos, vots;
      try { [todos, vots] = await Promise.all([projetosComTexto(), indiceVotacoes()]); } catch (e) {
        resultados.replaceChildren(estadoVazio({ icone: "v-erro", titulo: "Não foi possível carregar a busca", texto: "Verifique sua conexão e tente de novo.", acoes: [{ rotulo: "Tentar de novo", onclick: () => atualizar(true) }] }));
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
          h("h2", { id: "t-projetos" }, "Projetos", h("small", {}, `${num(achados.length)} com “${estado.q}”`)),
          h("p", { class: "secao__intro" }, "Os que têm o voto de cada deputado aparecem primeiro."),
          h("ul", { class: "projetos" }, mostrados.map((pr) => linhaProjeto(pr, vots, { assunto: nomes[pr.a] }))),
          achados.length > mostrados.length
            ? h("div", { class: "mais" }, h("button", { type: "button", class: "botao botao--leve", onclick: () => { limiteBusca += 10; atualizar(false); } },
                `Mostrar mais ${Math.min(10, achados.length - mostrados.length)} projetos`))
            : null));
      }
      if (tiles.length) {
        blocos.push(h("section", { class: "secao", "aria-labelledby": "t-assuntos" },
          h("h2", { id: "t-assuntos" }, "Assuntos"),
          h("ul", { class: "tiles" }, tiles.map((a) => contagem[a.slug] ? cartaoTile(a, contagem[a.slug], `com “${estado.q}”`, q) : cartaoTile(a, a.n, null, "")))));
      }
      if (!blocos.length) {
        blocos.push(estadoVazio({
          icone: "v-busca", titulo: `Nada encontrado com “${estado.q}”`,
          texto: "A busca olha o título, o resumo e o assunto dos projetos votados. Tente uma palavra mais simples, como “saúde”, “imposto” ou “escola”. Para achar um deputado, procure pelo nome na lista de deputados.",
          acoes: [
            { rotulo: "Limpar a busca", onclick: () => { campoBusca.value = ""; atualizar(true); campoBusca.focus(); } },
            { rotulo: "Procurar um deputado", href: "#/deputados" }] }));
      }
      resultados.replaceChildren(...blocos);
      anunciar(estadoTxt, achados.length ? `${plural(achados.length, "projeto", "projetos")} com “${estado.q}”` : `Nada encontrado com “${estado.q}”.`);
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
            h("h2", { id: "t-recentes" }, "Últimas votações"),
            h("p", { class: "secao__intro" }, "As mais recentes em que cada deputado votou."),
            lista(recentes)),
          apertadas.length
            ? h("section", { class: "secao", "aria-labelledby": "t-apertadas" },
                h("h2", { id: "t-apertadas" }, "Decididas por pouco"),
                h("p", { class: "secao__intro" }, "Votações em que sim e não ficaram a menos de 15% de diferença."),
                lista(apertadas))
            : null));
      } catch (e) { console.error(e); }
    })();
    return document.getElementById("titulo-inicio");
  }

  // ------------------------------------------------------------------ como o site funciona
  const OBJETIVOS = [
    "Mostrar o que cada deputado votou, em linguagem simples, sem nota e sem ranking.",
    "Organizar os projetos por assunto, para você achar o que importa para a sua vida.",
    "Ser neutro e apartidário, sem dizer quem votou certo ou errado.",
    "Deixar sempre o texto oficial ao lado do resumo, e avisar quando a inteligência artificial tem dúvida.",
    "Ser gratuito, sem anúncios e sem rastrear quem visita, com código aberto.",
  ];
  async function telaSobre() {
    const meta = await dados("meta");
    const pct = Math.round((meta.simbolicas / meta.votacoes) * 100);
    principal.replaceChildren(h("div", { class: "miolo texto-longo" },
      h("nav", { class: "migalhas", "aria-label": "Você está em" }, h("ol", {}, h("li", {}, h("a", { href: "#/" }, "Início")), h("li", { "aria-current": "page" }, "Como o site funciona"))),
      h("h1", { id: "titulo-sobre", tabindex: "-1" }, "Como o site funciona"),
      h("h2", {}, "Uma ferramenta em beta, em desenvolvimento"),
      h("p", {}, "O Voto de Verdade ainda está em desenvolvimento. Pode ter erros, e o que ele mostra e a forma como funciona podem mudar. Em caso de dúvida, confira no texto oficial da Câmara."),
      h("p", {}, "O Voto de Verdade pretende aproximar a sociedade do Congresso, dando transparência e visibilidade à atuação parlamentar, para que o cidadão acompanhe de forma simples e prática como seus parlamentares estão agindo. Para isso, o site busca:"),
      h("ul", {}, ...OBJETIVOS.map((o) => h("li", {}, o))),
      h("h2", {}, "Neutro e apartidário, sem nota e sem ranking"),
      h("p", {}, "Não dá nota, não faz ranking e não diz quem votou certo ou errado. Mostra o que cada deputado votou. Votar sim ou não numa votação não diz, sozinho, se o deputado apoia o assunto do projeto: muitas votações são sobre emendas, substitutivos ou pontos separados do texto."),
      h("h2", {}, "De onde vêm os dados"),
      h("p", {}, `Do portal de Dados Abertos da Câmara dos Deputados. O site mostra ${num(meta.votacoes)} votações em plenário, de ${data(meta.de)} a ${data(meta.ate)}, e é atualizado todos os dias. Quando a Câmara não vota (recesso, período de eleições), não há novidades.`),
      h("h2", {}, "Só a Câmara dos Deputados, por enquanto"),
      h("p", {}, "O site cobre os deputados federais. O Senado, as assembleias estaduais e as câmaras de vereadores não estão aqui."),
      h("h2", {}, "Quais votações o site mostra"),
      h("p", {}, "Um projeto costuma passar por várias votações no plenário. Aqui entram só as que decidem sobre o projeto em si, isto é, aprovar ou rejeitar. Ficam de fora as votações de urgência (que só decidem se o projeto anda mais rápido), de requerimentos, de emendas ou destaques isolados (que votam a mudança de um trecho) e de procedimento. Por isso um projeto que foi votado muitas vezes pode aparecer com uma só votação."),
      h("p", {}, "Às vezes a Câmara vota um substitutivo, um texto novo que troca o original. Essa votação aparece, com um aviso: o resumo foi feito a partir da ementa do projeto original, e o texto votado pode ser diferente."),
      h("h2", {}, "Assunto e resumo são feitos por inteligência artificial"),
      h("p", {}, "Uma inteligência artificial lê o texto oficial de cada projeto, escolhe o assunto e escreve um resumo em linguagem simples. Ela pode errar. Quando a classificação ou o resumo têm dúvida, o projeto mostra um aviso. O texto oficial fica sempre ao lado."),
      h("p", {}, "Ninguém revisa os resumos antes de irem ao ar, e por enquanto o site não tem um canal para pedir correções. Se algo parecer estranho, confira no texto oficial."),
      h("h2", {}, "Por que nem todo projeto mostra o voto de cada deputado"),
      h("p", {}, `${num(meta.simbolicas)} das ${num(meta.votacoes)} votações (${pct}%) foram simbólicas: os partidos chegam a um acordo e o resultado é anunciado sem registrar o voto de cada deputado. Nesses casos não há como saber como cada um votou. Só as ${num(meta.nominais)} votações nominais têm o voto de cada deputado.`),
      h("h2", {}, "O que significa “presidia a sessão”"),
      h("p", {}, "Quem conduz a sessão só vota em situações previstas no regimento (artigo 17). Nos dados da Câmara, o voto de quem presidia aparece com esse registro, e não como sim ou não."),
      h("h2", {}, "Licença e uso do conteúdo"),
      h("p", {}, "O código do site é aberto, com licença MIT. Os textos do site e os resumos feitos por inteligência artificial podem ser copiados e usados por qualquer pessoa, inclusive em matérias, desde que citem o Voto de Verdade e o endereço votodeverdade.com.br (licença CC BY 4.0). Os dados originais são da Câmara dos Deputados, que tem as próprias regras. Pedimos que o conteúdo não seja usado para treinar modelos de inteligência artificial. Consultá-lo para responder perguntas, citando o site, é bem-vindo."),
      h("h2", {}, "Quem faz e privacidade"),
      h("p", {}, "O Voto de Verdade é um site independente, sem ligação com a Câmara dos Deputados, com partidos ou com candidatos. Não usa cookies nem ferramentas que rastreiam quem visita. Se você escolher o modo escuro, só o seu navegador guarda essa escolha."),
      h("p", {}, h("a", { href: "#/" }, "Voltar ao início"))));
    document.title = "Como o site funciona: Voto de Verdade";
    return document.getElementById("titulo-sobre");
  }

  // ------------------------------------------------------------------ página do assunto
  async function telaAssunto(slug, p) {
    const [assuntos, projetos, votacoes] = await Promise.all([dados("assuntos"), projetosComTexto(), indiceVotacoes()]);
    const a = assuntos.find((x) => x.slug === slug);
    if (!a) return telaNaoEncontrada("assunto");
    const base = projetos.filter((x) => x.a === slug || x.s === slug);
    const nInd = base.filter((x) => x.ind).length;

    const estado = {
      q: p.get("q") || "", todos: p.get("todos") === "1" || !nInd,
      ord: p.get("ord") === "antiga" ? "antiga" : "recente",
      res: ["aprovado", "rejeitado"].includes(p.get("res")) ? p.get("res") : "", cert: p.get("cert") === "1",
    };
    let limite = Math.min(600, Math.max(POR_PAGINA, parseInt(p.get("n"), 10) || 0));

    const campoBusca = h("input", { id: "busca-a", type: "search", autocomplete: "off", spellcheck: "false", value: estado.q, placeholder: "uma palavra do projeto", enterkeyhint: "search" });
    const seletorOrd = h("select", { id: "ord-a" }, h("option", { value: "recente" }, "Mais recentes primeiro"), h("option", { value: "antiga" }, "Mais antigos primeiro"));
    const seletorRes = h("select", { id: "res-a" }, h("option", { value: "" }, "Todos"), h("option", { value: "aprovado" }, "Só aprovados"), h("option", { value: "rejeitado" }, "Só rejeitados"));
    seletorOrd.value = estado.ord; seletorRes.value = estado.res;
    const caixaCert = h("input", { type: "checkbox", id: "cert-a" }); caixaCert.checked = estado.cert;
    const abaInd = h("button", { type: "button", class: "aba", id: "aba-ind" });
    const abaTodos = h("button", { type: "button", class: "aba", id: "aba-todos" });
    const estadoTxt = h("p", { class: "estado", role: "status", "aria-live": "polite" });
    const lista = h("ul", { class: "projetos" });
    const maisBox = h("div", { class: "mais" });
    const vazio = h("div", { class: "vazio" });

    principal.replaceChildren(h("div", { class: "miolo" },
      h("nav", { class: "migalhas", "aria-label": "Você está em" },
        h("ol", {}, h("li", {}, h("a", { href: "#/" }, "Assuntos")), h("li", { "aria-current": "page" }, a.nome))),
      h("header", { class: "cabeca-assunto cabeca-assunto--cor", style: estiloAssunto(slug) },
        h("span", { class: "cabeca-assunto__icone" }, icone(slug)),
        h("div", {},
          h("h1", { id: "titulo-assunto", tabindex: "-1" }, a.nome),
          h("p", {}, a.descricao.charAt(0).toUpperCase() + a.descricao.slice(1) + "."))),
      h("p", { class: "guia-votacao" },
        h("strong", {}, "Votação simbólica: "), "os partidos chegam a um acordo e o resultado é anunciado sem registrar o voto de cada deputado. Por isso só os projetos da aba “Com voto de cada deputado” mostram como cada um votou; “Todos os projetos” inclui também os votados de forma simbólica ou secreta."),
      h("div", { class: "abas", role: "group", "aria-label": "Quais projetos mostrar" }, abaInd, abaTodos),
      h("form", { class: "filtros filtros--compacto", role: "search", "aria-label": `Procurar em ${a.nome}`, onsubmit: (e) => e.preventDefault() },
        h("div", { class: "campo" }, h("label", { for: "busca-a" }, "Procurar neste assunto"), campoBusca),
        h("details", { class: "ajuda mais-filtros" },
          h("summary", {}, "Mais filtros"),
          h("div", { class: "filtros__linha" },
            h("div", { class: "campo" }, h("label", { for: "res-a" }, "Resultado da votação"), seletorRes),
            h("div", { class: "campo" }, h("label", { for: "ord-a" }, "Ordem"), seletorOrd)),
          h("label", { class: "marcar", for: "cert-a" }, caixaCert, h("span", {}, "Esconder projetos com aviso de possível erro")))),
      estadoTxt, lista, vazio, maisBox,
      h("div", { class: "mais" }, botaoCompartilhar("assunto/" + slug, `${a.nome}: Voto de Verdade`))));
    document.title = `${a.nome}: Voto de Verdade`;

    function atualizar(reiniciar) {
      if (reiniciar) limite = POR_PAGINA;
      estado.q = campoBusca.value.trim(); estado.ord = seletorOrd.value; estado.res = seletorRes.value; estado.cert = caixaCert.checked;
      gravarEndereco("assunto/" + slug, limparParams({
        q: estado.q, todos: estado.todos && nInd ? "1" : "", ord: estado.ord === "recente" ? "" : estado.ord, res: estado.res, cert: estado.cert ? "1" : "",
        n: limite > POR_PAGINA ? String(limite) : "" }));

      const ts = termos(estado.q);
      const comFiltros = base.filter((x) =>
        (!ts.length || casa(x._t, ts)) && (!estado.res || (estado.res === "aprovado") === x.aprovada) &&
        (!estado.cert || ((x.ca === "alta") && (!x.cr || x.cr === "alta"))));
      const nIndF = comFiltros.filter((x) => x.ind).length;
      abaInd.textContent = `Com voto de cada deputado (${num(nIndF)})`;
      abaTodos.textContent = `Todos os projetos (${num(comFiltros.length)})`;
      abaInd.setAttribute("aria-pressed", String(!estado.todos)); abaTodos.setAttribute("aria-pressed", String(estado.todos));
      abaInd.disabled = !nInd;

      const r = (estado.todos ? comFiltros : comFiltros.filter((x) => x.ind)).slice();
      r.sort((x, y) => (estado.ord === "recente" ? (y.ultima > x.ultima ? 1 : -1) : (x.ultima > y.ultima ? 1 : -1)) || y.id - x.id);
      const mostrados = r.slice(0, limite);
      lista.replaceChildren(...mostrados.map((x) => linhaProjeto(x, votacoes)));
      anunciar(estadoTxt, r.length ? plural(r.length, "projeto", "projetos") : "");
      vazio.replaceChildren();
      if (!r.length) {
        const acoes = [];
        if (!estado.todos && comFiltros.length) {
          acoes.push({ rotulo: `Ver os ${num(comFiltros.length)} projetos, inclusive os sem voto de cada deputado`, onclick: () => { estado.todos = true; atualizar(true); } });
        }
        if (estado.q || estado.res || estado.cert) {
          acoes.push({ rotulo: "Limpar a busca e os filtros", onclick: () => { campoBusca.value = ""; estado.q = ""; estado.res = ""; estado.cert = false; seletorRes.value = ""; caixaCert.checked = false; atualizar(true); } });
        }
        vazio.append(estadoVazio({
          icone: "v-filtro", titulo: "Nenhum projeto com esses filtros",
          texto: !estado.todos && comFiltros.length ? "Nenhum dos projetos com o voto de cada deputado combina com a busca. Os outros foram votados de forma simbólica ou secreta." : "Tire algum filtro ou escreva outra palavra.",
          acoes }));
      }
      maisBox.replaceChildren();
      if (r.length > mostrados.length) {
        maisBox.append(h("button", { type: "button", class: "botao botao--leve", onclick: () => { limite += POR_PAGINA; atualizar(false); } },
          `Mostrar mais ${Math.min(POR_PAGINA, r.length - mostrados.length)} projetos`));
      }
    }

    comEspera(campoBusca, () => atualizar(true));
    for (const el of [seletorOrd, seletorRes, caixaCert]) el.addEventListener("change", () => atualizar(true));
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
    const raiz = h("div", { class: "painel" }, h("p", { class: "nota" }, "Carregando os votos…"));
    montar().catch((e) => {
      console.error(e);
      raiz.replaceChildren(h("p", { class: "nota" }, "Não foi possível carregar os votos desta votação. Recarregue a página e tente de novo."));
    });
    return raiz;

    async function montar() {
      const [deputados, arq] = await Promise.all([dados("deputados"), dados("votacoes/" + v.id)]);
      const porId = Object.fromEntries(deputados.map((d) => [d.id, d]));
      const linhas = arq.v.map(([did, cod, partido]) => {
        const d = porId[did] || { nome: "Deputado " + did, uf: "" };
        return { id: did, nome: d.nome, uf: d.uf || "", partido: partido || d.partido || "", cod, _t: semAcento(d.nome) };
      });
      const total = {}; for (const l of linhas) total[l.cod] = (total[l.cod] || 0) + 1;
      const nTotal = linhas.length;
      const partidos = [...new Set(linhas.map((l) => l.partido))].filter(Boolean).sort((a, b) => a.localeCompare(b, "pt-BR"));
      const ufs = [...new Set(linhas.map((l) => l.uf))].filter(Boolean).sort();
      const p = opc.p || new URLSearchParams();
      const estado = {
        q: p.get("q") || "", pt: partidos.includes(p.get("pt")) ? p.get("pt") : "", uf: ufs.includes(p.get("uf")) ? p.get("uf") : "",
        v: VOTO[p.get("v")] ? p.get("v") : "",
      };
      let limite = 60;
      const id = (x) => `${x}-${n}`;

      const placar = placarVotos(total, (cod) => { selV.value = selV.value === cod ? "" : cod; atualizar(true); });

      const campoQ = h("input", { id: id("q"), type: "search", autocomplete: "off", spellcheck: "false", value: estado.q, placeholder: "nome do deputado", enterkeyhint: "search" });
      const selPt = h("select", { id: id("pt") }, h("option", { value: "" }, "Todos"), partidos.map((x) => h("option", { value: x }, x)));
      const selUf = h("select", { id: id("uf") }, h("option", { value: "" }, "Todos"), ufs.map((x) => h("option", { value: x }, x)));
      const selV = h("select", { id: id("v") }, h("option", { value: "" }, "Todos"), ORDEM_VOTO.filter((c) => total[c]).map((c) => h("option", { value: c }, VOTO[c].nome)));
      selPt.value = estado.pt; selUf.value = estado.uf; selV.value = estado.v;
      const limpar = h("button", { type: "button", class: "botao botao--leve botao--pequeno" }, "Limpar filtros");
      const estadoTxt = h("p", { class: "estado", role: "status", "aria-live": "polite" });
      const lista = h("ul", { class: "deputados" });
      const vazioLista = h("div", {});
      const maisBox = h("div", { class: "mais" });

      const filtros = h("form", { class: "filtros filtros--compacto", role: "search", "aria-label": "Filtrar os votos", onsubmit: (e) => e.preventDefault() },
        h("div", { class: "filtros__linha filtros__linha--4" },
          h("div", { class: "campo campo--nome" }, h("label", { for: id("q") }, "Deputado"), campoQ),
          h("div", { class: "campo" }, h("label", { for: id("pt") }, "Partido"), selPt),
          h("div", { class: "campo" }, h("label", { for: id("uf") }, "Estado"), selUf),
          h("div", { class: "campo campo--so-desktop" }, h("label", { for: id("v") }, "Voto"), selV)),
        h("div", { class: "filtros__rodape" }, limpar));

      const ajudaVotos = h("details", { class: "ajuda ajuda--solta" },
        h("summary", {}, "O que significam abstenção, obstrução e “presidia a sessão”?"),
        h("ul", {},
          h("li", {}, "Abstenção: o deputado esteve presente e escolheu não votar nem sim nem não."),
          h("li", {}, "Obstrução: o deputado ou seu partido age para atrasar ou impedir a votação, em geral não votando."),
          h("li", {}, "Presidia a sessão: quem conduz a sessão só vota em situações previstas no regimento (artigo 17). O registro aparece assim nos dados da Câmara.")));

      raiz.replaceChildren(
        h("div", { class: "painel-topo" },
          h("div", { class: "painel-placar" },
            placar,
            h("p", { class: "nota" }, `${plural(nTotal, "deputado registrou", "deputados registraram")} voto; quem faltou não aparece. Toque em um número para ver só esses deputados.`),
            total.P ? h("p", { class: "nota" }, "“Presidia a sessão”: quem conduz a sessão só vota em casos especiais. Nesses casos o registro aparece assim, e não como sim ou não.") : null)),
        opc.descricao || null,
        h("div", { class: "bloco" }, filtros, estadoTxt, lista, vazioLista, maisBox, ajudaVotos));

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
        const r = filtrar().sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
        const mostrados = r.slice(0, limite);
        placar.marcar(estado.v);
        lista.replaceChildren(...mostrados.map((l) => h("li", { class: "deputado" },
          h("a", { class: "deputado__nome", href: "#/deputado/" + l.id }, l.nome),
          h("span", { class: "deputado__sub" }, [l.partido, l.uf].filter(Boolean).join(" · ")),
          fichaVoto(l.cod))));
        anunciar(estadoTxt, r.length
          ? `${plural(r.length, "deputado", "deputados")}${r.length !== nTotal ? ` de ${num(nTotal)}` : ""}`
          : "Nenhum deputado com esses filtros. Tire algum filtro ou escreva outro nome.");
        vazioLista.replaceChildren(...(r.length ? [] : [estadoVazio({
          icone: "v-filtro", titulo: "Nenhum deputado com esses filtros",
          texto: "Nesta votação, ninguém combina com a busca, o partido, o estado e o voto escolhidos. Tire algum filtro ou escreva outro nome.",
          acoes: [{ rotulo: "Limpar filtros", onclick: () => limpar.click() }] })]));
        limpar.hidden = !filtrando;
        maisBox.replaceChildren();
        if (r.length > mostrados.length) {
          maisBox.append(h("button", { type: "button", class: "botao botao--leve", onclick: () => { limite += 60; atualizar(false); } },
            `Mostrar mais ${Math.min(60, r.length - mostrados.length)} deputados`));
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
        h("p", { class: "nota" }, `${data(v.d)} · Resultado: ${v.ap ? "aprovada" : "rejeitada"}`),
        v.c !== "alta" && v.av ? h("div", { class: "cartao-aviso" }, h("strong", {}, "Atenção"), h("p", {}, v.av)) : null,
        painelVotos(v, { descricao: h("p", { class: "nota registro" }, "Registro oficial da votação: " + v.desc), p: params, gravar: (q) => { q.set("votacao", v.id); gravarEndereco("projeto/" + pr.id, q); } })].filter(Boolean));
    };

    const secaoVotos = h("section", { class: "bloco", "aria-labelledby": "votos-titulo" }, h("h2", { id: "votos-titulo" }, "Como cada deputado votou"));
    if (nominais.length) {
      if (nominais.length > 1) {
        const sel = h("select", { id: "sel-votacao" },
          nominais.slice().reverse().map((v) => h("option", { value: v.id }, `${data(v.d)}: ${descCurta(v.desc)}`)));
        sel.value = atual.id;
        sel.addEventListener("change", () => { const novo = nominais.find((v) => v.id === sel.value); p = new URLSearchParams(); mostrar(novo); gravarEndereco("projeto/" + pr.id, new URLSearchParams({ votacao: novo.id })); });
        secaoVotos.append(h("div", { class: "campo campo--largo" }, h("label", { for: "sel-votacao" }, `Este projeto teve ${nominais.length} votações com o voto de cada deputado. Escolha uma:`), sel));
      }
      secaoVotos.append(caixa);
    } else {
      const secreta = minhas.some((x) => x.t === "secreta");
      secaoVotos.append(estadoVazio(secreta
        ? { icone: "v-urna", titulo: "Votação secreta", texto: "Votação secreta: o voto de cada deputado não é divulgado." }
        : { icone: "v-urna", titulo: "Votação simbólica, sem voto individual", texto: "Votação simbólica: os partidos chegaram a um acordo e o resultado foi anunciado sem registrar o voto de cada deputado. Por isso não há como mostrar como cada um votou." }));
      secaoVotos.append(h("ul", { class: "lista-simples" }, minhas.map((v) => h("li", {}, `${data(v.d)} · ${v.ap ? "Aprovada" : "Rejeitada"}. ${v.desc}`))));
    }
    const partes = blocosProjeto(pr);
    const outrasSimbolicas = nominais.length ? minhas.filter((x) => x.t !== "nominal") : [];

    principal.replaceChildren(h("div", { class: "miolo pagina-projeto" },
      h("nav", { class: "migalhas", "aria-label": "Você está em" },
        h("ol", {},
          h("li", {}, h("a", { href: "#/" }, "Assuntos")),
          assunto ? h("li", {}, h("a", { href: "#/assunto/" + assunto.slug }, assunto.nome)) : null,
          h("li", { "aria-current": "page" }, pr.nome))),
      h("header", { class: "cabeca-projeto" },
        h("h1", { id: "titulo-projeto", tabindex: "-1" }, tituloCompleto(pr)),
        h("p", { class: "cabeca-projeto__meta" }, `${pr.nome} · última votação em ${data(pr.ultima)}`),
        h("div", { class: "cabeca-projeto__acoes" }, botaoCompartilhar("projeto/" + pr.id, `${descCurta(pr.titulo, 90)} | Voto de Verdade`))),
      h("div", { class: "resumo-projeto" }, resumoSemRepetir(pr), partes.avisos, partes.substitutivo),
      h("details", { class: "ajuda ajuda--solta" },
        h("summary", {}, "Pontos principais e texto oficial"),
        h("div", { class: "projeto__corpo" }, partes.pontos, partes.oficial)),
      secaoVotos,
      outrasSimbolicas.length ? h("p", { class: "nota" }, `Este projeto também teve ${outrasSimbolicas.length === 1 ? "uma votação simbólica" : outrasSimbolicas.length + " votações simbólicas"}, sem o voto de cada deputado.`) : null));
    if (nominais.length) mostrar(atual);
    {
      const base = `${pr.nome}: ${descCurta(pr.titulo, 60 - String(pr.nome).length - 2)}`;
      document.title = base.length + 17 <= 62 ? `${base} | Voto de Verdade` : base;
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
    const deputados = await dados("deputados");
    for (const d of deputados) d._t = semAcento(d.nome);
    const partidos = [...new Set(deputados.map((d) => d.partido))].filter(Boolean).sort((a, b) => a.localeCompare(b, "pt-BR"));
    const ufs = [...new Set(deputados.map((d) => d.uf))].filter(Boolean).sort();
    const estado = { q: p.get("q") || "", pt: partidos.includes(p.get("pt")) ? p.get("pt") : "", uf: ufs.includes(p.get("uf")) ? p.get("uf") : "", ex: p.get("ex") === "1" };
    let limite = 60;

    const campoQ = h("input", { id: "busca-d", type: "search", autocomplete: "off", spellcheck: "false", value: estado.q, placeholder: "nome do deputado", enterkeyhint: "search" });
    const selPt = h("select", { id: "dep-pt" }, h("option", { value: "" }, "Todos os partidos"), partidos.map((x) => h("option", { value: x }, x)));
    selPt.value = estado.pt;
    const chips = ufs.map((u) => h("li", {}, h("button", { type: "button", class: "chip-uf", "aria-pressed": "false", "data-uf": u, onclick: () => { estado.uf = estado.uf === u ? "" : u; atualizar(true); } }, u)));
    const caixaEx = h("input", { type: "checkbox", id: "dep-ex" }); caixaEx.checked = estado.ex;
    const estadoTxt = h("p", { class: "estado", role: "status", "aria-live": "polite" });
    const lista = h("ul", { class: "lista-dep" });
    const vazio = h("div", {});
    const maisBox = h("div", { class: "mais" });

    principal.replaceChildren(h("div", { class: "miolo" },
      h("section", { class: "abertura", "aria-labelledby": "titulo-deputados" },
        h("h1", { id: "titulo-deputados", tabindex: "-1" }, "Procure um deputado federal"),
        h("p", { class: "abertura__texto" }, "Veja como cada deputado votou nas votações nominais, as únicas em que o voto de cada um fica registrado. Sem nota e sem ranking.")),
      h("form", { class: "filtros", role: "search", "aria-label": "Procurar deputado", onsubmit: (e) => e.preventDefault() },
        h("div", {}, h("p", { class: "rotulo", id: "rotulo-uf" }, "Deputados do seu estado"), h("ul", { class: "chips-uf", "aria-labelledby": "rotulo-uf" }, chips)),
        h("div", { class: "filtros__linha" },
          h("div", { class: "campo" }, h("label", { for: "busca-d" }, "Nome"), campoQ),
          h("div", { class: "campo" }, h("label", { for: "dep-pt" }, "Partido"), selPt)),
        h("label", { class: "marcar", for: "dep-ex" }, caixaEx, h("span", {}, "Só quem está em exercício agora",
          h("small", {}, "Deixe desligado para ver também quem já deixou o cargo ou foi suplente no período.")))),
      estadoTxt, lista, vazio, maisBox));
    document.title = "Deputados: Voto de Verdade";

    function atualizar(reiniciar) {
      if (reiniciar) limite = 60;
      estado.q = campoQ.value.trim(); estado.pt = selPt.value; estado.ex = caixaEx.checked;
      gravarEndereco("deputados", limparParams({ q: estado.q, pt: estado.pt, uf: estado.uf, ex: estado.ex ? "1" : "" }));
      for (const b of principal.querySelectorAll(".chip-uf")) b.setAttribute("aria-pressed", String(b.dataset.uf === estado.uf));
      const ts = termos(estado.q);
      const r = deputados.filter((d) => (!ts.length || casa(d._t, ts)) && (!estado.pt || d.partido === estado.pt) && (!estado.uf || d.uf === estado.uf) && (!estado.ex || d.ex));
      const mostrados = r.slice(0, limite);
      lista.replaceChildren(...mostrados.map((d) => h("li", {}, h("a", { class: "linha-dep", href: "#/deputado/" + d.id },
        h("span", { class: "linha-dep__nome" }, d.nome),
        h("span", { class: "linha-dep__sub" }, [d.partido, d.uf].filter(Boolean).join(" · ") + (d.ex ? "" : " · fora do exercício agora"))))));
      anunciar(estadoTxt, r.length ? `${plural(r.length, "deputado", "deputados")}${r.length !== deputados.length ? ` de ${num(deputados.length)}` : ""}`
        : "Nenhum deputado com esses filtros. Confira a grafia do nome ou tire algum filtro.");
      vazio.replaceChildren(...(r.length ? [] : [estadoVazio({
        icone: "v-pessoa", titulo: "Nenhum deputado com esses filtros",
        texto: estado.ex ? "Confira a grafia do nome ou tire algum filtro. Quem já deixou o cargo só aparece se você desligar “Só quem está em exercício agora”." : "Confira a grafia do nome ou tire algum filtro. A busca ignora acentos e letras maiúsculas.",
        acoes: [{ rotulo: "Limpar filtros", onclick: () => { campoQ.value = ""; selPt.value = ""; caixaEx.checked = false; estado.uf = ""; atualizar(true); campoQ.focus(); } }] })]));
      maisBox.replaceChildren();
      if (r.length > mostrados.length) {
        maisBox.append(h("button", { type: "button", class: "botao botao--leve", onclick: () => { limite += 60; atualizar(false); } },
          `Mostrar mais ${Math.min(60, r.length - mostrados.length)} deputados`));
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
    const slugs = Object.keys(porAssunto).sort((a, b) => (nomeAssunto[a] === "Outros") - (nomeAssunto[b] === "Outros") || nomeAssunto[a].localeCompare(nomeAssunto[b], "pt-BR"));

    const estado = {
      q: p.get("q") || "", a: porAssunto[p.get("a")] ? p.get("a") : "", v: VOTO[p.get("v")] ? p.get("v") : "", ord: p.get("ord") === "antiga" ? "antiga" : "recente",
    };
    let limite = 30;

    const campoQ = h("input", { id: "busca-v", type: "search", autocomplete: "off", spellcheck: "false", value: estado.q, placeholder: "uma palavra do projeto", enterkeyhint: "search" });
    const selA = h("select", { id: "dep-a" }, h("option", { value: "" }, "Todos os assuntos"), slugs.map((x) => h("option", { value: x }, nomeAssunto[x])));
    const selV = h("select", { id: "dep-v" }, h("option", { value: "" }, "Todos os votos"), ORDEM_VOTO.filter((c) => total[c]).map((c) => h("option", { value: c }, VOTO[c].nome)));
    const selOrd = h("select", { id: "dep-ord" }, h("option", { value: "recente" }, "Mais recentes primeiro"), h("option", { value: "antiga" }, "Mais antigas primeiro"));
    selA.value = estado.a; selV.value = estado.v; selOrd.value = estado.ord;
    const limpar = h("button", { type: "button", class: "botao botao--leve botao--pequeno", id: "limpar-d" }, "Limpar filtros");
    const estadoTxt = h("p", { class: "estado", role: "status", "aria-live": "polite" });
    const tabelaBox = h("div", { class: "tabela-rolavel", tabindex: "0", role: "region", "aria-label": "Votos por assunto" });
    const lista = h("ul", { class: "votos-dep" });
    const vazioLista = h("div", {});
    const maisBox = h("div", { class: "mais" });

    const partidoAgora = [dep.partido, dep.uf].filter(Boolean).join(" · ");
    const historico = arq.pt && arq.pt.length > 1 ? `Nas votações, apareceu nos partidos: ${arq.pt.join(", ")} (do mais antigo ao mais recente).` : null;

    const temVotos = votos.length > 0;
    const placar = placarVotos(total, (cod) => { selV.value = selV.value === cod ? "" : cod; atualizar(true); });

    const conteudo = h("div", { class: "miolo" },
      h("nav", { class: "migalhas", "aria-label": "Você está em" },
        h("ol", {}, h("li", {}, h("a", { href: "#/deputados" }, "Deputados")), h("li", { "aria-current": "page" }, dep.nome))),
      h("header", { class: "cabeca-dep" },
        fotoDeputado(dep.id),
        h("div", {},
          h("h1", { id: "titulo-deputado", tabindex: "-1" }, dep.nome),
          h("p", { class: "cabeca-dep__sub" }, partidoAgora, dep.ex ? "" : " · não está em exercício agora"),
          historico ? h("p", { class: "nota" }, historico) : null,
          h("p", { class: "cabeca-projeto__acoes", style: "margin-top:1rem" }, botaoCompartilhar("deputado/" + dep.id, `${dep.nome}: Voto de Verdade`)))),
      temVotos
        ? h("section", { "aria-labelledby": "resumo-dep" },
            h("h2", { id: "resumo-dep" }, "Votos registrados"),
            placar,
            h("p", { class: "nota" }, `${plural(votos.length, "votação nominal", "votações nominais")} com voto registrado, de ${data(meta.de)} a ${data(meta.ate)}. Votações simbólicas e votações em que o deputado faltou não aparecem. Toque em um número para ver só aquele voto.`),
            total.P ? h("p", { class: "nota" }, "“Presidia a sessão”: quem conduz a sessão só vota em casos especiais. Nesses casos o registro aparece assim, e não como sim ou não.") : null)
        : estadoVazio({
            icone: "v-urna", titulo: "Sem voto registrado nas votações nominais",
            texto: "Não há voto deste deputado nas votações nominais do período. Isso pode acontecer com quem assumiu o mandato há pouco tempo ou não esteve nas votações em que o voto de cada um fica registrado.",
            acoes: [{ rotulo: "Procurar outro deputado", href: "#/deputados" }] }));

    if (temVotos) {
      conteudo.append(
        h("section", { class: "bloco", "aria-labelledby": "lista-dep" },
          h("h2", { id: "lista-dep" }, "Como votou"),
          h("form", { class: "filtros filtros--compacto", role: "search", "aria-label": "Filtrar os votos de " + dep.nome, onsubmit: (e) => e.preventDefault() },
            h("div", { class: "filtros__linha filtros__linha--3" },
              h("div", { class: "campo" }, h("label", { for: "busca-v" }, "Procurar nos projetos"), campoQ),
              h("div", { class: "campo" }, h("label", { for: "dep-a" }, "Assunto"), selA),
              h("div", { class: "campo" }, h("label", { for: "dep-v" }, "Voto"), selV)),
            h("details", { class: "ajuda mais-filtros" },
              h("summary", {}, "Mais opções"),
              h("div", { class: "campo campo--curto" }, h("label", { for: "dep-ord" }, "Ordem"), selOrd)),
            h("div", { class: "filtros__rodape" }, limpar)),
          estadoTxt, lista, vazioLista, maisBox,
          h("details", { class: "ajuda ajuda--solta" },
            h("summary", {}, "Ver os votos por assunto"),
            h("p", { class: "nota" }, "Conta pelo assunto principal de cada projeto. Escolha um assunto para ver só os votos nele."),
            tabelaBox),
          h("p", { class: "nota" }, "Votar sim ou não não diz, sozinho, se o deputado apoia o assunto do projeto: muitas votações são sobre emendas ou pontos separados do texto. Abra o projeto para ler o que foi votado.")));
    }
    principal.replaceChildren(conteudo);
    {
      const sigla = [dep.partido, dep.uf].filter(Boolean).join(" · ");
      let t = dep.nome;
      for (const parte of [sigla ? ` (${sigla})` : "", ": votos na Câmara", " | Voto de Verdade"]) if (t.length + parte.length <= 60) t += parte;
      document.title = t;
    }

    function desenharTabela() {
      tabelaBox.replaceChildren(h("table", { class: "tabela-partidos" },
        h("caption", { class: "so-leitor" }, "Votos por assunto"),
        h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Assunto"), h("th", { scope: "col", class: "num" }, "Sim"), h("th", { scope: "col", class: "num" }, "Não"),
          h("th", { scope: "col", class: "num" }, "Outros"), h("th", { scope: "col", class: "num" }, "Total"))),
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
      estado.q = campoQ.value.trim(); estado.a = selA.value; estado.v = selV.value; estado.ord = selOrd.value;
      gravarEndereco("deputado/" + id, limparParams({ q: estado.q, a: estado.a, v: estado.v, ord: estado.ord === "recente" ? "" : estado.ord }));
      desenharTabela();
      placar.marcar(estado.v);
      const ts = termos(estado.q);
      const r = votos.filter((x) => (!ts.length || casa(x._t, ts)) && (!estado.a || x.pr.a === estado.a) && (!estado.v || x.cod === estado.v));
      r.sort((x, y) => (estado.ord === "recente" ? (y.v.d > x.v.d ? 1 : y.v.d < x.v.d ? -1 : 0) : (x.v.d > y.v.d ? 1 : x.v.d < y.v.d ? -1 : 0)) || (x.v.id < y.v.id ? -1 : 1));
      const mostrados = r.slice(0, limite);
      lista.replaceChildren(...mostrados.map(({ v, pr, cod }) => h("li", {},
        h("a", { class: "voto-dep", href: "#/projeto/" + pr.id + "?votacao=" + encodeURIComponent(v.id) },
          h("span", { class: "voto-dep__titulo" }, pr.titulo),
          h("span", { class: "voto-dep__meta" }, `${pr.nome} · ${data(v.d)} · ${nomeAssunto[pr.a] || ""}`),
          fichaVoto(cod)))));
      anunciar(estadoTxt, r.length ? `${plural(r.length, "votação", "votações")}${r.length !== votos.length ? ` de ${num(votos.length)}` : ""}`
        : "Nenhuma votação com esses filtros. Tire algum filtro ou use outra palavra.");
      vazioLista.replaceChildren(...(r.length ? [] : [estadoVazio({
        icone: "v-filtro", titulo: "Nenhuma votação com esses filtros",
        texto: `${dep.nome} não tem voto registrado com essa combinação de palavra, assunto e voto. Tire algum filtro ou use outra palavra.`,
        acoes: [{ rotulo: "Limpar filtros", onclick: () => limpar.click() }] })]));
      limpar.hidden = !(estado.q || estado.a || estado.v);
      maisBox.replaceChildren();
      if (r.length > mostrados.length) {
        maisBox.append(h("button", { type: "button", class: "botao botao--leve", onclick: () => { limite += 30; atualizar(false); } },
          `Mostrar mais ${Math.min(30, r.length - mostrados.length)} votações`));
      }
    }
    if (temVotos) {
      comEspera(campoQ, () => atualizar(true));
      for (const el of [selA, selV, selOrd]) el.addEventListener("change", () => atualizar(true));
      limpar.addEventListener("click", () => { campoQ.value = ""; selA.value = ""; selV.value = ""; atualizar(true); campoQ.focus(); });
      atualizar(true);
    }
    return document.getElementById("titulo-deputado");
  }

  // ------------------------------------------------------------------ apoie (doação única, por serviço de terceiros)
  function telaApoie() {
    const servico = CONFIG.servico || "serviço de pagamento";
    principal.replaceChildren(h("div", { class: "miolo texto-longo" },
      h("nav", { class: "migalhas", "aria-label": "Você está em" }, h("ol", {}, h("li", {}, h("a", { href: "#/" }, "Início")), h("li", { "aria-current": "page" }, "Apoie"))),
      h("h1", { id: "titulo-apoie", tabindex: "-1" }, "Apoie o Voto de Verdade"),
      h("p", {}, `O Voto de Verdade é gratuito e não tem anúncios. Se ele foi útil para você, pode fazer uma doação no valor que quiser. Ela é única: o ${servico} oferece a opção de repetir todo mês, mas só vale se você marcar. Para doar, você não precisa preencher e-mail nem mensagem.`),
      h("p", { class: "apoie__acao" },
        h("a", { class: "botao", href: soHttps(CONFIG.doacao), target: "_blank", rel: "noopener noreferrer" }, "Fazer uma doação")),
      h("p", { class: "nota" }, `O ${servico} abre em outra aba. É outro site, com regras e política de privacidade próprias. Quem mantém o Voto de Verdade recebe de lá só o que você optar por informar e não vê os dados do seu cartão. O aviso de que não usamos cookies nem rastreio vale para este site, não para o ${servico}.`),
      h("h2", {}, "O que a doação não muda"),
      h("p", {}, "O site continua neutro e apartidário, sem nota e sem ranking. Quem doa não escolhe o que aparece, não ganha destaque e não influencia os resumos. Não é doação a uma associação ou ONG: o site é mantido por uma pessoa e a doação não dá direito a abatimento de imposto."),
      h("h2", {}, "Para onde vai o dinheiro"),
      h("p", {}, "Para manter o site no ar. Os principais custos são a inteligência artificial que escreve os resumos dos projetos e o endereço do site (domínio)."),
      h("p", {}, h("a", { href: "#/" }, "Voltar ao início"))));
    document.title = "Apoie o Voto de Verdade";
    return document.getElementById("titulo-apoie");
  }

  const NAO_ENCONTRADA = {
    projeto: { titulo: "Não achamos este projeto", texto: "O número pode estar errado, ou este projeto não teve votação de mérito no plenário desde 1º de fevereiro de 2023. Só esses projetos estão aqui.", acoes: [{ rotulo: "Buscar um projeto ou ver os assuntos", href: "#/" }, { rotulo: "Procurar um deputado", href: "#/deputados" }] },
    assunto: { titulo: "Não achamos este assunto", texto: "O endereço pode estar errado. Os assuntos disponíveis estão na página inicial.", acoes: [{ rotulo: "Ver todos os assuntos", href: "#/" }] },
    deputado: { titulo: "Não achamos este deputado", texto: "O endereço pode estar errado, ou a pessoa não foi deputada federal no período coberto (desde 1º de fevereiro de 2023). Procure pelo nome na lista.", acoes: [{ rotulo: "Procurar um deputado", href: "#/deputados" }] },
    votacao: { titulo: "Não achamos esta votação", texto: "O endereço pode estar errado. Procure o projeto pelo assunto ou por uma palavra.", acoes: [{ rotulo: "Buscar um projeto", href: "#/" }] },
    pagina: { titulo: "Não achamos esta página", texto: "O endereço pode estar errado ou a página não existe mais.", acoes: [{ rotulo: "Ver todos os assuntos", href: "#/" }, { rotulo: "Procurar um deputado", href: "#/deputados" }, { rotulo: "Como o site funciona", href: "#/sobre" }] },
  };
  function telaNaoEncontrada(tipo = "pagina") {
    const t = NAO_ENCONTRADA[tipo] || NAO_ENCONTRADA.pagina;
    principal.replaceChildren(h("div", { class: "miolo" },
      h("h1", { id: "titulo-nao", tabindex: "-1" }, t.titulo),
      estadoVazio({ icone: "v-mapa", titulo: "Nada aqui", texto: t.texto, acoes: t.acoes, pagina: true })));
    document.title = `${t.titulo}: Voto de Verdade`;
    return document.getElementById("titulo-nao");
  }

  // ------------------------------------------------------------------ rotas
  async function rotear(moverFoco) {
    if (location.hash === "#conteudo") { principal.focus(); return; }
    const { partes, p } = lerRota();
    const emDeputados = partes[0] === "deputados" || partes[0] === "deputado";
    for (const [id, ativo] of [["nav-assuntos", !emDeputados], ["nav-deputados", emDeputados]]) {
      const a = document.getElementById(id);
      if (ativo) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    }
    let titulo;
    try {
      if (!partes.length) titulo = await telaInicio(p);
      else if (partes[0] === "assunto" && partes[1]) titulo = await telaAssunto(partes[1], p);
      else if (partes[0] === "projeto" && partes[1]) titulo = await telaProjeto(partes[1], p);
      else if (partes[0] === "votacao" && partes[1]) titulo = await telaVotacao(partes[1], p);
      else if (partes[0] === "sobre") titulo = await telaSobre();
      else if (partes[0] === "apoie" && soHttps(CONFIG.doacao)) titulo = telaApoie();
      else if (partes[0] === "deputados") titulo = await telaDeputados(p);
      else if (partes[0] === "deputado" && partes[1]) titulo = await telaDeputado(partes[1], p);
      else titulo = telaNaoEncontrada();
    } catch (e) {
      console.error(e);
      principal.replaceChildren(h("div", { class: "miolo" },
        h("h1", { tabindex: "-1", id: "titulo-erro" }, "Não foi possível carregar os dados"),
        estadoVazio({ icone: "v-erro", titulo: "Algo impediu a página de carregar", texto: "Verifique sua conexão e tente de novo. Se continuar assim, volte mais tarde: o problema pode estar no site.",
          acoes: [{ rotulo: "Tentar de novo", onclick: () => location.reload() }, { rotulo: "Ir para o início", href: "#/" }], pagina: true })));
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
    const AVISO = "Assunto e resumo são feitos por inteligência artificial e podem conter erros. O site não dá nota nem faz ranking de deputados; votar sim ou não numa votação não diz, sozinho, se o deputado apoia o assunto.";
    const pagina = (caminho) => new URL(RAIZ + caminho + "/", location.href).href;
    const lim = (n, padrao) => Math.max(1, Math.min(50, Number.isFinite(n) ? n : padrao));
    const avisos = (p) => [(p.ca && p.ca !== "alta") ? (p.aa || "Dúvida da inteligência artificial sobre o assunto.") : null,
                           (p.cr && p.cr !== "alta") ? (p.ar || "Dúvida da inteligência artificial sobre o resumo.") : null].filter(Boolean);
    const registrar = (def) => {
      try {
        const r = mc.registerTool({ ...def, annotations: { readOnlyHint: true, untrustedContentHint: false } });
        if (r && r.catch) r.catch((e) => console.warn("WebMCP:", e));
      } catch (e) { console.warn("WebMCP:", e); }
    };

    registrar({
      name: "listar_assuntos",
      description: "Lista os assuntos em que os projetos votados na Câmara dos Deputados estão organizados, com a quantidade de projetos de cada um.",
      inputSchema: { type: "object", properties: {} },
      async execute() {
        const lista = await dados("assuntos");
        return { assuntos: lista.map((x) => ({ slug: x.slug, nome: x.nome, descricao: x.descricao, projetos: x.n, com_voto_de_cada_deputado: x.n_ind, pagina: pagina("assunto/" + x.slug) })), aviso: AVISO };
      },
    });

    registrar({
      name: "buscar_projetos",
      description: "Procura projetos votados na Câmara dos Deputados por palavras do título, resumo ou tema. Devolve os mais recentes primeiro.",
      inputSchema: {
        type: "object",
        properties: {
          consulta: { type: "string", description: "Palavras para procurar, por exemplo: aposentadoria, aluguel, vacina." },
          assunto: { type: "string", description: "Opcional. Slug do assunto, como saude ou educacao (veja listar_assuntos)." },
          so_com_voto_de_cada_deputado: { type: "boolean", description: "Opcional. Se verdadeiro, só projetos em que o voto de cada deputado foi registrado." },
          limite: { type: "number", description: "Quantos projetos devolver, de 1 a 50. Padrão 10." },
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
      description: "Mostra o placar e como cada deputado votou num projeto (votação nominal). Se o projeto só teve votação simbólica ou secreta, explica que não há voto individual.",
      inputSchema: {
        type: "object",
        properties: {
          projeto_id: { type: "string", description: "O id do projeto, como vem em buscar_projetos." },
          votacao_id: { type: "string", description: "Opcional. Id de uma votação específica; sem ele, usa a mais recente com voto de cada deputado." },
          voto: { type: "string", enum: ["S", "N", "A", "O", "P"], description: "Opcional. Só os deputados com este voto: S sim, N não, A abstenção, O obstrução, P presidia a sessão." },
        },
        required: ["projeto_id"],
      },
      async execute({ projeto_id, votacao_id, voto } = {}, { signal } = {}) {
        const [todos, vots, deputados] = await Promise.all([projetosComTexto(), indiceVotacoes(), dados("deputados")]);
        const p = todos.find((x) => String(x.id) === String(projeto_id));
        if (!p) return { error: `Projeto ${projeto_id} não encontrado. Use buscar_projetos para achar o id.` };
        const minhas = (vots.porProjeto[p.id] || []).slice().sort((x, y) => (x.d < y.d ? -1 : 1));
        const nominais = minhas.filter((v) => v.t === "nominal");
        const v = votacao_id ? minhas.find((x) => x.id === votacao_id) : nominais[nominais.length - 1];
        if (!v || v.t !== "nominal") {
          return { projeto: p.titulo, pagina: pagina("projeto/" + p.id),
            observacao: "Este projeto não teve votação nominal: na votação simbólica ou secreta o voto de cada deputado não é registrado.",
            votacoes: minhas.map((x) => ({ id: x.id, data: x.d, tipo: x.t, aprovada: x.ap })) };
        }
        const r = await fetch(RAIZ + "dados/votacoes/" + v.id + ".json", { signal });
        if (!r.ok) return { error: "Não consegui carregar os votos desta votação." };
        const arq = await r.json();
        const nomes = Object.fromEntries(deputados.map((d) => [d.id, d]));
        const NOME = { S: "Sim", N: "Não", A: "Abstenção", O: "Obstrução", P: "Presidia a sessão" };
        const grupos = {};
        for (const [did, cod, partido] of arq.v) {
          if (voto && cod !== voto) continue;
          (grupos[NOME[cod]] = grupos[NOME[cod]] || []).push(`${(nomes[did] || {}).nome || "Deputado " + did} (${partido || (nomes[did] || {}).partido || "?"}-${(nomes[did] || {}).uf || "?"})`);
        }
        for (const k in grupos) grupos[k].sort((x, y) => x.localeCompare(y, "pt-BR"));
        return { projeto: p.titulo, votacao: { id: v.id, data: v.d, aprovada: v.ap, descricao: v.desc },
          placar: { sim: v.s[0], nao: v.s[1], abstencao: v.s[2], obstrucao: v.s[3], presidia_a_sessao: v.s[4] },
          deputados_por_voto: grupos, outras_votacoes: nominais.filter((x) => x.id !== v.id).map((x) => ({ id: x.id, data: x.d })), pagina: pagina("projeto/" + p.id), aviso: AVISO };
      },
    });

    registrar({
      name: "buscar_deputado",
      description: "Procura deputados federais pelo nome, partido ou estado e devolve o id para usar em votos_do_deputado.",
      inputSchema: {
        type: "object",
        properties: {
          nome: { type: "string", description: "Parte do nome do deputado." },
          uf: { type: "string", description: "Opcional. Sigla do estado, como GO ou SP." },
          partido: { type: "string", description: "Opcional. Sigla do partido." },
          limite: { type: "number", description: "Quantos devolver, de 1 a 50. Padrão 10." },
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
      description: "Mostra como um deputado federal votou nas votações nominais, da mais recente para a mais antiga, sem nota e sem ranking.",
      inputSchema: {
        type: "object",
        properties: {
          deputado_id: { type: "number", description: "O id do deputado, como vem em buscar_deputado." },
          consulta: { type: "string", description: "Opcional. Palavras para filtrar os projetos." },
          voto: { type: "string", enum: ["S", "N", "A", "O", "P"], description: "Opcional. Só votos deste tipo." },
          limite: { type: "number", description: "Quantos votos devolver, de 1 a 50. Padrão 20." },
        },
        required: ["deputado_id"],
      },
      async execute({ deputado_id, consulta = "", voto, limite } = {}, { signal } = {}) {
        const [lista, vots, todos] = await Promise.all([dados("deputados"), indiceVotacoes(), projetosComTexto()]);
        const d = lista.find((x) => x.id === Number(deputado_id));
        if (!d) return { error: `Deputado ${deputado_id} não encontrado. Use buscar_deputado para achar o id.` };
        const r = await fetch(RAIZ + "dados/deputados/" + d.id + ".json", { signal });
        if (!r.ok) return { error: "Este deputado não tem voto registrado nas votações nominais do período." };
        const arq = await r.json();
        const porId = Object.fromEntries(todos.map((p) => [p.id, p]));
        const NOME = { S: "Sim", N: "Não", A: "Abstenção", O: "Obstrução", P: "Presidia a sessão" };
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
      `Dados da Câmara dos Deputados (Dados Abertos), de ${data(meta.de)} a ${data(meta.ate)}. Atualizado em ${data(meta.gerado_em)}.`;
  }).catch(() => {});

  // Nas páginas prontas (projeto/<id>/, deputado/<id>/...), um link do aplicativo abre o site na raiz, com o endereço limpo.
  if (RAIZ) {
    document.addEventListener("click", (e) => {
      const a = e.target.closest && e.target.closest('a[href^="#/"]');
      if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      location.assign(new URL(RAIZ, location.href).href + a.getAttribute("href"));
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
  window.addEventListener("hashchange", () => rotear(true));
  rotear(false);
})();
