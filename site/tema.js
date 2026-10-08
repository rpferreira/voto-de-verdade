// Aplica o tema escolhido (claro ou escuro) antes de a página aparecer, para não piscar.
// Fica em arquivo próprio (e não dentro da página) para a política de segurança do site não precisar permitir scripts embutidos.
try {
  var t = localStorage.getItem("tema");
  if (t === "dark" || t === "light") document.documentElement.dataset.theme = t;
} catch (e) { /* sem armazenamento: vale o tema do aparelho */ }
