"""The Pattern Seeker engine: NEW BEAT, Back and status as plain calls.

Both front ends use it: the MCP server (mcp_server.py) and the desktop window
(pattern_seeker.pyw, which runs these calls on a worker thread so it never
freezes). Each call blocks until FL has answered and returns what happened.
Built on generator (the music), mapping (which channel plays what), link (SysEx
over loopMIDI to the FL script) and pianoroll (hands-free chord writing).

Calls are serialised by a lock; `peek` is the one call that never waits, for a
status display that refreshes while a beat is being written.
"""

import functools
import random
import threading
import time

from seeker import ballad, eq, kits, link, pianoroll, playlist, sounds
from seeker.generator import (CYCLE, KEYS, Seeker, add_passing, bass_pitches, chord_name, in_register,
                              chord_notes, pad_notes)
from seeker.library import GENRES
from seeker.mapping import build_tracks, detect_role, fit_rack, map_rack

APPLY_TIMEOUT = 10.0    # a 64-bar pattern takes FL about 3 s to write
LOAD_TIMEOUT = 40.0     # a big VST can take a while to open
ERRORS = {
    "no_plugin": "That channel has no plugin to tweak (it is a sampler or an audio clip).",
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
    def plain(s):
        return "".join(c for c in s.lower() if c.isalnum())

    want = plain(text)
    for key, name, _ in genre_list():
        if want in [plain(n) for n in [key, name] + list(GENRES[key].get("aka", ()))]:
            return key
    raise SeekerError("Unknown genre %r. Known: %s"
                      % (text, ", ".join(n for _, n, _ in genre_list())))


BALLAD_NAMES = {"jazzballad", "ballad", "balladjazz", "jazzballads"}


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


def _locked(method):
    @functools.wraps(method)
    def run(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return run


class Engine:
    def __init__(self, seed=None):
        self._lock = threading.RLock()
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
    def peek(self):
        """(heartbeat or None, problem text) without waiting; None while busy."""
        if not self._lock.acquire(blocking=False):
            return None
        try:
            return link.heartbeat(), link.problem()
        finally:
            self._lock.release()

    @property
    def can_go_back(self):
        return bool(self.history)

    @_locked
    def status(self):
        hb = self.heartbeat()
        if not hb:
            return {"connected": False,
                    "problem": (link.problem() + ". " if link.problem() else "") + SETUP_HELP}
        rolemap = map_rack(hb["channels"])
        by_index = {ch["index"]: role for role, ch in rolemap.items()}
        for ch in hb["channels"]:       # every channel that is some kit's part
            by_index.setdefault(ch["index"], detect_role(ch["name"]))
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
    @_locked
    def new_beat(self, genre=None, key="C", scale="minor", bass=True, chords=True,
                 pad=True, play=True, set_tempo=False, new_pattern=False, tempo=None,
                 passing=False, build=False, guitar=True, drums=True):
        """tempo: an exact BPM to set FL to (wins over set_tempo).
        drums: False leaves the drums out (a breakdown); their channels are emptied.
        passing: end the progression on a passing diminished chord.
        build: first add a channel for every part of the genre's kit the rack lacks."""
        hb = self._need_fl()
        if tempo is not None:
            try:
                tempo = float(tempo)
            except (TypeError, ValueError):
                raise SeekerError("tempo must be a number of BPM, like 90.")
            if not 10 <= tempo <= 522:
                raise SeekerError("tempo must be between 10 and 522 BPM (FL's range).")
        genre_key = resolve_genre(genre)
        key_i = resolve_key(key)
        scale = (scale or "minor").strip().lower()
        if scale not in ("minor", "major"):
            raise SeekerError("scale must be 'minor' or 'major'.")
        # Auto genre stays in the project's tempo unless we may change it.
        # An exact tempo is always used, and steers an auto genre to one that fits it.
        if tempo is not None:
            beat = self.seeker.next(genre_key, tempo)
            beat.tempo, set_tempo = tempo, True
        else:
            beat = self.seeker.next(genre_key, None if (genre_key or set_tempo) else hb["tempo"])
        built = None
        if build:
            skip = [r for r, on in (("bass", bass), ("chords", chords), ("pad", pad),
                                    ("guitar", guitar)) if not on]
            built = self.build_rack(beat.genre, [r for r in kits.ROLES if r not in skip])
            hb = self._settled_rack(len(hb["channels"]) + len(built["added"]))
        # Only channels whose sound suits the genre play; other kits' drums and
        # basses are silenced in this pattern (`idle`).
        rolemap, idle = fit_rack(hb["channels"], beat.genre, strict=bool(build))
        wanted = [r for r in kits.parts(beat.genre) if r not in kits.optional(beat.genre)]
        keys_ch = rolemap.get("chords") if chords else None
        pad_ch = rolemap.get("pad") if pad else None
        guitar_ch = rolemap.get("guitar") if (guitar and beat.guitar) else None
        # With chords, a pad or a guitar everything follows one four-bar progression
        # and the 808 plays the root of whichever chord is sounding.
        prog = beat.chords["progs"][scale] if (keys_ch or pad_ch or guitar_ch) else None
        if prog and passing:
            prog = add_passing(prog)
        lanes, pitches = dict(beat.lanes), None
        # An upright or a bass guitar is written in its own register, two octaves
        # under the 808's, and no note leaves it.
        register = kits.bass_range(rolemap["bass"]["name"]) if "bass" in rolemap else None
        base = 36 if register else 60
        if not drums:
            lanes.update({r: [0] * len(v) for r, v in lanes.items() if r != "bass"})
        if not bass:
            del lanes["bass"]
        elif prog:
            lanes["bass"] = lanes["bass"] * (CYCLE // len(lanes["bass"]))
            pitches = {"bass": bass_pitches(beat.relative * (CYCLE // len(beat.relative)),
                                            key_i, scale, base, prog=prog)}
        else:
            pitches = {"bass": bass_pitches(beat.degrees, key_i, scale, base)}
        if pitches and register:
            pitches["bass"] = in_register(pitches["bass"], *register)
        tracks, missing = build_tracks(lanes, rolemap, pitches)
        if not tracks and not prog:
            raise SeekerError("No channel in the rack suits %s. Call new_beat with build=true "
                              "(or build_rack) to add its instruments, or name channels like "
                              "Kick, Snare, Hat, Bass, Piano, Pad." % beat.genre_name)
        for ch in idle:
            if bass or detect_role(ch["name"]) != "bass":   # bass off: basses are left alone
                tracks.append({"channel": ch["index"], "name": ch["name"], "role": "idle",
                               "bits": [], "vel": []})
        req = {"cmd": "apply", "tracks": tracks, "fill": True, "patternName": beat.name,
               "newPattern": new_pattern, "autoPlay": play,
               "tempo": beat.tempo if set_tempo else None,
               "minSteps": CYCLE if prog else 0}
        steps = 0 if new_pattern else hb.get("patternSteps", 0)
        total = max(CYCLE, ((steps + 15) // 16) * 16)
        rolls, played = [], {}      # played: part -> the channel it went to
        if keys_ch:
            notes = chord_notes(beat.chords["rhythm"], prog, key_i, scale,
                                beat.chords["voicing"])
            rolls.append((self._roll_key(keys_ch), keys_ch, pianoroll.tile(notes, total, CYCLE)))
            played["chords"] = keys_ch["name"]
        elif chords:
            missing = missing + ["chords"]
        if pad_ch:
            rolls.append((self._roll_key(pad_ch), pad_ch,
                          pianoroll.tile(pad_notes(prog, key_i, scale), total, CYCLE)))
            played["pad"] = pad_ch["name"]
        elif pad and "pad" in wanted:           # jazz, country: no pad to miss
            missing = missing + ["pad"]
        if guitar_ch:
            notes = chord_notes(beat.guitar["rhythm"], prog, key_i, scale,
                                beat.guitar["voicing"], beat.guitar["base"])
            rolls.append((self._roll_key(guitar_ch), guitar_ch,
                          pianoroll.tile(notes, total, CYCLE)))
            played["guitar"] = guitar_ch["name"]
        elif guitar and beat.guitar and "guitar" in wanted:
            missing = missing + ["guitar"]
        missing = [r for r in missing if r in wanted or r in ("chords",)]
        if not new_pattern:
            # Keys, pads and guitars of another kit that we wrote into this pattern
            # earlier are emptied, so only this beat's instruments play.
            now = {key for key, _, _ in rolls}
            by_key = {self._roll_key(ch): ch for ch in hb["channels"]}
            for key in self.last_rolls.get(hb["pattern"], {}):
                if key.startswith("part:") and key not in now and key in by_key:
                    rolls.append((key, by_key[key], []))
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
            kept = dict(self.last_rolls.get(pattern, {}), **{k: n for k, _, n in rolls})
            self.last_rolls[pattern] = {k: n for k, n in kept.items() if n}
        lanes_by_channel = {}
        for role, ch in rolemap.items():
            # a lane that sits out (classical has no drums) only clears its channel
            if role in kits.STEP_ROLES and any(lanes.get(role) or ()):
                lanes_by_channel[role] = ch["name"]
        lanes_by_channel.update(played)
        self.last_beat = {
            "genre": beat.genre_name, "tag": beat.tag, "patternName": beat.name,
            "pattern": pattern, "key": "%s %s" % (KEYS[key_i], scale),
            "tempo": beat.tempo if set_tempo else round(hb["tempo"], 2),
            "progression": self._describe(prog, key_i, scale) if prog else None,
            "written": lanes_by_channel,
            "noChannelFor": missing,
            "warnings": list(res.get("warnings") or []),
            "problems": problems,     # piano rolls that couldn't be written
        }
        if built:
            self.last_beat["built"] = built
        return self.last_beat

    @staticmethod
    def _roll_key(channel):
        """How a beat's piano-roll part is remembered: by the channel it is on."""
        return "part:%d:%s" % (channel["index"], channel["name"])

    @staticmethod
    def _describe(prog, key, scale):
        """'1111666644445555' in C major -> ['C', 'Am', 'F', 'G'] (one per change),
        with the beats each chord lasts."""
        out = []
        for ch in prog:
            if out and out[-1][0] == ch:
                out[-1][1] += 1
            else:
                out.append([ch, 1])
        return [{"chord": chord_name(ch, prog, key, scale), "beats": beats} for ch, beats in out]

    # ---- free notes on any channel (solos, melodies) ----------------------
    MAX_PART_NOTES = 2000

    @_locked
    def write_part(self, channel, notes):
        """Write `notes` - [pitch, start beat, length in beats, velocity 1-127], with
        beats counted from 0 at the pattern start and any fraction allowed - into the
        piano roll of `channel` (its rack index from status, or its name). Replaces
        what an earlier write_part put there; anything else in that roll is kept."""
        hb = self._need_fl()
        target = self._find_channel(hb["channels"], channel)
        if not isinstance(notes, (list, tuple)) or not notes:
            raise SeekerError("notes must be a non-empty list of "
                              "[pitch, start beat, length in beats, velocity].")
        if len(notes) > self.MAX_PART_NOTES:
            raise SeekerError("At most %d notes at a time." % self.MAX_PART_NOTES)
        steps = []
        for i, n in enumerate(notes):
            try:
                pitch, start, length = int(n[0]), float(n[1]), float(n[2])
                vel = int(n[3]) if len(n) > 3 else 100
            except (TypeError, ValueError, IndexError):
                raise SeekerError("note %d (%r) should be [pitch, start beat, length in "
                                  "beats, velocity]." % (i, n))
            if not 0 <= pitch <= 127:
                raise SeekerError("note %d: pitch %d is outside 0-127." % (i, pitch))
            if start < 0 or length <= 0 or start * 4 >= pianoroll.MAX_STEPS:
                raise SeekerError("note %d: start must be >= 0 (and under %d beats) and "
                                  "length > 0." % (i, pianoroll.MAX_STEPS // 4))
            steps.append((pitch, start * 4, length * 4, max(1, min(127, vel))))
        if not pianoroll.write_script(steps):
            raise SeekerError("Couldn't write the piano-roll script (FL's Settings "
                              "folder is missing).")
        res = self._ask({"cmd": "pianoRoll", "pianoRoll": {
            "channel": target["index"], "name": target["name"]}})
        if res is None:
            link.send({"cmd": "closePianoRoll"})
            raise SeekerError("FL Studio didn't answer in time.")
        if res.get("pianoRoll"):
            link.send({"cmd": "closePianoRoll"})
            raise SeekerError(ERRORS.get(res["pianoRoll"], "Couldn't open the piano roll: %s"
                                         % res["pianoRoll"]))
        pattern = hb["pattern"]
        role = "ch:%d:%s" % (target["index"], target["name"])
        self.history.append((pattern, [], self.last_rolls.get(pattern)))
        del self.history[:-50]
        problems = self._run_rolls([(role, target, steps)])
        self.last_rolls[pattern] = dict(self.last_rolls.get(pattern, {}), **{role: steps})
        end = max(s + l for _, s, l, _ in steps) / 4.0
        return {"channel": target["name"], "pattern": pattern, "notes": len(steps),
                "beats": round(end, 3), "problems": problems,
                "canGoBack": bool(self.history)}

    @staticmethod
    def _find_channel(rack, channel):
        if isinstance(channel, str):
            want = channel.strip().lower()
            for ch in rack:             # a name wins: "808" is a channel, not index 808
                if ch["name"].lower() == want:
                    return ch
            if want.lstrip("-").isdigit():
                channel = int(want)
        if isinstance(channel, int) and not isinstance(channel, bool):
            for ch in rack:
                if ch["index"] == channel:
                    return ch
        elif isinstance(channel, str):
            want = channel.strip().lower()
            for ch in rack:
                if ch["name"].lower() == want:
                    return ch
        raise SeekerError("No channel %r. The rack has: %s" % (channel, ", ".join(
            "%d %s" % (ch["index"], ch["name"]) for ch in rack)))

    # ---- a whole rack for a genre -------------------------------------------
    @_locked
    def build_rack(self, genre, parts=None):
        """Add a channel for each part of `genre`'s kit (kits.py) that the rack has
        no channel for yet: drums, bass, keys, pad. Parts already there are kept."""
        genre_key = resolve_genre(genre)
        if not genre_key:
            raise SeekerError("build_rack needs a genre: %s"
                              % ", ".join(n for _, n, _ in genre_list()))
        wanted = self._parts(parts)
        hb = self._need_fl()
        # strict: a part counts as there only when its channel has the genre's own
        # kind of sound (or a plain name) - an 808 is no cello.
        have, _ = fit_rack(hb["channels"], genre_key, strict=True)
        out = {"genre": GENRES[genre_key]["name"], "added": [], "problems": [],
               "kept": {r: have[r]["name"] for r in wanted if r in have}}
        spec = kits.parts(genre_key)
        for role in wanted:
            # not in spec: the genre has no such part. optional: played, never built.
            if role in have or role not in spec or role in kits.optional(genre_key):
                continue
            choices = list(spec[role])
            self.seeker.rng.shuffle(choices)
            pick = None
            for sound in choices:
                installed = []
                for option in sound.options:
                    try:
                        sounds.resolve(option)
                        installed.append(option)
                    except sounds.SoundError:
                        pass                # not on this PC
                if installed:               # options are listed best first
                    pick = sound, self.seeker.rng.choice(installed[:3])
                    break
            if not pick:
                out["problems"].append("%s: none of its sounds are on this PC" % role)
                continue
            sound, option = pick
            _, color, volume = kits.CHANNELS[role]
            try:
                made = self.add_channel(option, name=sound.name, color=color, volume=volume)
            except SeekerError as e:        # FL itself is in the way: stop here
                out["problems"].append("%s: %s" % (role, e))
                return out
            out["added"].append({"part": role, "channel": made["channel"],
                                 "name": made["name"], "sound": made["sound"],
                                 "insert": made.get("insert")})
            out["problems"] += ["%s: %s" % (made["name"], w) for w in made["warnings"]
                                if w.startswith("not routed")]
        return out

    @staticmethod
    def _parts(parts):
        """['drums', 'pad'] -> the roles to build, in rack order; None = all."""
        if not parts:
            return list(kits.ROLES)
        drums = list(kits.DRUM_ROLES)
        alias = {"drums": drums, "keys": ["chords"], "piano": ["chords"], "808": ["bass"],
                 "open hat": ["openhat"], "hats": ["hat", "openhat"], "strings": ["pad"]}
        chosen = set()
        for part in parts:
            key = str(part).strip().lower()
            if key not in alias and key not in kits.ROLES:
                raise SeekerError("Unknown part %r. Use: drums, %s."
                                  % (part, ", ".join(kits.ROLES)))
            chosen.update(alias.get(key, [key]))
        return [r for r in kits.ROLES if r in chosen]

    def _settled_rack(self, channels, wait=3.0):
        """The heartbeat once it shows `channels` channels (it trails FL by a second)."""
        deadline = time.time() + wait
        while True:
            hb = self._need_fl()
            if len(hb["channels"]) >= channels or time.time() > deadline:
                return hb
            time.sleep(0.1)

    # ---- new channels, and shaping the ones there ---------------------------
    @_locked
    def list_sounds(self, search="", kind="all", limit=40):
        """Instruments and samples that can be loaded: {total, sounds: [{kind, id}]}."""
        try:
            found = sounds.search(search, kind)
        except sounds.SoundError as e:
            raise SeekerError(str(e))
        limit = max(1, min(int(limit or 40), 500))
        return {"total": len(found), "shown": min(limit, len(found)),
                "sounds": [{"kind": it["kind"], "id": it["id"]} for it in found[:limit]]}

    @_locked
    def add_channel(self, sound, name=None, color=None, volume=None, pan=None, show=False,
                    route=True):
        """Load an instrument or a sample into a NEW channel at the end of the rack.

        FL itself opens the file (see sounds.py); we watch the rack for the channel
        to appear, then name and colour it and close the plugin window it opened.
        route: send it through its own mixer insert, named after it (route_channels)."""
        hb = self._need_fl()
        change = self._channel_change(name, color, volume, pan)
        try:
            item = sounds.resolve(sound)
            before = [ch["name"] for ch in hb["channels"]]
            sounds.open_in_fl(item, change.get("name"))
        except sounds.SoundError as e:
            raise SeekerError(str(e))
        deadline, rack = time.time() + LOAD_TIMEOUT, None
        while time.time() < deadline:
            now = link.heartbeat()
            if now and len(now["channels"]) > len(before):
                rack = now["channels"]
                break
            time.sleep(0.1)
        if rack is None:
            raise SeekerError("FL Studio didn't add a channel for %s within %d s (is a "
                              "dialog open in FL?)." % (item["id"], LOAD_TIMEOUT))
        new = rack[-1]      # FL appends; if the rack was reordered, find the newcomer
        for i, ch in enumerate(rack):
            if i >= len(before) or ch["name"] != before[i]:
                new = ch
                break
        if item.get("flex"):
            # The preset file carries neutral knobs. One preset on and back again
            # makes FLEX load the preset's own.
            ident = {"channel": new["index"], "name": new["name"]}
            for step in (1, -1):
                self._apply(dict(ident, cmd="plugin", presetStep=step, limit=0))
                self._preset_now(ident, wait=6.0)
        res = self._apply({"cmd": "channel", "channel": new["index"], "name": new["name"],
                           "set": change, "editor": bool(show)})
        info = res["channel"]
        rack_now = (res.get("state") or {}).get("channels") or []
        roles = {ch["index"]: role for role, ch in map_rack(rack_now).items()}
        out = {"channel": info["index"], "name": info["name"], "plugin": info.get("plugin", ""),
               "sound": item["id"], "kind": item["kind"], "role": roles.get(info["index"]),
               "warnings": list(res.get("warnings") or [])}
        if route:
            try:
                done = self._route([dict(c, **info) if c["index"] == info["index"] else c
                                    for c in rack_now] or [info], [info["index"]])
                if done["routed"]:
                    out["insert"] = done["routed"][0]["insert"]
                out["warnings"] += done["warnings"]
            except SeekerError as e:
                out["warnings"].append("not routed to a mixer insert: %s" % e)
        return out

    # ---- EQ on the mixer inserts (CFilteR-01) ---------------------------------
    @_locked
    def eq(self, channel, bands, clear=True):
        """Set CFilteR-01 on `channel`'s mixer insert: bands in real units
        ([{shape, freq, gain, q, slope, band?, on?}]). clear: every other band off."""
        hb = self._need_fl()
        return self._eq_channel(self._find_channel(hb["channels"], channel), bands, clear)

    @_locked
    def mix_eq(self, genre, clear=True):
        """Give every part the genre's starting EQ (kits.eq_for) on its insert."""
        hb = self._need_fl()
        genre_key = resolve_genre(genre)
        if genre_key is None:
            raise SeekerError("mix_eq needs a genre (the EQ suits the genre's sounds).")
        rolemap, _ = fit_rack(hb["channels"], genre_key)
        out = {"genre": GENRES[genre_key]["name"], "channels": [], "problems": []}
        for role in kits.ROLES:
            ch = rolemap.get(role)
            bands = kits.eq_for(genre_key, role) if ch else []
            if not bands:
                continue
            try:
                done = self._eq_channel(ch, bands, clear)
                out["channels"].append(dict(done, part=role))
            except SeekerError as e:
                out["problems"].append("%s: %s" % (ch["name"], e))
        return out

    def _eq_channel(self, ch, bands, clear):
        if not isinstance(bands, (list, tuple)):
            raise SeekerError("bands must be a list like [{\"shape\": \"low cut\", "
                              "\"freq\": 40}].")
        insert = ch.get("insert")
        if not insert:
            raise SeekerError("%s plays straight into the master; route_channels gives it "
                              "an insert first." % ch["name"])
        res = self._apply({"cmd": "mixer", "track": insert, "slots": True})
        slot = next((s for s, name, _ in res.get("slots", [])
                     if eq.PLUGIN.lower() in name.lower()), None)
        if slot is None:
            raise SeekerError("No %s on insert %d (%s). Put one in a slot of that insert."
                              % (eq.PLUGIN, insert, res.get("trackName", "")))
        try:
            rows, used = eq.band_sets(slot, bands)
        except eq.EqError as e:
            raise SeekerError(str(e))
        clears = eq.clear_sets(slot, used) if clear else []
        self._apply({"cmd": "mixer", "track": insert, "set": rows + clears})
        # FL hands a VST's new value back one request late: setting the same values
        # again returns what the plugin now holds, in its own words.
        back = self._apply({"cmd": "mixer", "track": insert, "set": rows})
        got = back.get("set", [])
        warnings = list(back.get("warnings") or [])
        # Seen live: a band read back at its old value, and (2026-11-20, a freshly
        # loaded CFilteR-01) FL's value said a setting took while the plugin's own
        # text showed it hadn't. So a setting counts as set only when both agree.
        wanted = {r[1]: r[2] for r in rows}
        for attempt in range(4):
            bad_text = eq.misread(bands, got)
            off = [r for r in rows
                   if r[1] in bad_text
                   or not any(g[1] == r[1] and abs(g[3] - wanted[r[1]]) < 1e-3 for g in got)]
            if not off:
                break
            if attempt == 3:
                warnings.append("%d settings didn't take on %s: %s. Run eq again, or set "
                                "them by hand." % (len(off), eq.PLUGIN, ", ".join(
                                    g[2] for g in got if g[1] in {r[1] for r in off})))
                break
            # send the whole of each band that's off: its parameters depend on each other
            redo = {r[1] // eq.PARAMS_PER_BAND for r in off}
            again_rows = [r for r in rows if r[1] // eq.PARAMS_PER_BAND in redo]
            self._apply({"cmd": "mixer", "track": insert, "set": again_rows})
            again = self._apply({"cmd": "mixer", "track": insert, "set": again_rows})
            fixed = {g[1]: g for g in again.get("set", [])}
            got = [fixed.get(g[1], g) for g in got]
        shown = eq.describe(got)
        return {"channel": ch["name"], "insert": insert, "insertName": res.get("trackName"),
                "slot": slot + 1, "bands": [shown.get("Band %d" % n, "") for n in sorted(used)],
                "warnings": warnings}

    # ---- mixer routing ------------------------------------------------------
    MIXER_INSERTS = 125     # FL 2026: inserts 1-125 (0 is the master)

    @_locked
    def route_channels(self, channels=None, reroute=False):
        """Give channels their own mixer insert, named and coloured after the channel.

        channels: rack indexes or names; default every channel still going straight
        to the master. reroute: also move channels that already have an insert."""
        hb = self._need_fl()
        rack = hb["channels"]
        if channels:
            picked = [self._find_channel(rack, c)["index"] for c in channels]
        else:
            picked = [c["index"] for c in rack]
        if not reroute:
            picked = [i for i in picked if not rack[i].get("insert")]
        if not picked:
            return {"routed": [], "kept": [{"channel": c["name"], "insert": c.get("insert")}
                                           for c in rack if c.get("insert")], "warnings": []}
        return self._route(rack, picked)

    def _route(self, rack, picked):
        """Route rack channels `picked` (indexes) to free inserts.

        An insert is taken when a channel already plays through it or the user gave
        it a name. Each channel gets, in order of preference: a free-standing insert
        named like it (a template's labelled insert), insert N for rack index N, then
        the lowest free insert."""
        res = self._ask({"cmd": "mixer", "names": self.MIXER_INSERTS}, timeout=4.0)
        if res is None or "names" not in res:
            raise SeekerError("FL Studio didn't list its mixer inserts (reload the Pattern "
                              "Seeker script in FL: it needs version 16 or newer).")
        names = res["names"]
        by_index = {c["index"]: c for c in rack}
        routed_to = {c.get("insert") for c in rack if c["index"] not in picked} - {0, None}
        named = {t for t, n in enumerate(names, 1) if n.strip() != "Insert %d" % t}
        taken = set(routed_to)
        spots = {}
        # 1: a labelled insert nobody plays through, waiting for this channel
        for i in picked:
            want = by_index[i]["name"].strip().lower()
            spot = next((t for t, n in enumerate(names, 1)
                         if n.strip().lower() == want and t not in taken), None)
            if spot is not None:
                spots[i] = spot
                taken.add(spot)

        def free(t):
            return 1 <= t <= len(names) and t not in taken and t not in named
        # 2: insert N for rack index N. A project starts with FL's Sampler at index
        #    0, so the first instrument added lands on insert 1 (the user's way).
        for i in picked:
            if i not in spots and free(i):
                spots[i] = i
                taken.add(i)
        # 3: the lowest free insert
        for i in picked:
            if i not in spots:
                spot = next((t for t in range(1, len(names) + 1) if free(t)), None)
                if spot is None:
                    raise SeekerError("Every mixer insert is in use or named.")
                spots[i] = spot
                taken.add(spot)
        routes, out = [], []
        for i in picked:
            ch = by_index[i]
            routes.append([i, spots[i], ch["name"], ch.get("color")])
        res = self._apply({"cmd": "mixer", "routes": routes})
        for ch_i, insert, label in res.get("routes", []):
            out.append({"channel": by_index[ch_i]["name"], "index": ch_i, "insert": insert,
                        "insertName": label})
        return {"routed": out, "warnings": list(res.get("warnings") or [])}

    @staticmethod
    def _channel_change(name, color, volume, pan):
        change = {}
        if name is not None and str(name).strip():
            change["name"] = str(name).strip()
        if color is not None and str(color).strip():
            text = str(color).strip().lstrip("#")
            try:
                if len(text) != 6:
                    raise ValueError
                change["color"] = int(text, 16)
            except ValueError:
                raise SeekerError("color must look like #RRGGBB, e.g. #E0782F.")
        for key, value, lo in (("volume", volume, 0.0), ("pan", pan, -1.0)):
            if value is not None:
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    value = None
                if value is None or not lo <= value <= 1.0:
                    raise SeekerError("%s must be a number from %g to 1." % (key, lo))
                change[key] = value
        return change

    @_locked
    def set_channel(self, channel, name=None, color=None, volume=None, pan=None,
                    params=None, preset=0, preset_name=None, show=None):
        """Rename / recolour / set level and pan of a channel, load one of its
        plugin's presets (by name, or stepping: +1 next, -1 previous) and set
        plugin parameters: params = {parameter name or index: value from 0 to 1}."""
        hb = self._need_fl()
        target = self._find_channel(hb["channels"], channel)
        change = self._channel_change(name, color, volume, pan)
        pairs = []
        for key, value in (params or {}).items():
            try:
                value = float(value)
            except (TypeError, ValueError):
                raise SeekerError("parameter %r needs a number from 0 to 1." % key)
            if not 0.0 <= value <= 1.0:
                raise SeekerError("parameter %r: %g is outside 0 to 1 (every plugin "
                                  "parameter runs from 0 to 1)." % (key, value))
            text = str(key).strip()
            pairs.append([int(text) if text.isdigit() else text, value])
        try:
            preset = int(preset or 0)
        except (TypeError, ValueError):
            raise SeekerError("preset is a number of steps: 1 = next, -1 = previous.")
        preset_name = (preset_name or "").strip()
        if not (change or pairs or preset or preset_name or show is not None):
            raise SeekerError("Nothing to change: give a name, color, volume, pan, "
                              "params, preset, preset_name or show.")
        out = {"warnings": []}
        ident = {"channel": target["index"], "name": target["name"]}
        info = None
        if preset or preset_name:
            res, now = self._load_preset(ident, preset, preset_name)
            out["presetCount"] = (res.get("presets") or {}).get("presetCount", 0)
            if now:
                out["preset"] = now["preset"]
            out["warnings"] += res.get("warnings") or []
            info = res["channel"]
        if pairs:
            res = self._apply(dict(ident, cmd="plugin", set=pairs, limit=0))
            out.update(unknownParams=res.get("unknown", []),
                       changed=[self._param(p) for p in res.get("changed", [])])
            out["warnings"] += res.get("warnings") or []
            info = res["channel"]
        if change or show is not None:
            res = self._apply(dict(ident, cmd="channel", set=change,
                                   editor=None if show is None else bool(show)))
            out["warnings"] += res.get("warnings") or []
            info = res["channel"]
        return dict(self._channel(info), **out)

    def _load_preset(self, ident, steps, wanted):
        """Step `steps` presets on, or go to the one named `wanted`. Returns FL's
        last answer and {preset, presetIndex} (None when FL didn't show which)."""
        if wanted:
            listing = self._apply(dict(ident, cmd="plugin", presets=True, limit=0))
            names = (listing.get("presets") or {}).get("presets") or []
            want = wanted.lower()
            hits = [i for i, n in enumerate(names) if n.strip().lower() == want] \
                or [i for i, n in enumerate(names) if want in n.lower()]
            if not hits:
                raise SeekerError("No preset named %r on %s (it has %d; list them with "
                                  "channel_params presets=true)."
                                  % (wanted, ident["name"], len(names)))
            if len(hits) > 1:
                raise SeekerError("%d presets match %r: %s%s" % (
                    len(hits), wanted, ", ".join(names[i] for i in hits[:8]),
                    " ..." if len(hits) > 8 else ""))
            # FL can't say which preset is loaded until one is stepped to: step
            # once, see where that landed, then take the short way round.
            res = self._apply(dict(ident, cmd="plugin", presetStep=1, limit=0))
            now = self._preset_now(ident)
            if now is None:
                self._ask(dict(ident, cmd="plugin", presetStep=-1, limit=0))    # undo the look
                raise SeekerError("%s doesn't show which preset is loaded, so %r can't be "
                                  "found by name. Step with preset=1 / -1, or add a new "
                                  "channel from its preset file (list_sounds %r)."
                                  % (ident["name"], wanted, wanted))
            ahead = (hits[0] - now["presetIndex"]) % len(names)
            steps = ahead if ahead <= len(names) - ahead else ahead - len(names)
            if not steps:
                return res, now
            res = self._apply(dict(ident, cmd="plugin", presetStep=steps, limit=0))
            return res, self._preset_now(ident, expect=hits[0])
        res = self._apply(dict(ident, cmd="plugin", presetStep=steps, limit=0))
        return res, self._preset_now(ident)

    def _preset_now(self, ident, expect=None, wait=2.5):
        """The preset FL's hint bar names, once it does (it trails the step a little)."""
        deadline = time.time() + wait
        while True:
            res = self._ask(dict(ident, cmd="plugin", presetAt=True, limit=0))
            now = ((res or {}).get("presets") or {})
            if "presetIndex" in now and expect in (None, now["presetIndex"]):
                return now
            if time.time() > deadline:
                return None
            time.sleep(0.1)

    @staticmethod
    def _param(row):
        out = {"index": row[0], "name": row[1], "value": row[2]}
        if len(row) > 3:
            out["shows"] = row[3]
        return out

    @staticmethod
    def _channel(info):
        out = {"channel": info["index"], "name": info["name"], "plugin": info.get("plugin", "")}
        if "color" in info:
            out["color"] = "#%06X" % info["color"]
        for key in ("volume", "pan"):
            if key in info:
                out[key] = info[key]
        return out

    @_locked
    def channel_params(self, channel, search="", limit=60, presets=False):
        """A channel's level, pan, colour and - for a plugin - the parameters whose
        name contains `search`, and with `presets` the names of its presets."""
        hb = self._need_fl()
        target = self._find_channel(hb["channels"], channel)
        ident = {"channel": target["index"], "name": target["name"]}
        if not target.get("plugin"):
            res = self._apply(dict(ident, cmd="channel"))
            return dict(self._channel(res["channel"]), params=[], paramCount=0,
                        note="A sampler: only name, color, volume and pan can be set.")
        res = self._apply(dict(ident, cmd="plugin", find=search or "", presets=bool(presets),
                               limit=max(1, min(int(limit or 60), 120))))
        return dict(self._channel(res["channel"]), **dict(
            res.get("presets") or {},
            paramCount=res.get("paramCount", 0), matching=res.get("matching", 0),
                    params=[self._param(p) for p in res.get("params", [])]))

    # ---- the song: patterns laid out in the playlist ------------------------
    # What each letter of a song structure is, and how it differs from the rest.
    SECTIONS = {
        "A": ("Verse", 0x4C8BF5, {"pad": False}),       # leaner: no pad
        "B": ("Chorus", 0xF5A623, {}),                  # everything
        "C": ("Bridge", 0x9B59B6, {"drums": False}),    # a breakdown: no drums
    }
    MAX_CLIPS = 200

    def _song(self, **fields):
        res = self._ask(dict(fields, cmd="song"), 4.0)
        if res is None:
            raise SeekerError("FL Studio didn't answer in time.")
        if not res.get("ok"):
            raise SeekerError("FL error: %s" % (res.get("detail") or res.get("error")))
        return res

    @_locked
    def arrange(self, sections, track=1, start_bar=None, song_mode=True):
        """Lay patterns out along a playlist track, one section after another.

        sections: pattern numbers, or {"pattern": n, "bars": 8}; a pattern
        shorter than its section is repeated to fill it. start_bar: where the
        first one starts; None = where the song ends now (bar 1 when empty)."""
        self._need_fl()
        wanted = []
        for item in sections or []:
            if isinstance(item, dict):
                item = (item.get("pattern"), item.get("bars"))
            elif not isinstance(item, (list, tuple)):
                item = (item, None)
            try:
                pattern = int(item[0])
                bars = int(item[1]) if len(item) > 1 and item[1] else None
            except (TypeError, ValueError):
                raise SeekerError("sections must be pattern numbers, or "
                                  '{"pattern": 2, "bars": 8}.')
            if pattern < 1 or (bars is not None and bars < 1):
                raise SeekerError("Pattern numbers and bars start at 1.")
            wanted.append((pattern, bars))
        if not wanted:
            raise SeekerError("Give at least one pattern to place.")
        try:
            track = int(track)
            start_bar = None if start_bar is None else int(start_bar)
        except (TypeError, ValueError):
            raise SeekerError("track and start_bar must be whole numbers.")
        if start_bar is not None and start_bar < 1:
            raise SeekerError("Bars are counted from 1.")
        info = self._song(lengths=[p for p, _ in wanted])
        per_bar = int(info["ticksPerBar"])
        steps_per_bar = max(1, per_bar * 4 // int(info["ppq"]))
        before = int(info.get("songTicks") or 0)
        bar = start_bar or (before + 1) // per_bar + 1
        first, clips, laid = bar, [], []
        for (pattern, bars), steps in zip(wanted, info["lengths"]):
            length = max(1, -(-int(steps) // steps_per_bar))
            count = -(-(bars or length) // length)
            laid.append({"pattern": pattern, "bar": bar, "bars": count * length,
                         "clips": count})
            for _ in range(count):
                clips.append((pattern, bar))
                bar += length
        if len(clips) > self.MAX_CLIPS:
            raise SeekerError("That is %d clips - %d at most in one go."
                              % (len(clips), self.MAX_CLIPS))
        try:
            out = playlist.place_clips(self._song, clips, track)
        except playlist.PlaylistError as e:
            if e.placed:
                self.history.append(("clips", len(e.placed), before))
            raise SeekerError("%s %d of %d clips were placed%s." % (
                e, len(e.placed), len(clips),
                " (back takes them out)" if e.placed else ""))
        self.history.append(("clips", len(clips), before))
        del self.history[:-50]
        if song_mode:
            self._song(songMode=True)
            time.sleep(0.1)     # FL reports the old mode in the answer that changes it
        mode = self._song()
        return {"track": track, "startBar": first, "endBar": bar - 1, "sections": laid,
                "clips": len(clips), "songMode": bool(mode.get("songMode")),
                "warnings": list(out.get("warnings") or [])}

    @_locked
    def new_song(self, genre=None, key="C", scale="minor", structure="ABABCB", bars=8,
                 tempo=None, set_tempo=False, build=False, track=1, start_bar=None,
                 bass=True, chords=True, pad=True, guitar=True, passing=False):
        """A whole song: one new pattern per letter of `structure` (A verse, B
        chorus, C bridge - same genre, key and tempo, each its own groove and
        progression), then the letters laid out in the playlist, `bars` each."""
        if "".join(c for c in str(genre or "").lower() if c.isalnum()) in BALLAD_NAMES:
            # a ballad has its own form and is written note by note
            return self.new_ballad(key if key else "Eb", tempo, build, track, start_bar)
        letters = [c for c in str(structure or "").upper() if c.isalpha()]
        if not letters:
            raise SeekerError("structure is letters, one per section, like ABABCB.")
        if len(set(letters)) > 8:
            raise SeekerError("At most 8 different sections.")
        try:
            bars = int(bars)
        except (TypeError, ValueError):
            raise SeekerError("bars must be a whole number.")
        if not 1 <= bars <= 64:
            raise SeekerError("bars (per section) must be between 1 and 64.")
        hb = self._need_fl()
        genre_key = resolve_genre(genre)
        if not genre_key:       # auto: one genre for the whole song
            fit = tempo if tempo is not None else (None if set_tempo else hb["tempo"])
            genre_key = self.seeker.next(None, fit).genre
        made, built = {}, None
        for letter in dict.fromkeys(letters):
            title, color, change = self.SECTIONS.get(letter, ("Part " + letter, 0x5F9E6E, {}))
            first = not made
            options = dict(bass=bass, chords=chords, pad=pad, guitar=guitar, drums=True)
            if first and build:
                # the whole kit now, whatever this section leaves out
                skip = [r for r in ("bass", "chords", "pad", "guitar") if not options[r]]
                built = self.build_rack(genre_key, [r for r in kits.ROLES if r not in skip])
                self._settled_rack(len(hb["channels"]) + len(built["added"]))
            options.update({k: v and options[k] for k, v in change.items()})
            beat = self.new_beat(genre_key, key, scale, play=False, new_pattern=True,
                                 tempo=tempo if first else None,
                                 set_tempo=set_tempo and first, passing=passing, **options)
            if beat["problems"]:
                # A piano roll that didn't take (it happens on the first beat after
                # channels were added): once more, on the same pattern.
                beat = self.new_beat(genre_key, key, scale, play=False, passing=passing,
                                     **options)
            name ="%s - %s" % (title, beat["patternName"])
            self._song(pattern=beat["pattern"], name=name, color=color)
            made[letter] = dict(beat, section=title, patternName=name)
        laid = self.arrange([(made[c]["pattern"], bars) for c in letters], track, start_bar)
        for row, letter in zip(laid["sections"], letters):
            row["section"] = made[letter]["section"]
        first = made[letters[0]]
        out = {"genre": first["genre"], "key": first["key"], "tempo": first["tempo"],
               "structure": "".join(letters), "arrangement": laid,
               "patterns": [{"section": m["section"], "letter": c, "pattern": m["pattern"],
                             "patternName": m["patternName"],
                             "progression": m["progression"], "written": m["written"],
                             "noChannelFor": m["noChannelFor"],
                             "warnings": m["warnings"], "problems": m["problems"]}
                            for c, m in made.items()]}
        if built:
            out["built"] = built
        return out

    # ---- Jazz Ballad: a whole song written note by note ---------------------------
    BALLAD_PARTS = {"keys": "chords", "bass": "bass", "ride": "hat", "rim": "perc",
                    "kick": "kick", "snare": "snare"}

    @_locked
    def new_ballad(self, key="Eb", tempo=66, build=False, track=1, start_bar=None, seed=None):
        """A jazz trio ballad (seeker/ballad.py): Intro, A, A, bridge, A + tag
        ending, each section its own pattern of piano-roll parts, laid out in
        the playlist."""
        hb = self._need_fl()
        key_i = resolve_key(key)
        tempo = 66.0 if tempo is None else float(tempo)
        if not 40 <= tempo <= 100:
            raise SeekerError("A ballad sits between 40 and 100 BPM (66 is typical).")
        built = None
        if build:
            built = self.build_rack("jazz", [r for r in kits.ROLES if r not in ("pad", "guitar")])
            hb = self._settled_rack(len(hb["channels"]) + len(built["added"]))
        rolemap, _ = fit_rack(hb["channels"], "jazz", strict=bool(build))
        missing = [part for part, role in self.BALLAD_PARTS.items() if role not in rolemap]
        if "keys" in missing or "bass" in missing:
            raise SeekerError("The ballad needs a keys channel and a bass channel that suit "
                              "jazz (Rhodes, Piano, Upright Bass...). Use build=true to add "
                              "the trio.")
        seed = seed if seed is not None else random.randrange(1 << 30)
        song = ballad.compose(key_i, seed)
        made, problems = [], []
        for i, sec in enumerate(song["sections"]):
            rolls = []
            for part, notes in sec["parts"].items():
                ch = rolemap.get(self.BALLAD_PARTS[part])
                if ch and notes:
                    steps = [(p, s * 4, l * 4, v) for p, s, l, v in notes]
                    rolls.append((self._roll_key(ch), ch, steps))
            name = "%s - Jazz Ballad" % sec["name"]
            req = {"cmd": "apply", "tracks": [], "fill": False, "newPattern": True,
                   "patternName": name, "autoPlay": False,
                   "tempo": tempo if i == 0 else None}
            if rolls and pianoroll.write_script(rolls[0][2]):
                req["pianoRoll"] = {"channel": rolls[0][1]["index"], "name": rolls[0][1]["name"]}
            else:
                rolls = []
            res = self._apply(req)
            pattern = res["pattern"]
            self.history.append((pattern, res["prev"], self.last_rolls.get(pattern)))
            wrong = self._run_rolls(rolls) if rolls else []
            if wrong:
                # A piano roll that didn't take (seen on the first one after channels
                # were added): those channels once more.
                again = [r for r in rolls if any(e.startswith(r[1]["name"] + ":") for e in wrong)]
                wrong = self._rewrite_rolls(again)
            problems += ["%s: %s" % (sec["name"], w) for w in wrong]
            self.last_rolls[pattern] = {k: n for k, _, n in rolls}
            color = ballad.SECTION_COLORS.get(sec["name"].rstrip("123"), 0x4F7FB0)
            self._song(pattern=pattern, name=name, color=color)
            made.append({"section": sec["name"], "pattern": pattern, "bars": sec["bars"],
                         "chords": sec["chords"]})
        laid = self.arrange([(m["pattern"], m["bars"]) for m in made], track, start_bar)
        out = {"genre": "Jazz Ballad", "key": "%s major" % ballad.NAMES[key_i], "tempo": tempo,
               "seed": seed, "form": "Intro A A B A + ending", "sections": made,
               "arrangement": laid,
               "written": {part: rolemap[role]["name"] for part, role in
                           self.BALLAD_PARTS.items() if role in rolemap},
               "noChannelFor": missing, "problems": problems}
        if built:
            out["built"] = built
        return out

    def _rewrite_rolls(self, rolls):
        """Write rolls whose piano roll didn't take: open each one's roll again."""
        if not rolls:
            return []
        if not pianoroll.write_script(rolls[0][2]):
            return ["%s: couldn't write the piano-roll script" % rolls[0][1]["name"]]
        res = self._ask({"cmd": "pianoRoll", "pianoRoll": {
            "channel": rolls[0][1]["index"], "name": rolls[0][1]["name"]}})
        if res is None or res.get("pianoRoll"):
            link.send({"cmd": "closePianoRoll"})
            return ["%s: couldn't open the piano roll" % r[1]["name"] for r in rolls]
        return self._run_rolls(rolls)

    # ---- Back ------------------------------------------------------------
    @_locked
    def back(self):
        if not self.history:
            raise SeekerError("Nothing to go back to yet.")
        hb = self._need_fl()
        if self.history[-1][0] == "clips":
            # Clips come out the way they went in: one FL undo step each.
            _, count, before = self.history.pop()
            self._song(undo=count)
            time.sleep(0.2)
            after = int(self._song().get("songTicks") or 0)
            out = {"removedClips": count, "problems": [], "canGoBack": bool(self.history)}
            if after != before:
                out["problems"].append(
                    "The song isn't the length it was before - if something else was "
                    "edited in FL since, that was undone instead: redo with Ctrl+Alt+Z.")
            return out
        pattern, tracks, old_rolls = self.history[-1]
        if hb["pattern"] != pattern:
            raise SeekerError("Back restores Pattern %s - select it in FL first." % pattern)
        self.history.pop()
        req = {"cmd": "apply", "tracks": tracks, "fill": False}
        rolemap = {}
        for ch in hb["channels"]:       # rolls are keyed by their channel
            rolemap["ch:%d:%s" % (ch["index"], ch["name"])] = ch
            rolemap[self._roll_key(ch)] = ch
        # every roll written since, and every roll that beat emptied, goes back
        keys = list(self.last_rolls.get(pattern, {}))
        keys += [k for k in (old_rolls or {}) if k not in keys]
        rolls = [(key, rolemap[key], (old_rolls or {}).get(key, []))
                 for key in keys if key in rolemap]
        if rolls and pianoroll.write_script(rolls[0][2]):
            req["pianoRoll"] = {"channel": rolls[0][1]["index"], "name": rolls[0][1]["name"]}
        else:
            rolls = []
        res = self._apply(req)
        problems = self._run_rolls(rolls) if rolls else []
        if rolls:
            self.last_rolls[res["pattern"]] = {k: n for k, _, n in rolls if n}
        return {"restoredPattern": res["pattern"], "problems": problems,
                "canGoBack": bool(self.history)}

    # ---- piano rolls (chords, pad) --------------------------------------
    def _run_rolls(self, rolls):
        """Write each roll in turn. The first one's piano roll was already opened
        (by the apply request, or by write_part); returns a list of problems
        ([] = all written)."""
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
                if pianoroll.close_script_dialogs():
                    # Ours never opens a dialog: another script ran. Close it so FL
                    # isn't left blocked, and don't re-run "last script" (that one).
                    return "FL ran a different piano-roll script; closed it unchanged"
                now = self._edits()
                if now is not None and now > before:
                    return ""
            before = self._edits() or before
        return "the piano-roll script didn't run (is a window covering its top-left corner?)"
