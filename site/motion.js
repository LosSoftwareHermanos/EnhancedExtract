// The motion layer. Everything here moves what is already on the page: with reduced motion, a failed
// script or no GSAP, the page is complete and still.
//
// The one big moment is the "How it works" scene: its yellow stage holds for two screens and the scroll
// runs the 24-part job, so the parts strike out and the free space comes back as the visitor scrolls.
// Around it: headings rise line by line, screenshots wipe open, pictures drift inside their frames, the
// terminal capture prints top to bottom, lists arrive in order, and the hero eases away as it leaves.
(() => {
  if (!window.gsap || !window.ScrollTrigger || !window.Stage) return;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const once = (trigger, start = 'top 88%') => ({ trigger, start, once: true });

  /* ---------- the scene: scroll runs the job ---------- */
  window.Scenes = window.Scenes || {};
  Scenes['space-back'] = (root, o = {}) => Stage.scene(root, {
    hold: o.hold ?? 2,
    scrub: true,
    phone: 'rest',                       // the phone keeps the slider and the Play button
    build(tl) {
      // Verification is quick to watch; the deleting gets most of the hold, and the end rests a beat.
      const job = { v: 0 };
      const push = () => { if (window.EESim && !EESim.playing) EESim.set(Math.round(job.v)); };
      if (window.EESim) EESim.set(0);
      tl.to(job, { v: 430, duration: 0.16, ease: 'none', onUpdate: push }, 0.04)
        .to(job, { v: 880, duration: 0.6, ease: 'none', onUpdate: push }, 0.2)
        .to(job, { v: 1000, duration: 0.08, ease: 'none', onUpdate: push }, 0.8);
    },
  });

  Stage.smooth();
  Stage.init();
  if (reduce) return;

  /* ---------- hero: numbers count in, then the hero eases away as it leaves ---------- */
  const count = (el, to, digits = 2) => {
    const o = { v: 0 };
    gsap.to(o, { v: to, duration: 1.1, delay: 0.5, ease: 'expo.out', onUpdate: () => { if (!el.dataset.userSet) el.textContent = o.v.toFixed(digits); } });
  };
  const needed = document.querySelector('[data-needed]');
  const free = document.querySelector('.chip-b .chip-value b');
  if (needed) count(needed, parseFloat(needed.textContent));
  if (free) count(free, parseFloat(free.textContent));

  const hero = document.querySelector('.hero');
  if (hero && !Stage.phone) {
    const out = { trigger: hero, start: 'top top', end: 'bottom 30%', scrub: true };
    gsap.to('.hero-title', { yPercent: -18, ease: 'none', scrollTrigger: out });
    gsap.to('.chip-a', { y: -90, ease: 'none', scrollTrigger: out });
    gsap.to('.chip-c', { y: -60, ease: 'none', scrollTrigger: out });
    gsap.to('.chip-b', { y: -120, ease: 'none', scrollTrigger: out });
  }
  // The recording grows into place as it comes up the screen.
  gsap.fromTo('.demo-wrap', { scale: 0.9, y: 40 }, {
    scale: 1, y: 0, ease: 'none',
    scrollTrigger: { trigger: '.demo-wrap', start: 'top bottom', end: 'top 30%', scrub: true },
  });

  /* ---------- headings: lines rise from behind their own baseline ---------- */
  const heads = $$('main h2.h2, .foot-contact');
  heads.forEach((h) => { h.removeAttribute('data-reveal'); h.classList.add('is-in'); });
  document.fonts.ready.then(() => {
    heads.forEach((h) => {
      SplitText.create(h, {
        type: 'lines', mask: 'lines', aria: 'auto', autoSplit: true,
        onSplit: (self) => gsap.from(self.lines, {
          yPercent: 112, duration: 1, ease: 'expo.out', stagger: 0.09,
          scrollTrigger: once(h, 'top 90%'),
        }),
      });
    });
    ScrollTrigger.refresh();
  });

  /* ---------- screenshots: the picture wipes open inside its frame ---------- */
  $$('.frame:not(.demo)').forEach((f) => {
    f.removeAttribute('data-reveal');
    f.classList.add('is-in');
    const img = f.querySelector('img');
    if (!img) return;
    gsap.fromTo(img, { clipPath: 'inset(0% 0% 100% 0%)' }, {
      clipPath: 'inset(0% 0% 0% 0%)', duration: 1.15, ease: 'power4.inOut',
      scrollTrigger: once(f, 'top 90%'),
      clearProps: 'clipPath',
    });
  });

  // Pictures held a little larger than their frames drift as the page passes.
  $$('.mosaic img, .safety-shot img, .needs-shot img').forEach((img) => {
    gsap.set(img, { scale: 1.08 });
    gsap.fromTo(img, { yPercent: -3 }, {
      yPercent: 3, ease: 'none',
      scrollTrigger: { trigger: img.closest('figure'), start: 'top bottom', end: 'bottom top', scrub: true },
    });
  });

  // The terminal capture prints top to bottom, tied to the scroll like output arriving.
  const term = document.querySelector('.cli-shot img');
  if (term) {
    gsap.killTweensOf(term);
    gsap.fromTo(term, { clipPath: 'inset(0% 0% 100% 0%)' }, {
      clipPath: 'inset(0% 0% 0% 0%)', ease: 'steps(18)',
      scrollTrigger: { trigger: '.cli-shot', start: 'top 85%', end: 'center 50%', scrub: 0.3 },
    });
  }

  /* ---------- the job bar builds left to right before the scene starts ---------- */
  gsap.from('.stage', {
    clipPath: 'inset(0% 100% 0% 0%)', duration: 0.9, ease: 'power3.inOut', stagger: 0.12,
    scrollTrigger: once('.stages', 'top 92%'), clearProps: 'clipPath',
  });

  /* ---------- lists arrive in order ---------- */
  const lists = [
    ['.needs-table', 'tr'],
    ['.faq-list', 'details'],
    ['.check-steps', 'li'],
    ['#download .dl-rows', '.dl-row'],
    ['.answer-rows', 'div'],
    ['.examples', '.ex'],
    ['.bars', '.bar-row'],
    ['.foot-meta', 'p'],
    ['.foot-top', ':scope > *'],
  ];
  lists.forEach(([box, item]) => {
    const b = document.querySelector(box);
    if (!b) return;
    gsap.from(b.querySelectorAll(item), {
      y: 18, autoAlpha: 0, duration: 0.7, ease: 'power3.out', stagger: 0.055,
      scrollTrigger: once(b, 'top 90%'),
    });
  });

  /* ---------- the closing line slides home onto the margin as the page ends ---------- */
  const footContactOffset = matchMedia('(max-width: 1080px)').matches ? '1.5%' : '7%';
  gsap.fromTo('.foot-contact', { x: footContactOffset }, {
    x: '0%', ease: 'none',
    scrollTrigger: { trigger: '.foot', start: 'top bottom', end: 'bottom bottom', scrub: true },
  });

  addEventListener('load', () => ScrollTrigger.refresh());
})();
