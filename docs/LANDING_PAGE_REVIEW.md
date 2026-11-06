# Landing page completion review

> Historical work record before the 0.1.0 release. See [RELEASE_NOTES.md](RELEASE_NOTES.md) for the current distributed version.

Reviewed 6 November 2026. Work remains uncommitted on `main`; nothing was pushed.

## Recovered session

Claude chat: **Cyberpunk Team landing page**.
Session ID: `01e1f6d3-62fd-43d2-8466-df79bf03d8ab`.

The session built `site/`, then added scroll motion and a WebGL backdrop. It stopped at the usage limit during final inspection. Its last two checklist items were:

- [x] Inspect, film scroll, fix: reran the browser inspector, recorded the scroll, reviewed every final screenshot and scene sheet, and checked interactive controls.
- [x] Report: this document records the results and remaining release limits.

The earlier checklist items already had implementations: app styling research, motion planning, locally bundled GSAP/ScrollTrigger/SplitText/Lenis, the background shader, and section/scene animation. Those implementations were retained and checked here.

## Changes in this continuation

- Prevented the hero number animation from overwriting a visitor's deletion-toggle choice.
- Made reveal hiding depend on successful interaction-script initialization, so blocked external scripts leave the page's content readable.
- Shortened the phone's displayed PowerShell command. The full command expands on keyboard focus and remains available through Copy.
- Aligned the private-beta notice with the hero composition.
- Corrected ZIP/7z/TAR availability throughout the page and interactive archive examples. This working source contains that development work; the linked beta 1 release does not.
- Identified the recording as the real app UI running its demo engine with sample data. The space comparison is an illustrative simulation, not an extraction benchmark.
- Added `-ErrorAction Stop` to the displayed PowerShell download command so download failure stops before launching an installer.

Only landing-page files and review artifacts were changed in this continuation. Existing engine, UI, packaging, and documentation changes from other sessions were preserved.

## Verification

| Check | Result |
| --- | --- |
| `python -m unittest discover -s tests` | 39 passed |
| `cargo test --manifest-path ui/src-tauri/Cargo.toml --lib` | 8 passed |
| `npm run build` from `ui/` | TypeScript and Vite build passed |
| `node --check` on main, motion, and backdrop scripts | Passed |
| taste-skill lint on production page HTML/CSS/JS | 0 failures, 0 warnings |
| taste-skill inspector with `--film` | 0 failures at 1440, 768, and 390 px; 2 style warnings |
| taste-skill scene inspection | Desktop scene ran; phone and reduced-motion layouts readable |
| Overflow at 320, 390, 768, and 1440 px | None |
| Referenced local assets | All returned HTTP 200 |
| Full desktop scroll | No broken images or unrevealed content |
| Browser console | No errors or warnings during the interactive review |
| Recorded demo | Paused initially; Play, Pause, and resume controls worked |
| Simulation | Slider endpoints and Play/Pause worked; final state has 0 archive parts left and 7.20 GB free |
| Archive examples | Padded RAR parts, old RAR volumes, split 7z/ZIP, compressed TAR, unsupported names, and text escaping checked |
| Clipboard | Copy success and denied-permission text-selection fallback passed |
| Reduced-motion phone | Videos paused, no smooth scrolling, no hidden sections; Play advances the simulation without travel |
| Blocked external scripts | Content remains visible and internal anchors resolve |
| `git diff --check` | Passed |

The two inspector warnings are retained deliberately: monospace is confined to command text, and extra measured sizes include the product interface fragments and responsive headings. Production-page lint excludes the earlier `wireframe.html`, which remains a design draft and has its own older styling.

Evidence: `.taste-skill/inspect/report.json`, `.taste-skill/inspect/*.jpg`, `.taste-skill/scenes/*.jpg`, `.taste-skill/functional-checks.json`, and `.taste-skill/landing-scroll.mp4`. The final film contact sheets reflect the final page; the MP4 records the desktop inspection before the last notice-alignment adjustment.

## Visual critique

ROUND 2

Seen in one second: large game-extraction headline, yellow download action, and disk-space controls.

Idea (one sentence): EnhancedExtract's archive parts become the moving insert in the headline and the material of the scroll-driven space comparison.

Live thing: the deletion switch changes the required space; the visitor can scrub the illustrated job and enter multipart archive names.

Layout words by section: hero=poster / demonstration=film / process=held scene / safety=statement with evidence / library=mosaic / Explorer=input and answer / CLI=command and capture / requirements=table / FAQ=accordion / download=platform panel / footer=contact statement.

Scores: design 8 · usability 7 · creativity 7 · content 8 → overall 7.5.

Caps applied: creativity is limited to 7 because space-recovery storytelling also fits competing extraction tools. This is a self-review, not an independent jury result.

Top three problems (most visible first), each with the screenshot it shows in and the fix:

1. The phone PowerShell row overwhelmed the first screen (`mobile-fold.jpg`, first round). Fixed with a one-line preview, full command on focus, and Copy.
2. The private-beta note sat at the far left below a centered desktop hero (`desktop-fold.jpg`, first round). Fixed with centered desktop alignment and left alignment on phones.
3. The app footage could be read as a real archive benchmark (`desktop-page-01.jpg`). Fixed with a visible demo-engine/sample-data caption and an illustrative-simulation description.

Direction retained: **The sentence is the layout**, seed `514656895`; no redraws. The app's existing yellow/black palette and Oxanium/Bai Jamjuree type remain. Media comes from this project's app captures and existing demonstration assets; no newly sourced stock photos or clips were added. The app screenshots contain sample data. The backdrop and interactive space diagram are drawn in code. Existing font/component credits remain in the footer.

## Release limits

The GitHub repository was verified as private with `gh repo view`. The release assets and page checksums match the authenticated `gh release view v0.1.0-beta.1` metadata. Anonymous visitors cannot use those private download links; the plain PowerShell download command also needs publicly accessible assets and does not inherit a browser's GitHub login. The page discloses the private-beta status. Repository visibility and releases were not changed.

ZIP/7z/TAR support needs a new tested release before the page can advertise it as downloadable. These source tests do not constitute a fresh installed-binary or Explorer integration test. ISO space freeing remains experimental.

For local preview: `python -m http.server 8765 --bind 127.0.0.1 --directory site`, then open `http://127.0.0.1:8765/`.

## ASCII shader and ZIP wording revision

The user subsequently supplied an ASCII-fluid React component and requested its shader in place of the grid backdrop. The underlying WebGL engine is now adapted in `site/ascii-fluid.js`; `site/backdrop.js` initializes it as an ES module. React, shadcn and Tailwind were not added to the static landing page.

The adaptation retains the fluid solver, glyph atlas and pointer trails. The palette uses `#fcee0a` ink on `#0b0c12`, with subdued glyph brightness and a quieter central reading area. A slow ambient ribbon field keeps the background visible without pointer input. Glyph cells are 13 CSS pixels; rendering is capped at 30 frames per second, with a smaller simulation on coarse-pointer devices and a capped pixel ratio. Touch scrolling does not inject pointer forces. The drawing buffer follows the canvas viewport, rather than the full document height.

ZIP, 7z and TAR are now described as supported in the current build in the hero, requirements, FAQ and interactive examples. The older beta 1 download's different capabilities are explained in the download section. This supersedes the earlier development-only wording in this review. Existing release assets were not replaced.

Browser checks in `.taste-skill/ascii-checks.json` passed: live shader initialization, viewport-sized buffer, rendering paused under reduced motion and document hiding, rendering resumed after preference/visibility changes, phone overflow, current ZIP example text, and fallback after WebGL context loss. No JavaScript exceptions occurred during those checks. Syntax checks and production-page lint passed. Final inspection again reported 0 failures at desktop, tablet and phone widths, with the same two documented typography warnings; all scene checks passed. Every final render and scene sheet was opened for visual review.

Visual follow-up: composition and the previous 7.5 self-review score remain unchanged. The ASCII field replaces the grid without covering controls or obscuring headings in the reviewed frames. No new photographs, footage, or other media were sourced. The earlier MP4 is historical; the latest inspector film contact sheets show the ASCII background. This revision remains uncommitted.
