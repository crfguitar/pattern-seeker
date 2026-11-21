"""The hand-written jazz ballad (2026-11-20) that the Jazz Ballad style is built from.

Eb major, 66 BPM, 40 bars: Intro(4) A1(8) A2(8) B(8) A3 + tag ending(12), for a
trio rack (Jazz Kick / Snare / Ride / Rim, Upright Bass, Rhodes). The user's
verdict: "Thats a banger!". A1 is the A2 part with the original bar 8 (Ebmaj9,
Fm9 Bb13 turnaround); the rest is exactly what was written into FL.

Writes one JSON file per section and channel, out/<section>__<channel>.json, as
write_part note lists [pitch, start beat, length in beats, velocity]. Beats count
from 0 at the section start; T is a swung offbeat (the third triplet)."""
import json
import os

T = 2 / 3
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")

V = {  # rootless voicings, moving as little as possible
    "Ebmaj9": [50, 53, 55, 58], "Cm11": [51, 53, 55, 58], "Fm9": [51, 55, 56, 60],
    "Bb13": [50, 55, 56, 60], "Gm9": [53, 57, 58, 62], "C7b9": [52, 55, 58, 61],
    "Abmaj9": [51, 55, 58, 60], "Db9#11": [51, 53, 55, 59], "C7alt": [52, 56, 58, 63],
    "Bb13b9": [50, 55, 56, 59], "Bbm9": [49, 53, 56, 60], "Eb7b9": [49, 52, 55, 58],
    "Abmaj9lo": [48, 51, 55, 58], "Dbm9": [52, 56, 59, 63], "Gb13": [52, 56, 58, 63],
    "Dm7b5": [50, 53, 56, 60], "G7alt": [53, 56, 59, 63], "Cm9": [51, 55, 58, 62],
    "F13": [51, 55, 57, 62], "Bb9sus": [51, 53, 56, 60], "Bb7b9": [50, 55, 56, 59],
    "Cbmaj7#11": [47, 51, 54, 58], "Bb7sus4b9": [51, 53, 56, 59],
    "Ebmaj9#11": [55, 57, 62, 65],
}


def comp(events, lift=0):
    """events: (start, length, chord, velocity)"""
    return [[p, round(s, 4), round(l, 4), min(127, v + lift)]
            for s, l, c, v in events for p in V[c]]


def notes(events, lift=0):
    return [[p, round(s, 4), round(l, 4), min(127, v + lift)] for p, s, l, v in events]


def shift(part, by):
    return [[p, round(s + by, 4), l, v] for p, s, l, v in part]


# ---- A section, bars 1-6 (as in Pattern 1) --------------------------------------
A_COMP_16 = [(0, 1.9, "Ebmaj9", 62), (2, 1.9, "Cm11", 56), (4, 1.6, "Fm9", 60),
             (5 + T, 2.2, "Bb13", 58), (8, 1.9, "Gm9", 62), (10, 1.9, "C7b9", 57),
             (12, 1.6, "Fm9", 60), (13 + T, 2.2, "Bb13", 58), (16, 1.9, "Abmaj9", 64),
             (18, 1.9, "Db9#11", 58), (20, 1.6, "Gm9", 62), (21 + T, 2.2, "C7alt", 60)]
A_MEL_16 = [
    (67, 0, 1.5, 84), (70, 1 + T, 1 / 3, 72), (74, 2, 4 / 3, 88), (72, 3 + 1 / 3, 1 / 3, 70), (70, 3 + T, 1 / 3, 74),
    (68, 4, 5 / 3, 84), (67, 5 + T, 1 / 3, 70), (67, 6, 1, 80), (65, 7, T, 72), (67, 7 + T, 1 / 3, 76),
    (70, 8, 1.5, 86), (74, 9 + T, 1 / 3, 78), (73, 10, 1, 88), (70, 11, T, 76), (67, 11 + T, 1 / 3, 72),
    (68, 12, 2, 84), (67, 14, 1, 76), (68, 15 + 1 / 3, 1 / 3, 70), (70, 15 + T, 1 / 3, 78),
    (72, 16, 1.5, 90), (70, 17 + T, 1 / 3, 74), (67, 18, 4 / 3, 86), (65, 19 + 1 / 3, 1 / 3, 70), (63, 19 + T, 1 / 3, 74),
    (70, 20, T, 80), (74, 20 + T, 1, 86), (77, 21 + T, 1 / 3, 82), (76, 22, T, 90), (75, 22 + T, T, 84),
    (73, 23 + 1 / 3, 1 / 3, 78), (72, 23 + T, 1 / 3, 80)]
A_BASS_16 = [(39, 0, 1.9, 100), (36, 2, 1.4, 92), (40, 3 + T, 0.3, 80),
             (41, 4, 1.9, 98), (34, 6, 1.9, 92),
             (43, 8, 1.9, 98), (36, 10, 1.4, 92), (40, 11 + T, 0.3, 80),
             (41, 12, 1.9, 98), (34, 14, 1.9, 92),
             (32, 16, 1.9, 100), (37, 18, 1.9, 94),
             (43, 20, 1.9, 98), (36, 22, 1.4, 92), (40, 23 + T, 0.3, 80)]
# bar 7 (Fm9 | Bb13b9), shared by A1, A2 and A3
BAR7_COMP = [(24, 1.9, "Fm9", 60), (26, 1.9, "Bb13b9", 56)]
BAR7_MEL = [(72, 24, 1, 86), (68, 25, T, 78), (67, 25 + T, 1 / 3, 72), (71, 26, T, 84),
            (68, 26 + T, T, 76), (65, 27 + 1 / 3, T, 74)]


def ride(bars, quarter=(66, 58, 64, 58), skip=42, start=0):
    out = []
    for bar in range(bars):
        b = start + bar * 4
        for off, v in ((0, quarter[0]), (1, quarter[1]), (1 + T, skip), (2, quarter[2]),
                       (3, quarter[3]), (3 + T, skip)):
            out.append([60, round(b + off, 4), 0.25, v])
    return out


def rim(bars, start=0):
    return [[60, start + bar * 4 + 3, 0.25, 50 if bar % 2 else 44] for bar in range(bars)]


def kick(bars, v1=34, v3=28, start=0):
    out = []
    for bar in range(bars):
        out += [[60, start + bar * 4, 0.25, v1], [60, start + bar * 4 + 2, 0.25, v3]]
    return out


def snare(hits):
    return [[60, round(s, 4), 0.25, v] for s, v in hits]


LIFT = ((30 + 1 / 3, 30), (30 + T, 36), (31, 40), (31 + 1 / 3, 46), (31 + T, 54))
A_GHOSTS = ((6 + T, 26), (14 + 1 / 3, 24), (22 + T, 28))

sections = {}

# ---- Intro: Rhodes and bass, no drums --------------------------------------------
sections["Intro"] = {
    "Rhodes": comp([(0, 3.9, "Abmaj9", 54), (4, 1.9, "Gm9", 52), (6, 1.9, "C7b9", 50),
                    (8, 3.9, "Fm9", 54), (12, 1.9, "Bb9sus", 52), (14, 1.9, "Bb7b9", 50)])
    + notes([(72, 0, 1.5, 72), (70, 1 + T, 1 / 3, 62), (67, 2, 2, 70),
             (74, 4, 1.5, 74), (73, 6, 2, 72),
             (72, 8, 2, 72), (68, 10, 2, 66),
             (75, 12, 4 / 3, 72), (72, 13 + 1 / 3, T, 64), (71, 14, 4 / 3, 70),
             (68, 15 + 1 / 3, 1 / 3, 62), (70, 15 + T, 1 / 3, 68)]),
    "Upright Bass": notes([(44, 0, 3.8, 82), (43, 4, 1.9, 80), (36, 6, 1.9, 78),
                           (41, 8, 3.8, 82), (34, 12, 3.8, 84)]),
}

# ---- A2: A1 with bar 8 turned into a ii-V of Ab (into the bridge) ------------------
sections["A2"] = {
    "Rhodes": comp(A_COMP_16 + BAR7_COMP + [(28, 1.6, "Bbm9", 60), (29 + T, 2.2, "Eb7b9", 60)])
    + notes(A_MEL_16 + BAR7_MEL + [(65, 28, 4 / 3, 82), (63, 29 + 1 / 3, 1 / 3, 70),
                                   (67, 30, T, 84), (64, 30 + T, T, 80), (67, 31 + 1 / 3, T, 84)]),
    "Upright Bass": notes(A_BASS_16 + [(41, 24, 1.9, 98), (34, 26, 1.9, 92),
                                       (34, 28, 1.9, 96), (39, 30, 1.4, 94), (33, 31 + T, 0.3, 82)]),
    "Jazz Ride": ride(8),
    "Jazz Rim": rim(8),
    "Jazz Kick": kick(8),
    "Jazz Snare": snare(A_GHOSTS + ((31, 44), (31 + 1 / 3, 52), (31 + T, 60))),
}

# ---- B: the bridge - higher melody, walking bass, busier ride ---------------------
B_COMP = [(0, 1.9, "Abmaj9lo", 64), (2 + T, 1.2, "Abmaj9lo", 54),
          (4, 1.6, "Dbm9", 62), (5 + T, 2.2, "Gb13", 60),
          (8, 1.9, "Gm9", 62), (10, 1.9, "C7b9", 58),
          (12, 1.6, "Dm7b5", 60), (13 + T, 2.2, "G7alt", 62),
          (16, 1.9, "Cm9", 64), (18 + T, 1.2, "Cm9", 54),
          (20, 1.9, "F13", 62), (22 + T, 1.2, "F13", 54),
          (24, 1.9, "Fm9", 62), (26 + T, 1.2, "Fm9", 52),
          (28, 1.6, "Bb9sus", 60), (29 + T, 2.2, "Bb7b9", 62)]
B_MEL = [(72, 0, T, 88), (75, T, 1 / 3, 80), (79, 1, 5 / 3, 94), (77, 2 + T, 1 / 3, 80), (75, 3, T, 86), (72, 3 + T, 1 / 3, 80),
         (76, 4, 1.5, 92), (75, 5 + T, 4 / 3, 90), (73, 7, T, 84), (70, 7 + T, 1 / 3, 80),
         (74, 8, 1.5, 92), (72, 9 + T, 1 / 3, 80), (70, 10, T, 84), (73, 10 + T, 1, 90), (72, 11 + T, 1 / 3, 80),
         (72, 12, T, 86), (68, 12 + T, T, 82), (65, 13 + 1 / 3, 1 / 3, 76), (71, 13 + T, 1, 92), (70, 14 + T, 1 / 3, 82),
         (68, 15, T, 84), (67, 15 + T, 1 / 3, 80),
         (74, 16, 2, 96), (75, 18 + T, 1 / 3, 84), (74, 19, T, 88), (72, 19 + T, 1 / 3, 82),
         (74, 20, 1.5, 94), (69, 21 + T, 1 / 3, 80), (72, 22, 1, 88), (75, 23, T, 90), (74, 23 + T, 1 / 3, 84),
         (72, 24, 1.5, 90), (68, 25 + T, 1 / 3, 78), (67, 26, 1, 84), (65, 27, T, 78), (67, 27 + T, 1 / 3, 80),
         (68, 28, 4 / 3, 86), (70, 29 + 1 / 3, 1 / 3, 78), (71, 29 + T, 1, 90), (68, 30 + T, T, 82), (65, 31 + 1 / 3, T, 80)]
WALK = [32, 36, 39, 38, 37, 40, 42, 44, 43, 41, 36, 37, 38, 41, 43, 37,
        36, 39, 43, 40, 41, 45, 43, 42, 41, 44, 39, 35, 34, 39, 41, 38]
sections["B"] = {
    "Rhodes": comp(B_COMP) + notes(B_MEL),
    "Upright Bass": [[p, i, 0.85, 98 if i % 2 == 0 else 90] for i, p in enumerate(WALK)],
    "Jazz Ride": ride(8, quarter=(72, 64, 70, 64), skip=50),
    "Jazz Rim": rim(8),
    "Jazz Kick": kick(8, 40, 34),
    "Jazz Snare": snare(((1 + T, 34), (6 + T, 38), (10 + T, 34), (13 + T, 40), (17 + T, 34),
                         (21 + T, 38), (25 + T, 34), (29 + T, 40))
                        + ((30 + 1 / 3, 36), (30 + T, 42), (31, 48), (31 + 1 / 3, 54), (31 + T, 62))),
}

# ---- A3 + tag ending (12 bars) --------------------------------------------------
TAG_COMP = [(28, 1.6, "Gm9", 58), (29 + T, 2.2, "C7alt", 58),
            (32, 1.6, "Fm9", 56), (33 + T, 2.2, "Bb13b9", 54),
            (36, 1.6, "Gm9", 54), (37 + T, 2.2, "C7alt", 54),
            (40, 1.9, "Cbmaj7#11", 52), (42, 1.9, "Bb7sus4b9", 50),
            (44, 3.9, "Ebmaj9#11", 50)]
TAG_MEL = [(70, 28, 4 / 3, 80), (74, 29 + 1 / 3, 1 / 3, 72), (75, 30, 4 / 3, 82), (73, 31 + 1 / 3, T, 76),
           (72, 32, 1.5, 78), (68, 33 + T, 1 / 3, 68), (67, 34, 1, 76), (68, 35, T, 70), (71, 35 + T, 1 / 3, 72),
           (70, 36, 4 / 3, 74), (74, 37 + 1 / 3, T, 70), (76, 38, T, 76), (75, 38 + T, T, 72), (73, 39 + 1 / 3, T, 70),
           (70, 40, 4 / 3, 70), (65, 41 + 1 / 3, T, 62), (68, 42, 1, 66), (71, 43, T, 64), (68, 43 + T, 1 / 3, 60),
           (74, 44, 4 / 3, 66), (69, 45 + 1 / 3, 2.6, 62)]
TAG_BASS = [(43, 28, 1.9, 94), (36, 30, 1.4, 90), (40, 31 + T, 0.3, 78),
            (41, 32, 1.9, 92), (34, 34, 1.4, 88), (44, 35 + T, 0.3, 76),
            (43, 36, 1.9, 90), (36, 38, 1.4, 86), (36, 39 + T, 0.3, 74),
            (35, 40, 1.9, 86), (34, 42, 1.9, 82),
            (39, 44, 3.9, 84)]
sections["A3"] = {
    "Rhodes": comp(A_COMP_16 + BAR7_COMP + TAG_COMP) + notes(A_MEL_16 + BAR7_MEL + TAG_MEL),
    "Upright Bass": notes(A_BASS_16 + [(41, 24, 1.9, 98), (34, 26, 1.4, 92), (44, 27 + T, 0.3, 80)]
                          + TAG_BASS),
    "Jazz Ride": ride(10) + ride(1, quarter=(56, 50, 54, 48), skip=36, start=40)
    + [[60, 44, 0.25, 58]],
    "Jazz Rim": rim(10),
    "Jazz Kick": kick(11) + [[60, 44, 0.25, 40]],
    "Jazz Snare": snare(A_GHOSTS + ((26 + T, 26), (34 + T, 24), (38 + T, 26))),
}

os.makedirs(OUT, exist_ok=True)
for sec, parts in sections.items():
    for ch, part in parts.items():
        assert all(0 <= p <= 127 and s >= 0 and l > 0 for p, s, l, v in part), (sec, ch)
        with open(os.path.join(OUT, "%s__%s.json" % (sec, ch)), "w") as fh:
            json.dump(part, fh)
    ends = {ch: max(s + l for _, s, l, _ in part) for ch, part in parts.items()}
    print(sec, {ch: len(p) for ch, p in parts.items()}, "ends at beat", round(max(ends.values()), 2))
