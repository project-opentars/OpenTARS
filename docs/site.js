// openTARS: abas de instalação, copiar, enviar o link do celular, o interruptor de Wi-Fi e os vídeos. Nada aqui fala com terceiros.
(function () {
  var calmo = matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Escala para o monólito cobrir a tela antes de abrir.
  var mono = document.querySelector('.mono');
  function medir() {
    if (!mono || !mono.offsetWidth) return;
    var alvo = Math.max(innerWidth / mono.offsetWidth, innerHeight / mono.offsetHeight) * 1.12;
    document.documentElement.style.setProperty('--s', alvo.toFixed(2));
  }
  medir();
  addEventListener('resize', medir);

  // Abas: já abrem no sistema de quem visita.
  var abas = [].slice.call(document.querySelectorAll('[role="tab"]'));
  function escolher(aba, foco) {
    abas.forEach(function (a) {
      var sim = a === aba;
      a.setAttribute('aria-selected', sim);
      a.tabIndex = sim ? 0 : -1;
      document.getElementById(a.getAttribute('aria-controls')).hidden = !sim;
    });
    if (foco) aba.focus();
  }
  abas.forEach(function (a, i) {
    a.addEventListener('click', function () { escolher(a); });
    a.addEventListener('keydown', function (e) {
      var passo = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
      if (!passo) return;
      e.preventDefault();
      escolher(abas[(i + passo + abas.length) % abas.length], true);
    });
  });
  var ua = navigator.userAgent;
  var celular = /Android|iPhone|iPad|iPod/i.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
  var inicio = /Mac/.test(ua) ? 't-mac' : /Ubuntu|Debian/i.test(ua) ? 't-deb' : /Linux|X11/.test(ua) ? 't-deb' : 't-win';
  var aba = document.getElementById(inicio);
  if (aba) escolher(aba);

  // No celular não se instala: oferece mandar o link para o computador.
  var bloco = document.querySelector('.phone'), get = document.querySelector('.get');
  if (celular && bloco && get) {
    bloco.hidden = false;
    get.hidden = true;
    var enviar = document.getElementById('enviar'), endereco = 'https://project-opentars.github.io/OpenTARS/';
    enviar.addEventListener('click', function () {
      if (navigator.share) {
        navigator.share({ title: 'openTARS', text: 'Your AI, on your computer.', url: endereco }).catch(function () {});
      } else if (navigator.clipboard) {
        navigator.clipboard.writeText(endereco).then(function () { enviar.textContent = 'Link copied'; });
      }
    });
  }

  // Copiar.
  document.querySelectorAll('[data-copy]').forEach(function (b) {
    b.addEventListener('click', function () {
      navigator.clipboard.writeText(document.getElementById(b.dataset.copy).textContent).then(function () {
        b.textContent = 'Copied';
        setTimeout(function () { b.textContent = 'Copy'; }, 1600);
      }, function () { b.textContent = 'Select it'; });
    });
  });

  // Interruptor: desligar o Wi-Fi marca o que continua funcionando.
  var wifi = document.getElementById('wifi'), secao = document.querySelector('.home'), estado = document.getElementById('wifi-status');
  if (wifi && secao) {
    secao.classList.add('armada');
    secao.querySelectorAll('.still li').forEach(function (li, i) { li.style.setProperty('--i', i); });
    wifi.addEventListener('click', function () {
      var ligado = wifi.getAttribute('aria-checked') === 'true';
      wifi.setAttribute('aria-checked', String(!ligado));
      secao.classList.toggle('off', ligado);
      estado.textContent = ligado ? 'Still working.' : 'Go on, try it.';
    });
  }

  // Vídeos: só tocam quando aparecem; com "reduzir movimento" ficam parados e com controles.
  var videos = document.querySelectorAll('video[data-auto]');
  if (calmo) {
    videos.forEach(function (v) { v.controls = true; });
  } else if ('IntersectionObserver' in window) {
    var olho = new IntersectionObserver(function (itens) {
      itens.forEach(function (i) {
        if (i.isIntersecting) { var p = i.target.play(); if (p) p.catch(function () {}); } else { i.target.pause(); }
      });
    }, { threshold: .15 });
    videos.forEach(function (v) { olho.observe(v); });
  }
})();
