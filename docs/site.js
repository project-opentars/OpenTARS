// Efeitos de mouse do site: brilho que segue o cursor nos painéis escuros e inclinação leve no terminal e nas capturas.
// Só com mouse de verdade e sem "reduzir movimento"; no toque e em leitores de tela a página continua igual.
(function () {
  if (!matchMedia('(hover: hover) and (pointer: fine)').matches) return;
  document.documentElement.classList.add('com-mouse');
  var calmo = matchMedia('(prefers-reduced-motion: reduce)').matches;
  var INCLINACAO = 4; // graus no máximo
  document.querySelectorAll('.term, .model, .tested, .cloud, .shot, .cmd').forEach(function (el) {
    var inclina = !calmo && (el.classList.contains('term') || el.classList.contains('shot'));
    var caixa = null, pedido = 0, x = 0, y = 0;

    function aplicar() {
      pedido = 0;
      if (!caixa) return;
      var px = (x - caixa.left) / caixa.width, py = (y - caixa.top) / caixa.height;
      el.style.setProperty('--mx', (px * 100).toFixed(1) + '%');
      el.style.setProperty('--my', (py * 100).toFixed(1) + '%');
      if (inclina) {
        el.style.setProperty('--ry', ((px - 0.5) * 2 * INCLINACAO).toFixed(2) + 'deg');
        el.style.setProperty('--rx', ((0.5 - py) * 2 * INCLINACAO).toFixed(2) + 'deg');
      }
    }
    function soltar() {
      caixa = null;
      if (pedido) { cancelAnimationFrame(pedido); pedido = 0; }
      el.classList.remove('sob-mouse');
      el.style.setProperty('--rx', '0deg');
      el.style.setProperty('--ry', '0deg');
      document.removeEventListener('pointermove', seguir);
      removeEventListener('scroll', soltar);
    }
    // Enquanto o mouse está em cima, quem decide se ele saiu é a caixa medida na ENTRADA (painel reto), e não o contorno
    // inclinado: perto da borda, a inclinação faria o painel "fugir" do cursor e piscar.
    function seguir(e) {
      x = e.clientX; y = e.clientY;
      if (x < caixa.left || x > caixa.right || y < caixa.top || y > caixa.bottom) return soltar();
      if (!pedido) pedido = requestAnimationFrame(aplicar);
    }
    el.addEventListener('pointerenter', function (e) {
      if (caixa) return;
      caixa = el.getBoundingClientRect();
      el.classList.add('sob-mouse');
      document.addEventListener('pointermove', seguir);
      addEventListener('scroll', soltar, { passive: true }); // rolando, o painel sai de baixo do mouse: solta
      seguir(e);
    });
  });
})();
