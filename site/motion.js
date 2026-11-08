// The motion layer. Only what explains something moves: the hero figures count up to their values.
// Section reveals are a short CSS fade (styles.css). With reduced motion, a failed script or no GSAP,
// the page is complete and still.
(() => {
  if (!window.gsap || !window.Stage) return;
  Stage.init();
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const count = (el, to, digits = 2) => {
    const o = { v: 0 };
    gsap.to(o, { v: to, duration: 0.8, delay: 0.3, ease: 'expo.out', onUpdate: () => { if (!el.dataset.userSet) el.textContent = o.v.toFixed(digits); } });
  };
  const needed = document.querySelector('[data-needed]');
  const free = document.querySelector('.chip-b .chip-value b');
  if (needed) count(needed, parseFloat(needed.textContent));
  if (free) count(free, parseFloat(free.textContent));
})();
