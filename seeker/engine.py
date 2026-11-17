"""Headless Pattern Seeker: the same NEW BEAT / Back the window has, as plain calls.

The tkinter app drives FL with timers so its window never freezes. A server
(the MCP server in mcp_server.py) wants the opposite: one call that blocks until
FL has the beat and returns what happened. This module is that, built on the
same pieces: generator (the music), mapping (which channel plays what), link
(SysEx over loopMIDI to the FL script) and pianoroll (hands-free chord writing).
"""

import time

from seeker import link, pianoroll
from seeker.generator import CYCLE, KEYS, SCALES, Seeker, bass_pitches, chord_notes, pad_notes
from seeker.library import GENRES
from seeker.mapping import build_tracks, map_rack

APPLY_TIMEOUT = 10.0    # a 64-bar pattern takes FL about 3 s to write
ERRORS = {
    "rack_changed": "The channel rack changed mid-request - try again.",
    "busy": "FL Studio is busy (is a dialog open?) - try again.",
}
SETUP_HELP = ("FL Studio isn't answering. In FL: Options > MIDI settings > Input "
              "'Pattern Seeker In': Controller type 'Pattern Seeker', enabled, with a port "
              "number; Output 'Pattern Seeker Out': the same port number. Only one program "
              "can hold the ports, so close the Pattern Seeker window while using this.")


class SeekerError(Exception):
    """Something the caller (a person or an AI) should be told in plain words."""


def genre_list():
    """[(key, display name, (min bpm, max bpm))] sorted by name."""
    return sorted(((k, g["name"], tuple(g["bpm"])) for k, g in GENRES.items()),
                  key=lambda g: g[1])


def resolve_genre(text):
    """'boom bap', 'Boom Bap' or 'boom_bap' -> genre key; None/'auto' -> None."""
    if not text or text.strip().lower() in ("auto", "any", "random"):
        return None
    want = "".join(c for c in text.lower() if c.isalnum())
    for key, name, _ in genre_list():
        if want in ("".join(c for c in key.lower() if c.isalnum()),
                    "".join(c for c in name.lower() if c.isalnum())):
            return key
    raise SeekerError("Unknown genre %r. Known: %s"
                      % (text, ", ".join(n for _, n, _ in genre_list())))


def resolve_key(text):
    """'A', 'a', 'Bb', 'F#' -> index into KEYS."""
    t = (text or "C").strip()
    t = t[:1].upper() + t[1:].lower()
    flats = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}
    t = flats.get(t, t)
    if t not in KEYS:
        raise SeekerError("Unknown key %r. Use one of %s (flats work too)."
                          % (text, ", ".join(KEYS)))
    return KEYS.index(t)


class Engine:
    def __init__(self, seed=None):
        self.seeker = Seeker(seed)
        self.history = []       # (pattern, previous steps, previous piano rolls)
        self.last_rolls = {}    # pattern -> {role: notes we last wrote to its piano roll}
        self.last_beat = None   # summary dict of the most recent beat

    # ---- talking to FL -------------------------------------------------
    def heartbeat(self, wait=3.0):
        """Latest rack snapshot; waits a little on first use while the ports open."""
        deadline = time.time() + wait
        while True:
            hb = link.heartbeat()
            if hb or time.time() > deadline:
                return hb
            time.sleep(0.05)

    def _need_fl(self):
        hb = self.heartbeat()
        if not hb:
            raise SeekerError((link.problem() + ". " if link.problem() else "") + SETUP_HELP)
        if hb.get("version") != link.script_version():
            raise SeekerError("FL is running an older Pattern Seeker script. In FL: View > "
                              "Script output > Pattern Seeker tab > Reload script.")
        return hb

    def _ask(self, req, timeout=1.5):
        request_id = link.send(req)
        deadline = time.time() + timeout
        while time.time() < deadline:
            res = link.response(request_id)
            if res is not None:
                return res
            time.sleep(0.02)
        return None

    def _apply(self, req):
        res = self._ask(req, APPLY_TIMEOUT)
        if res is None:
            raise SeekerError("FL Studio didn't answer in time.")
        if not res.get("ok"):
            raise SeekerError(ERRORS.get(res.get("error"), "FL error: %s"
                                         % (res.get("detail") or res.get("error"))))
        return res

    # ---- status ----------------------------------------------------------
    def status(self):
        hb = self.heartbeat()
        if not hb:
            return {"connected": False,
                    "problem": (link.problem() + ". " if link.problem() else "") + SETUP_HELP}
        rolemap = map_rack(hb["channels"])
        by_index = {ch["index"]: role for role, ch in rolemap.items()}
        return {
            "connected": True,
            "scriptCurrent": hb.get("version") == link.script_version(),
            "pattern": hb["pattern"], "patternName": hb.get("patternName", ""),
            "patternSteps": hb.get("patternSteps", 0),
            "tempo": round(hb["tempo"], 2), "playing": hb.get("playing", False),
            "channels": [dict(ch, role=by_index.get(ch["index"])) for ch in hb["channels"]],
            "canGoBack": bool(self.history),
            "lastBeat": self.last_beat,
        }

    # ---- NEW BEAT ------------------------------------------------------
    def new_beat(self, genre=None, key="C", scale="minor", bass=True, chords=True,
                 pad=True, play=True, set_tempo=False, new_pattern=False):
        hb = self._need_fl()
        genre_key = resolve_genre(genre)
        key_i = resolve_key(key)
        scale = (scale or "minor").strip().lower()
        if scale not in ("minor", "major"):
            raise SeekerError("scale must be 'minor' or 'major'.")
        rolemap = map_rack(hb["channels"])
        # Auto genre stays in the project's tempo unless we may change it.
        beat = self.seeker.next(genre_key, None if (genre_key or set_tempo) else hb["tempo"])
        keys_ch = rolemap.get("chords") if chords else None
        pad_ch = rolemap.get("pad") if pad else None
        # With chords or a pad everything follows one four-bar progression and
        # the 808 plays the root of whichever chord is sounding.
        prog = beat.chords["progs"][scale] if (keys_ch or pad_ch) else None
        lanes, pitches = dict(beat.lanes), None
        if not bass:
            del lanes["bass"]
        elif prog:
            lanes["bass"] = lanes["bass"] * (CYCLE // len(lanes["bass"]))
            pitches = {"bass": bass_pitches(beat.relative * (CYCLE // len(beat.relative)),
                                            key_i, scale, prog=prog)}
        else:
            pitches = {"bass": bass_pitches(beat.degrees, key_i, scale)}
        tracks, missing = build_tracks(lanes, rolemap, pitches)
        if not tracks and not prog:
            raise SeekerError("No drum channels found. Name channels like Kick, Snare, Clap, "
                              "Hat, 808, Piano, Synth and try again.")
        req = {"cmd": "apply", "tracks": tracks, "fill": True, "patternName": beat.name,
               "newPattern": new_pattern, "autoPlay": play,
               "tempo": beat.tempo if set_tempo else None,
               "minSteps": CYCLE if prog else 0}
        steps = 0 if new_pattern else hb.get("patternSteps", 0)
        total = max(CYCLE, ((steps + 15) // 16) * 16)
        rolls = []
        if keys_ch:
            notes = chord_notes(beat.chords["rhythm"], prog, key_i, scale,
                                beat.chords["voicing"])
            rolls.append(("chords", keys_ch, pianoroll.tile(notes, total, CYCLE)))
        elif chords:
            missing = missing + ["chords"]
        if pad_ch:
            rolls.append(("pad", pad_ch, pianoroll.tile(pad_notes(prog, key_i, scale),
                                                        total, CYCLE)))
        elif pad:
            missing = missing + ["pad"]
        if rolls and pianoroll.write_script(rolls[0][2]):
            req["pianoRoll"] = {"channel": rolls[0][1]["index"], "name": rolls[0][1]["name"]}
        else:
            rolls = []

        res = self._apply(req)
        pattern = res["pattern"]
        self.history.append((pattern, res["prev"], self.last_rolls.get(pattern)))
        del self.history[:-50]
        problems = self._run_rolls(rolls) if rolls else []
        if rolls:
            self.last_rolls[pattern] = dict(self.last_rolls.get(pattern, {}),
                                            **{r: n for r, _, n in rolls})
        lanes_by_channel = {}
        for role, ch in rolemap.items():
            if role in lanes or any(r == role for r, _, _ in rolls):
                lanes_by_channel[role] = ch["name"]
        self.last_beat = {
            "genre": beat.genre_name, "tag": beat.tag, "patternName": beat.name,
            "pattern": pattern, "key": "%s %s" % (KEYS[key_i], scale),
            "tempo": beat.tempo if set_tempo else round(hb["tempo"], 2),
            "progression": self._describe(prog, key_i, scale) if prog else None,
            "written": lanes_by_channel,
            "noChannelFor": missing,
            "warnings": list(res.get("warnings") or []) + problems,
        }
        return self.last_beat

    @staticmethod
    def _describe(prog, key, scale):
        """'1111666644445555' in C major -> ['C', 'Am', 'F', 'G'] (one per change),
        with the beats each chord lasts."""
        steps = SCALES[scale]
        out = []
        for ch in prog:
            if out and out[-1][0] == ch:
                out[-1][1] += 1
            else:
                out.append([ch, 1])
        names = []
        for ch, beats in out:
            d = int(ch) - 1
            root = steps[d]
            third = (steps[(d + 2) % 7] - root) % 12
            fifth = (steps[(d + 4) % 7] - root) % 12
            quality = "" if third == 4 else ("dim" if fifth == 6 else "m")
            names.append({"chord": KEYS[(key + root) % 12] + quality, "beats": beats})
        return names

    # ---- Back ------------------------------------------------------------
    def back(self):
        if not self.history:
            raise SeekerError("Nothing to go back to yet.")
        hb = self._need_fl()
        pattern, tracks, old_rolls = self.history[-1]
        if hb["pattern"] != pattern:
            raise SeekerError("Back restores Pattern %s - select it in FL first." % pattern)
        self.history.pop()
        req = {"cmd": "apply", "tracks": tracks, "fill": False}
        rolemap = map_rack(hb["channels"])
        rolls = [(role, rolemap[role], (old_rolls or {}).get(role, []))
                 for role in self.last_rolls.get(pattern, {}) if role in rolemap]
        if rolls and pianoroll.write_script(rolls[0][2]):
            req["pianoRoll"] = {"channel": rolls[0][1]["index"], "name": rolls[0][1]["name"]}
        else:
            rolls = []
        res = self._apply(req)
        problems = self._run_rolls(rolls) if rolls else []
        if rolls:
            self.last_rolls[res["pattern"]] = {r: n for r, _, n in rolls}
        return {"restoredPattern": res["pattern"], "warnings": problems,
                "canGoBack": bool(self.history)}

    # ---- piano rolls (chords, pad) --------------------------------------
    def _run_rolls(self, rolls):
        """Write each roll in turn. The first one's piano roll was already opened by
        the apply request; returns a list of problems ([] = all written)."""
        problems = []
        try:
            for i, (role, channel, notes) in enumerate(rolls):
                if i:
                    if not pianoroll.write_script(notes):
                        problems.append("%s: couldn't write the piano-roll script"
                                        % channel["name"])
                        continue
                    res = self._ask({"cmd": "pianoRoll", "pianoRoll": {
                        "channel": channel["index"], "name": channel["name"]}})
                    if res is None or res.get("pianoRoll"):
                        problems.append("%s: couldn't open the piano roll" % channel["name"])
                        continue
                problem = self._run_script_once()
                if problem:
                    problems.append("%s: %s" % (channel["name"], problem))
        finally:
            link.send({"cmd": "closePianoRoll"})
        return problems

    def _edits(self):
        res = self._ask({"cmd": "edits"}, 0.4)
        return None if res is None else res.get("edits", 0)

    def _run_script_once(self):
        time.sleep(0.12)
        before = self._edits()
        hwnd = None
        for _ in range(10):                 # the window can take a moment
            hwnd = pianoroll.find_piano_roll()
            if hwnd:
                break
            time.sleep(0.06)
        if before is None or hwnd is None:
            return "FL's piano roll didn't open"
        for way in ("menu", "shortcut"):
            pianoroll.bring_forward(hwnd)
            if way == "menu" and not pianoroll.run_from_menu(hwnd):
                continue                    # icon hidden or script not listed
            if way == "shortcut":
                pianoroll.press_run_last_script()
            deadline = time.time() + 1.6
            while time.time() < deadline:
                time.sleep(0.06)
                now = self._edits()
                if now is not None and now > before:
                    return ""
            before = self._edits() or before
        return "the piano-roll script didn't run (is a window covering its top-left corner?)"
