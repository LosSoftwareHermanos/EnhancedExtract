/* UI sounds: the same files and the same mapping as the first (Tkinter) version, in sounds.py.
   Played through Web Audio so a click sounds at once and fast typing can overlap. Sound is an
   extra: if audio fails, every call here quietly does nothing. The mute switch is remembered. */
import { useEffect, useSyncExternalStore } from "react";
import button from "./assets/sounds/glass_001.ogg";
import minimize from "./assets/sounds/toggle_001.ogg";
import exit from "./assets/sounds/back_001.ogg";
import key from "./assets/sounds/click_003.ogg";
import checkOn from "./assets/sounds/select_007.ogg";
import checkOff from "./assets/sounds/select_008.ogg";
import progress from "./assets/sounds/kuzu420-sci-fi-radar-beeping-571479.mp3";
import tab from "./assets/sounds/forceField_001.ogg";
import zap from "./assets/sounds/forceField_000.ogg";
import popup from "./assets/sounds/soundshelfstudio-cyber-ui-click-527091.mp3";
import soundOn from "./assets/sounds/glass_005.ogg";
import soundOff from "./assets/sounds/glass_006.ogg";

const FILES = {
  button, minimize, exit, key, check_on: checkOn, check_off: checkOff, progress,
  buffer_up: checkOn, buffer_down: checkOff, tab, popup,
  sound_on: soundOn, sound_off: soundOff,
  // Job screens: a part verified / deleted, and the job finishing well or not.
  part_verified: checkOn, part_deleted: zap, job_ok: soundOn, job_failed: checkOff,
  boot: zap,                      // the start-up splash
  access_granted: soundOn,        // a password was accepted
};
export type Sound = keyof typeof FILES;
const VOLUME = 0.6;
const PROGRESS_VOLUME = 0.3;    // it loops for the whole job, so it sits under the other sounds
const MUTE_KEY = "ee.muted";

let ctx: AudioContext | null = null;
const buffers = new Map<Sound, AudioBuffer>();
let loading: Promise<void> | null = null;
let loop: AudioBufferSourceNode | null = null;
let progressWanted = 0;         // running-job screens that want the loop
let muted = (() => { try { return localStorage.getItem(MUTE_KEY) === "1"; } catch { return false; } })();
const listeners = new Set<() => void>();

/** Decode every sound in the background, so the first click isn't silent. */
export function preload() {
  if (loading) return loading;
  try { ctx = new AudioContext(); } catch { return (loading = Promise.resolve()); }
  loading = Promise.all(Object.entries(FILES).map(async ([name, url]) => {
    try { buffers.set(name as Sound, await ctx!.decodeAudioData(await (await fetch(url)).arrayBuffer())); } catch { /* that one stays silent */ }
  })).then(() => syncLoop());
  return loading;
}

function start(name: Sound, volume: number, looping = false) {
  const buf = buffers.get(name);
  if (!ctx || !buf) return null;
  if (ctx.state === "suspended") void ctx.resume();     // audio starts on the first click
  const src = ctx.createBufferSource();
  const gain = ctx.createGain();
  src.buffer = buf; src.loop = looping; gain.gain.value = volume;
  src.connect(gain).connect(ctx.destination);
  src.start();
  return src;
}

const lastPlayed = new Map<Sound, number>();

export function play(name: Sound) {
  if (muted) return;
  // The same sound twice within 40 ms is one event seen twice (React runs effects twice in
  // development), not two clicks.
  const now = performance.now();
  if (now - (lastPlayed.get(name) ?? -1e9) < 40) return;
  lastPlayed.set(name, now);
  start(name, VOLUME);
}

/** Length of a sound in ms (0 if it isn't loaded), to let the exit sound finish before closing. */
export const lengthMs = (name: Sound) => Math.round((buffers.get(name)?.duration ?? 0) * 1000);

function syncLoop() {
  const want = progressWanted > 0 && !muted;
  if (want && !loop) loop = start("progress", PROGRESS_VOLUME, true);
  if (!want && loop) { loop.stop(); loop = null; }
}

/** Loop the progress sound while `active` (a job running on screen), like the first version. */
export function useProgressSound(active: boolean) {
  useEffect(() => {
    if (!active) return;
    progressWanted++; syncLoop();
    return () => { progressWanted--; syncLoop(); };
  }, [active]);
}

export const isMuted = () => muted;

export function setMuted(m: boolean) {
  muted = m;
  try { localStorage.setItem(MUTE_KEY, m ? "1" : "0"); } catch { /* private mode: holds for this run */ }
  syncLoop();
  listeners.forEach((l) => l());
}

/** The mute switch: turning sound on plays glass_005 after, turning it off plays glass_006 before. */
export function toggleMuted() {
  if (muted) { setMuted(false); play("sound_on"); }
  else { play("sound_off"); setMuted(true); }
}

export function useMuted() {
  return useSyncExternalStore((l) => { listeners.add(l); return () => listeners.delete(l); }, isMuted);
}

/** One set of listeners for the whole page, instead of a sound prop on every control:
 *  buttons click (or play their data-sound, "none" for silence), switches and checkboxes tick
 *  on/off, the slider ticks up/down, and typing into a text box clicks per key. */
export function installSounds() {
  const lastRange = new WeakMap<HTMLInputElement, number>();
  const onClick = (e: MouseEvent) => {
    const target = e.target as Element | null;
    const b = target?.closest?.("button");
    if (!b) {   // a switch row's text toggles its switch too
      const tog = target?.closest?.(".sw")?.querySelector<HTMLButtonElement>(".tog");
      if (tog && !tog.disabled) play(tog.getAttribute("aria-checked") === "true" ? "check_off" : "check_on");
      return;
    }
    if (b.disabled) return;
    const own = b.dataset.sound;
    if (own) { if (own !== "none") play(own as Sound); return; }
    if (b.classList.contains("tog") || b.getAttribute("role") === "checkbox") play(b.getAttribute("aria-checked") === "true" ? "check_off" : "check_on");
    else if (b.classList.contains("choice")) play("check_on");
    else if (b.matches(".btn, .ri")) play("button");
  };
  const onChange = (e: Event) => {
    const t = e.target as HTMLInputElement;
    if (t.type === "checkbox") play(t.checked ? "check_on" : "check_off");
  };
  const onInput = (e: Event) => {
    const t = e.target as HTMLInputElement;
    if (t.type !== "range") return;
    const v = Number(t.value), before = lastRange.get(t) ?? Number(t.defaultValue);
    if (v !== before) play(v > before ? "buffer_up" : "buffer_down");
    lastRange.set(t, v);
  };
  const onKey = (e: KeyboardEvent) => {
    const t = e.target as EventTarget | null;
    if (!(t instanceof HTMLInputElement || t instanceof HTMLTextAreaElement) || t.readOnly || t.disabled) return;
    if (t instanceof HTMLInputElement && !["text", "password", "search", ""].includes(t.type)) return;
    if ((e.key.length === 1 && !e.ctrlKey && !e.altKey) || e.key === "Backspace" || e.key === "Delete") play("key");
  };
  // Capture phase: read the control before React handles the event. React re-renders between
  // listeners on a real click, after which the button may already be disabled (Rescan) or
  // marked as the current page (the rail), and would stay silent.
  document.addEventListener("click", onClick, true);
  document.addEventListener("change", onChange, true);
  document.addEventListener("input", onInput, true);
  document.addEventListener("keydown", onKey, true);
  return () => {
    document.removeEventListener("click", onClick, true);
    document.removeEventListener("change", onChange, true);
    document.removeEventListener("input", onInput, true);
    document.removeEventListener("keydown", onKey, true);
  };
}
