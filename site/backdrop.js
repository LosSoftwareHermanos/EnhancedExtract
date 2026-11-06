// ASCII fluid shader adapted from the user-supplied component.
import { createAsciiFluid } from './ascii-fluid.js';

const canvas = document.querySelector('[data-backdrop]');
if (canvas) {
  const effect = createAsciiFluid(canvas, {
    theme: 'dark', color: '#fcee0a', backgroundColor: '#0b0c12',
    charset: ' .:-=+01/<>[]{}#@', cellSize: 13,
    force: 1.25, dissipation: 0.03, brush: 0.75,
    animate: true, interactive: true,
  });
  if (!effect) canvas.remove();
  else {
    canvas.classList.add('is-on');
    canvas.addEventListener('webglcontextlost', () => {
      effect.destroy();
      canvas.remove();
    }, { once: true });
    const dim = () => { canvas.style.opacity = String(1 - Math.min(1, scrollY / innerHeight) * 0.55); };
    addEventListener('scroll', dim, { passive: true });
    dim();
    addEventListener('pagehide', e => { if (!e.persisted) effect.destroy(); });
  }
}
