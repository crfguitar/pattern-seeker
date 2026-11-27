"""Requiem Block - a dark chamber-orchestra hip-hop instrumental, D minor, 76 BPM
(a 152 half-time feel), with room for a rapper. No showpiece lead: a violas
staccato ostinato drives it, the violins only carry a slow theme in the hooks.

    python examples/requiem_block.py          # compose, print the plan and the checks
    python examples/requiem_block.py build    # add the channels
    python examples/requiem_block.py write    # write the patterns (lay them out with arrange)
    python examples/requiem_block.py rewrite Violins Horns   # new notes, playlist kept

Orchestra: FLEX Essential Strings / Winds (the Divertimento's players) plus GM
timpani. Drums: Cymatics PLUTO one-shots; 808: Cymatics SOLARIS (C1 at note 60).

Harmony: Hook Dm | Bb | Gm | A (the A major is harmonic minor's dark pull home);
Verse Dm | Dm | Bb | A; Bridge Gm | Eb | Dm | A (the flat sixth darkens it);
Outro Dm | Bb | A | Dm.

Dynamics follow the Divertimento rules the user signed off on: the orchestra
stays in velocity 54-90, a melody about +5 over its section, accompaniment -4 to
-6 under, every section starts at its own level, changes eased over two bars.

Form (bars): Intro 4 | Hook 1 8 | Verse 1 16 | Hook 2 8 | Verse 2 16 | Bridge 8
             | Hook 3 8 | Outro 4 = 72 bars, 3:47.
"""

import collections
import json
import os
import random
import statistics
import sys

TEMPO = 76
SAMPLES = os.environ.get("PATTERN_SEEKER_SAMPLES", os.path.join(os.path.expanduser("~"), "Music", "Samples"))
PLUTO = os.path.join(SAMPLES, r"Cymatics-DrumOneShots(PLUTO)\Cymatics - Drum One Shots (PLUTO)")
SOLARIS = os.path.join(SAMPLES, r"Cymatics-808&BassCollection(Solaris)"
                       r"\Cymatics - 808 & Bass Collection (SOLARIS)")

# channel: (sound, colour, volume, pan). Hats left (drum-panning memory); the strings
# sit as a chamber group would: violins left, violas centre-right, cellos right.
BAND = {
    "Kick": (PLUTO + r"\Cymatics - Kick (Jinx).wav", "#C8553D", 0.78, 0.0),
    "Snare": (PLUTO + r"\Cymatics - Snare (Hardcore).wav", "#E0A33A", 0.64, 0.0),
    "Clap": (PLUTO + r"\Cymatics - Clap (Grenade).wav", "#E8C15A", 0.42, 0.0),
    "Hat": (PLUTO + r"\Cymatics - Hihat (Outside).wav", "#D9CB5E", 0.40, -0.15),
    "Open hat": (PLUTO + r"\Cymatics - Open Hat (Shining).wav", "#C9B85A", 0.28, -0.15),
    "Rim": (PLUTO + r"\Cymatics - Rim (Helper).wav", "#A8B05A", 0.30, 0.20),
    "808": (SOLARIS + r"\Cymatics - 808 Phones (C).wav", "#7A4FA0", 0.50, 0.0),
    "Violins": ("FLEX/Essential Strings/Violins Sustain", "#5FA8E8", 0.58, -0.35),
    "Pizz": ("FLEX/Essential Strings/Violins Pizzicato", "#7FB8E8", 0.42, -0.25),
    "Violas": ("FLEX/Essential Strings/Violas Staccato", "#5FB889", 0.52, 0.12),
    "Cellos": ("FLEX/Essential Strings/Cellos Sustain", "#3F9E6E", 0.55, 0.30),
    "Basses": ("FLEX/Essential Strings/Bass Sustain", "#2F7F58", 0.50, 0.38),
    "Horns": ("FLEX/Essential Winds/Horns Sustain", "#E0B040", 0.40, -0.10),
    "Timpani": ("FLEX/General Midi Library/Timpani", "#C05050", 0.50, 0.0),
}
ORCH = {"Violins", "Pizz", "Violas", "Cellos", "Basses", "Horns", "Timpani"}

# ---- harmony ------------------------------------------------------------------------------
HOOK = ["Dm", "Bb", "Gm", "A"]
VERSE = ["Dm", "Dm", "Bb", "A"]
BRIDGE = ["Gm", "Eb", "Dm", "A"]
OUTRO = ["Dm", "Bb", "A", "Dm"]
OSTINATO = {"Dm": (62, 57, 65, 57), "Bb": (58, 53, 62, 53), "Gm": (55, 50, 58, 50),
            "A": (57, 52, 61, 52), "Eb": (63, 58, 67, 58)}       # root, fifth below, third
HORNS = {"Dm": (50, 53, 57), "Bb": (50, 53, 58), "Gm": (50, 55, 58), "A": (49, 52, 57),
         "Eb": (51, 55, 58)}
CELLO = {"Dm": 53, "Bb": 50, "Gm": 46, "A": 49, "Eb": 51}         # the chord's third, tenor
BASS = {"Dm": 38, "Bb": 34, "Gm": 43, "A": 33, "Eb": 39}          # bowed basses, no 808
ROOT808 = {"Dm": 62, "Bb": 70, "Gm": 67, "A": 69, "Eb": 63}       # C1 sample: D1 = 62
PIZZ = {"Dm": (74, 77), "Bb": (74, 77), "Gm": (74, 70), "A": (73, 76), "Eb": (75, 79)}
THEME = [  # the hook's violin line, (pitch, beat, length): slow, inside the staff
    [(69, 0, 2), (65, 2, 1), (64, 3, 1)],
    [(62, 0, 3), (65, 3, 1)],
    [(67, 0, 1.5), (69, 1.5, .5), (70, 2, 2)],
    [(69, 0, 2), (73, 2, 2)],
    [(74, 0, 2), (72, 2, 1), (69, 3, 1)],
    [(70, 0, 3), (69, 3, 1)],
    [(67, 0, 2), (65, 2, 1), (62, 3, 1)],
    [(61, 0, 4)],                                            # C#: the pull back to D
]
BRIDGE_LINE = {"Gm": 74, "Eb": 79, "Dm": 77, "A": 76}         # long high notes

# orchestra level per section (velocity of the accompaniment; melody +5, under -5)
DYN = {"Intro": 60, "Hook 1": 76, "Verse 1": 66, "Hook 2": 78, "Verse 2": 67,
       "Bridge": 70, "Hook 3": 80, "Outro": 67}
LEVEL = {"Intro": -6, "Hook 1": 3, "Verse 1": -3, "Hook 2": 4, "Verse 2": -2,
         "Bridge": -4, "Hook 3": 5, "Outro": -6}            # the drums' offset


class Sec:
    def __init__(self, name, bars, color, prog):
        self.name, self.bars, self.color, self.prog = name, bars, color, prog
        self.parts = collections.defaultdict(list)

    def chord(self, bar):
        return self.prog[bar % len(self.prog)]

    def add(self, ch, pitch, start, length, vel):
        self.parts[ch].append([pitch, round(start, 4), round(length, 4), vel])


def hit(s, rng, ch, t, vel, pitch=60, length=0.2):
    s.add(ch, pitch, max(0.0, t + rng.uniform(-0.005, 0.005)), length, vel + rng.randint(-3, 3))


# ---- the orchestra ------------------------------------------------------------------------
def ostinato(s, rng, v, bars=None, start=0):
    """Violas, staccato 8ths: root, fifth below, third, fifth below - accent on the beat."""
    for i in range(start, bars or s.bars):
        notes = OSTINATO[s.chord(i)]
        for k in range(8):
            acc = 4 if k % 2 == 0 else 0
            hit(s, rng, "Violas", i * 4 + k * 0.5, v - 3 + acc, notes[k % 4], 0.3)


def cellos(s, v, bars=None, start=0):
    for i in range(start, bars or s.bars):
        s.add("Cellos", CELLO[s.chord(i)], i * 4, 3.9, v - 4)


def basses(s, v, bars=None, start=0):
    for i in range(start, bars or s.bars):
        s.add("Basses", BASS[s.chord(i)], i * 4, 3.9, v - 4)


def horns(s, v, bars=None, start=0):
    for i in range(start, bars or s.bars):
        for k, p in enumerate(HORNS[s.chord(i)]):
            s.add("Horns", p, i * 4, 3.9, v - 5 - k)


def theme(s, rng, v):
    for i in range(s.bars):
        for p, at, length in THEME[i % 8]:
            hit(s, rng, "Violins", i * 4 + at, v + 5 + (2 if at == 0 else 0), p, length - 0.05)


def pizz(s, rng, v):
    for i in range(s.bars):
        a, b = PIZZ[s.chord(i)]
        hit(s, rng, "Pizz", i * 4 + 1.5, v - 2, a, 0.3)
        if i % 2 == 1:
            hit(s, rng, "Pizz", i * 4 + 3.5, v - 5, b, 0.3)


def timpani_roll(s, rng, t, v, beats=2, pitch=45):
    """32nds swelling into the downbeat at t + beats."""
    n = int(beats / 0.125)
    for r in range(n):
        hit(s, rng, "Timpani", t + r * 0.125, v - 10 + int(14 * r / n), pitch, 0.12)


# ---- the drums ----------------------------------------------------------------------------
KICKS = [[0, 0.75, 2.5], [0, 2.25, 2.75], [0, 0.75, 1.5, 2.5], [0, 2.5, 3.25]]
VERSE_KICKS = [[0, 2.5], [0, 1.75, 2.5], [0, 2.5], [0, 0.75, 2.5, 3.25]]


def drums(s, rng, bars, kicks, busy, end="fill", start=0):
    kicks_at = []
    for i in range(start, bars):
        t = i * 4
        last = i == bars - 1
        for k in kicks[i % 4]:
            kicks_at.append(t + k)
            hit(s, rng, "Kick", t + k, 94 if k == 0 else 86)
        for beat in (1, 3):
            hit(s, rng, "Snare", t + beat, 92)
            hit(s, rng, "Clap", t + beat + 0.01, 80)
        if last and end == "fill":
            for k, v in ((3.5, 70), (3.625, 76), (3.75, 82), (3.875, 88)):
                hit(s, rng, "Snare", t + k, v)
        step = 0.25 if busy else 0.5
        roll = busy and i % 4 == 3 and not last
        k = 0.0
        while k < 4 - 1e-6:
            if last and end == "fill" and k >= 3.5:
                break
            if roll and k >= 3:
                break
            v = 76 if k == int(k) else 66 if (k * 2) == int(k * 2) else 58
            hit(s, rng, "Hat", t + k, v, length=0.08)
            k += step
        if roll:                                         # one triplet roll every four bars
            for r in range(6):
                hit(s, rng, "Hat", t + 3 + r / 6, 58 + 3 * r, length=0.05)
        if busy and i % 2 == 1:
            hit(s, rng, "Open hat", t + 2.5, 70, length=0.5)
        if not busy:
            hit(s, rng, "Rim", t + 1.75, 62)
            if i % 2 == 1:
                hit(s, rng, "Rim", t + 3.75, 58)
    return kicks_at


def bass808(s, kicks_at, bars, start=0):
    starts = sorted(set(round(k, 4) for k in kicks_at if start * 4 <= k < bars * 4))
    for j, t in enumerate(starts):
        nxt = starts[j + 1] if j + 1 < len(starts) else bars * 4
        bar = int(t // 4)
        nxt = min(nxt, (bar + 1) * 4) if s.chord(bar) != s.chord(bar + 1) else nxt
        s.add("808", ROOT808[s.chord(bar)], t, max(0.25, nxt - t - 0.04), 92 if t % 4 == 0 else 84)


# ---- sections -----------------------------------------------------------------------------
def intro(rng):
    s = Sec("Intro", 4, "#2F5F48", VERSE)
    v = DYN["Intro"]
    ostinato(s, rng, v)
    cellos(s, v)
    basses(s, v)
    hit(s, rng, "Timpani", 0, v, 38, 1.5)
    timpani_roll(s, rng, 14, v + 8)                       # into the hook
    return s


def hook(name, rng):
    s = Sec(name, 8, "#3F9E6E", HOOK)
    v = DYN[name]
    ostinato(s, rng, v)
    cellos(s, v)
    horns(s, v)
    theme(s, rng, v)
    hit(s, rng, "Timpani", 0, v + 4, 38, 1.5)
    hit(s, rng, "Timpani", 16, v, 38, 1.5)
    kicks = drums(s, rng, 8, KICKS, busy=True, end="fill" if name != "Hook 3" else None)
    bass808(s, kicks, 8)
    return s


def verse(name, rng, busy):
    s = Sec(name, 16, "#4F7FA8", VERSE)
    v = DYN[name]
    ostinato(s, rng, v - 2)
    cellos(s, v)
    pizz(s, rng, v)
    hit(s, rng, "Timpani", 0, v, 38, 1.5)
    kicks = drums(s, rng, 16, VERSE_KICKS, busy=busy)
    bass808(s, kicks, 16)
    timpani_roll(s, rng, 62, v + 6)
    return s


def bridge(rng):
    """Four bars of strings and horns alone (the beat drops out), then the drums and
    808 come back under them and the timpani rolls into the last hook."""
    s = Sec("Bridge", 8, "#2F5F48", BRIDGE)
    v = DYN["Bridge"]
    ostinato(s, rng, v - 4, bars=4)
    ostinato(s, rng, v, start=4)
    cellos(s, v)
    basses(s, v, bars=4)
    horns(s, v - 2)
    for i in range(8):
        s.add("Violins", BRIDGE_LINE[s.chord(i)], i * 4, 3.9, v + 3 + (2 if i >= 4 else 0))
    kicks = drums(s, rng, 8, VERSE_KICKS, busy=False, start=4)
    bass808(s, kicks, 8, start=4)
    timpani_roll(s, rng, 30, v + 8)
    return s


def outro(rng):
    s = Sec("Outro", 4, "#2F5F48", OUTRO)
    v = DYN["Outro"]
    ostinato(s, rng, v, bars=3)
    cellos(s, v)
    basses(s, v)
    horns(s, v - 4)
    s.add("Violins", 74, 8, 7.9, v + 3)                   # a held D over the last two chords
    s.add("808", ROOT808["Dm"], 12, 3.9, 74)               # the 808 once, under the last D minor
    hit(s, rng, "Timpani", 12, v, 38, 2)
    return s


def compose(seed=76):
    rng = random.Random(seed)
    secs = [intro(rng), hook("Hook 1", rng), verse("Verse 1", rng, False), hook("Hook 2", rng),
            verse("Verse 2", rng, True), bridge(rng), hook("Hook 3", rng), outro(rng)]
    for i, s in enumerate(secs):
        end = s.bars * 4
        level = LEVEL[s.name]
        nxt = LEVEL[secs[i + 1].name] if i + 1 < len(secs) else level
        dyn = DYN[s.name]
        ndyn = DYN[secs[i + 1].name] if i + 1 < len(secs) else dyn
        for ch, notes in s.parts.items():
            for n in notes:
                # ease into the next section over the last two bars (half the step):
                # each section still starts at its own level
                ramp = max(0.0, (n[1] - (end - 8)) / 8)
                if ch in ORCH:
                    n[3] = int(round(min(92, max(52, n[3] + ramp * (ndyn - dyn) * 0.5))))
                else:
                    n[3] = int(round(min(100, max(50, n[3] + level + ramp * (nxt - level) * 0.5))))
                n[1] = round(max(0.0, n[1]), 4)
                n[2] = round(max(0.05, min(n[2], end - n[1])), 4)
    return secs


def check(secs, orch_only=True):
    meds = []
    for s in secs:
        for b in range(s.bars):
            vs = [n[3] for ch, ns in s.parts.items() if (ch in ORCH) == orch_only
                  for n in ns if b * 4 <= n[1] < b * 4 + 4]
            meds.append((s.name, b + 1, statistics.median(vs) if vs else None))
    return sorted(((abs(b[2] - a[2]), a, b) for a, b in zip(meds, meds[1:]) if a[2] and b[2]),
                  reverse=True)


def main(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, root)
    do = argv[1] if len(argv) > 1 else "plan"
    secs = compose()
    if do == "plan":
        bar = 1
        for s in secs:
            ov = [n[3] for ch, ns in s.parts.items() if ch in ORCH for n in ns] or [0]
            print("bars %2d-%2d  %-8s %4d notes  orchestra vel %d-%d  %s" % (
                bar, bar + s.bars - 1, s.name, sum(len(v) for v in s.parts.values()),
                min(ov), max(ov), " ".join(s.prog)))
            bar += s.bars
        print("%d bars, %.2f minutes at %d BPM" % (bar - 1, (bar - 1) * 4 / TEMPO, TEMPO))
        for jump, a, b in check(secs)[:3]:
            print("  orchestra median move %.1f: %s %d -> %s %d" % (jump, a[0], a[1], b[0], b[1]))
        return
    from seeker import link
    from seeker.engine import Engine
    engine = Engine()
    try:
        if do == "build":
            have = {c["name"] for c in engine.status()["channels"]}
            for name, (sound, color, volume, pan) in BAND.items():
                if name in have:
                    continue
                made = engine.add_channel(sound, name, color, volume, pan)
                print(name, "-> channel", made["channel"], "insert", made.get("insert"),
                      made["warnings"], file=sys.stderr, flush=True)
        elif do == "rewrite":
            first = int(os.environ.get("FIRST_PATTERN", "2"))
            parts = argv[2:] or list(BAND)
            for n, sec in enumerate(secs):
                engine._song(pattern=first + n)
                for ch in parts:
                    if not sec.parts.get(ch) and argv[2:]:
                        engine.clear_part(ch)
                        print("pattern %d %s %s cleared" % (first + n, sec.name, ch), flush=True)
                    elif sec.parts.get(ch):
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
