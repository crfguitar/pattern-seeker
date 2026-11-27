"""First Light - a hand-written soul-flip instrumental in the King's Disease
(Nas x Hit-Boy) mould, 80 BPM, with room for a rapper.

    python examples/first_light.py          # compose, print the plan and the checks
    python examples/first_light.py build    # add the drum and 808 channels
    python examples/first_light.py write    # write the patterns (lay them out with arrange)
    python examples/first_light.py rewrite Sampel 808   # new notes, playlist kept

The sample: First Choice - "Wake Up To Me" (the user's Tracklib file), played by
Sampel (the user's Serato Sample clone) on channel 1. Sampel's own analysis:
75.12 BPM, key D, first beat 0.032 s. It was sliced from Pattern Seeker with
Sampel's automation parameters: Seek to song beat 8 (6.42 s), Autoset Mode = Set
Slicer, Autoset on, Slicer Size Up (1 -> 2 beats). That gives 16 two-beat slices
over song beats 8-40, pad N = MIDI 35 + N (pad 1 = C1 = 36):

  pad  3-8   F | Fmaj7 | Bbmaj7 | F | Fmaj7 | Bbmaj7   intro chords, light "ooh"s
  pad  9-11  Em7 | Em7 | A7                          no vocal at all
  pad 12     A, "Wake" on its last beat
  pad 13     D, "up ..."
  pad 14     A, "... to me"
  pad 15-16  Dmaj7 / Em, the line again

Sampel is in Hold mode (a note plays its slice for as long as it is held and
stops at the slice end) and mono (a new chop cuts the last). Sync + Pitch 'n
Time stretch the 75 BPM record to FL's tempo without changing its pitch.

The flip: verses loop the intro chords re-chopped (F | Bbmaj7 F | Fmaj7 Bbmaj7 |
Em7 A7), with restrikes; the hook is the title line, "Wake / up / to me" over
Em7 A | D A, stuttered every other time. The last bar of each verse sets up
"Wake" with the drums cut so the hook lands on "up".

Drums from the Hit-Boy pack: knocking kick, boom-bap snare + slap, eighth hats
(sixteenths in the hook), side-stick ghosts, open hat, shaker, crash. An 808
(C1 sample) plays the chop's roots under the kicks.

Form (bars): Intro 4 | Hook 8 | Verse 1 16 | Hook 8 | Verse 2 16 | Hook 8
             | Outro 4 = 64 bars, 3:12.
"""

import collections
import json
import os
import random
import statistics
import sys

TEMPO = 80
SAMPLES = os.environ.get("PATTERN_SEEKER_SAMPLES", os.path.join(os.path.expanduser("~"), "Music", "Samples"))
PACK = os.path.join(SAMPLES, r"Hit-Boy\Hit-Boy (Shows the Screen)")

# channel: (sample, colour, volume, pan). Hats left: the user's habit (drum-panning memory).
BAND = {
    "Kick": (r"\Kicks\Hit Boy Kick-1.wav", "#C8553D", 0.80, 0.0),
    "Snare": (r"\Snares\HITBOY BOOMBAP 2.wav", "#E0A33A", 0.66, 0.0),
    "Clap": (r"\Claps\HitBoy Slap.wav", "#E8C15A", 0.48, 0.0),
    "Hat": (r"\Closed Hats\HitHats11.wav", "#D9CB5E", 0.40, -0.18),
    "Open hat": (r"\Open Hats\OpenHH Butta 1.wav", "#C9B85A", 0.30, -0.18),
    "Rim": (r"\Percs\just blaze SIDE_STI.WAV", "#A8B05A", 0.34, 0.15),
    "Shaker": (r"\Percs\Neptunes Shaker.WAV", "#BFAE7A", 0.26, 0.30),
    "808": (r"\808s\808s (Honorable C Note).wav", "#7A4FA0", 0.52, 0.0),
    "Crash": (r"\Crashes & Cymbals\Crash Boots.wav", "#8A8A8A", 0.30, 0.25),
}
SAMPEL = "Sampel"
# A soft organ bed from Verse 1 on (the user: "background organ when verse 1 kicks in").
KEYS = {"Organ": ("FLEX/Chill-Lo-Fi/Vintage Soap Organ", "#6F6FA8", 0.30, 0.12)}

# Organ voicings around the vocal-free middle (F3-F#4), moving by step:
# F family keeps F A C (the record's own maj7 rubs against it as a maj7 should),
# Bbmaj7 is F A D, then G B D -> G C# E -> A C# E -> A D F#.
VOICE = {3: (53, 57, 60), 4: (53, 57, 60), 6: (53, 57, 60), 7: (53, 57, 60),
         5: (53, 57, 62), 8: (53, 57, 62), 9: (55, 59, 62), 10: (55, 59, 62),
         11: (55, 61, 64), 12: (57, 61, 64), 14: (57, 61, 64), 13: (57, 62, 66),
         15: (57, 61, 66), 16: (55, 59, 64)}


def pad(n):
    return 35 + n                      # Sampel: pad 1 = MIDI 36


CHORD = {3: "F", 4: "F", 5: "Bb", 6: "F", 7: "F", 8: "Bb", 9: "E", 10: "E", 11: "A",
         12: "A", 13: "D", 14: "A", 15: "D", 16: "E"}
ROOT = {"F": 65, "Bb": 70, "E": 64, "A": 69, "D": 62}      # 808 sample is C1: F1 = 65

# chops: (pad, beat in bar, length in beats)
VERSE = [[(3, 0, 2), (4, 2, 1.5), (3, 3.5, 0.5)],
         [(5, 0, 2), (6, 2, 2)],
         [(7, 0, 1.5), (7, 1.5, 0.5), (8, 2, 2)],
         [(9, 0, 2), (11, 2, 2)]]
TO_HOOK = [(9, 0, 2), (12, 2, 2)]                          # "...Wake" leads into the hook
UP = [(13, 0, 2), (14, 2, 2)]                              # "up ... to me"
UP_STUTTER = [(13, 0, 2), (14, 2, 0.5), (14, 2.5, 0.5), (14, 3, 1)]
WAKE = [(9, 0, 2), (12, 2, 2)]
TURN = [(9, 0, 2), (11, 2, 2)]                             # instrumental: back to the verse
HOOK = [UP, WAKE, UP_STUTTER, WAKE, UP, WAKE, UP_STUTTER, TURN]
INTRO = [[(3, 0, 2), (4, 2, 2)], [(5, 0, 2), (6, 2, 2)], [(7, 0, 2), (8, 2, 2)], TO_HOOK]
OUTRO = [UP, TURN, [(3, 0, 2), (4, 2, 2)], [(5, 0, 2), (6, 2, 2)]]

LEVEL = {"Intro": -4, "Hook 1": 4, "Verse 1": -2, "Hook 2": 5, "Verse 2": -1,
         "Hook 3": 6, "Outro": -4}
SWING = 0.03


class Sec:
    def __init__(self, name, bars, color):
        self.name, self.bars, self.color = name, bars, color
        self.parts = collections.defaultdict(list)
        self.chops = []                # (abs beat, pad, length) for the 808

    def add(self, ch, pitch, start, length, vel):
        self.parts[ch].append([pitch, round(start, 4), length, vel])


def sw(k):
    return k * 0.25 + (SWING if k % 2 else 0)


def hit(s, rng, ch, t, vel, pitch=60, length=0.25):
    s.add(ch, pitch, t + rng.uniform(-0.008, 0.008), length, vel + rng.randint(-3, 3))


def chop(s, bars, bar0=0):
    for i, bar in enumerate(bars):
        for p, at, length in bar:
            t = (bar0 + i) * 4 + at
            s.add(SAMPEL, pad(p), t, length - 0.02, 100)
            s.chops.append((t, p, length))


def chord_at(s, t):
    cur = None
    for at, p, _ in sorted(s.chops):
        if at <= t + 1e-6:
            cur = CHORD[p]
    return cur


def bass(s, kicks_by_bar, bar0, bars):
    """808 on every kick, on the chop's root, held to the next kick or chord change."""
    for i in range(bars):
        t0 = (bar0 + i) * 4
        kicks = sorted(kicks_by_bar.get(bar0 + i, []))
        changes = sorted({round(a, 4) for a, _, _ in s.chops if t0 <= a < t0 + 4})
        starts = sorted(set(kicks) | {c for c in changes if c - t0 in (0, 2)
                                      and not any(0 < k - c < 0.5 for k in kicks)})
        for j, t in enumerate(starts):
            c = chord_at(s, t)
            if c is None:
                continue
            end = min([x for x in starts[j + 1:]] + [t0 + 4])
            vel = 92 if t in kicks else 78
            s.add("808", ROOT[c], t, max(0.25, end - t - 0.03), vel)


def organ(s, vel, stop=None, swell=0, fade=0):
    """Held chords under the chops, one per change of root (restrikes don't retrigger).
    stop: the beat it drops out (so "Wake" sits alone); swell / fade: bars of a
    soft entry or exit."""
    runs = []
    for at, p, _ in sorted(s.chops):
        if not runs or CHORD[p] != CHORD[runs[-1][1]]:
            runs.append((at, p))
    end = s.bars * 4 if stop is None else stop
    for j, (at, p) in enumerate(runs):
        if at >= end:
            break
        nxt = runs[j + 1][0] if j + 1 < len(runs) else s.bars * 4
        length = min(nxt, end) - at - 0.05
        v = vel
        if swell and at < swell * 4:
            v -= round(8 * (1 - at / (swell * 4)))
        if fade and at > (s.bars - fade) * 4:
            v -= round(8 * (at - (s.bars - fade) * 4) / (fade * 4))
        for k, n in enumerate(VOICE[p]):
            s.add("Organ", n, at, length, v - (2 if k == 2 else 0))


KICKS = [[0, 0.75, 2.5], [0, 1.75, 2.25], [0, 0.75, 2.5, 3.25], [0, 1.5, 2.5, 2.75]]


def drums(s, rng, bar0, bars, hook=False, busy=False, end="fill"):
    """end: 'fill' = a snare pickup in the last bar, 'cut' = drums stop after beat 1
    of the last bar (the vocal "Wake" sits alone), None = play through."""
    kicks_by_bar = {}
    for i in range(bars):
        b, t = bar0 + i, (bar0 + i) * 4
        last = i == bars - 1
        cut = last and end == "cut"
        ks = [k for k in KICKS[i % 4] if not (cut and k > 0)]
        kicks_by_bar[b] = [round(t + k + (SWING if (k * 4) % 2 else 0), 4) for k in ks]
        for k in kicks_by_bar[b]:
            hit(s, rng, "Kick", k, 94 if abs(k - t) < 1e-6 else 86)
        if cut:
            continue
        for beat in (1, 3):
            hit(s, rng, "Snare", t + beat + 0.01, 92)
            hit(s, rng, "Clap", t + beat + 0.015, 80)
        if last and end == "fill":
            for k, v in ((13, 66), (14, 72), (15, 80)):
                hit(s, rng, "Snare", t + sw(k), v)
        step = 1 if hook or busy else 2
        for k in range(0, 16, step):
            if last and end == "fill" and k >= 13:
                break
            v = 76 if k % 4 == 0 else 66 if k % 2 == 0 else 56
            hit(s, rng, "Hat", t + sw(k), v, length=0.12)
        if hook and i % 4 == 3 and not last:                # a triplet roll into the next phrase
            for r in range(3):
                hit(s, rng, "Hat", t + 3.5 + r / 6, 60 + r * 5, length=0.08)
        if hook and i % 2 == 1:
            hit(s, rng, "Open hat", t + 1.5, 70, length=0.4)
        if hook:
            for k in range(2, 16, 4):
                hit(s, rng, "Shaker", t + sw(k), 62)
        elif i % 2 == 1:
            hit(s, rng, "Rim", t + sw(11), 62)
            if rng.random() < 0.5:
                hit(s, rng, "Rim", t + sw(15), 56)
    return kicks_by_bar


# ---- sections ---------------------------------------------------------------------------
def intro(rng):
    s = Sec("Intro", 4, "#C07A3A")
    chop(s, INTRO)                                        # the record on its own
    for k in range(8):                                    # a shaker creeps in
        hit(s, rng, "Shaker", 8 + k * 0.5 + SWING, 54 + k)
    return s


def hook(name, rng):
    s = Sec(name, 8, "#E0782F")
    chop(s, HOOK)
    hit(s, rng, "Crash", 0, 80, length=2)
    kicks = drums(s, rng, 0, 8, hook=True, end="fill")
    bass(s, kicks, 0, 8)
    if name != "Hook 1":                                  # the organ arrives with Verse 1
        organ(s, 60)
    return s


def verse(name, rng, busy):
    s = Sec(name, 16, "#5A7FA8")
    chop(s, VERSE * 3 + VERSE[:3] + [TO_HOOK])
    hit(s, rng, "Crash", 0, 68, length=2)
    kicks = drums(s, rng, 0, 16, busy=busy, end="cut")
    bass(s, kicks, 0, 16)
    organ(s, 66, stop=15 * 4 + 2, swell=2 if name == "Verse 1" else 0)
    return s


def outro(rng):
    s = Sec("Outro", 4, "#C07A3A")
    chop(s, OUTRO)
    kicks = drums(s, rng, 0, 2, end=None)
    bass(s, kicks, 0, 2)
    s.add("808", ROOT["F"], 8, 3.9, 74)                   # the 808 rings once under the last chords
    organ(s, 62, fade=2)
    return s


def compose(seed=2020):
    rng = random.Random(seed)
    secs = [intro(rng), hook("Hook 1", rng), verse("Verse 1", rng, False), hook("Hook 2", rng),
            verse("Verse 2", rng, True), hook("Hook 3", rng), outro(rng)]
    for i, s in enumerate(secs):
        level = LEVEL[s.name]
        nxt = LEVEL[secs[i + 1].name] if i + 1 < len(secs) else level
        end = s.bars * 4
        for ch, notes in s.parts.items():
            for n in notes:
                if ch != SAMPEL:                          # Sampel's velocity switch is off
                    ramp = max(0.0, (n[1] - (end - 8)) / 8) * (nxt - level) * 0.5
                    n[3] = int(round(min(100, max(50, n[3] + level + ramp))))
                n[1] = round(max(0.0, n[1]), 4)
                n[2] = round(max(0.05, min(n[2], end - n[1])), 4)
    return secs


def check(secs):
    meds = []
    for s in secs:
        for b in range(s.bars):
            vs = [n[3] for ch, ns in s.parts.items() if ch != SAMPEL
                  for n in ns if b * 4 <= n[1] < b * 4 + 4]
            meds.append((s.name, b + 1, statistics.median(vs) if vs else None))
    return sorted(((abs(b[2] - a[2]), a, b) for a, b in zip(meds, meds[1:]) if a[2] and b[2]),
                  reverse=True)


def main(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, root)
    secs = compose()
    do = argv[1] if len(argv) > 1 else "plan"
    if do == "plan":
        bar = 1
        for s in secs:
            vs = [n[3] for ch, ns in s.parts.items() if ch != SAMPEL for n in ns] or [0]
            chops = " ".join(str(p) for _, p, _ in sorted(s.chops)[:12])
            print("bars %2d-%2d  %-8s %4d notes  vel %d-%d  chops %s ..." % (
                bar, bar + s.bars - 1, s.name, sum(len(v) for v in s.parts.values()),
                min(vs), max(vs), chops))
            bar += s.bars
        print("%d bars, %.2f minutes at %d BPM" % (bar - 1, (bar - 1) * 4 / TEMPO, TEMPO))
        for jump, a, b in check(secs)[:3]:
            print("  median move %.1f: %s %d -> %s %d" % (jump, a[0], a[1], b[0], b[1]))
        return
    from seeker import link
    from seeker.engine import Engine
    engine = Engine()
    try:
        if do == "build":
            have = {c["name"] for c in engine.status()["channels"]}
            for name, (sample, color, volume, pan) in BAND.items():
                if name in have:
                    continue
                made = engine.add_channel(PACK + sample, name, color, volume, pan)
                print(name, "-> channel", made["channel"], "insert", made.get("insert"),
                      made["warnings"], file=sys.stderr, flush=True)
            for name, (sound, color, volume, pan) in KEYS.items():
                if name not in have:
                    made = engine.add_channel(sound, name, color, volume, pan)
                    print(name, "-> channel", made["channel"], "insert", made.get("insert"),
                          made["warnings"], file=sys.stderr, flush=True)
        elif do == "rewrite":
            first = int(os.environ.get("FIRST_PATTERN", "2"))
            parts = argv[2:] or [SAMPEL] + list(BAND)
            for n, sec in enumerate(secs):
                engine._song(pattern=first + n)
                for ch in parts:
                    if sec.parts.get(ch):
                        bad = engine.write_part(ch, sec.parts[ch])["problems"]
                        print("pattern %d %s %s %s" % (first + n, sec.name, ch, bad or "ok"), flush=True)
        elif do == "write":
            sections = [{"name": s.name, "color": s.color, "parts": dict(s.parts)} for s in secs]
            done = engine.write_song(sections, tempo=TEMPO, arrange=False)
            print(json.dumps({"sections": done["sections"], "problems": done["problems"],
                              "warnings": done.get("warnings")}, default=str))
    finally:
        link.close()


if __name__ == "__main__":
    main(sys.argv)
