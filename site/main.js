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

  /* ---------- hero visual: the same job run both ways. The switch and the buttons share one state ---------- */
  const viz = $('[data-viz]');
  if (viz) {
    // An illustrative set: 24 parts, 47.30 GB in, 52.10 GB out, on a drive with 12.00 GB free.
    const SET = 47.3, GAME = 52.1, FREE = 12, POOL = SET + FREE, READ = 0.32, HOLD = 3.2;
    const cells = $$('[data-viz-parts] i', viz), N = cells.length, PART = SET / N;
    const stallAt = FREE / GAME * N; // keeping every part, D: is full here (23%)
    const el = (k) => $(`[data-viz-${k}]`, viz);
    const titleEl = el('title'), arcEl = el('arc'), outEl = el('out'), freeEl = el('free'), flagEl = el('flag');
    const filesEl = el('files'), leftEl = el('left'), leftBar = el('left-bar'), logEl = el('log');
    const modeBtns = $$('[data-viz-mode]', viz);
    // The drive meter: one tick per ~1 GB of the space the job can use (the parts plus what is free).
    const TICKS = 60;
    const ticks = Array.from({ length: TICKS }, () => el('meter').appendChild(document.createElement('span')));
    const pad = (n) => String(n).padStart(2, '0');
    const deleting = () => !toggle || toggle.checked;
    const set = (node, text) => { if (node.textContent !== text) node.textContent = text; };
    let p = 0, hold = 0, full = false, done = false, raf = 0, last = 0, onScreen = false;

    // The job log: the last three things the job did, written the way the CLI reports them.
    let lines = [], logged = 0, ended = false;
    const log = (tone, glyph, verb, text, num = '') => {
      lines = [...lines, { tone, glyph, verb, text, num }].slice(-3);
      logEl.replaceChildren(...lines.map((l) => {
        const li = document.createElement('li');
        if (l.tone) li.className = 'is-' + l.tone;
        [['g', l.glyph], ['v', l.verb], ['', l.text], ['n', l.num]].forEach(([c, t]) => {
          const s = document.createElement('span'); if (c) s.className = c; s.textContent = t; li.append(s);
        });
        return li;
      }));
    };
    const syncLog = (del, whole, free) => {
      for (; logged < whole; logged++) {
        if (del) log('', '›', `part ${pad(logged + 1)}`, 'extracted, flushed, deleted', `+${fmt(PART)} GB`);
        else log('', '›', `part ${pad(logged + 1)}`, 'extracted, kept on D:');
      }
      if (ended || !(full || done)) return;
      ended = true;
      if (full) log('bad', '×', 'stopped', `D: is full at ${Math.round(stallAt / N * 100)}%: needs ${fmt(GAME)} GB, has ${fmt(FREE)}`);
      else log('good', '✓', 'done', `${fmt(GAME)} GB written, 0 parts left`, `${fmt(free)} GB free`);
    };

    const draw = () => {
      const del = deleting(), whole = Math.min(Math.floor(p), N);
      const files = p / N * GAME;
      const left = del ? N - whole : N;
      const arc = left * PART;
      const free = Math.max(POOL - arc - files, 0);
      cells.forEach((c, i) => {
        const f = Math.min(Math.max(p - i, 0), 1);
        c.style.setProperty('--f', f);
        c.classList.toggle('is-read', f > 0 && f < 1);
        c.classList.toggle('is-gone', f >= 1 && del);
        c.classList.toggle('is-kept', f >= 1 && !del);
      });
      ticks.forEach((t, k) => {
        const at = (k + 0.5) / TICKS * POOL;
        const cls = at < arc ? 't-arc' : at < arc + files ? 't-game' : '';
        if (t.className !== cls) t.className = cls;
      });
      filesEl.style.width = (files / GAME * 100) + '%';
      leftBar.style.width = (left / N * 100) + '%';
      set(arcEl, `${fmt(arc)} GB`);
      set(outEl, `${fmt(files)} / ${fmt(GAME)} GB`);
      set(leftEl, `${left} / ${N}`);
      set(freeEl, fmt(free));
      set(flagEl, full ? 'Disk full' : done ? 'Done' : 'Fits');
      set(titleEl, del ? 'Each part goes the moment its files are on disk' : 'A usual extractor keeps every part until the end');
      viz.classList.toggle('is-keep', !del);
      viz.classList.toggle('is-full', full);
      viz.classList.toggle('is-done', done);
      modeBtns.forEach((b) => b.setAttribute('aria-pressed', String((b.dataset.vizMode === 'ee') === del)));
      syncLog(del, whole, free);
    };
    const begin = () => {
      lines = []; logged = 0; ended = false;
      log('now', '›', 'verify', `${N} of ${N} parts OK, ${fmt(SET)} GB`);
    };
    const tick = (dt) => {
      if (hold > 0) { hold -= dt; if (hold <= 0) { p = 0; full = done = false; begin(); } return; }
      p += dt / READ;
      if (!deleting() && p >= stallAt) { p = stallAt; full = true; hold = HOLD; }
      else if (p >= N) { p = N; done = true; hold = HOLD; }
    };
    const frame = (t) => {
      // Real elapsed time, so a throttled tab (an embedded preview, a background window) jumps ahead
      // instead of crawling. The cap only stops a long-hidden tab from skipping the whole run.
      tick(last ? Math.min((t - last) / 1000, 1) : 0);
      last = t; draw();
      raf = requestAnimationFrame(frame);
    };
    const stop = () => { cancelAnimationFrame(raf); raf = 0; };
    const start = () => { if (raf || !onScreen || reduce.matches) return; last = 0; raf = requestAnimationFrame(frame); };
    const restart = () => {
      hold = 0; full = done = false; p = 0;
      begin();
      // Reduced motion: show where each way ends up instead of running it.
      if (reduce.matches) { if (deleting()) { p = N; done = true; } else { p = stallAt; full = true; } }
      draw();
    };
    modeBtns.forEach((b) => b.addEventListener('click', () => {
      const ee = b.dataset.vizMode === 'ee';
      if (!toggle) return;
      if (toggle.checked !== ee) { toggle.checked = ee; toggle.dispatchEvent(new Event('change', { bubbles: true })); } else restart();
    }));
    el('replay').addEventListener('click', restart);
    toggle?.addEventListener('change', restart);
    new IntersectionObserver(([e]) => { onScreen = e.isIntersecting; onScreen ? start() : stop(); }).observe(viz);
    reduce.addEventListener('change', () => { stop(); restart(); start(); });
    restart();
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
