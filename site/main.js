(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const fmt = (n) => n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  /* ---------- hero: the deletion switch changes the space the job needs ---------- */
  const toggle = $('[data-delete-toggle]');
  if (toggle) {
    const needed = $('[data-needed]'), fit = $('[data-fit]'), chipA = $('.chip-a'), chipB = $('.chip-b');
    const sync = () => {
      const on = toggle.checked;
      needed.textContent = on ? '9.87' : '53.10';
      fit.textContent = on ? 'Fits' : 'Won’t fit';
      fit.className = 'state ' + (on ? 'is-ok' : 'is-bad');
      chipA.classList.toggle('is-bad', !on);
      chipB.classList.toggle('is-bad', !on);
    };
    toggle.addEventListener('change', () => { needed.dataset.userSet = 'true'; sync(); });
    sync();
  }

  /* ---------- videos: play only while on screen, never under reduced motion ---------- */
  const vids = $$('video[data-autoplay]');
  const want = new WeakMap();
  const vio = new IntersectionObserver((entries) => {
    for (const e of entries) {
      const v = e.target;
      if (e.isIntersecting && !reduce.matches && want.get(v) !== false) {
        if (v.preload === 'none') v.preload = 'auto';
        v.play().catch(() => {});
      } else v.pause();
    }
  }, { threshold: 0.2 });
  vids.forEach((v) => vio.observe(v));
  /* ---------- the recorded run: plays only when asked ---------- */
  const demo = $('[data-demo]');
  if (demo) {
    const v = $('video', demo), play = $('[data-demo-play]', demo), pause = $('[data-demo-pause]', demo), label = $('[data-demo-label]', demo);
    const sync = () => {
      const playing = !v.paused && !v.ended;
      demo.classList.toggle('is-playing', playing);
      play.hidden = playing;
      pause.hidden = !playing;
      label.textContent = v.ended ? 'Watch again' : v.currentTime > 0 ? 'Keep watching' : 'Watch it run';
    };
    ['play', 'pause', 'ended'].forEach((e) => v.addEventListener(e, sync));
    play.addEventListener('click', () => {
      if (v.ended) v.currentTime = 0;
      v.play().then(() => pause.focus({ preventScroll: true })).catch(() => {});
    });
    pause.addEventListener('click', () => { v.pause(); play.focus({ preventScroll: true }); });
    v.addEventListener('click', () => { if (!v.paused) v.pause(); });
    // Leaving the screen pauses it; the visitor resumes it themselves.
    new IntersectionObserver(([e]) => { if (!e.isIntersecting && !v.paused) v.pause(); }, { threshold: 0.1 }).observe(v);
    sync();
  }

  /* ---------- how it works: drag through a 24-part job ---------- */
  const sim = $('[data-sim]');
  if (sim) {
    const PARTS = 24, PACKED = 47.3, UNPACKED = 52.1, FREE = 12, FILES = 1204;
    const B1 = 0.43, B2 = 0.88;
    const strip = $('[data-parts]', sim);
    for (let i = 0; i < PARTS; i++) strip.appendChild(document.createElement('i'));
    const parts = $$('i', strip);
    const scrub = $('[data-scrub]', sim), play = $('[data-play]', sim), head = $('[data-playhead]', sim);
    const stages = { verify: $('.stage-verify', sim), extract: $('.stage-extract', sim), done: $('.stage-done', sim) };
    const el = (k) => $(`[data-${k}]`, sim);
    const live = $('[data-sim-live]', sim);
    let lastPhase = '';

    const render = () => {
      const v = scrub.value / 1000;
      let phase, f, e;
      if (v < B1) { phase = 'verify'; f = v / B1; e = 0; }
      else if (v < B2) { phase = 'extract'; f = (v - B1) / (B2 - B1); e = f; }
      else { phase = 'done'; f = (v - B2) / (1 - B2); e = 1; }

      const now = e >= 1 ? PARTS : Math.floor(e * PARTS);
      parts.forEach((p, i) => {
        p.classList.toggle('is-gone', i < now);
        p.classList.toggle('is-now', phase === 'extract' && i === now);
      });
      for (const k in stages) stages[k].classList.toggle('is-active', k === phase);

      const st = stages[phase];
      const x = st.offsetLeft + f * st.offsetWidth;
      head.style.transform = `translateX(${x}px)`;

      const written = UNPACKED * e;
      const ee = FREE - written + now * (PACKED / PARTS);
      const usual = FREE - written;
      const pct = phase === 'verify' ? Math.round(f * 100) : phase === 'extract' ? Math.round(e * 100) : 100;
      el('phase').textContent = phase === 'verify' ? 'Verifying' : phase === 'extract' ? 'Extracting' : 'Done';
      el('pct').textContent = pct;
      el('files').textContent = Math.round(FILES * e).toLocaleString('en-US');
      el('left').textContent = PARTS - now;
      el('ee').textContent = fmt(ee);
      const box = $('[data-usual-box]', sim);
      if (usual < 0) {
        el('usual').textContent = 'Disk full';
        el('usual-sub').textContent = `Ran out at ${Math.round((FREE / UNPACKED) * 100)}%. Every part stays until the end.`;
        box.classList.add('is-full');
      } else {
        el('usual').innerHTML = `<b>${fmt(usual)}</b> GB`;
        el('usual-sub').textContent = phase === 'verify' ? 'Same so far: nothing is written yet.' : 'Every part stays on disk until the end.';
        box.classList.remove('is-full');
      }
      const valuetext = `${el('phase').textContent} ${pct} percent. ${fmt(ee)} GB free with EnhancedExtract; ${usual < 0 ? 'disk full' : fmt(usual) + ' GB free'} the usual way.`;
      scrub.setAttribute('aria-valuetext', valuetext);
      if (phase !== lastPhase) { lastPhase = phase; if (live) live.textContent = valuetext; }
    };

    let raf = 0;
    const stop = () => { cancelAnimationFrame(raf); raf = 0; play.textContent = 'Play'; };
    play.addEventListener('click', () => {
      if (raf) return stop();
      if (reduce.matches) { scrub.value = scrub.value >= 1000 ? 0 : 1000; render(); return; }
      if (+scrub.value >= 1000) scrub.value = 0;
      const start = performance.now(), from = +scrub.value, dur = 9000 * (1 - from / 1000);
      play.textContent = 'Pause';
      const step = (t) => {
        const k = Math.min(1, (t - start) / dur);
        scrub.value = from + (1000 - from) * k;
        render();
        if (k < 1) raf = requestAnimationFrame(step); else stop();
      };
      raf = requestAnimationFrame(step);
    });
    scrub.addEventListener('input', () => { if (raf) stop(); render(); });
    // The scroll scene (motion.js) drives the same job while its stage is held.
    window.EESim = { set(v) { if (raf) stop(); scrub.value = v; render(); }, get playing() { return !!raf; } };
    addEventListener('resize', render);
    render();
  }

  /* ---------- explorer: the typed file name, answered the way the app would ---------- */
  const input = $('[data-partname]');
  if (input) {
    const rows = $('[data-answer]'), cmd = $('[data-cmd]'), cmdBox = cmd.parentElement;
    const DIR = 'D:\\Downloads';
    const OTHER = 'zip|zipx|7z|tar|gz|tgz|bz2|tbz|tbz2|xz|txz|zst|tzst|lzma|cab|wim';   // everything but RAR, through 7-Zip
    let answered = false, lastSig = '';
    const answer = (raw) => {
      const name = raw.trim().split(/[\\/]/).pop();
      let m, out;
      if ((m = name.match(/^(.+)\.part(\d+)\.rar$/i))) {
        const first = `${m[1]}.part${'1'.padStart(m[2].length, '0')}.rar`;
        out = { rows: [['Starts from', first], ['Extracts to', `${DIR}\\${m[1]}`], ['In the menu', 'Extract, Extract and free space, Open dashboard']],
          cmd: `python cli.py rar extract "${DIR}\\${first}" --delete --dry-run` };
      } else if ((m = name.match(/^(.+)\.(rar|r\d\d)$/i))) {
        const first = `${m[1]}.rar`;
        out = { rows: [['Starts from', first], ['Extracts to', `${DIR}\\${m[1]}`], ['In the menu', 'Extract, Extract and free space, Open dashboard']],
          cmd: `python cli.py rar extract "${DIR}\\${first}" --delete --dry-run` };
      } else if ((m = name.match(/^(.+)\.iso$/i))) {
        out = { rows: [['Opens', 'The ISO install screen'], ['Then', 'Mounts it as a drive, runs setup, frees the ISO behind it'], ['Needs', 'Administrator and WinFsp (bundled)']],
          cmd: `python cli.py iso install "${DIR}\\${name}" --install-dir "D:\\Games\\${m[1]}" --install-size-mb 52000 --silent --dry-run` };
      } else if ((m = name.match(new RegExp('^(.+?)\\.(' + OTHER + ')\\.(\\d{3,})$', 'i')))) {
        // a split set, Pack.7z.003: only the first piece opens
        const first = `${m[1]}.${m[2]}.${'1'.padStart(m[3].length, '0')}`;
        out = { rows: [['Starts from', first], ['Extracts to', `${DIR}\\${m[1]}`], ['In the menu', 'Extract, Extract and free space, Open dashboard']],
          cmd: `python cli.py archive extract "${DIR}\\${first}" --delete --dry-run` };
      } else if ((m = name.match(/^(.+)\.z\d{2,}$/i))) {
        const first = `${m[1]}.zip`;
        out = { rows: [['Starts from', first], ['Extracts to', `${DIR}\\${m[1]}`], ['In the menu', 'Extract, Extract and free space, Open dashboard']],
          cmd: `python cli.py archive extract "${DIR}\\${first}" --delete --dry-run` };
      } else if ((m = name.match(/^(.+?)\.tar\.(gz|bz2|xz|zst|lzma|z)$/i)) || (m = name.match(new RegExp('^(.+)\\.(' + OTHER + ')$', 'i')))) {
        out = { rows: [['Opens', name], ['Extracts to', `${DIR}\\${m[1]}`], ['In the menu', 'Extract, Extract and free space, Open dashboard']],
          cmd: `python cli.py archive extract "${DIR}\\${name}" --delete --dry-run` };
      } else {
        out = { rows: [['Waiting for', 'A file name ending in .rar, .zip, .7z, .tar.gz or .iso']], cmd: '' };
      }
      if (new RegExp('\\.(' + OTHER + ')(\\.\\d{3,})?$|\\.z\\d{2,}$', 'i').test(name)) {
        out.rows.push(['Availability', 'Supported in 0.1.0 with bundled 7-Zip']);
      }
      const sig = out.rows.map((r) => r[0] + r[1]).join('|') + out.cmd;
      if (sig === lastSig) return;
      lastSig = sig;
      rows.replaceChildren(...out.rows.map(([k, v, bad], i) => {
        const d = document.createElement('div'), dt = document.createElement('dt'), dd = document.createElement('dd');
        dt.textContent = k; dd.textContent = v; if (bad) dd.className = 'is-bad';
        if (answered) { d.className = 'row-in'; d.style.setProperty('--i', i); }
        d.append(dt, dd); return d;
      }));
      cmd.textContent = out.cmd;
      cmdBox.hidden = !out.cmd;
      answered = true;
    };
    input.addEventListener('input', () => answer(input.value));
    $$('[data-example]').forEach((b) => b.addEventListener('click', () => { input.value = b.dataset.example; answer(input.value); input.focus(); }));
    answer(input.value);
  }

  /* ---------- copy the PowerShell command ---------- */
  $$('[data-copy]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const panel = btn.closest('.dl');
      const text = $('[data-ps]', panel).textContent.trim();
      const note = $('[data-copied]', panel);
      try {
        await navigator.clipboard.writeText(text);
        note.textContent = 'Copied. Paste it into PowerShell or a Run box.';
      } catch {
        const r = document.createRange(); r.selectNodeContents($('[data-ps]', panel));
        getSelection().removeAllRanges(); getSelection().addRange(r);
        note.textContent = 'Selected. Press Ctrl+C to copy.';
      }
      btn.classList.add('is-done');
      setTimeout(() => { btn.classList.remove('is-done'); note.textContent = ''; }, 2600);
    });
  });

  /* ---------- reveals: once, staggered inside each section ---------- */
  document.documentElement.classList.add('reveals-ready');
  const groups = new Map();
  $$('[data-reveal]').forEach((n) => {
    const s = n.closest('section') || document.body;
    const i = groups.get(s) || 0; groups.set(s, i + 1);
    n.style.setProperty('--d', Math.min(i, 4));
  });
  // A scroll check rather than an observer: a jump (anchor link, Page Down, a fast fling) can skip an
  // observer's threshold and leave content hidden. Anything at or above 92% of the screen is shown.
  let pending = $$('[data-reveal]');
  let ticking = false;
  const check = () => {
    ticking = false;
    const line = innerHeight * 0.92;
    pending = pending.filter((n) => {
      if (n.getBoundingClientRect().top < line) { n.classList.add('is-in'); return false; }
      return true;
    });
    if (!pending.length) { removeEventListener('scroll', onScroll); removeEventListener('resize', onScroll); }
  };
  const onScroll = () => check();
  addEventListener('scroll', onScroll, { passive: true });
  addEventListener('resize', onScroll);
  check();
  setTimeout(check, 400);
  const sw = $('.pw-switch');
  if (sw) new IntersectionObserver((es, o) => { if (es[0].isIntersecting) { sw.classList.add('is-on'); o.disconnect(); } }, { threshold: 1 }).observe(sw);
})();
