/* Voto de Verdade: telas "Assuntos" (início) e "Página do assunto".
   JavaScript puro, sem bibliotecas. Os dados vêm de dados/*.json (feitos por site/exportar_dados.py).
   Endereços: #/  e  #/assunto/<slug>?q=...&ind=1&ord=...  (os filtros ficam no endereço para poder compartilhar). */
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

  // ------------------------------------------------------------------ tela inicial
  async function telaInicio(p) {
    const [assuntos, meta] = await Promise.all([dados("assuntos"), dados("meta")]);
    const estado = { q: p.get("q") || "", ind: p.get("ind") === "1", ord: p.get("ord") || "az" };
    if (!["az", "mais", "recente"].includes(estado.ord)) estado.ord = "az";

    const pctSimbolicas = Math.round((meta.simbolicas / meta.votacoes) * 100);

    const campoBusca = h("input", {
      id: "busca", type: "search", name: "q", autocomplete: "off", spellcheck: "false",
      placeholder: "aposentadoria, aluguel, vacina, armas…", value: estado.q, enterkeyhint: "search",
    });
    const caixaInd = h("input", { type: "checkbox", id: "so-ind" });
    caixaInd.checked = estado.ind;
    const seletor = h("select", { id: "ordem" },
      h("option", { value: "az" }, "Ordem alfabética"),
      h("option", { value: "mais" }, "Com mais projetos"),
      h("option", { value: "recente" }, "Votados mais recentemente"));
    seletor.value = estado.ord;
    const estadoTxt = h("p", { class: "estado", role: "status", "aria-live": "polite" });
    const lista = h("ul", { class: "indice" });

    const conteudo = h("div", { class: "miolo" },
      h("section", { class: "abertura", "aria-labelledby": "titulo-inicio" },
        h("h1", { id: "titulo-inicio", tabindex: "-1" }, "Sobre o que você quer saber como a Câmara votou?"),
        h("p", { class: "abertura__texto" },
          "Escolha um assunto, veja o que foi votado e como cada deputado federal votou. Sem nota e sem ranking: só o que cada um votou.")),
      h("form", { class: "controles", role: "search", "aria-label": "Procurar assunto", onsubmit: (e) => e.preventDefault() },
        h("div", { class: "linha-controles" },
          h("div", { class: "campo" }, h("label", { for: "busca" }, "Procure por um tema ou palavra"), campoBusca),
          h("div", { class: "campo" }, h("label", { for: "ordem" }, "Ordenar assuntos"), seletor)),
        h("label", { class: "marcar", for: "so-ind" }, caixaInd,
          h("span", {}, "Só projetos em que cada deputado votou",
            h("small", {}, `${meta.projetos_com_voto_individual.toLocaleString("pt-BR")} de ${meta.projetos.toLocaleString("pt-BR")} projetos`))),
        h("details", { class: "ajuda" },
          h("summary", {}, "Por que nem todo projeto tem o voto de cada deputado?"),
          h("p", {},
            `Em ${meta.simbolicas.toLocaleString("pt-BR")} das ${meta.votacoes.toLocaleString("pt-BR")} votações (${pctSimbolicas}%), os partidos chegaram a um acordo e a votação foi simbólica: o resultado é anunciado sem registrar o voto de cada deputado. Nesses casos o site mostra o resultado, mas não há como saber como cada um votou.`))),
      estadoTxt,
      lista,
      h("section", { class: "como-ler", "aria-labelledby": "como-ler-titulo" },
        h("h2", { id: "como-ler-titulo" }, "Como ler o que você vai encontrar"),
        h("div", { class: "como-ler__grade" },
          h("div", {}, h("h3", {}, "Os dados são oficiais"),
            h("p", {}, `Vêm do portal de Dados Abertos da Câmara dos Deputados e cobrem as votações de ${data(meta.de)} a ${data(meta.ate)}, de projetos votados em plenário.`)),
          h("div", {}, h("h3", {}, "Assunto e resumo são feitos por inteligência artificial"),
            h("p", {}, "Ela lê o texto oficial e pode errar. Quando não temos certeza, avisamos no projeto. O texto oficial fica sempre ao lado do resumo.")),
          h("div", {}, h("h3", {}, "Não damos nota nem fazemos ranking"),
            h("p", {}, "Mostramos o que cada deputado votou. Dizer quem votou certo ou errado é com você.")))));

    principal.replaceChildren(conteudo);
    document.title = "Voto de Verdade: como a Câmara dos Deputados votou";
    document.getElementById("rodape-dados").textContent =
      `Dados da Câmara dos Deputados (Dados Abertos), de ${data(meta.de)} a ${data(meta.ate)}. Atualizado em ${data(meta.gerado_em)}.`;

    let versao = 0;
    async function atualizar() {
      const minha = ++versao;
      estado.q = campoBusca.value.trim();
      estado.ind = caixaInd.checked;
      estado.ord = seletor.value;
      gravarEndereco("", limparParams({ q: estado.q, ind: estado.ind ? "1" : "", ord: estado.ord === "az" ? "" : estado.ord }));

      const ts = termos(estado.q);
      let contagem = null;
      if (ts.length) {
        anunciar(estadoTxt, "Procurando…");
        try {
          const todos = await projetosComTexto();
          if (minha !== versao) return;
          contagem = {};
          for (const pr of todos) {
            if (estado.ind && !pr.ind) continue;
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
        const total = estado.ind ? a.n_ind : a.n;
        let n = total, rotulo = null;
        if (contagem) {
          const achados = contagem[a.slug] || 0;
          const casaNome = casa(semAcento(a.nome + " " + a.descricao), ts);
          if (!achados && !(casaNome && total > 0)) continue;
          if (achados) { n = achados; rotulo = `com “${estado.q}”`; }
        } else if (!total) continue;
        linhas.push({ a, n, rotulo });
      }

      const porNome = (x, y) => (x.a.nome === "Outros") - (y.a.nome === "Outros") || x.a.nome.localeCompare(y.a.nome, "pt-BR");
      if (estado.ord === "mais") linhas.sort((x, y) => y.n - x.n || porNome(x, y));
      else if (estado.ord === "recente") linhas.sort((x, y) => (y.a.ultima > x.a.ultima ? 1 : y.a.ultima < x.a.ultima ? -1 : porNome(x, y)));
      else linhas.sort(porNome);

      const params = limparParams({ q: estado.q, ind: estado.ind ? "1" : "" });
      const itens = linhas.map(({ a, n, rotulo }) => {
        const destino = "#/assunto/" + a.slug + (params.toString() ? "?" + params : "");
        const blocoDados = h("span", { class: "linha-assunto__dados" },
          h("span", { class: "linha-assunto__num" }, `${plural(n, "projeto", "projetos")}${rotulo ? " " + rotulo : ""}`),
          h("span", { class: "linha-assunto__sub" }, `Último votado em ${data(a.ultima)}`));
        if (!estado.ind) {
          blocoDados.append(
            h("span", { class: "barra", "aria-hidden": "true" }, h("i", { style: `width:${Math.max(2, Math.round((a.n_ind / a.n) * 100))}%` })),
            h("span", { class: "linha-assunto__sub" }, `${a.n_ind.toLocaleString("pt-BR")} com voto de cada deputado`));
        }
        return h("li", {}, h("a", { class: "linha-assunto", href: destino },
          h("span", { class: "linha-assunto__nome" }, a.nome),
          h("span", { class: "linha-assunto__desc" }, a.descricao),
          blocoDados));
      });
      lista.replaceChildren(...itens);

      if (!linhas.length) {
        anunciar(estadoTxt, estado.q
          ? `Nenhum assunto com “${estado.q}”. Tente uma palavra mais simples, como “saúde” ou “imposto”.`
          : "Nenhum assunto para mostrar.");
      } else {
        anunciar(estadoTxt, `${plural(linhas.length, "assunto", "assuntos")}${estado.q ? ` com “${estado.q}”` : ""}${estado.ind ? ", só com voto de cada deputado" : ""}`);
      }
    }

    let espera;
    campoBusca.addEventListener("input", () => { clearTimeout(espera); espera = setTimeout(atualizar, 180); });
    caixaInd.addEventListener("change", atualizar);
    seletor.addEventListener("change", atualizar);
    await atualizar();
    return document.getElementById("titulo-inicio");
  }

  // ------------------------------------------------------------------ página do assunto
  const TIPO = {
    nominal: "Cada deputado votou",
    simbolica: "Votação simbólica (sem o voto de cada deputado)",
    secreta: "Votação secreta",
  };

  function cartaoProjeto(pr, slug, nomes) {
    const incerto = (pr.ca && pr.ca !== "alta") || (pr.cr && pr.cr !== "alta");
    const abrir = h("span", { class: "projeto__abrir", "aria-hidden": "true" }, "Ler resumo");
    const detalhes = h("details", { class: "projeto" });
    detalhes.addEventListener("toggle", () => { abrir.textContent = detalhes.open ? "Fechar" : "Ler resumo"; });

    const outro = pr.a === slug ? (pr.s ? `Também trata de ${nomes[pr.s]}` : null) : `Assunto principal: ${nomes[pr.a]}`;
    const meta = h("span", { class: "projeto__meta" },
      h("span", {}, "Votado em ", h("b", {}, data(pr.ultima))),
      h("span", {}, TIPO[pr.tipo] || ""),
      h("span", {}, pr.aprovada ? "Aprovado" : "Rejeitado"),
      pr.n > 1 && h("span", {}, `${pr.n} votações`),
      outro && h("span", {}, outro),
      incerto && h("span", { class: "selo-aviso" }, "Classificação incerta"));

    const avisos = [];
    if (pr.aa) avisos.push(h("p", {}, pr.aa));
    if (pr.ar) avisos.push(h("p", {}, pr.ar));
    if (pr.subst) avisos.push(h("p", {}, "O resumo foi feito a partir da ementa do projeto original. A votação foi sobre um substitutivo ou emenda, e o texto votado pode ser diferente."));

    const corpo = h("div", { class: "projeto__corpo" },
      pr.resumo
        ? h("div", {}, h("span", { class: "rotulo-ia" }, "Resumo feito por inteligência artificial"), h("p", {}, pr.resumo))
        : h("p", {}, "Ainda não há resumo deste projeto. Leia o texto oficial abaixo."),
      pr.pontos && pr.pontos.length ? h("div", {}, h("h3", {}, "Pontos principais"), h("ul", {}, pr.pontos.map((x) => h("li", {}, x)))) : null,
      avisos.length ? h("div", { class: "cartao-aviso" }, h("strong", {}, "Atenção"), avisos) : null,
      h("div", {}, h("h3", {}, `Texto oficial (${pr.nome})`), h("p", { class: "oficial" }, pr.ementa || "Sem ementa."),
        pr.texto ? h("p", {}, h("a", { href: pr.texto, target: "_blank", rel: "noopener noreferrer" }, "Ler o texto completo no site da Câmara")) : null));

    detalhes.append(h("summary", {}, h("span", { class: "projeto__titulo" }, pr.titulo), meta, abrir), corpo);
    return h("li", {}, detalhes);
  }

  async function telaAssunto(slug, p) {
    const [assuntos, projetos, meta] = await Promise.all([dados("assuntos"), projetosComTexto(), dados("meta")]);
    const a = assuntos.find((x) => x.slug === slug);
    if (!a) return telaNaoEncontrada();
    const nomes = Object.fromEntries(assuntos.map((x) => [x.slug, x.nome]));
    const base = projetos.filter((x) => x.a === slug || x.s === slug);

    const estado = {
      q: p.get("q") || "", ind: p.get("ind") === "1", ord: p.get("ord") === "antiga" ? "antiga" : "recente",
      res: ["aprovado", "rejeitado"].includes(p.get("res")) ? p.get("res") : "", cert: p.get("cert") === "1",
    };
    let limite = POR_PAGINA;

    const campoBusca = h("input", { id: "busca-a", type: "search", autocomplete: "off", spellcheck: "false", value: estado.q, placeholder: "uma palavra do projeto", enterkeyhint: "search" });
    const seletorOrd = h("select", { id: "ord-a" }, h("option", { value: "recente" }, "Mais recentes primeiro"), h("option", { value: "antiga" }, "Mais antigos primeiro"));
    seletorOrd.value = estado.ord;
    const seletorRes = h("select", { id: "res-a" }, h("option", { value: "" }, "Todos"), h("option", { value: "aprovado" }, "Só aprovados"), h("option", { value: "rejeitado" }, "Só rejeitados"));
    seletorRes.value = estado.res;
    const caixaInd = h("input", { type: "checkbox", id: "ind-a" }); caixaInd.checked = estado.ind;
    const caixaCert = h("input", { type: "checkbox", id: "cert-a" }); caixaCert.checked = estado.cert;
    const estadoTxt = h("p", { class: "estado", role: "status", "aria-live": "polite" });
    const lista = h("ul", { class: "projetos" });
    const maisBox = h("div", { class: "mais" });

    const conteudo = h("div", { class: "miolo" },
      h("nav", { class: "migalhas", "aria-label": "Você está em" },
        h("ol", {}, h("li", {}, h("a", { href: "#/" }, "Assuntos")), h("li", { "aria-current": "page" }, a.nome))),
      h("header", { class: "cabeca-assunto" },
        h("h1", { id: "titulo-assunto", tabindex: "-1" }, a.nome),
        h("p", {}, `${a.descricao.charAt(0).toUpperCase() + a.descricao.slice(1)}. ${plural(a.n, "projeto votado", "projetos votados")}, ${a.n_ind.toLocaleString("pt-BR")} com o voto de cada deputado.`)),
      h("div", { class: "aviso-previa" }, h("p", {}, h("strong", {}, "Versão de teste. "), "Ainda não mostramos como cada deputado votou em cada projeto. Essa é a próxima tela. Por enquanto você já pode ler o que cada projeto propõe e como terminou a votação.")),
      h("form", { class: "filtros", role: "search", "aria-label": `Filtrar projetos de ${a.nome}`, onsubmit: (e) => e.preventDefault() },
        h("div", { class: "filtros__linha" },
          h("div", { class: "campo" }, h("label", { for: "busca-a" }, "Procurar neste assunto"), campoBusca),
          h("div", { class: "campo" }, h("label", { for: "res-a" }, "Resultado da votação"), seletorRes),
          h("div", { class: "campo" }, h("label", { for: "ord-a" }, "Ordem"), seletorOrd)),
        h("div", { class: "filtros__marcas" },
          h("label", { class: "marcar", for: "ind-a" }, caixaInd, h("span", {}, "Só projetos em que cada deputado votou")),
          h("label", { class: "marcar", for: "cert-a" }, caixaCert,
            h("span", {}, "Esconder projetos com aviso de possível erro", h("small", {}, "Deixe desligado para ver tudo. Os avisos aparecem em cada projeto."))))),
      estadoTxt, lista, maisBox);

    principal.replaceChildren(conteudo);
    document.title = `${a.nome}: Voto de Verdade`;

    function atualizar(reiniciar) {
      if (reiniciar) limite = POR_PAGINA;
      estado.q = campoBusca.value.trim(); estado.ord = seletorOrd.value; estado.res = seletorRes.value;
      estado.ind = caixaInd.checked; estado.cert = caixaCert.checked;
      gravarEndereco("assunto/" + slug, limparParams({
        q: estado.q, ind: estado.ind ? "1" : "", ord: estado.ord === "recente" ? "" : estado.ord, res: estado.res, cert: estado.cert ? "1" : "" }));

      const ts = termos(estado.q);
      let r = base.filter((x) =>
        (!ts.length || casa(x._t, ts)) && (!estado.ind || x.ind) &&
        (!estado.res || (estado.res === "aprovado") === x.aprovada) &&
        (!estado.cert || ((x.ca === "alta") && (!x.cr || x.cr === "alta"))));
      r.sort((x, y) => (estado.ord === "recente" ? (y.ultima > x.ultima ? 1 : -1) : (x.ultima > y.ultima ? 1 : -1)) || y.id - x.id);

      const mostrados = r.slice(0, limite);
      lista.replaceChildren(...mostrados.map((x) => cartaoProjeto(x, slug, nomes)));
      const filtrado = r.length !== base.length;
      anunciar(estadoTxt, r.length
        ? `${plural(r.length, "projeto", "projetos")}${filtrado ? ` de ${base.length.toLocaleString("pt-BR")}` : ""}`
        : "Nenhum projeto com esses filtros. Tire algum filtro ou use outra palavra.");
      maisBox.replaceChildren();
      if (r.length > mostrados.length) {
        maisBox.append(h("button", { type: "button", class: "botao botao--leve", onclick: () => { limite += POR_PAGINA; atualizar(false); } },
          `Mostrar mais ${Math.min(POR_PAGINA, r.length - mostrados.length)} projetos`));
      }
    }

    let espera;
    campoBusca.addEventListener("input", () => { clearTimeout(espera); espera = setTimeout(() => atualizar(true), 180); });
    for (const el of [seletorOrd, seletorRes, caixaInd, caixaCert]) el.addEventListener("change", () => atualizar(true));
    atualizar(true);
    return document.getElementById("titulo-assunto");
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
    const nav = document.getElementById("nav-assuntos");
    nav.setAttribute("aria-current", "page");
    let titulo;
    try {
      if (!partes.length) titulo = await telaInicio(p);
      else if (emAssunto && partes[1]) titulo = await telaAssunto(partes[1], p);
      else titulo = telaNaoEncontrada();
    } catch (e) {
      console.error(e);
      principal.replaceChildren(h("div", { class: "miolo", style: "padding-block:3rem" },
        h("h1", { tabindex: "-1", id: "titulo-erro" }, "Não foi possível carregar os dados"),
        h("p", {}, "Verifique sua conexão e recarregue a página.")));
      titulo = document.getElementById("titulo-erro");
    }
    if (moverFoco && titulo) { titulo.focus({ preventScroll: true }); window.scrollTo(0, 0); }
  }

  window.addEventListener("hashchange", () => rotear(true));
  rotear(false);
})();
