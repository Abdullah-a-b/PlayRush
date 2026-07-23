function createStars() {
  const starsContainer = document.getElementById("stars");
  if (!starsContainer) return;

  // 📱 على الجوال/التطبيق نقلّل عدد النجوم: 150 عنصراً متحركاً
  // تُثقل أول إطار داخل WebView وتبدو كتعليق.
  const isApp    = window.PR_IS_APP === true || (typeof window.Capacitor !== 'undefined');
  const isMobile = isApp || window.innerWidth <= 820
                || (window.matchMedia && window.matchMedia('(pointer: coarse)').matches);
  const COUNT = isMobile ? 45 : 150;

  // نبني في DocumentFragment: إدراج واحد بدل 150 إعادة تخطيط
  const frag = document.createDocumentFragment();
  for (let i = 0; i < COUNT; i++) {
    const star = document.createElement("div");
    star.className = "star" + (Math.random() > 0.3 ? " purple" : "");
    star.style.left = `${Math.random() * 100}%`;
    star.style.top = `${Math.random() * 100}%`;
    star.style.animationDelay = `${Math.random() * 2}s`;
    frag.appendChild(star);
  }
  starsContainer.appendChild(frag);
}

// نؤجّل الرسم لما بعد أول إطار حتى تظهر الواجهة فوراً
window.addEventListener("load", () => {
  if (window.requestIdleCallback) requestIdleCallback(createStars, { timeout: 800 });
  else requestAnimationFrame(() => setTimeout(createStars, 0));
});
