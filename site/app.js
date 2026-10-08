/* Voto de Verdade: início, página do assunto (com o voto de cada deputado dentro de cada projeto), votação, deputados e "como funciona".
   JavaScript puro, sem bibliotecas. Os dados vêm de dados/*.json (feitos por site/exportar_dados.py).
   Endereços: #/   #/assunto/<slug>?q=...&todos=1   #/votacao/<id>?q=...&pt=PT&uf=GO&v=S
   #/deputados?q=...&pt=PT&uf=GO   #/deputado/<id>?q=...&a=<assunto>&v=S
   (os filtros ficam no endereço para poder compartilhar). */
(function () {
  "use strict";

  const principal = document.getElementById("conteudo");
  const memoria = {};
  const POR_PAGINA = 30;

  // ------------------------------------------------------------------ utilidades
  async function dados(nome) {
    if (memoria[nome]) return memoria[nome];
    if (window.__DADOS__ && window.__DADOS__[nome]) return (memoria[nome] = window.__DADOS__[nome]);
    const r = await fetch("dados/" + nome + ".json");
    if (!r.ok) throw new Error("Não consegui carregar " + nome);
    return (memoria[nome] = await r.json());
  }

  const semAcento = (t) => (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const formato = new Intl.DateTimeFormat("pt-BR", { day: "numeric", month: "long", year: "numeric" });
  const data = (iso) => (iso ? formato.format(new Date(iso + "T12:00:00")) : "");
  const plural = (n, um, varios) => `${n.toLocaleString("pt-BR")} ${n === 1 ? um : varios}`;

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

  function lerRota() {
    const bruto = location.hash.replace(/^#\/?/, "");
    const [caminho, consulta = ""] = bruto.split("?");
    return { partes: caminho.split("/").filter(Boolean).map(decodeURIComponent), p: new URLSearchParams(consulta) };
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

  function anunciar(el, texto) {
    el.textContent = texto;
  }

  // ------------------------------------------------------------------ busca
  let indiceProjetos = null;
  async function projetosComTexto() {
    if (indiceProjetos) return indiceProjetos;
    const lista = await dados("projetos");
    for (const p of lista) {
      p._t = semAcento([p.titulo, p.resumo, p.ementa, p.nome, (p.tags || []).join(" ")].join(" "));
    }
    return (indiceProjetos = lista);
  }
  const termos = (q) => semAcento(q).split(/\s+/).filter((t) => t.length > 1);
  const casa = (texto, ts) => ts.every((t) => texto.includes(t));

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
  };
  const SVGNS = "http://www.w3.org/2000/svg";
  function icone(slug) {
    const s = document.createElementNS(SVGNS, "svg");
    for (const [k, v] of Object.entries({ viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "1.8", "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true", class: "icone" })) s.setAttribute(k, v);
    for (const d of (ICONES[slug] || ICONES.outros).split("|")) {
      const p = document.createElementNS(SVGNS, "path"); p.setAttribute("d", d); s.append(p);
    }
    return s;
  }
  const estiloAssunto = (slug) => `--h:${HUES[slug] ?? 215}${slug === "outros" ? ";--sat:0.25" : ""}`;

  // ------------------------------------------------------------------ tela inicial
  async function telaInicio(p) {
    const [assuntos, meta] = await Promise.all([dados("assuntos"), dados("meta")]);
    const estado = { q: p.get("q") || "" };

    const campoBusca = h("input", {
      id: "busca", type: "search", name: "q", autocomplete: "off", spellcheck: "false",
      placeholder: "aposentadoria, aluguel, vacina…", value: estado.q, enterkeyhint: "search",
    });
    const estadoTxt = h("p", { class: "estado", role: "status", "aria-live": "polite" });
    const lista = h("ul", { class: "tiles" });

    principal.replaceChildren(h("div", { class: "miolo" },
      h("section", { class: "heroi", "aria-labelledby": "titulo-inicio" },
        h("h1", { id: "titulo-inicio", tabindex: "-1" }, "Como a Câmara votou o que importa para você?"),
        h("p", { class: "heroi__texto" }, "Escolha um assunto, veja os projetos votados e o voto de cada deputado federal."),
        h("form", { class: "heroi__busca", role: "search", "aria-label": "Procurar assunto", onsubmit: (e) => e.preventDefault() },
          h("label", { for: "busca", class: "so-leitor" }, "Procure por um tema ou palavra"), campoBusca),
        h("p", { class: "heroi__link" }, "Já sabe quem? ", h("a", { href: "#/deputados" }, "Procure um deputado pelo nome"))),
      estadoTxt, lista,
      h("p", { class: "confianca" },
        `Dados oficiais da Câmara dos Deputados, de ${data(meta.de)} a ${data(meta.ate)}. Assunto e resumo são feitos por inteligência artificial e podem errar; avisamos quando há dúvida. `,
        h("a", { href: "#/sobre" }, "Como o site funciona"))));
    document.title = "Voto de Verdade: como a Câmara dos Deputados votou";
    document.getElementById("rodape-dados").textContent =
      `Dados da Câmara dos Deputados (Dados Abertos), de ${data(meta.de)} a ${data(meta.ate)}. Atualizado em ${data(meta.gerado_em)}.`;

    let versao = 0;
    async function atualizar() {
      const minha = ++versao;
      estado.q = campoBusca.value.trim();
      gravarEndereco("", limparParams({ q: estado.q }));
      const ts = termos(estado.q);
      let contagem = null;
      if (ts.length) {
        anunciar(estadoTxt, "Procurando…");
        try {
          const todos = await projetosComTexto();
          if (minha !== versao) return;
          contagem = {};
          for (const pr of todos) {
            if (!casa(pr._t, ts)) continue;
            contagem[pr.a] = (contagem[pr.a] || 0) + 1;
            if (pr.s) contagem[pr.s] = (contagem[pr.s] || 0) + 1;
          }
        } catch (e) {
          anunciar(estadoTxt, "Não foi possível carregar a busca. Recarregue a página e tente de novo.");
          return;
        }
      }
      const linhas = [];
      for (const a of assuntos) {
        let n = a.n, rotulo = null;
        if (contagem) {
          const achados = contagem[a.slug] || 0;
          if (!achados && !casa(semAcento(a.nome + " " + a.descricao), ts)) continue;
          if (achados) { n = achados; rotulo = `com “${estado.q}”`; }
        }
        linhas.push({ a, n, rotulo });
      }
      const porNome = (x, y) => (x.a.nome === "Outros") - (y.a.nome === "Outros") || x.a.nome.localeCompare(y.a.nome, "pt-BR");
      if (contagem) linhas.sort((x, y) => (y.rotulo ? y.n : 0) - (x.rotulo ? x.n : 0) || porNome(x, y)); else linhas.sort(porNome);

      const q = estado.q ? "?q=" + encodeURIComponent(estado.q) : "";
      lista.replaceChildren(...linhas.map(({ a, n, rotulo }) => h("li", {},
        h("a", { class: "tile", style: estiloAssunto(a.slug), href: "#/assunto/" + a.slug + q },
          h("span", { class: "tile__icone" }, icone(a.slug)),
          h("span", { class: "tile__nome" }, a.nome),
          h("span", { class: "tile__desc" }, a.descricao),
          h("span", { class: "tile__num" }, h("b", {}, n.toLocaleString("pt-BR")), ` ${n === 1 ? "projeto" : "projetos"}${rotulo ? " " + rotulo : ""}`),
          null))));
      anunciar(estadoTxt, linhas.length
        ? (estado.q ? `${plural(linhas.length, "assunto", "assuntos")} com “${estado.q}”` : "")
        : `Nenhum assunto com “${estado.q}”. Tente uma palavra mais simples, como “saúde” ou “imposto”.`);
    }
    let espera;
    campoBusca.addEventListener("input", () => { clearTimeout(espera); espera = setTimeout(atualizar, 180); });
    await atualizar();
    return document.getElementById("titulo-inicio");
  }

  // ------------------------------------------------------------------ como o site funciona
  async function telaSobre() {
    const meta = await dados("meta");
    const pct = Math.round((meta.simbolicas / meta.votacoes) * 100);
    principal.replaceChildren(h("div", { class: "miolo texto-longo" },
      h("nav", { class: "migalhas", "aria-label": "Você está em" }, h("ol", {}, h("li", {}, h("a", { href: "#/" }, "Início")), h("li", { "aria-current": "page" }, "Como o site funciona"))),
      h("h1", { id: "titulo-sobre", tabindex: "-1" }, "Como o site funciona"),
      h("h2", {}, "De onde vêm os dados"),
      h("p", {}, `Do portal de Dados Abertos da Câmara dos Deputados. O site mostra ${meta.votacoes.toLocaleString("pt-BR")} votações em plenário, de ${data(meta.de)} a ${data(meta.ate)}, e é atualizado todos os dias.`),
      h("h2", {}, "Assunto e resumo são feitos por inteligência artificial"),
      h("p", {}, "Uma inteligência artificial lê o texto oficial de cada projeto, escolhe o assunto e escreve um resumo em linguagem simples. Ela pode errar, e ninguém revisa cada resumo. Quando a classificação ou o resumo têm dúvida, o projeto mostra um aviso. O texto oficial fica sempre ao lado."),
      h("h2", {}, "Por que nem todo projeto mostra o voto de cada deputado"),
      h("p", {}, `${meta.simbolicas.toLocaleString("pt-BR")} das ${meta.votacoes.toLocaleString("pt-BR")} votações (${pct}%) foram simbólicas: os partidos chegam a um acordo e o resultado é anunciado sem registrar o voto de cada deputado. Nesses casos não há como saber como cada um votou. Só as ${meta.nominais.toLocaleString("pt-BR")} votações nominais têm o voto de cada deputado.`),
      h("h2", {}, "O que o site não faz"),
      h("p", {}, "Não dá nota, não faz ranking e não diz quem votou certo ou errado. Mostra o que cada deputado votou. Votar sim ou não numa votação não diz, sozinho, se o deputado apoia o assunto do projeto: muitas votações são sobre emendas, substitutivos ou pontos separados do texto."),
      h("p", {}, h("a", { href: "#/" }, "Voltar ao início"))));
    document.title = "Como o site funciona: Voto de Verdade";
    return document.getElementById("titulo-sobre");
  }

  // ------------------------------------------------------------------ página do assunto
  const TIPO = {
    nominal: "Cada deputado votou",
    simbolica: "Votação simbólica (sem o voto de cada deputado)",
    secreta: "Votação secreta",
  };

  // Resumo, avisos, pontos principais e texto oficial de um projeto (nesta ordem).
  function blocosProjeto(pr, semResumo) {
    const avisos = [];
    if (pr.aa) avisos.push(h("p", {}, pr.aa));
    if (pr.ar) avisos.push(h("p", {}, pr.ar));
    if (pr.subst) avisos.push(h("p", {}, "O resumo foi feito a partir da ementa do projeto original. A votação foi sobre um substitutivo ou emenda, e o texto votado pode ser diferente."));
    return [
      semResumo ? null : pr.resumo
        ? h("div", {}, h("span", { class: "rotulo-ia" }, "Resumo feito por inteligência artificial"), h("p", {}, pr.resumo))
        : h("p", {}, "Ainda não há resumo deste projeto. Leia o texto oficial abaixo."),
      avisos.length ? h("div", { class: "cartao-aviso" }, h("strong", {}, "Atenção"), avisos) : null,
      pr.pontos && pr.pontos.length ? h("div", {}, h("h3", {}, "Pontos principais"), h("ul", {}, pr.pontos.map((x) => h("li", {}, x)))) : null,
      h("div", {}, h("h3", {}, `Texto oficial (${pr.nome})`), h("p", { class: "oficial" }, pr.ementa || "Sem ementa."),
        pr.texto ? h("p", {}, h("a", { href: pr.texto, target: "_blank", rel: "noopener noreferrer" }, "Ler o texto completo no site da Câmara")) : null),
    ];
  }

  const descCurta = (t) => {
    t = (t || "").replace(/\s+/g, " ");
    if (t.length <= 80) return t;
    const c = t.slice(0, 79), i = c.lastIndexOf(" ");
    return c.slice(0, i > 40 ? i : 79) + "…";
  };

  // Uma linha da lista de projetos: leva à página do projeto, que já mostra os votos.
  function linhaProjeto(pr, slug, nomes, votacoes) {
    const incerto = (pr.ca && pr.ca !== "alta") || (pr.cr && pr.cr !== "alta");
    const minhas = votacoes.porProjeto[pr.id] || [];
    const nominais = minhas.filter((x) => x.t === "nominal").sort((x, y) => (x.d < y.d ? -1 : 1));
    const ultima = nominais[nominais.length - 1];
    let placar = null;
    if (ultima && ultima.s) {
      const soma = ultima.s.reduce((a, b) => a + b, 0), outros = ultima.s[2] + ultima.s[3] + ultima.s[4];
      placar = h("span", { class: "mini-placar" },
        h("span", { class: "barra-voto barra-voto--fina", "aria-hidden": "true" },
          ORDEM_VOTO.map((c, i) => (ultima.s[i] ? h("i", { class: "seg-" + c, style: `width:${(ultima.s[i] / soma) * 100}%` }) : null))),
        h("span", {}, `${ultima.s[0].toLocaleString("pt-BR")} sim · ${ultima.s[1].toLocaleString("pt-BR")} não${outros ? ` · ${outros.toLocaleString("pt-BR")} outros` : ""}`));
    }
    const sem = !nominais.length ? (pr.tipo === "secreta" ? "Votação secreta" : "Votação simbólica, sem o voto de cada deputado") : null;
    return h("li", {}, h("a", { class: "proj", href: "#/projeto/" + pr.id },
      h("span", { class: "proj__titulo" }, pr.titulo),
      h("span", { class: "proj__meta" },
        h("span", {}, data(pr.ultima)), h("span", {}, pr.aprovada ? "Aprovado" : "Rejeitado"), sem && h("span", {}, sem),
        incerto && h("span", { class: "selo-aviso" }, "Classificação incerta")),
      placar));
  }

  async function telaAssunto(slug, p) {
    const [assuntos, projetos, votacoes] = await Promise.all([dados("assuntos"), projetosComTexto(), indiceVotacoes()]);
    const a = assuntos.find((x) => x.slug === slug);
    if (!a) return telaNaoEncontrada();
    const nomes = Object.fromEntries(assuntos.map((x) => [x.slug, x.nome]));
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
      h("div", { class: "abas", role: "group", "aria-label": "Quais projetos mostrar" }, abaInd, abaTodos),
      h("form", { class: "filtros filtros--compacto", role: "search", "aria-label": `Procurar em ${a.nome}`, onsubmit: (e) => e.preventDefault() },
        h("div", { class: "campo" }, h("label", { for: "busca-a" }, "Procurar neste assunto"), campoBusca),
        h("details", { class: "ajuda mais-filtros" },
          h("summary", {}, "Mais filtros"),
          h("div", { class: "filtros__linha" },
            h("div", { class: "campo" }, h("label", { for: "res-a" }, "Resultado da votação"), seletorRes),
            h("div", { class: "campo" }, h("label", { for: "ord-a" }, "Ordem"), seletorOrd)),
          h("label", { class: "marcar", for: "cert-a" }, caixaCert, h("span", {}, "Esconder projetos com aviso de possível erro")))),
      estadoTxt, lista, vazio, maisBox));
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
      abaInd.textContent = `Com voto de cada deputado (${nIndF.toLocaleString("pt-BR")})`;
      abaTodos.textContent = `Todos os projetos (${comFiltros.length.toLocaleString("pt-BR")})`;
      abaInd.setAttribute("aria-pressed", String(!estado.todos)); abaTodos.setAttribute("aria-pressed", String(estado.todos));
      abaInd.disabled = !nInd;

      const r = (estado.todos ? comFiltros : comFiltros.filter((x) => x.ind)).slice();
      r.sort((x, y) => (estado.ord === "recente" ? (y.ultima > x.ultima ? 1 : -1) : (x.ultima > y.ultima ? 1 : -1)) || y.id - x.id);
      const mostrados = r.slice(0, limite);
      lista.replaceChildren(...mostrados.map((x) => linhaProjeto(x, slug, nomes, votacoes)));
      anunciar(estadoTxt, r.length ? plural(r.length, "projeto", "projetos") : "");
      vazio.replaceChildren();
      if (!r.length) {
        vazio.append(h("p", {}, "Nenhum projeto com esses filtros."));
        if (!estado.todos && comFiltros.length) {
          vazio.append(h("button", { type: "button", class: "botao botao--leve", onclick: () => { estado.todos = true; atualizar(true); } },
            `Ver os ${comFiltros.length.toLocaleString("pt-BR")} projetos, inclusive os sem voto de cada deputado`));
        }
      }
      maisBox.replaceChildren();
      if (r.length > mostrados.length) {
        maisBox.append(h("button", { type: "button", class: "botao botao--leve", onclick: () => { limite += POR_PAGINA; atualizar(false); } },
          `Mostrar mais ${Math.min(POR_PAGINA, r.length - mostrados.length)} projetos`));
      }
    }

    let espera;
    campoBusca.addEventListener("input", () => { clearTimeout(espera); espera = setTimeout(() => atualizar(true), 180); });
    for (const el of [seletorOrd, seletorRes, caixaCert]) el.addEventListener("change", () => atualizar(true));
    abaInd.addEventListener("click", () => { estado.todos = false; atualizar(true); });
    abaTodos.addEventListener("click", () => { estado.todos = true; atualizar(true); });
    atualizar(false);
    return document.getElementById("titulo-assunto");
  }

  // ------------------------------------------------------------------ voto de cada deputado
  const VOTO = {
    S: { nome: "Sim", plural: "votaram sim" },
    N: { nome: "Não", plural: "votaram não" },
    A: { nome: "Abstenção", plural: "se abstiveram" },
    O: { nome: "Obstrução", plural: "fizeram obstrução" },
    P: { nome: "Presidia a sessão", plural: "presidiam a sessão" },
  };
  const ORDEM_VOTO = ["S", "N", "A", "O", "P"];

  const fichaVoto = (cod) => h("span", { class: "voto voto--" + cod }, VOTO[cod].nome);


  // ------------------------------------------------------------------ painel "como cada deputado votou"
  // Usado dentro de cada projeto (página do assunto) e na página da votação.
  let contadorPainel = 0;
  function painelVotos(v, opc) {
    opc = opc || {};
    const n = ++contadorPainel;
    const raiz = h("div", { class: "painel" + (opc.tabela ? "" : " painel--compacto") }, h("p", { class: "nota" }, "Carregando os votos…"));
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

      const placar = h("dl", { class: "placar" }, ORDEM_VOTO.filter((c) => total[c]).map((c) =>
        h("div", {}, h("dt", {}, VOTO[c].nome), h("dd", {}, total[c].toLocaleString("pt-BR")))));
      const barraTotal = h("div", { class: "barra-voto", "aria-hidden": "true" }, ORDEM_VOTO.filter((c) => total[c]).map((c) =>
        h("i", { class: "seg-" + c, style: `width:${(total[c] / nTotal) * 100}%` })));

      const campoQ = h("input", { id: id("q"), type: "search", autocomplete: "off", spellcheck: "false", value: estado.q, placeholder: "nome do deputado", enterkeyhint: "search" });
      const selPt = h("select", { id: id("pt") }, h("option", { value: "" }, "Todos os partidos"), partidos.map((x) => h("option", { value: x }, x)));
      const selUf = h("select", { id: id("uf") }, h("option", { value: "" }, "Todos os estados"), ufs.map((x) => h("option", { value: x }, x)));
      const selV = h("select", { id: id("v") }, h("option", { value: "" }, "Todos os votos"), ORDEM_VOTO.filter((c) => total[c]).map((c) => h("option", { value: c }, VOTO[c].nome)));
      selPt.value = estado.pt; selUf.value = estado.uf; selV.value = estado.v;
      const limpar = h("button", { type: "button", class: "botao botao--leve" }, "Limpar filtros");
      const estadoTxt = h("p", { class: "estado", role: "status", "aria-live": "polite" });
      const tabelaBox = h("div", { class: "tabela-rolavel", tabindex: "0", role: "region", "aria-label": "Como cada partido votou" });
      const lista = h("ul", { class: "deputados" });
      const maisBox = h("div", { class: "mais" });

      const filtros = h("form", { class: "filtros filtros--compacto", role: "search", "aria-label": "Filtrar os votos", onsubmit: (e) => e.preventDefault() },
        h("div", { class: "filtros__linha filtros__linha--4" },
          h("div", { class: "campo" }, h("label", { for: id("q") }, "Deputado"), campoQ),
          h("div", { class: "campo" }, h("label", { for: id("pt") }, "Partido"), selPt),
          h("div", { class: "campo" }, h("label", { for: id("uf") }, "Estado"), selUf),
          h("div", { class: "campo" }, h("label", { for: id("v") }, "Voto"), selV)),
        h("div", { class: "filtros__rodape" }, limpar));

      const ajudaVotos = h("details", { class: "ajuda ajuda--solta" },
        h("summary", {}, "O que significam abstenção, obstrução e “presidia a sessão”?"),
        h("ul", {},
          h("li", {}, h("b", {}, "Abstenção: "), "o deputado esteve presente e escolheu não votar nem sim nem não."),
          h("li", {}, h("b", {}, "Obstrução: "), "o deputado ou seu partido age para atrasar ou impedir a votação, em geral não votando."),
          h("li", {}, h("b", {}, "Presidia a sessão: "), "quem conduz a sessão só vota em situações previstas no regimento (artigo 17). O registro aparece assim nos dados da Câmara.")));

      raiz.replaceChildren(...[
        placar, barraTotal,
        h("p", { class: "nota" }, `${plural(nTotal, "deputado registrou", "deputados registraram")} voto. Quem faltou ou não votou não aparece na lista.`),
        opc.tabela ? h("div", { class: "bloco" }, h("h3", { class: "subtitulo" }, "Como cada partido votou"),
          h("p", { class: "nota" }, "Cada deputado conta no partido em que estava no dia da votação. Escolha um partido para ver os deputados dele."), tabelaBox) : null,
        h("div", { class: "bloco" }, opc.tabela ? h("h3", { class: "subtitulo" }, "Como cada deputado votou") : null, filtros, estadoTxt, lista, maisBox, ajudaVotos)].filter(Boolean));

      function filtrar(ignorar) {
        const ts = termos(estado.q);
        return linhas.filter((l) =>
          (!ts.length || casa(l._t, ts)) && (ignorar.includes("pt") || !estado.pt || l.partido === estado.pt) &&
          (!estado.uf || l.uf === estado.uf) && (ignorar.includes("v") || !estado.v || l.cod === estado.v));
      }

      function desenharTabela() {
        if (!opc.tabela) return;
        const por = {};
        for (const l of filtrar(["pt", "v"])) { const t = (por[l.partido || "Sem partido"] ||= { S: 0, N: 0, O: 0, n: 0 }); t.n++; if (l.cod === "S" || l.cod === "N") t[l.cod]++; else t.O++; }
        const nomes = Object.keys(por).sort((a, b) => a.localeCompare(b, "pt-BR"));
        if (!nomes.length) { tabelaBox.replaceChildren(h("p", { class: "nota" }, "Nenhum deputado com esses filtros.")); return; }
        tabelaBox.replaceChildren(h("table", { class: "tabela-partidos" },
          h("caption", { class: "so-leitor" }, "Votos por partido"),
          h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Partido"), h("th", { scope: "col", class: "num" }, "Sim"), h("th", { scope: "col", class: "num" }, "Não"),
            h("th", { scope: "col", class: "num" }, "Outros"), h("th", { scope: "col", class: "num" }, "Total"))),
          h("tbody", {}, nomes.map((nm) => {
            const t = por[nm], ativo = estado.pt === nm;
            return h("tr", { class: ativo ? "ativa" : null },
              h("th", { scope: "row" },
                h("button", { type: "button", class: "link-botao", "aria-pressed": ativo ? "true" : "false", onclick: () => { selPt.value = ativo ? "" : nm; atualizar(true); } }, nm),
                h("span", { class: "barra-voto barra-voto--fina", "aria-hidden": "true" },
                  h("i", { class: "seg-S", style: `width:${(t.S / t.n) * 100}%` }), h("i", { class: "seg-N", style: `width:${(t.N / t.n) * 100}%` }), h("i", { class: "seg-O", style: `width:${(t.O / t.n) * 100}%` }))),
              h("td", { class: "num" }, t.S), h("td", { class: "num" }, t.N), h("td", { class: "num" }, t.O), h("td", { class: "num" }, t.n));
          }))));
      }

      function atualizar(reiniciar) {
        if (reiniciar) limite = 60;
        estado.q = campoQ.value.trim(); estado.pt = selPt.value; estado.uf = selUf.value; estado.v = selV.value;
        if (opc.gravar) opc.gravar(limparParams({ q: estado.q, pt: estado.pt, uf: estado.uf, v: estado.v }));
        desenharTabela();
        const r = filtrar([]).sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
        const mostrados = r.slice(0, limite);
        lista.replaceChildren(...mostrados.map((l) => h("li", { class: "deputado" },
          h("a", { class: "deputado__nome", href: "#/deputado/" + l.id }, l.nome),
          h("span", { class: "deputado__sub" }, [l.partido, l.uf].filter(Boolean).join(" · ")),
          fichaVoto(l.cod))));
        anunciar(estadoTxt, r.length
          ? `${plural(r.length, "deputado", "deputados")}${r.length !== nTotal ? ` de ${nTotal.toLocaleString("pt-BR")}` : ""}`
          : "Nenhum deputado com esses filtros. Tire algum filtro ou escreva outro nome.");
        limpar.hidden = !(estado.q || estado.pt || estado.uf || estado.v);
        maisBox.replaceChildren();
        if (r.length > mostrados.length) {
          maisBox.append(h("button", { type: "button", class: "botao botao--leve", onclick: () => { limite += 60; atualizar(false); } },
            `Mostrar mais ${Math.min(60, r.length - mostrados.length)} deputados`));
        }
      }
      let espera;
      campoQ.addEventListener("input", () => { clearTimeout(espera); espera = setTimeout(() => atualizar(true), 180); });
      for (const el of [selPt, selUf, selV]) el.addEventListener("change", () => atualizar(true));
      limpar.addEventListener("click", () => { campoQ.value = ""; selPt.value = ""; selUf.value = ""; selV.value = ""; atualizar(true); campoQ.focus(); });
      atualizar(true);
    }
  }

  // ------------------------------------------------------------------ página do projeto (com os votos)
  async function telaProjeto(id, p) {
    const [vots, projetos, assuntos] = await Promise.all([indiceVotacoes(), dados("projetos"), dados("assuntos")]);
    const pr = projetos.find((x) => String(x.id) === String(id));
    if (!pr) return telaNaoEncontrada();
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
        h("p", { class: "nota" }, `${data(v.d)} · ${v.ap ? "Aprovada" : "Rejeitada"}`),
        h("p", { class: "oficial" }, v.desc),
        v.c !== "alta" && v.av ? h("div", { class: "cartao-aviso" }, h("strong", {}, "Atenção"), h("p", {}, v.av)) : null,
        painelVotos(v, { tabela: true, p: params, gravar: (q) => { q.set("votacao", v.id); gravarEndereco("projeto/" + pr.id, q); } })].filter(Boolean));
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
      secaoVotos.append(h("p", { class: "nota" }, minhas.some((x) => x.t === "secreta")
        ? "Votação secreta: o voto de cada deputado não é divulgado."
        : "Votação simbólica: os partidos chegaram a um acordo e o resultado foi anunciado sem registrar o voto de cada deputado. Por isso não há como mostrar como cada um votou."));
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
        h("h1", { id: "titulo-projeto", tabindex: "-1" }, pr.titulo),
        h("p", { class: "cabeca-projeto__meta" }, `${pr.nome} · votado em ${data(pr.ultima)} · ${pr.aprovada ? "aprovado" : "rejeitado"}`)),
      h("div", { class: "resumo-projeto" }, resumoSemRepetir(pr), partes[1]),
      secaoVotos,
      outrasSimbolicas.length ? h("p", { class: "nota" }, `Este projeto também teve ${outrasSimbolicas.length === 1 ? "uma votação simbólica" : outrasSimbolicas.length + " votações simbólicas"}, sem o voto de cada deputado.`) : null,
      h("details", { class: "ajuda ajuda--solta" },
        h("summary", {}, "Pontos principais e texto oficial"),
        h("div", { class: "projeto__corpo" }, partes[2], partes[3]))));
    if (nominais.length) mostrar(atual);
    document.title = `${pr.nome}: Voto de Verdade`;
    return document.getElementById("titulo-projeto");
  }

  // O título da página é a primeira frase do resumo; aqui vai só o resto, para não repetir.
  function resumoSemRepetir(pr) {
    if (!pr.resumo) return blocosProjeto(pr)[0];
    const resto = pr.resumo.startsWith(pr.titulo) ? pr.resumo.slice(pr.titulo.length).trim() : pr.resumo;
    return h("div", {}, h("span", { class: "rotulo-ia" }, "Título e resumo feitos por inteligência artificial"), resto ? h("p", {}, resto) : null);
  }

  // Endereço antigo de uma votação: abre a página do projeto, já nessa votação.
  async function telaVotacao(id, p) {
    const vots = await indiceVotacoes();
    const v = vots.porId[id];
    if (!v) return telaNaoEncontrada();
    const q = new URLSearchParams(p); q.set("votacao", id);
    history.replaceState(null, "", `#/projeto/${v.p}?${q}`);
    return telaProjeto(String(v.p), q);
  }

  // ------------------------------------------------------------------ deputados (busca) e página do deputado
  const fotoDeputado = (id) => h("img", {
    class: "foto-dep", src: `https://www.camara.leg.br/internet/deputado/bandep/${id}.jpg`, alt: "", width: "96", height: "128",
    loading: "lazy", referrerpolicy: "no-referrer", onerror: (e) => e.target.remove(),
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
    const selUf = h("select", { id: "dep-uf" }, h("option", { value: "" }, "Todos os estados"), ufs.map((x) => h("option", { value: x }, x)));
    selPt.value = estado.pt; selUf.value = estado.uf;
    const caixaEx = h("input", { type: "checkbox", id: "dep-ex" }); caixaEx.checked = estado.ex;
    const estadoTxt = h("p", { class: "estado", role: "status", "aria-live": "polite" });
    const lista = h("ul", { class: "lista-dep" });
    const maisBox = h("div", { class: "mais" });

    principal.replaceChildren(h("div", { class: "miolo" },
      h("section", { class: "abertura", "aria-labelledby": "titulo-deputados" },
        h("h1", { id: "titulo-deputados", tabindex: "-1" }, "Procure um deputado federal"),
        h("p", { class: "abertura__texto" }, "Veja como cada um votou nas votações em que o voto de cada deputado foi registrado. Sem nota e sem ranking.")),
      h("form", { class: "filtros", role: "search", "aria-label": "Procurar deputado", onsubmit: (e) => e.preventDefault() },
        h("div", { class: "filtros__linha" },
          h("div", { class: "campo" }, h("label", { for: "busca-d" }, "Nome"), campoQ),
          h("div", { class: "campo" }, h("label", { for: "dep-pt" }, "Partido"), selPt),
          h("div", { class: "campo" }, h("label", { for: "dep-uf" }, "Estado"), selUf)),
        h("label", { class: "marcar", for: "dep-ex" }, caixaEx, h("span", {}, "Só quem está em exercício agora",
          h("small", {}, "Deixe desligado para ver também quem já deixou o cargo ou foi suplente no período.")))),
      estadoTxt, lista, maisBox));
    document.title = "Deputados: Voto de Verdade";

    function atualizar(reiniciar) {
      if (reiniciar) limite = 60;
      estado.q = campoQ.value.trim(); estado.pt = selPt.value; estado.uf = selUf.value; estado.ex = caixaEx.checked;
      gravarEndereco("deputados", limparParams({ q: estado.q, pt: estado.pt, uf: estado.uf, ex: estado.ex ? "1" : "" }));
      const ts = termos(estado.q);
      const r = deputados.filter((d) => (!ts.length || casa(d._t, ts)) && (!estado.pt || d.partido === estado.pt) && (!estado.uf || d.uf === estado.uf) && (!estado.ex || d.ex));
      const mostrados = r.slice(0, limite);
      lista.replaceChildren(...mostrados.map((d) => h("li", {}, h("a", { class: "linha-dep", href: "#/deputado/" + d.id },
        h("span", { class: "linha-dep__nome" }, d.nome),
        h("span", { class: "linha-dep__sub" }, [d.partido, d.uf].filter(Boolean).join(" · ") + (d.ex ? "" : " · fora do exercício agora"))))));
      anunciar(estadoTxt, r.length ? `${plural(r.length, "deputado", "deputados")}${r.length !== deputados.length ? ` de ${deputados.length.toLocaleString("pt-BR")}` : ""}`
        : "Nenhum deputado com esses filtros. Confira a grafia do nome ou tire algum filtro.");
      maisBox.replaceChildren();
      if (r.length > mostrados.length) {
        maisBox.append(h("button", { type: "button", class: "botao botao--leve", onclick: () => { limite += 60; atualizar(false); } },
          `Mostrar mais ${Math.min(60, r.length - mostrados.length)} deputados`));
      }
    }
    let espera;
    campoQ.addEventListener("input", () => { clearTimeout(espera); espera = setTimeout(() => atualizar(true), 180); });
    for (const el of [selPt, selUf, caixaEx]) el.addEventListener("change", () => atualizar(true));
    atualizar(true);
    return document.getElementById("titulo-deputados");
  }

  async function telaDeputado(id, p) {
    const [deputados, vots, projetos, assuntos] = await Promise.all([dados("deputados"), indiceVotacoes(), dados("projetos"), dados("assuntos")]);
    const dep = deputados.find((d) => String(d.id) === id);
    if (!dep) return telaNaoEncontrada();
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
    const limpar = h("button", { type: "button", class: "botao botao--leve", id: "limpar-d" }, "Limpar filtros");
    const estadoTxt = h("p", { class: "estado", role: "status", "aria-live": "polite" });
    const tabelaBox = h("div", { class: "tabela-rolavel", tabindex: "0", role: "region", "aria-label": "Votos por assunto" });
    const lista = h("ul", { class: "votos-dep" });
    const maisBox = h("div", { class: "mais" });

    const partidoAgora = [dep.partido, dep.uf].filter(Boolean).join(" · ");
    const historico = arq.pt && arq.pt.length > 1 ? `Nas votações, apareceu nos partidos: ${arq.pt.join(", ")} (do mais antigo ao mais recente).` : null;

    const temVotos = votos.length > 0;
    const placar = h("dl", { class: "placar" }, ORDEM_VOTO.filter((c) => total[c]).map((c) => h("div", {}, h("dt", {}, VOTO[c].nome), h("dd", {}, total[c].toLocaleString("pt-BR")))));

    const conteudo = h("div", { class: "miolo" },
      h("nav", { class: "migalhas", "aria-label": "Você está em" },
        h("ol", {}, h("li", {}, h("a", { href: "#/deputados" }, "Deputados")), h("li", { "aria-current": "page" }, dep.nome))),
      h("header", { class: "cabeca-dep" },
        fotoDeputado(dep.id),
        h("div", {},
          h("h1", { id: "titulo-deputado", tabindex: "-1" }, dep.nome),
          h("p", { class: "cabeca-dep__sub" }, partidoAgora, dep.ex ? "" : " · não está em exercício agora"),
          historico ? h("p", { class: "nota" }, historico) : null)),
      temVotos
        ? h("section", { "aria-labelledby": "resumo-dep" },
            h("h2", { id: "resumo-dep" }, "Votos registrados"),
            placar,
            h("p", { class: "nota" }, `${plural(votos.length, "votação nominal", "votações nominais")} com voto registrado, de ${data(meta.de)} a ${data(meta.ate)}. Votações simbólicas e votações em que o deputado faltou não aparecem.`))
        : h("p", { class: "aviso-previa" }, "Não há voto registrado deste deputado nas votações nominais do período."));

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
          estadoTxt, lista, maisBox,
          h("details", { class: "ajuda ajuda--solta" },
            h("summary", {}, "Ver os votos por assunto"),
            h("p", { class: "nota" }, "Conta pelo assunto principal de cada projeto. Escolha um assunto para ver só os votos nele."),
            tabelaBox),
          h("p", { class: "nota" }, "Votar sim ou não não diz, sozinho, se o deputado apoia o assunto do projeto: muitas votações são sobre emendas ou pontos separados do texto. Abra o projeto para ler o que foi votado.")));
    }
    principal.replaceChildren(conteudo);
    document.title = `${dep.nome}: Voto de Verdade`;

    function desenharTabela() {
      tabelaBox.replaceChildren(h("table", { class: "tabela-partidos" },
        h("caption", { class: "so-leitor" }, "Votos por assunto"),
        h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Assunto"), h("th", { scope: "col", class: "num" }, "Sim"), h("th", { scope: "col", class: "num" }, "Não"),
          h("th", { scope: "col", class: "num" }, "Outros"), h("th", { scope: "col", class: "num" }, "Total"))),
        h("tbody", {}, slugs.map((sl) => {
          const t = porAssunto[sl], ativo = estado.a === sl;
          return h("tr", { class: ativo ? "ativa" : null },
            h("th", { scope: "row" },
              h("button", { type: "button", class: "link-botao", "aria-pressed": ativo ? "true" : "false", onclick: () => { selA.value = ativo ? "" : sl; atualizar(true); } }, nomeAssunto[sl]),
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
      const ts = termos(estado.q);
      const r = votos.filter((x) => (!ts.length || casa(x._t, ts)) && (!estado.a || x.pr.a === estado.a) && (!estado.v || x.cod === estado.v));
      r.sort((x, y) => (estado.ord === "recente" ? (y.v.d > x.v.d ? 1 : y.v.d < x.v.d ? -1 : 0) : (x.v.d > y.v.d ? 1 : x.v.d < y.v.d ? -1 : 0)) || (x.v.id < y.v.id ? -1 : 1));
      const mostrados = r.slice(0, limite);
      lista.replaceChildren(...mostrados.map(({ v, pr, cod }) => h("li", {},
        h("a", { class: "voto-dep", href: "#/projeto/" + pr.id + "?votacao=" + encodeURIComponent(v.id) },
          h("span", { class: "voto-dep__titulo" }, pr.titulo),
          h("span", { class: "voto-dep__meta" }, `${pr.nome} · ${data(v.d)} · ${nomeAssunto[pr.a] || ""}`),
          fichaVoto(cod)))));
      anunciar(estadoTxt, r.length ? `${plural(r.length, "votação", "votações")}${r.length !== votos.length ? ` de ${votos.length.toLocaleString("pt-BR")}` : ""}`
        : "Nenhuma votação com esses filtros. Tire algum filtro ou use outra palavra.");
      limpar.hidden = !(estado.q || estado.a || estado.v);
      maisBox.replaceChildren();
      if (r.length > mostrados.length) {
        maisBox.append(h("button", { type: "button", class: "botao botao--leve", onclick: () => { limite += 30; atualizar(false); } },
          `Mostrar mais ${Math.min(30, r.length - mostrados.length)} votações`));
      }
    }
    if (temVotos) {
      let espera;
      campoQ.addEventListener("input", () => { clearTimeout(espera); espera = setTimeout(() => atualizar(true), 180); });
      for (const el of [selA, selV, selOrd]) el.addEventListener("change", () => atualizar(true));
      limpar.addEventListener("click", () => { campoQ.value = ""; selA.value = ""; selV.value = ""; atualizar(true); campoQ.focus(); });
      atualizar(true);
    }
    return document.getElementById("titulo-deputado");
  }

  function telaNaoEncontrada() {
    principal.replaceChildren(h("div", { class: "miolo", style: "padding-block:3rem" },
      h("h1", { id: "titulo-nao", tabindex: "-1" }, "Não achamos esta página"),
      h("p", {}, "O endereço pode estar errado ou o assunto não existe mais."),
      h("p", {}, h("a", { href: "#/" }, "Ver todos os assuntos"))));
    document.title = "Página não encontrada: Voto de Verdade";
    return document.getElementById("titulo-nao");
  }

  // ------------------------------------------------------------------ rotas
  async function rotear(moverFoco) {
    if (location.hash === "#conteudo") { principal.focus(); return; }
    const { partes, p } = lerRota();
    const emAssunto = partes[0] === "assunto";
    const emDeputados = partes[0] === "deputados" || partes[0] === "deputado";
    document.getElementById("nav-assuntos").toggleAttribute("aria-current", !emDeputados);
    document.getElementById("nav-deputados").toggleAttribute("aria-current", emDeputados);
    for (const id of ["nav-assuntos", "nav-deputados"]) {
      const a = document.getElementById(id);
      if (a.hasAttribute("aria-current")) a.setAttribute("aria-current", "page");
    }
    let titulo;
    try {
      if (!partes.length) titulo = await telaInicio(p);
      else if (emAssunto && partes[1]) titulo = await telaAssunto(partes[1], p);
      else if (partes[0] === "projeto" && partes[1]) titulo = await telaProjeto(partes[1], p);
      else if (partes[0] === "votacao" && partes[1]) titulo = await telaVotacao(partes[1], p);
      else if (partes[0] === "sobre") titulo = await telaSobre();
      else if (partes[0] === "deputados") titulo = await telaDeputados(p);
      else if (partes[0] === "deputado" && partes[1]) titulo = await telaDeputado(partes[1], p);
      else titulo = telaNaoEncontrada();
    } catch (e) {
      console.error(e);
      principal.replaceChildren(h("div", { class: "miolo", style: "padding-block:3rem" },
        h("h1", { tabindex: "-1", id: "titulo-erro" }, "Não foi possível carregar os dados"),
        h("p", {}, "Verifique sua conexão e recarregue a página.")));
      titulo = document.getElementById("titulo-erro");
    }
    if (moverFoco && titulo) {
      titulo.focus({ preventScroll: true });
      const voltou = !clicou && posicoes[location.hash] != null;
      window.scrollTo(0, voltou ? posicoes[location.hash] : 0);
    }
    clicou = false;
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
