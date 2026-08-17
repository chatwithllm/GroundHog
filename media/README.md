# Pool-Robo RTK — media

Diagrams, animations, videos, and board-probing photos for the RTK rover project.

## diagrams/
- ⚠️ `architecture.png`, `complete_flow.png`, `arch_handdrawn.png` — **STALE**: depict the superseded MDDS30/brushed + external-encoder design. Motors are actually **BLDC5520 with integrated drivers** (24V+GND+PWM+DIR+FG, no MDDS30). Regenerate before reuse. Current truth = the HTML diagrams + videos below.
- `whiteboard.html` — self-drawing animated SVG, BLDC direct-drive (open in a browser; Replay button).
- `flowchart.html`, `wiring.html`, `wiring_planner.html`, `infographic.html` — updated to BLDC direct-drive (F405 brushed-with-relay: PWM speed + DIR + FG feedback).

## videos/
- `explainer.mp4` — hand-drawn explainer, strokes reveal per stage with narration captions (~56s).
- `explainer_pen.mp4` — same, with a visible marker drawing each stroke (~56s).
- `doodle.mp4` — doodle-style explainer: cartoon icons (rover cart, satellites, cloud, chips, battery) sketched in (~52s).

## probe/
Multimeter probe-point references for the SP5 board bring-up:
- `probe_final.png` — full board with GND / rail-cap / battery-connector markers.
- `vf_gnd.png`, `vf_cap2.png`, `vf_batt2.png` — verified close-ups (GND pad, 25V330 motor-rail cap, battery VDD/PWR pins).
- `rail_cap_zoom2.png`, `probe_points.svg` — earlier probe annotations.

## src/
- `mkvideo.py` — generator for the hand-drawn explainer videos (edit + rerun to regenerate).
- `mkdoodle.py` — generator for the doodle video.
Regenerate: `python3 mkvideo.py` (writes PNG frames) then `ffmpeg -framerate 20 -i frames/f%04d.png -vf "scale=1280:720,format=yuv420p" -c:v libx264 -crf 20 out.mp4`.
