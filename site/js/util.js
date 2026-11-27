/* Utilidades puras do Voto de Verdade: não dependem do idioma, da página nem de dados carregados.
   Primeiro módulo tirado do app.js (veja docs/modulos.md). Tudo aqui precisa continuar sem estado:
   o que depende de idioma (tx, data, num) ou de dados fica em outros módulos. */

// Monta um elemento: h("div", { class: "x", onclick: fn }, filho, "texto", [lista]). Atributo false/null some; true vira atributo vazio.
export function h(tag, attrs, ...filhos) {
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

const SVGNS = "http://www.w3.org/2000/svg";
export function svg(tag, attrs) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
  return el;
}

export const semAcento = (t) => (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

// "pl4952" vale como "pl 4952". Termos de até 3 letras só casam no começo de uma palavra ("ia" não acha "previdência").
export const termos = (q) => semAcento(q).replace(/([a-z])(\d)/g, "$1 $2").split(/\s+/).filter((t) => t.length > 1);
export const casa = (texto, ts) => ts.every((t) => (t.length <= 3 ? texto.startsWith(t) || texto.includes(" " + t) || new RegExp("[^a-z0-9]" + t.replace(/[^a-z0-9]/g, "\\$&")).test(texto) : texto.includes(t)));

// Endereço com "%" malformado (por exemplo #/assunto/%) não pode derrubar o roteador: vira "não encontrado".
export const decodificar = (t) => { try { return decodeURIComponent(t); } catch (e) { return t; } };
// Só aceitamos link https que venha dos dados; qualquer outro esquema (javascript:, data:…) é ignorado.
export const soHttps = (u) => (typeof u === "string" && /^https:\/\//i.test(u) ? u : null);

export const somaDe = (obj, chaves) => chaves.reduce((a, k) => a + (obj[k] || 0), 0);
export const pctNum = (a, b) => (b ? Math.round((1000 * a) / b) / 10 : 0);
