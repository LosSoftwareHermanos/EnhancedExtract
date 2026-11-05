import { useEffect, useRef } from "react";

/**
 * The app's backdrop: one WebGL2 fragment shader drawing a faint cyberpunk floor grid that runs toward
 * a horizon, with scanlines, film grain and a vignette, in the brand's yellow and cyan.
 *
 * Kept cheap on purpose:
 * - rendered at half the window's resolution and scaled up by CSS (a quarter of the pixels);
 * - capped at 30 fps, and stopped completely while the window is hidden or minimised;
 * - one full-screen triangle, no textures, no extra passes;
 * - with reduced motion or effects off it draws one still frame and stops.
 * `energy` (0..1) speeds the grid up while jobs run, so the app looks alive only when it is working.
 */
const VERT = `#version 300 es
in vec2 p; void main() { gl_Position = vec4(p, 0.0, 1.0); }`;

const FRAG = `#version 300 es
precision mediump float;
uniform vec2 r; uniform float t; uniform float e;
out vec4 o;
float hash(vec2 p) { return fract(sin(dot(p, vec2(41.3, 289.1))) * 43758.5453); }
void main() {
  vec2 uv = gl_FragCoord.xy / r;
  vec3 col = vec3(0.043, 0.047, 0.071);                 // ground #0b0c12
  float horizon = 0.46;
  if (uv.y < horizon) {
    float d = horizon - uv.y;                           // distance below the horizon
    float z = 0.35 / (d + 0.012);                       // depth
    vec2 g = vec2((uv.x - 0.5) * z * 2.4, z + t * (0.18 + 0.9 * e));
    vec2 f = abs(fract(g) - 0.5);
    vec2 w = fwidth(g) * 1.2;
    float line = max(1.0 - smoothstep(0.0, w.x, f.x), 1.0 - smoothstep(0.0, w.y, f.y));
    float fade = smoothstep(0.0, 0.32, d) * (1.0 - smoothstep(0.30, 0.46, d) * 0.5);
    vec3 yellow = vec3(0.988, 0.933, 0.039);
    col += yellow * line * fade * (0.055 + 0.07 * e);
  }
  // horizon haze: a thin cyan band, brighter while working
  float haze = exp(-pow((uv.y - horizon) * 22.0, 2.0));
  col += vec3(0.0, 0.9, 0.94) * haze * (0.035 + 0.05 * e);
  // scanlines, grain, vignette
  col *= 0.975 + 0.025 * step(1.0, mod(gl_FragCoord.y, 3.0));
  col += (hash(gl_FragCoord.xy + fract(t) * 91.7) - 0.5) * 0.018;
  vec2 v = uv - 0.5;
  col *= 1.0 - dot(v, v) * 0.55;
  o = vec4(col, 1.0);
}`;

export function Backdrop({ energy, enabled }: { energy: number; enabled: boolean }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const energyRef = useRef(energy);
  energyRef.current = energy;

  useEffect(() => {
    const cv = canvas.current!;
    cv.style.display = "";
    // The same canvas always hands back the same context, so effects re-running (toggle, dev
    // StrictMode) must not destroy it; cleanup frees the program and buffer instead.
    const gl = cv.getContext("webgl2", { antialias: false, alpha: false, powerPreference: "low-power", preserveDrawingBuffer: false });
    if (!gl || gl.isContextLost()) { cv.style.display = "none"; return; }   // no WebGL2: the CSS ground shows instead

    const shader = (type: number, src: string) => { const s = gl.createShader(type)!; gl.shaderSource(s, src); gl.compileShader(s); return s; };
    const prog = gl.createProgram()!;
    gl.attachShader(prog, shader(gl.VERTEX_SHADER, VERT));
    gl.attachShader(prog, shader(gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) { cv.style.display = "none"; return; }
    gl.useProgram(prog);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, "p");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    const uR = gl.getUniformLocation(prog, "r"), uT = gl.getUniformLocation(prog, "t"), uE = gl.getUniformLocation(prog, "e");

    const SCALE = 0.5;
    const resize = () => {
      const w = Math.max(1, Math.round(innerWidth * SCALE)), h = Math.max(1, Math.round(innerHeight * SCALE));
      if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; gl.viewport(0, 0, w, h); }
      gl.uniform2f(uR, w, h);
    };
    resize();

    let e = energyRef.current, raf = 0, last = 0, t = 0;
    const draw = (dt: number) => {
      e += (energyRef.current - e) * Math.min(1, dt * 1.5);   // ease the grid speed in and out
      t += dt;
      gl.uniform1f(uT, t);
      gl.uniform1f(uE, e);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };
    const still = !enabled || matchMedia("(prefers-reduced-motion: reduce)").matches;
    const loop = (now: number) => {
      raf = requestAnimationFrame(loop);
      if (now - last < 1000 / 30) return;                     // 30 fps is plenty for a slow backdrop
      const dt = last ? Math.min(0.1, (now - last) / 1000) : 0;
      last = now;
      draw(dt);
    };
    const start = () => { if (!raf && !still && document.visibilityState === "visible") { last = 0; raf = requestAnimationFrame(loop); } };
    const stop = () => { cancelAnimationFrame(raf); raf = 0; };
    const onVis = () => (document.visibilityState === "visible" ? start() : stop());
    const onResize = () => { resize(); if (still) draw(0); };

    draw(0);
    start();
    document.addEventListener("visibilitychange", onVis);
    addEventListener("resize", onResize);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVis);
      removeEventListener("resize", onResize);
      gl.deleteBuffer(buf);
      gl.deleteProgram(prog);
    };
  }, [enabled]);

  return <canvas ref={canvas} className="backdrop" aria-hidden="true" />;
}
