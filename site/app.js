/* Voto de Verdade: telas "Assuntos" (início), "Página do assunto", "Votação", "Deputados" e "Página do deputado".
   JavaScript puro, sem bibliotecas. Os dados vêm de dados/*.json (feitos por site/exportar_dados.py).
   Endereços: #/   #/assunto/<slug>?q=...&ind=1&ord=...   #/votacao/<id>?q=...&pt=PT&uf=GO&v=S
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

  // Resumo, pontos principais, avisos e texto oficial de um projeto (usado na página do assunto e na da votação).
  function blocosProjeto(pr, semResumo) {
    const avisos = [];
    if (pr.aa) avisos.push(h("p", {}, pr.aa));
    if (pr.ar) avisos.push(h("p", {}, pr.ar));
    if (pr.subst) avisos.push(h("p", {}, "O resumo foi feito a partir da ementa do projeto original. A votação foi sobre um substitutivo ou emenda, e o texto votado pode ser diferente."));
    return [
      semResumo ? null : pr.resumo
        ? h("div", {}, h("span", { class: "rotulo-ia" }, "Resumo feito por inteligência artificial"), h("p", {}, pr.resumo))
        : h("p", {}, "Ainda não há resumo deste projeto. Leia o texto oficial abaixo."),
      pr.pontos && pr.pontos.length ? h("div", {}, h("h3", {}, "Pontos principais"), h("ul", {}, pr.pontos.map((x) => h("li", {}, x)))) : null,
      avisos.length ? h("div", { class: "cartao-aviso" }, h("strong", {}, "Atenção"), avisos) : null,
      h("div", {}, h("h3", {}, `Texto oficial (${pr.nome})`), h("p", { class: "oficial" }, pr.ementa || "Sem ementa."),
        pr.texto ? h("p", {}, h("a", { href: pr.texto, target: "_blank", rel: "noopener noreferrer" }, "Ler o texto completo no site da Câmara")) : null),
    ];
  }

  // As votações de um projeto, cada uma com o caminho para ver o voto de cada deputado.
  function blocoVotacoes(pr, votacoes) {
    const minhas = (votacoes.porProjeto[pr.id] || []).slice().sort((x, y) => (x.d < y.d ? 1 : x.d > y.d ? -1 : 0));
    if (!minhas.length) return null;
    return h("div", { class: "votacoes" },
      h("h3", {}, minhas.length === 1 ? "Votação" : `${minhas.length} votações`),
      h("ul", {}, minhas.map((v) => h("li", {},
        h("p", { class: "votacao__quando" }, h("b", {}, data(v.d)), ` · ${v.ap ? "Aprovada" : "Rejeitada"} · ${TIPO[v.t] || ""}`),
        h("p", { class: "oficial" }, v.desc),
        v.c !== "alta" && v.av ? h("p", { class: "cartao-aviso" }, v.av) : null,
        v.t === "nominal"
          ? h("p", {}, h("a", { class: "botao-link", href: "#/votacao/" + encodeURIComponent(v.id) }, "Ver como cada deputado votou"))
          : h("p", { class: "oficial" }, v.t === "secreta"
              ? "Votação secreta: o voto de cada deputado não é divulgado."
              : "Votação simbólica: o resultado foi anunciado sem registrar o voto de cada deputado.")))));
  }

  function cartaoProjeto(pr, slug, nomes, votacoes) {
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

    const corpo = h("div", { class: "projeto__corpo" }, blocosProjeto(pr), blocoVotacoes(pr, votacoes));

    detalhes.append(h("summary", {}, h("span", { class: "projeto__titulo" }, pr.titulo), meta, abrir), corpo);
    return h("li", {}, detalhes);
  }

  async function telaAssunto(slug, p) {
    const [assuntos, projetos, meta, votacoes] = await Promise.all([dados("assuntos"), projetosComTexto(), dados("meta"), indiceVotacoes()]);
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
      lista.replaceChildren(...mostrados.map((x) => cartaoProjeto(x, slug, nomes, votacoes)));
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

  // ------------------------------------------------------------------ tela de votação
  const VOTO = {
    S: { nome: "Sim", plural: "votaram sim" },
    N: { nome: "Não", plural: "votaram não" },
    A: { nome: "Abstenção", plural: "se abstiveram" },
    O: { nome: "Obstrução", plural: "fizeram obstrução" },
    P: { nome: "Presidia a sessão", plural: "presidiam a sessão" },
  };
  const ORDEM_VOTO = ["S", "N", "A", "O", "P"];

  const fichaVoto = (cod) => h("span", { class: "voto voto--" + cod }, VOTO[cod].nome);

  async function telaVotacao(id, p) {
    const [vots, deputados, projetos, assuntos] = await Promise.all([indiceVotacoes(), dados("deputados"), dados("projetos"), dados("assuntos")]);
    const v = vots.porId[id];
    if (!v) return telaNaoEncontrada();
    const pr = projetos.find((x) => x.id === v.p);
    if (!pr) return telaNaoEncontrada();
    const assunto = assuntos.find((x) => x.slug === pr.a);

    const outras = (vots.porProjeto[pr.id] || []).filter((x) => x.id !== v.id).sort((x, y) => (x.d < y.d ? 1 : -1));
    const nominal = v.t === "nominal";
    let linhas = [];
    if (nominal) {
      const arq = await dados("votacoes/" + id);
      const porId = Object.fromEntries(deputados.map((d) => [d.id, d]));
      linhas = arq.v.map(([did, cod, partido]) => {
        const d = porId[did] || { nome: "Deputado " + did, uf: "" };
        return { id: did, nome: d.nome, uf: d.uf || "", partido: partido || d.partido || "", cod, _t: semAcento(d.nome) };
      });
    }

    const migalhas = h("nav", { class: "migalhas", "aria-label": "Você está em" },
      h("ol", {},
        h("li", {}, h("a", { href: "#/" }, "Assuntos")),
        assunto ? h("li", {}, h("a", { href: "#/assunto/" + assunto.slug }, assunto.nome)) : null,
        h("li", { "aria-current": "page" }, "Votação de " + data(v.d))));

    const cabeca = h("header", { class: "cabeca-assunto" },
      h("p", { class: "cabeca-assunto__projeto" }, pr.nome),
      h("h1", { id: "titulo-votacao", tabindex: "-1" }, `Votação de ${data(v.d)}`),
      h("p", { class: "cabeca-assunto__resultado" }, `${v.ap ? "Aprovada" : "Rejeitada"}. ${nominal ? "Cada deputado votou." : TIPO[v.t] || ""}`),
      pr.resumo
        ? h("div", { class: "sobre-projeto" }, h("span", { class: "rotulo-ia" }, "Resumo do projeto feito por inteligência artificial"), h("p", {}, pr.resumo))
        : h("div", { class: "sobre-projeto" }, h("p", {}, pr.ementa || "")));

    const oficial = h("section", { class: "votacao-oficial", "aria-labelledby": "oficial-titulo" },
      h("h2", { id: "oficial-titulo" }, "O que foi votado"),
      h("p", { class: "oficial" }, v.desc),
      v.c !== "alta" && v.av ? h("div", { class: "cartao-aviso" }, h("strong", {}, "Atenção"), h("p", {}, v.av)) : null);

    const sobre = h("details", { class: "ajuda ajuda--solta" },
      h("summary", {}, "Ver os pontos principais e o texto oficial do projeto"),
      h("div", { class: "projeto__corpo" }, blocosProjeto(pr, true)));

    const outrasVot = outras.length ? h("section", { class: "outras-votacoes", "aria-labelledby": "outras-titulo" },
      h("h2", { id: "outras-titulo" }, "Outras votações deste projeto"),
      h("ul", {}, outras.map((o) => h("li", {},
        o.t === "nominal" ? h("a", { href: "#/votacao/" + encodeURIComponent(o.id) }, `${data(o.d)}`) : h("span", {}, data(o.d)),
        ` · ${o.ap ? "Aprovada" : "Rejeitada"} · ${TIPO[o.t] || ""}`)))) : null;

    document.title = `Votação de ${data(v.d)}, ${pr.nome}: Voto de Verdade`;

    if (!nominal) {
      principal.replaceChildren(h("div", { class: "miolo" }, migalhas, cabeca, oficial,
        h("div", { class: "aviso-previa" }, h("p", {}, v.t === "secreta"
          ? "Esta votação foi secreta. A Câmara não divulga o voto de cada deputado."
          : "Esta votação foi simbólica: os partidos chegaram a um acordo e o resultado foi anunciado sem registrar o voto de cada deputado. Por isso não há como mostrar como cada um votou.")),
        sobre, outrasVot));
      return document.getElementById("titulo-votacao");
    }

    // ---- votação nominal
    const total = {}; for (const l of linhas) total[l.cod] = (total[l.cod] || 0) + 1;
    const nTotal = linhas.length;
    const partidos = [...new Set(linhas.map((l) => l.partido))].filter(Boolean).sort((a, b) => a.localeCompare(b, "pt-BR"));
    const ufs = [...new Set(linhas.map((l) => l.uf))].filter(Boolean).sort();

    const placar = h("dl", { class: "placar" }, ORDEM_VOTO.filter((c) => total[c]).map((c) =>
      h("div", {}, h("dt", {}, VOTO[c].nome), h("dd", {}, (total[c] || 0).toLocaleString("pt-BR")))));
    const barraTotal = h("div", { class: "barra-voto", "aria-hidden": "true" }, ORDEM_VOTO.filter((c) => total[c]).map((c) =>
      h("i", { class: "seg-" + c, style: `width:${(total[c] / nTotal) * 100}%` })));

    const estado = {
      q: p.get("q") || "", pt: partidos.includes(p.get("pt")) ? p.get("pt") : "", uf: ufs.includes(p.get("uf")) ? p.get("uf") : "",
      v: VOTO[p.get("v")] ? p.get("v") : "", ord: ["partido", "uf"].includes(p.get("ord")) ? p.get("ord") : "nome",
    };
    let limite = 60;

    const campoQ = h("input", { id: "busca-dep", type: "search", autocomplete: "off", spellcheck: "false", value: estado.q, placeholder: "nome do deputado", enterkeyhint: "search" });
    const selPt = h("select", { id: "sel-pt" }, h("option", { value: "" }, "Todos os partidos"), partidos.map((x) => h("option", { value: x }, x)));
    const selUf = h("select", { id: "sel-uf" }, h("option", { value: "" }, "Todos os estados"), ufs.map((x) => h("option", { value: x }, x)));
    const selV = h("select", { id: "sel-v" }, h("option", { value: "" }, "Todos os votos"), ORDEM_VOTO.filter((c) => total[c]).map((c) => h("option", { value: c }, VOTO[c].nome)));
    const selOrd = h("select", { id: "sel-ord" }, h("option", { value: "nome" }, "Nome do deputado"), h("option", { value: "partido" }, "Partido"), h("option", { value: "uf" }, "Estado"));
    selPt.value = estado.pt; selUf.value = estado.uf; selV.value = estado.v; selOrd.value = estado.ord;
    const limpar = h("button", { type: "button", class: "botao botao--leve", id: "limpar" }, "Limpar filtros");

    const estadoTxt = h("p", { class: "estado", role: "status", "aria-live": "polite" });
    const tabelaBox = h("div", { class: "tabela-rolavel", tabindex: "0", role: "region", "aria-label": "Como cada partido votou" });
    const lista = h("ul", { class: "deputados" });
    const maisBox = h("div", { class: "mais" });

    const filtros = h("form", { class: "filtros", role: "search", "aria-label": "Filtrar os votos", onsubmit: (e) => e.preventDefault() },
      h("div", { class: "filtros__linha filtros__linha--4" },
        h("div", { class: "campo" }, h("label", { for: "busca-dep" }, "Nome do deputado"), campoQ),
        h("div", { class: "campo" }, h("label", { for: "sel-pt" }, "Partido"), selPt),
        h("div", { class: "campo" }, h("label", { for: "sel-uf" }, "Estado"), selUf),
        h("div", { class: "campo" }, h("label", { for: "sel-v" }, "Voto"), selV)),
      h("div", { class: "filtros__rodape" },
        h("div", { class: "campo campo--curto" }, h("label", { for: "sel-ord" }, "Ordenar a lista por"), selOrd),
        limpar));

    const ajudaVotos = h("details", { class: "ajuda ajuda--solta" },
      h("summary", {}, "O que significam abstenção, obstrução e “presidia a sessão”?"),
      h("ul", {},
        h("li", {}, h("b", {}, "Abstenção: "), "o deputado esteve presente e escolheu não votar nem sim nem não."),
        h("li", {}, h("b", {}, "Obstrução: "), "o deputado ou seu partido age para atrasar ou impedir a votação, em geral não votando."),
        h("li", {}, h("b", {}, "Presidia a sessão: "), "quem conduz a sessão só vota em situações previstas no regimento (artigo 17). O registro aparece assim nos dados da Câmara.")));

    const conteudo = h("div", { class: "miolo" }, migalhas, cabeca, oficial,
      h("section", { "aria-labelledby": "placar-titulo" },
        h("h2", { id: "placar-titulo" }, "Resultado"),
        placar, barraTotal,
        h("p", { class: "nota" }, `${plural(nTotal, "deputado registrou", "deputados registraram")} voto nesta votação. Quem faltou ou não votou não aparece na lista.`)),
      sobre,
      h("section", { "aria-labelledby": "partidos-titulo", class: "bloco" },
        h("h2", { id: "partidos-titulo" }, "Como cada partido votou"),
        h("p", { class: "nota" }, "Cada deputado conta no partido em que estava no dia da votação. Escolha um partido para ver os deputados dele."),
        tabelaBox),
      h("section", { "aria-labelledby": "deputados-titulo", class: "bloco" },
        h("h2", { id: "deputados-titulo" }, "Como cada deputado votou"),
        filtros, estadoTxt, lista, maisBox, ajudaVotos),
      outrasVot);
    principal.replaceChildren(conteudo);

    function filtrar(ignorar) {
      const ts = termos(estado.q);
      return linhas.filter((l) =>
        (!ts.length || casa(l._t, ts)) && (ignorar.includes("pt") || !estado.pt || l.partido === estado.pt) &&
        (!estado.uf || l.uf === estado.uf) && (ignorar.includes("v") || !estado.v || l.cod === estado.v));
    }

    function desenharTabela() {
      const base = filtrar(["pt", "v"]);
      const por = {};
      for (const l of base) { const t = (por[l.partido || "Sem partido"] ||= { S: 0, N: 0, O: 0, n: 0 }); t.n++; if (l.cod === "S" || l.cod === "N") t[l.cod]++; else t.O++; }
      const nomes = Object.keys(por).sort((a, b) => a.localeCompare(b, "pt-BR"));
      if (!nomes.length) { tabelaBox.replaceChildren(h("p", { class: "nota" }, "Nenhum deputado com esses filtros.")); return; }
      tabelaBox.replaceChildren(h("table", { class: "tabela-partidos" },
        h("caption", { class: "so-leitor" }, "Votos por partido"),
        h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Partido"), h("th", { scope: "col", class: "num" }, "Sim"), h("th", { scope: "col", class: "num" }, "Não"),
          h("th", { scope: "col", class: "num" }, "Outros"), h("th", { scope: "col", class: "num" }, "Total"))),
        h("tbody", {}, nomes.map((nm) => {
          const t = por[nm];
          const ativo = estado.pt === nm;
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
      estado.q = campoQ.value.trim(); estado.pt = selPt.value; estado.uf = selUf.value; estado.v = selV.value; estado.ord = selOrd.value;
      gravarEndereco("votacao/" + encodeURIComponent(id), limparParams({ q: estado.q, pt: estado.pt, uf: estado.uf, v: estado.v, ord: estado.ord === "nome" ? "" : estado.ord }));
      desenharTabela();

      const r = filtrar([]);
      const cmp = (a, b) => a.nome.localeCompare(b.nome, "pt-BR");
      r.sort(estado.ord === "partido" ? (a, b) => a.partido.localeCompare(b.partido, "pt-BR") || cmp(a, b)
        : estado.ord === "uf" ? (a, b) => a.uf.localeCompare(b.uf, "pt-BR") || cmp(a, b) : cmp);
      const mostrados = r.slice(0, limite);
      lista.replaceChildren(...mostrados.map((l) => h("li", { class: "deputado" },
        h("a", { class: "deputado__nome", href: "#/deputado/" + l.id }, l.nome),
        h("span", { class: "deputado__sub" }, [l.partido, l.uf].filter(Boolean).join(" · ")),
        fichaVoto(l.cod))));

      const filtrado = r.length !== nTotal;
      anunciar(estadoTxt, r.length
        ? `${plural(r.length, "deputado", "deputados")}${filtrado ? ` de ${nTotal.toLocaleString("pt-BR")}` : ""}`
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
    for (const el of [selPt, selUf, selV, selOrd]) el.addEventListener("change", () => atualizar(true));
    limpar.addEventListener("click", () => { campoQ.value = ""; selPt.value = ""; selUf.value = ""; selV.value = ""; atualizar(true); campoQ.focus(); });
    atualizar(true);
    return document.getElementById("titulo-votacao");
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
            h("p", { class: "nota" }, `${plural(votos.length, "votação nominal com voto registrado", "votações nominais com voto registrado")}, de ${data(meta.de)} a ${data(meta.ate)}. Votações simbólicas não registram o voto de cada deputado, então não entram aqui. Quando o deputado faltou ou não votou, a votação não aparece.`))
        : h("p", { class: "aviso-previa" }, "Não há voto registrado deste deputado nas votações nominais do período."));

    if (temVotos) {
      conteudo.append(
        h("section", { class: "bloco", "aria-labelledby": "assuntos-dep" },
          h("h2", { id: "assuntos-dep" }, "Por assunto"),
          h("p", { class: "nota" }, "Conta pelo assunto principal de cada projeto. Escolha um assunto para ver só os votos nele."),
          tabelaBox),
        h("section", { class: "bloco", "aria-labelledby": "lista-dep" },
          h("h2", { id: "lista-dep" }, "Votação por votação"),
          h("form", { class: "filtros", role: "search", "aria-label": "Filtrar os votos de " + dep.nome, onsubmit: (e) => e.preventDefault() },
            h("div", { class: "filtros__linha filtros__linha--4" },
              h("div", { class: "campo" }, h("label", { for: "busca-v" }, "Procurar nos projetos"), campoQ),
              h("div", { class: "campo" }, h("label", { for: "dep-a" }, "Assunto"), selA),
              h("div", { class: "campo" }, h("label", { for: "dep-v" }, "Voto"), selV),
              h("div", { class: "campo" }, h("label", { for: "dep-ord" }, "Ordem"), selOrd)),
            h("div", { class: "filtros__rodape" }, limpar)),
          estadoTxt, lista, maisBox,
          h("p", { class: "nota" }, "Votar sim ou não em uma votação não diz, sozinho, se o deputado apoia o assunto do projeto. Muitas votações são sobre emendas, substitutivos ou pontos separados do texto (destaques). Leia o que foi votado em cada uma.")));
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
      lista.replaceChildren(...mostrados.map(({ v, pr, cod }) => h("li", { class: "voto-dep" },
        h("div", { class: "voto-dep__topo" }, h("b", {}, data(v.d)), fichaVoto(cod)),
        h("p", { class: "voto-dep__titulo" }, pr.titulo),
        h("p", { class: "oficial" }, `${pr.nome}. ${v.desc}`),
        h("p", {}, h("a", { href: "#/votacao/" + encodeURIComponent(v.id) }, "Ver a votação e os outros deputados"),
          " · ", h("a", { href: "#/assunto/" + pr.a }, nomeAssunto[pr.a] || "Assunto"))))); 
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
      else if (partes[0] === "votacao" && partes[1]) titulo = await telaVotacao(partes[1], p);
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
    if (moverFoco && titulo) { titulo.focus({ preventScroll: true }); window.scrollTo(0, 0); }
  }

  window.addEventListener("hashchange", () => rotear(true));
  rotear(false);
})();
