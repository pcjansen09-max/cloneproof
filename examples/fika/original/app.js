(function () {
  'use strict';
  var header = document.querySelector('.site-header');
  function onScroll() {
    if (window.scrollY > 40) header.classList.add('scrolled');
    else header.classList.remove('scrolled');
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  var items = document.querySelectorAll('.reveal');
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) {
          e.target.classList.add('in');
          io.unobserve(e.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });
    items.forEach(function (el, i) {
      el.style.transitionDelay = (i % 3) * 90 + 'ms';
      io.observe(el);
    });
  } else {
    items.forEach(function (el) { el.classList.add('in'); });
  }

  var form = document.getElementById('news-form');
  var msg = document.getElementById('form-msg');
  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var v = document.getElementById('email').value.trim();
    if (/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)) {
      msg.textContent = 'Bedankt! Check je inbox voor je kortingscode.';
    } else {
      msg.textContent = 'Vul een geldig e-mailadres in.';
    }
  });
})();
