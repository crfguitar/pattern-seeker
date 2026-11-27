"""Night Shift - a hand-written trap instrumental in F minor, 140 BPM, with room
for a rapper. Every sound is a sample from the user's Cymatics Trap Gods pack.

    python examples/trap_gods.py          # compose, print the plan and the checks
    python examples/trap_gods.py build    # add the thirteen sampler channels
    python examples/trap_gods.py write    # write the patterns (lay them out with arrange)
    python examples/trap_gods.py rewrite Bell 808   # new notes, playlist kept

Samples are played chromatically by FL's sampler: written note 60 plays the
sample as recorded. Measured (FFT) roots: the 808s are C1 (so F1 = note 65),
BELL Gems is C5 (it sounds an octave over what is written), PAD Detune and
PLUCK Drink Up are C4 (they sound as written), so the pluck doubles the bell
exactly an octave down.

What makes it trap: half-time snare + clap on beat 3, a kick/808 pattern that
changes every bar, hats in eighths and sixteenths with triplet and 32nd rolls,
an open hat on the off-beat, a dark minor loop with a harmonic-minor V
(Fm | Db | Bbm | C), a bell hook doubled by a pluck, reverse risers and an
impact into each hook.

Room for the rapper: verses keep the drums, 808 and a quiet pad; the bell only
answers in the last beat of every fourth bar. The hook carries the melody.

Form (bars): Intro 8 | Hook 1 16 | Verse 1 16 | Hook 2 16 | Verse 2 16 | Break 4
             | Hook 3 16 | Outro 8 = 100 bars, about 2:51.
"""

import collections
import json
import os
import random
import statistics
import sys

TEMPO = 140
SAMPLES = os.environ.get("PATTERN_SEEKER_SAMPLES", os.path.join(os.path.expanduser("~"), "Music", "Samples"))
PACK = os.path.join(SAMPLES, "Cymatics Trap Gods")

# channel: (sample, colour, volume, pan)
BAND = {
    "Kick": (r"\Kicks\Cymatics - Kick (Bob).wav", "#C8553D", 0.80, 0.0),
    "Snare": (r"\Snares\Cymatics - Snare (Hybrid).wav", "#E0A33A", 0.62, 0.0),
    "Clap": (r"\Claps\Cymatics - Clap (Burner).wav", "#E8C15A", 0.55, 0.0),
    "Hat": (r"\Hats\Closed\Cymatics - Hihat (Edge).wav", "#D9CB5E", 0.42, 0.20),
    "Open hat": (r"\Hats\Open\Cymatics - Open Hat (Hazelnut).wav", "#C9B85A", 0.32, 0.20),   # same side as the hat
    "Rim": (r"\Snares\Rim\Cymatics - Rim (Atomic).wav", "#A8B05A", 0.30, -0.30),
    "Perc": (r"\Percussion\Cymatics - Percussion (Toronto).wav", "#9FB07A", 0.28, 0.35),
    "808": (r"\808s\Cymatics - 808 Burned (C).wav", "#7A4FA0", 0.50, 0.0),     # 0.72 drowned the hats
    "Bell": (r"\One Shots\Cymatics - BELL Gems (C).wav", "#5FA8E0", 0.44, 0.10),
    "Pad": (r"\One Shots\Cymatics - PAD Detune (C).wav", "#4F6FBF", 0.36, 0.0),
    "Pluck": (r"\One Shots\Cymatics - PLUCK Drink Up (C).wav", "#4FB8A8", 0.30, -0.18),
    "Riser": (r"\FX\Cymatics - Reverse (Breath).wav", "#8A8A8A", 0.32, 0.0),
    "Impact": (r"\FX\Cymatics - Impact (Fighter).wav", "#6A6A6A", 0.34, 0.0),
}

# ---- harmony (written notes) ---------------------------------------------------------------
LOOP = ["Fm", "Db", "Bbm", "C"]
PAD = {"Fm": [53, 56, 60, 65], "Db": [53, 56, 61, 65],      # F stays on top: a dark pedal
       "Bbm": [53, 58, 61, 65], "C": [52, 55, 60, 64]}      # C major: the harmonic-minor V
ROOT = {"Fm": 65, "Db": 61, "Bbm": 70, "C": 60}             # 808: F1 Db1 Bb1 C1

LEVEL = {"Intro": -6, "Hook 1": 3, "Verse 1": -3, "Hook 2": 4, "Verse 2": -2,
         "Break": -6, "Hook 3": 6, "Outro": -4}

# the bell hook, written pitches (it sounds an octave up): pitch, beat, length
HOOK = [
    [(72, 0, .75), (68, .75, .75), (65, 1.5, .5), (67, 2, .5), (68, 2.5, 1.5)],                    # Fm
    [(68, 0, .75), (65, .75, .75), (61, 1.5, .5), (63, 2, 1), (65, 3, 1)],                        # Db
    [(70, 0, .75), (65, .75, .75), (61, 1.5, .5), (65, 2, .5), (70, 2.5, .5), (73, 3, 1)],        # Bbm
    [(72, 0, 1.5), (67, 1.5, .5), (64, 2, 1), (67, 3, 1)],                                         # C
]
HOOK_END = [(72, 0, 1.5), (71, 1.5, .5), (67, 2, 2)]       # second time round the C bar: B natural
ANSWERS = [[(72, 3, .25), (68, 3.25, .25), (65, 3.5, .5)],
           [(65, 3, .25), (67, 3.25, .25), (68, 3.5, .5)],
           [(73, 3, .33), (72, 3.33, .33), (67, 3.67, .33)]]


class Sec:
    def __init__(self, name, bars, color):
        self.name, self.bars, self.color = name, bars, color
        self.parts = collections.defaultdict(list)

    def add(self, ch, pitch, start, length, vel):
        self.parts[ch].append([pitch, round(start, 4), length, vel])


def hit(s, rng, ch, t, vel, pitch=60, length=0.25):
    s.add(ch, pitch, t, length, vel + rng.randint(-2, 2))


# ---- melodic parts --------------------------------------------------------------------------
def pad(s, bar, bars, vel):
    for i in range(bars):
        c = LOOP[i % 4]
        for k, p in enumerate(PAD[c]):
            s.add("Pad", p, (bar + i) * 4, 3.95, vel - k)


def bell_hook(s, bar, bars, vel, pluck=True):
    for i in range(bars):
        phrase = HOOK_END if i % 8 == 7 else HOOK[i % 4]
        for p, at, length in phrase:
            accent = 4 if at == 0 else 0
            s.add("Bell", p, (bar + i) * 4 + at, length * 0.95, vel + accent)
            if pluck:
                s.add("Pluck", p, (bar + i) * 4 + at, length * 0.8, vel - 6 + accent)


def answers(s, bar, bars, vel, rng):
    for i in range(3, bars, 4):
        for p, at, length in ANSWERS[rng.randrange(3)]:
            s.add("Bell", p, (bar + i) * 4 + at, length * 0.9, vel)


# ---- drums and 808 --------------------------------------------------------------------------
KICKS = [[0, .75, 2.5], [0, 1.5, 3.25], [0, .75, 1.75, 3.5], [0, 2.5, 3]]


def drums(s, bar, bars, rng, full=True, drop_end=True, rolls=True):
    """Half-time trap: snare + clap on 3, kicks and 808 together, hats with rolls."""
    for i in range(bars):
        t = (bar + i) * 4
        last = i == bars - 1
        drop = drop_end and last                 # the beat cuts out on the last two beats
        kicks = KICKS[i % 4]
        for j, k in enumerate(kicks):
            if drop and k >= 2:
                continue
            hit(s, rng, "Kick", t + k, 92 if k == 0 else 84)
            nxt = kicks[j + 1] if j + 1 < len(kicks) else 4
            root = ROOT[LOOP[i % 4]]
            up = 12 if (i % 2 == 1 and j == len(kicks) - 1 and root < 66) else 0
            s.add("808", root + up, t + k, max(0.25, nxt - k - 0.05), 90 if k == 0 else 82)
        if not drop:
            hit(s, rng, "Snare", t + 2, 90)
            hit(s, rng, "Clap", t + 2, 86)
        if i % 8 == 7 and not drop:              # a snare pickup into the next eight
            hit(s, rng, "Snare", t + 3.5, 70)
            hit(s, rng, "Snare", t + 3.75, 78)
        # hats: sixteenths in the hook, eighths in the verse, a roll every bar or two
        step = 0.25 if full else 0.5
        roll_at = None
        if rolls and (full or i % 2 == 1):
            roll_at = [1.5, 3.0, 2.5, 3.5][i % 4]
        k = 0.0
        while k < (2 if drop else 4):
            if roll_at is not None and roll_at <= k < roll_at + 0.5:
                kind = [1 / 6, 1 / 8, 1 / 6, 1 / 8][i % 4]       # triplet 16ths or 32nds
                n = int(round(0.5 / kind))
                for r in range(n):
                    hit(s, rng, "Hat", t + k + r * kind, 58 + r * 3, length=0.1)
                k += 0.5
                continue
            on = abs(k - round(k)) < 1e-6
            hit(s, rng, "Hat", t + k, 74 if on else 62, length=0.12)
            k += step
        if full and i % 2 == 1 and not drop:
            hit(s, rng, "Open hat", t + 3.5, 70, length=0.4)
        if full and i % 4 == 2:
            hit(s, rng, "Perc", t + 1.25, 66)
        if i % 4 == 1 and not drop:
            hit(s, rng, "Rim", t + 3.75, 64)


def riser(s, end_beat, vel=72):
    """The reverse sample ends right on the next section's downbeat (3.58 s)."""
    beats = 3.58 * TEMPO / 60
    s.add("Riser", 60, round(end_beat - beats, 4), beats, vel)


# ---- sections ----------------------------------------------------------------------------
def intro(rng):
    s = Sec("Intro", 8, "#4F6FBF")
    pad(s, 0, 8, 70)
    bell_hook(s, 0, 8, 68, pluck=False)
    for i in range(4, 8):                                 # hats tick in, no kick yet
        for k in range(8):
            hit(s, rng, "Hat", (i * 4) + k * 0.5, 62 if k % 2 else 70, length=0.12)
    for i in range(6, 8):                                 # the 808 breathes once a bar
        s.add("808", ROOT[LOOP[i % 4]], i * 4, 3.5, 80)
    riser(s, 32)
    return s


def hook(name, rng):
    s = Sec(name, 16, "#E0782F")
    s.add("Impact", 60, 0, 6, 76)
    pad(s, 0, 16, 72)
    bell_hook(s, 0, 16, 78)
    drums(s, 0, 16, rng, full=True)
    return s


def verse(name, rng, n):
    s = Sec(name, 16, "#5A7FA8")
    pad(s, 0, 16, 62)                                     # quiet under the voice
    drums(s, 0, 16, rng, full=n == 2)                     # verse 2: sixteenth hats
    answers(s, 0, 16, 64, rng)
    riser(s, 64, 66)
    return s


def break_(rng):
    s = Sec("Break", 4, "#8A5A3A")
    pad(s, 0, 4, 66)
    bell_hook(s, 0, 2, 66, pluck=False)
    for i in range(4):
        s.add("808", ROOT[LOOP[i]], i * 4, 3.9, 78)
    for k in range(16):                                   # hats build back in 32nds
        hit(s, rng, "Hat", 14 + k * 0.125, 54 + k * 2, length=0.08)
    riser(s, 16, 74)
    return s


def outro(rng):
    s = Sec("Outro", 8, "#4F6FBF")
    pad(s, 0, 8, 66)
    bell_hook(s, 0, 4, 70)
    drums(s, 0, 4, rng, full=False, drop_end=False)
    bell_hook(s, 4, 3, 62, pluck=False)
    for p in PAD["Fm"]:                                   # home on Fm, held
        s.add("Pad", p, 28, 4, 62)
    s.add("Bell", 65, 28, 4, 62)
    s.add("808", ROOT["Fm"], 28, 3.5, 70)
    return s


def compose(seed=140):
    rng = random.Random(seed)
    secs = [intro(rng), hook("Hook 1", rng), verse("Verse 1", rng, 1), hook("Hook 2", rng),
            verse("Verse 2", rng, 2), break_(rng), hook("Hook 3", rng), outro(rng)]
    for i, s in enumerate(secs):
        level = LEVEL[s.name]
        nxt = LEVEL[secs[i + 1].name] if i + 1 < len(secs) else level
        end = s.bars * 4
        for notes in s.parts.values():
            for n in notes:
                ramp = max(0.0, (n[1] - (end - 8)) / 8) * (nxt - level) * 0.5
                n[3] = int(round(min(100, max(50, n[3] + level + ramp))))
                n[1] = round(max(0.0, n[1]), 4)
                n[2] = round(max(0.05, min(n[2], end - n[1])), 4)
    return secs


def check(secs):
    meds = []
    for s in secs:
        for b in range(s.bars):
            vs = [n[3] for ns in s.parts.values() for n in ns if b * 4 <= n[1] < b * 4 + 4]
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
            vs = [n[3] for ns in s.parts.values() for n in ns]
            print("bars %3d-%3d  %-8s %4d notes  vel %d-%d  %s" % (
                bar, bar + s.bars - 1, s.name, len(vs), min(vs), max(vs), ", ".join(sorted(s.parts))))
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
        elif do == "rewrite":
            first = int(os.environ.get("FIRST_PATTERN", "2"))
            parts = argv[2:] or list(BAND)
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
