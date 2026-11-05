import { createContext, useContext, useEffect, useRef } from "react";
import logo from "../assets/logo.png";
import wordmark from "../assets/wordmark.png";

/** Effects on/off (the rail's switch) and reduced motion, in one place. */
export const FxContext = createContext(true);
const reduced = () => typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
export const useFx = () => useContext(FxContext) && !reduced();

const GLYPHS = "ΣΞ#%&/\\<>=+*01ABCDEFXZ";

/**
 * Text that "decodes" in once: random glyphs settle left to right into the real text (about 380 ms).
 * Used on screen titles, which change only when you change screens. Screen readers get the text at once.
 */
export function Decode({ text, className }: { text: string; className?: string }) {
  const fx = useFx();
  const el = useRef<HTMLSpanElement>(null);
  // Frames write the text node directly: no React render per frame.
  useEffect(() => {
    const node = el.current;
    if (!node) return;
    if (!fx) { node.textContent = text; return; }
    let raf = 0;
    const start = performance.now(), dur = 380;
    const tick = (now: number) => {
      const k = Math.min(1, (now - start) / dur);
      node.textContent = scramble(text, k);
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(raf); node.textContent = text; };
  }, [text, fx]);
  return <span className={className} aria-label={text}><span aria-hidden="true" ref={el}>{text}</span></span>;
}
function scramble(text: string, k: number) {
  const fixed = Math.floor(text.length * k);
  let out = text.slice(0, fixed);
  for (let i = fixed; i < text.length; i++) out += text[i] === " " ? " " : GLYPHS[(Math.random() * GLYPHS.length) | 0];
  return out;
}

/** A number that moves to its new value instead of jumping (420 ms, ease-out). */
export function Num({ value, format }: { value: number; format: (n: number) => string }) {
  const fx = useFx();
  const el = useRef<HTMLSpanElement>(null);
  const from = useRef(value);
  const fmt = useRef(format);
  fmt.current = format;
  // Frames write the text node directly (no React render per frame), and a frame is only
  // written when the formatted text actually changes.
  useEffect(() => {
    const node = el.current;
    if (!node) return;
    if (!fx || from.current === value) { from.current = value; node.textContent = fmt.current(value); return; }
    let raf = 0, last = "";
    const a = from.current, start = performance.now(), dur = 420;
    const tick = (now: number) => {
      const k = Math.min(1, (now - start) / dur), eased = 1 - Math.pow(1 - k, 3);
      const cur = a + (value - a) * eased;
      from.current = cur;
      const s = fmt.current(cur);
      if (s !== last) { node.textContent = s; last = s; }
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, fx]);
  return <span ref={el}>{format(from.current)}</span>;
}

/** Start-up: the Σ logo glitches in, the wordmark wipes across, then the app shows (about 1 s, once per launch). */
export function Boot({ onDone }: { onDone: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDone, 1150);
    return () => clearTimeout(t);
  }, [onDone]);
  return (
    <div className="boot" aria-hidden="true" onClick={onDone}>
      <img className="boot-logo" src={logo} alt="" />
      <img className="boot-word" src={wordmark} alt="" />
      <span className="boot-bar"><i /></span>
    </div>
  );
}
