/* مساحة المباراة المرئية، دون تغيير قواعد اللعبة أو أحداثها. */
(function () {
  const main = document.querySelector('.bank-main, .career-main');
  const answer = document.getElementById('answerBox');
  if (!main || !answer) return;
  document.body.classList.add('mobile-match');
  const helps = document.getElementById('careerHelpsBar') || document.getElementById('bankHelpsBar');
  if (helps) main.appendChild(helps);
  const viewport = window.visualViewport;
  let baseline = window.innerHeight;
  function sync() {
    const height = viewport ? viewport.height : window.innerHeight;
    const focused = document.activeElement === document.getElementById('answerInput');
    if (!focused) baseline = Math.max(height, window.innerHeight);
    document.documentElement.style.setProperty('--match-height', `${Math.round(height)}px`);
    const keyboard = window.innerWidth <= 768 && baseline - height > 120;
    document.body.classList.toggle('match-keyboard-open', keyboard);
    document.body.classList.toggle('match-answering', answer.style.display !== 'none');
  }
  viewport?.addEventListener('resize', sync);
  window.addEventListener('resize', sync);
  document.addEventListener('focusout', () => setTimeout(sync, 100));
  new MutationObserver(sync).observe(answer, { attributes: true, attributeFilter: ['style'] });
  sync();
})();
