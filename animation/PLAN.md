# Animated explainers for the Stock Learn Easy reel slot

## What happened

v1 (`bull-vs-bear.html`, 1.10.2026) put two cartoon animals on a flat navy
field with Hebrew copy. Ofir's verdict: not good enough, wrong language, and
it does not go in the slot. Three specific notes:

1. **It has no world.** The characters float on a background colour. It should
   feel like they live somewhere — a village.
2. **English only.** The Instagram account is English end to end; a Hebrew
   reel cannot ship to it. v1 was Hebrew because the brief arrived in Hebrew.
3. **Plan it.** Stop improvising a scene and design the thing first.

v1 stays in the folder as the reference for what the pipeline can do, not as
something to publish.

## What v2 has to be

A short film, not a motion-graphics card. The test is whether a frame pulled
at random looks like a place rather than a slide.

### The world

A village at the edge of a field, held in the brand's navy twilight so the
reel still reads as Stock Learn Easy and not as generic stock footage.

| Layer | Contents | Parallax |
|---|---|---|
| sky | gradient + stars, mood-driven | 0.02 |
| weather | drifting clouds, sun/moon | 0.06 |
| hills far | two rounded ridges | 0.14 |
| hills near | darker ridge, treeline | 0.30 |
| village | barn, cottages with lit windows, windmill, trees | 0.50 |
| sign | the market notice board the price line lives on | 0.62 |
| road | dirt band the characters walk on | 0.85 |
| characters | bull, bear | 1.00 |
| foreground | grass tufts, fence rail | 1.45 |

Depth comes from the parallax spread, not from drawing more detail. The
windmill turns and the clouds drift the whole way through, so no frame is
ever fully still.

### Mood as the explanation

The lighting carries the lesson, so the words do not have to:

- **scene 1** — calm blue twilight, stars out, windows lit
- **scene 2 (bull)** — the sky lifts and warms, a green glow rises, stars fade
- **scene 3 (bear)** — it cools and darkens, a red glow, cloud cover thickens
- **scene 4** — back to calm, both animals either side of the board

### Motion

- real four-legged walk cycles, two segments per leg with a knee bend, near
  and far pairs in opposite phase
- body bob and a slight pitch at twice the stride frequency
- head nod and tail swing off the same phase, so the whole animal reads as
  one rhythm
- deterministic blinks, dust puffs under the hooves, a slow camera drift and
  push-in per scene

### Copy (English)

| Scene | On screen | Narration |
|---|---|---|
| 1 | Two animals run the market | "Every market has two animals living in it." |
| 2 | BULL MARKET / Horns toss up. Prices climb. | "When the bull runs through town, it throws its horns up. Prices climb. That's a bull market." |
| 3 | BEAR MARKET / Paw swipes down. Prices fall. | "When the bear comes down the hill, it swipes its paw down. Prices fall. That's a bear market." |
| 4 | Horns up. Paws down. | "Horns up. Paws down. That's the whole difference." |

20.5 seconds. v1 crammed four lines into 15s and the synthesiser had to read
at 226 wpm to fit; the budget here is set so every line lands under 165 wpm.

Type is DM Serif Display over DM Sans, the same pairing `design.py` uses for
the carousels, so the reel and the cards are visibly the same brand.

## Built, 1.10.2026

`village.html` is v2 as specified above, and `render.py --scene village` is the
build. Everything in the table and the copy list made it in. Five things were
decided at the easel rather than on paper, and they are the reason the frames
read as a place:

- **Rotation pivots on the hind hooves** (`PIVOT = -62` art units behind the
  character origin), not on the body centre. A rear-up that pivots in the
  middle looks like the animal is being lifted by a crane; pivoting at the back
  feet lifts the front end and leaves the hind legs planted, so the horn throw
  and the paw swipe cost almost no vertical offset.
- **Stride phase comes from distance travelled**, `p = x / 170`, never from
  `t`. The feet therefore cannot slide along the road no matter how the easing
  on `x` is changed later.
- **The swipe arm replaces the near fore leg** instead of being added to it,
  otherwise the bear grows a third front limb for a second and a half.
- **The slam ends down and forward** (`-58 * rear + 12 * slam`). An earlier
  version ended at +58 and the paw disappeared under the belly, which read as
  the bear bowing.
- **The board is never empty.** Outside the two market scenes it carries a flat
  grey drift, so scene 1 is a notice board rather than a blank rectangle.

## How it is built

Unchanged from v1, because this part worked: every visual property is a pure
function of `?t=`, frames are grabbed by a pool of headless Chrome processes,
`say` provides the voiceover, ffmpeg assembles. See `render.py`.

    ./render.py --scene village --still 7.2    # look at one frame
    ./render.py --scene village --fps 10       # rough cut
    ./render.py --scene village                # the real thing

Two traps already paid for:

- passing `--user-data-dir` makes this Chrome build hang forever instead of
  screenshotting; `--virtual-time-budget` is what makes it exit
- an absolutely positioned element with no `left` falls back to its static
  position, which flips with the document direction

## The voice, 1.10.2026

Ofir watched v2 and said the visuals were a large step up but the narration
was not good enough and had to improve significantly. He was right, and the
plan had already called it: macOS `say` was the weakest thing in the film.
Only the compact voices are installed on this machine, no Premium or Enhanced
ones, and compact Samantha is audibly synthetic.

The fix is `~/.local/bin/say-neural.py`, a local neural voice (Kokoro, 82M
params, ONNX on the CPU). It is the mirror image of the `transcribe-voice.sh`
/ whisper.cpp setup already running for his voice notes: a model on disk in
`~/.local/share/kokoro-models`, no account, no API key, nothing leaving the
machine. `render.py` picks the engine per scene — `engine: "neural"` for the
English film, `engine: "say"` for the Hebrew v1, since Kokoro has no Hebrew.

`--voice-only` was added at the same time and matters more than it looks:
auditioning a voice used to mean re-rendering 512 frames for seven minutes to
change an audio track that no frame depends on. It now copies the video track
and re-dubs in about twelve seconds.

## v3, 1.10.2026: built for the feed instead of for a screening

Ofir watched v2 and asked for research before any more work. What came back
(written up in `REELS-PLAN.md`) said the film was well made and badly shaped
for the surface it ships to. Phase 1 of that plan is now in:

- **Cold open.** The film starts on the answer frame, both animals already in
  their poses with both price lines crossing on the board, and the question
  over it. The title is at full opacity on frame 0, because a hook that fades
  in is not a hook. The old opening spent 2.6 seconds on a title card and a
  walk-on, and the first real event landed at second 7.75.
- **It loops.** `POSE` defines the answer frame once and both ends read it, the
  camera returns to `CAM0`, and the closing title clears before the last frame
  so the seam is a clean match. The closing line, "The bull, and the bear",
  calls back to the opening question. Clouds and the windmill do not line up
  and should not: a perfect pixel match would read as a freeze.
- **Burned-in captions.** `render.py` measures each voice clip, splits the line
  on punctuation, and writes `captions.js`; the scene reads `window.CAPTIONS`.
  Timing comes from the same measurement as the audio, so the two cannot drift.
  The voice pass now runs *before* the frames for this reason.
- **The safe area.** Instagram covers the top 14% and the bottom 35%. The app
  strip at y 1636 and the footer at y 1806 were both underneath its caption
  stack, which meant the one element aimed at app installs was invisible in
  the only place it is ever watched. Both are gone, replaced by a small mark at
  the top left that is present in every frame including the first and last, so
  it brands the film without being an end card that breaks the loop.
- **Five narration beats, not four**, and the `sub` line is gone: the captions
  now say what it used to say, and running both was saying it twice.

The split horizon glow (`gGlowL` and `gGlowR`) is what makes the answer frame
possible: green rising on the bull's side, red on the bear's, both at once in
the `duel` mood. Each animal's rim light reads its own side.

## The episode engine, 1.10.2026 (overnight)

Ofir asked for several videos of different kinds by morning, working
unattended. Hand-tuning each one was not an option at that scale, so the film
became a template instead of a one-off.

The five-beat skeleton never changes, because it is the structure the research
endorsed. What an episode supplies is `episodes/<id>.js`: four titles, three
chart shapes, two hook colours, and which animal does what in the two teaching
beats. `render.py` copies the chosen file to `episode.js` before any frame is
grabbed, and holds the narration and the beat table.

`sceneLayout(t, S, spec, prevBull, prevBear)` is the piece that made this
possible. It is a pure function, so the close can evaluate the end of scene B
and blend from wherever the animals actually finished back to `POSE` without
the episode data having to state it. The action vocabulary is small on purpose:
`rearUp`, `swipe`, `pace`, and `both` for the one lesson that needs the two
animals on stage arguing.

Four episodes ship: `bull-bear`, `correction` (ten percent against twenty),
`volatility` (noise close up, trend far away), `compound` (slow for years, then
fast). Charts live in one `PATHS` table, so a new lesson is usually a new path
and five lines of data.

Two things the stills caught before the renders: with both animals on stage the
camera has already panned right, so their marks had to move from 300/830 to
520/940 or the bull hung off the left edge; and the hook's two chart colours
had to become per-episode, because green-good red-bad says the wrong thing when
the two lines are "noise" and "trend".

The music bed is synthesised, not licensed: five detuned sine partials, each
completing a whole number of cycles in 20.5s, generated three times long with
the middle slice taken so the filters are in steady state. That is what gets
the loop seam from 28% of peak down to under 2%.

## Three bugs the overnight run paid for

**Shared mutable data between runs.** `episode.js` and `captions.js` were two
files in this directory that every run rewrote. That is invisible until two
runs overlap, and then it is vicious: a re-dub launched while a render was in
flight rewrote both files mid-render, and `compound.mp4` came out carrying
`correction`'s title and chart and `bull-bear`'s captions. Nothing failed and
nothing logged a warning; the only way to catch it was to pull a frame out of
the finished video and look at it. Both files are now one `data-<pid>.js` per
run, passed to the page as `?d=`, written at the start and deleted at the end.
The page `document.write`s it, which blocks parsing until it loads and so
keeps the synchronous behaviour the rest of the scene assumes.

**One slow frame killed a whole render.** Chrome occasionally stalls past the
120s timeout when this machine is loaded, and `grab` raised, which aborted the
pool, which lost twenty-five minutes of finished frames. It now retries three
times with a pause and a longer ceiling.

**Kokoro aborts under memory pressure.** Synthesising while two renders were
running killed the voice with SIGABRT. Same treatment: three attempts with a
breather, because it is a resource problem rather than a bad line.

The pattern in all three: the failure was in the seams between runs, not in any
single run, and two of the three produced a plausible-looking artefact rather
than an error.

## How to check a render actually came out right

Do not trust the log. Two of the three bugs above produced a file that encoded
cleanly, reported success, and was wrong. The only check that catches them is
to pull a frame out of the finished mp4 and look at it:

    ffmpeg -ss 9.0 -i out/<id>.mp4 -frames:v 1 -y /tmp/check.png

Second 9 lands inside the first teaching beat, so the title, the chart and the
caption should all belong to the same episode. Second 15 does the same for the
second beat.

## Open, not done

- the characters are drawn, not rigged, so a new pose means new SVG
- `pace` is the weakest of the three actions: it overshoots to the right and
  the animal can end up near the frame edge
- the characters still only exist in profile, which is the real limit on them
  acting against each other; a turnaround is the next real piece of work
- a paid cloud TTS (ElevenLabs and the like) would still beat Kokoro, but it
  needs an account and a key from Ofir; not worth raising again unless the
  local voice turns out to be the thing holding the reel back
