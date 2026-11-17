"""Pattern Seeker - one button, endless beats, straight into FL's channel rack.

A small always-on-top window. NEW BEAT (or the global hotkey) writes a fresh
genre drum pattern onto the drum channels of the current FL Studio pattern.
"""

import ctypes
import queue
import threading
import tkinter as tk
from ctypes import wintypes
from tkinter import ttk

from seeker import link, pianoroll
from seeker.generator import CYCLE, KEYS, Seeker, bass_pitches, chord_notes, pad_notes
from seeker.library import GENRES
from seeker.mapping import build_tracks, map_rack

AUTO = "Auto (fits tempo)"
BG, PANEL, FG, DIM, ACCENT, BAD = "#23272b", "#2e3338", "#e8eaec", "#8b949e", "#e8793a", "#e05555"
TIMEOUT_MS = 10000     # a 64-bar pattern takes FL about 3 s to write
ERRORS = {
    "rack_changed": "Channel rack changed mid-click - press again.",
    "busy": "FL Studio is busy (a dialog is open?) - try again.",
}
MODS = {"ctrl": 0x2, "alt": 0x1, "shift": 0x4, "win": 0x8}


def parse_hotkey(text):
    """'ctrl+alt+b' -> (modifier mask, virtual key) or None."""
    parts = [p.strip().lower() for p in text.split("+") if p.strip()]
    if not parts:
        return None
    key, mods = parts[-1], 0
    for p in parts[:-1]:
        if p not in MODS:
            return None
        mods |= MODS[p]
    if len(key) == 1 and key.isalnum():
        return mods, ord(key.upper())
    if key == "space":
        return mods, 0x20
    if key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        return mods, 0x6F + int(key[1:])
    return None


def listen_hotkey(combo, out):
    """Block on a system-wide hotkey; runs in a daemon thread."""
    user32 = ctypes.windll.user32
    if not user32.RegisterHotKey(None, 1, combo[0] | 0x4000, combo[1]):  # MOD_NOREPEAT
        out.put("hotkey-taken")
        return
    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        if msg.message == 0x0312:  # WM_HOTKEY
            out.put("hotkey")


class App:
    def __init__(self, root):
        self.root = root
        self.settings = link.load_settings()
        self.seeker = Seeker()
        self.history = []        # (pattern, tracks, piano-roll notes) to step back through
        self.pending = None      # (request id, beat or None, ms waited)
        self.refocus = False     # give the keyboard back to this window afterwards
        self.events = queue.Queue()
        self.notice = ""

        root.title("Pattern Seeker")
        root.configure(bg=BG)
        root.attributes("-topmost", True)
        root.resizable(False, False)
        if self.settings.get("geometry"):
            try:
                root.geometry(self.settings["geometry"])
            except tk.TclError:
                pass

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=PANEL, background=PANEL,
                        foreground=FG, arrowcolor=FG, bordercolor=PANEL)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL)],
                  foreground=[("readonly", FG)])
        root.option_add("*TCombobox*Listbox.background", PANEL)
        root.option_add("*TCombobox*Listbox.foreground", FG)

        self.status = tk.Label(root, bg=BG, fg=DIM, anchor="w", justify="left",
                               wraplength=330, font=("Segoe UI", 9))
        self.status.pack(fill="x", padx=12, pady=(10, 4))

        self.names = [AUTO] + sorted(g["name"] for g in GENRES.values())
        self.by_name = {g["name"]: k for k, g in GENRES.items()}
        self.genre = tk.StringVar(value=self.settings.get("genre", AUTO))
        if self.genre.get() not in self.names:
            self.genre.set(AUTO)
        ttk.Combobox(root, textvariable=self.genre, values=self.names, state="readonly",
                     height=len(self.names), font=("Segoe UI", 10)).pack(fill="x", padx=12)

        self.button = tk.Button(
            root, text="NEW BEAT", command=self.new_beat, bg=ACCENT, fg="white",
            activebackground="#f08a4b", activeforeground="white", relief="flat",
            font=("Segoe UI", 16, "bold"), cursor="hand2", height=2)
        self.button.pack(fill="x", padx=12, pady=10)

        row = tk.Frame(root, bg=BG)
        row.pack(fill="x", padx=12)
        self.back_btn = tk.Button(row, text="◀ Back", command=self.back, bg=PANEL, fg=FG,
                                  activebackground=PANEL, activeforeground=FG,
                                  relief="flat", font=("Segoe UI", 9), state="disabled")
        self.back_btn.pack(side="left")
        self.opts = {}
        for key, label, default in (("autoPlay", "Play", True),
                                    ("setTempo", "Set tempo", False),
                                    ("newPattern", "New pattern", False)):
            var = tk.BooleanVar(value=self.settings.get(key, default))
            self.opts[key] = var
            tk.Checkbutton(row, text=label, variable=var, bg=BG, fg=FG, selectcolor=PANEL,
                           activebackground=BG, activeforeground=FG,
                           font=("Segoe UI", 9)).pack(side="left", padx=(8, 0))

        row2 = tk.Frame(root, bg=BG)
        row2.pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(row2, text="Key", bg=BG, fg=FG, font=("Segoe UI", 9)).pack(side="left")
        self.key = tk.StringVar(value=self.settings.get("key", "C"))
        if self.key.get() not in KEYS:
            self.key.set("C")
        ttk.Combobox(row2, textvariable=self.key, values=KEYS, state="readonly",
                     width=3, height=12, font=("Segoe UI", 9)).pack(side="left", padx=(4, 0))
        self.scale = tk.StringVar(value=self.settings.get("scale", "Minor"))
        if self.scale.get() not in ("Minor", "Major"):
            self.scale.set("Minor")
        ttk.Combobox(row2, textvariable=self.scale, values=("Minor", "Major"),
                     state="readonly", width=6, font=("Segoe UI", 9)).pack(side="left", padx=(4, 0))
        self.bass_on = tk.BooleanVar(value=self.settings.get("bass", True))
        self.chords_on = tk.BooleanVar(value=self.settings.get("chords", True))
        self.synth_on = tk.BooleanVar(value=self.settings.get("synth", True))
        for label, var in (("808", self.bass_on), ("Chords", self.chords_on),
                           ("Synth", self.synth_on)):
            tk.Checkbutton(row2, text=label, variable=var, bg=BG, fg=FG, selectcolor=PANEL,
                           activebackground=BG, activeforeground=FG,
                           font=("Segoe UI", 9)).pack(side="left", padx=(6, 0))
        self.last_rolls = {}     # pattern -> {role: notes we last wrote to its piano roll}
        self.chord_job = None    # set while the piano-roll script is being run

        self.info = tk.Label(root, bg=BG, fg=FG, anchor="w", justify="left",
                             wraplength=330, font=("Segoe UI", 9))
        self.info.pack(fill="x", padx=12, pady=(8, 10))

        root.bind("<space>", lambda e: self.new_beat())
        root.bind("<Return>", lambda e: self.new_beat())
        root.bind("<BackSpace>", lambda e: self.back())
        root.protocol("WM_DELETE_WINDOW", self.close)

        state = link.install_script()
        if state == "no-fl":
            self.notice = "FL Studio settings folder not found - script not installed."
        elif state in ("installed", "updated"):
            self.notice = "FL script %s. Restart FL Studio (or reload the script) to load it." % state

        self.hotkey = self.settings.get("hotkey", "ctrl+alt+b")
        combo = parse_hotkey(self.hotkey)
        if combo:
            threading.Thread(target=listen_hotkey, args=(combo, self.events), daemon=True).start()

        self.say(self.notice or "Press NEW BEAT, Space, or %s from anywhere."
                 % self.hotkey.title())
        self.tick()

    # ---- status -------------------------------------------------------
    def say(self, text, bad=False):
        self.info.config(text=text, fg=BAD if bad else FG)

    def tick(self):
        while not self.events.empty():
            ev = self.events.get()
            if ev == "hotkey":
                self.new_beat()
            elif ev == "hotkey-taken":
                self.say("Hotkey %s is in use by another app; the button still works."
                         % self.hotkey.title(), bad=True)
        hb = link.heartbeat()
        if not hb:
            self.status.config(text="● " + (link.problem() or "FL Studio not answering"),
                               fg=BAD)
        elif hb.get("version") != link.script_version():
            self.status.config(text="● FL is running an old script - reload it", fg=BAD)
        else:
            self.status.config(
                text="● FL connected  ·  Pattern %s  ·  %g BPM"
                     % (hb["pattern"], round(hb["tempo"], 1)), fg="#6cc070")
        self.root.after(400, self.tick)

    # ---- actions ------------------------------------------------------
    def new_beat(self):
        if self.pending or self.chord_job:
            return
        self.refocus = self.root.focus_displayof() is not None
        hb = link.heartbeat()
        if not hb:
            self.say(link.problem() or
                     "FL Studio isn't answering. In FL: Options > MIDI settings > Input "
                     "'Pattern Seeker In': Controller type 'Pattern Seeker', Enable, pick "
                     "a port number. Output 'Pattern Seeker Out': same port number.",
                     bad=True)
            return
        rolemap = map_rack(hb["channels"])
        set_tempo = self.opts["setTempo"].get()
        chosen = self.by_name.get(self.genre.get())
        # Auto: stay in the project's tempo unless we're allowed to change it.
        beat = self.seeker.next(chosen, None if (chosen or set_tempo) else hb["tempo"])
        key, scale = KEYS.index(self.key.get()), self.scale.get().lower()
        new_pattern = self.opts["newPattern"].get()
        keys_ch = rolemap.get("chords") if self.chords_on.get() else None
        lead_ch = rolemap.get("pad") if self.synth_on.get() else None
        # With chords or a pad, everything follows one four-bar progression
        # and the 808 plays the root of whichever chord is sounding.
        prog = beat.chords["progs"][scale] if (keys_ch or lead_ch) else None
        lanes, pitches = dict(beat.lanes), None
        if not self.bass_on.get():
            del lanes["bass"]       # leave the 808 channel exactly as it is
        elif prog:
            lanes["bass"] = lanes["bass"] * (CYCLE // len(lanes["bass"]))
            pitches = {"bass": bass_pitches(beat.relative * (CYCLE // len(beat.relative)),
                                            key, scale, prog=prog)}
        else:
            pitches = {"bass": bass_pitches(beat.degrees, key, scale)}
        tracks, missing = build_tracks(lanes, rolemap, pitches)
        if not tracks and not prog:
            self.say("No drum channels found. Name channels like Kick, Snare, Clap, "
                     "Hat, 808, Piano, Synth and press again.", bad=True)
            return
        req = {
            "cmd": "apply", "tracks": tracks, "fill": True, "patternName": beat.name,
            "newPattern": new_pattern,
            "autoPlay": self.opts["autoPlay"].get(),
            "tempo": beat.tempo if set_tempo else None,
            "minSteps": CYCLE if prog else 0,
        }
        # Same length the drums are tiled to: the pattern, rounded up to a bar.
        steps = 0 if new_pattern else hb.get("patternSteps", 0)
        total = max(CYCLE, ((steps + 15) // 16) * 16)
        rolls = []                  # (role, channel, notes) for each piano roll we fill
        if keys_ch:
            notes = chord_notes(beat.chords["rhythm"], prog, key, scale,
                                beat.chords["voicing"])
            rolls.append(("chords", keys_ch, pianoroll.tile(notes, total, CYCLE)))
        elif self.chords_on.get():
            missing = missing + ["chords"]
        if lead_ch:
            notes = pad_notes(prog, key, scale)
            rolls.append(("pad", lead_ch, pianoroll.tile(notes, total, CYCLE)))
        elif self.synth_on.get():
            missing = missing + ["synth"]
        if rolls and pianoroll.write_script(rolls[0][2]):
            req["pianoRoll"] = {"channel": rolls[0][1]["index"], "name": rolls[0][1]["name"]}
        else:
            rolls = []
        self.begin(link.send(req), {"beat": beat, "missing": missing, "rolls": rolls,
                                    "label": "%s %s" % (self.key.get(), scale)})

    def back(self):
        if self.pending or self.chord_job or not self.history:
            return
        self.refocus = self.root.focus_displayof() is not None
        hb = link.heartbeat()
        pattern, tracks, old_rolls = self.history[-1]
        if not hb or hb["pattern"] != pattern:
            self.say("Back restores Pattern %s - select it in FL first." % pattern, bad=True)
            return
        self.history.pop()
        req = {"cmd": "apply", "tracks": tracks, "fill": False}
        rolemap = map_rack(hb["channels"])
        # Every piano roll we wrote on this pattern goes back to what it held before.
        rolls = [(role, rolemap[role], (old_rolls or {}).get(role, []))
                 for role in self.last_rolls.get(pattern, {}) if role in rolemap]
        if rolls and pianoroll.write_script(rolls[0][2]):
            req["pianoRoll"] = {"channel": rolls[0][1]["index"], "name": rolls[0][1]["name"]}
        else:
            rolls = []
        self.begin(link.send(req), {"beat": None, "rolls": rolls})

    def begin(self, request_id, context):
        self.pending = (request_id, context, 0)
        self.button.config(state="disabled")
        self.root.after(30, self.wait)

    # ---- chords: run the piano-roll script in FL, hands-free ----------
    def ask(self, req, then, timeout=1500, waited=0, request_id=None):
        """Send `req` to FL and call then(response or None) without blocking the UI."""
        if request_id is None:
            request_id = link.send(req)
        res = link.response(request_id)
        if res is None and waited < timeout:
            self.root.after(25, self.ask, req, then, timeout, waited + 25, request_id)
        else:
            then(res)

    def run_rolls(self, res, text, rolls):
        """Fill each piano roll in `rolls` in turn. The first is already open (the
        beat request asked for it): run our script there, check FL saw the edit,
        move on to the next channel, and finally put the user's view back."""
        self.chord_job = {"text": text, "rolls": list(rolls), "problems": []}
        self.button.config(state="disabled")
        self.roll_opened(res)

    def roll_opened(self, res):
        job = self.chord_job
        if res is None or res.get("pianoRoll"):
            self.chords_done("couldn't open the piano roll (%s)"
                             % (res.get("pianoRoll") if res else "FL didn't answer"))
            return
        job.update(ways=["menu", "shortcut"], found=0)
        self.root.after(120, self.chords_baseline)

    def chords_baseline(self):
        self.ask({"cmd": "edits"}, self.chords_trigger)

    def chords_trigger(self, res):
        job = self.chord_job
        hwnd = pianoroll.find_piano_roll()
        if res is None or hwnd is None:
            job["found"] += 1
            if res is not None and job["found"] < 10:      # the window can take a moment
                self.root.after(60, self.chords_trigger, res)
            else:
                self.chords_done("FL's piano roll didn't open")
            return
        job["edits"] = res.get("edits", 0)
        way = job["ways"].pop(0)
        pianoroll.bring_forward(hwnd)
        if way == "menu" and not pianoroll.run_from_menu(hwnd):
            way = job["ways"].pop(0)        # icon hidden or script not listed
        if way == "shortcut":
            pianoroll.press_run_last_script()
        job["deadline"] = 1500
        self.root.after(80, self.chords_check)

    def chords_check(self, res=None):
        job = self.chord_job
        if res is not None and res.get("edits", 0) > job["edits"]:
            self.chords_done("")
        elif job["deadline"] > 0:
            job["deadline"] -= 110
            self.root.after(60, self.ask, {"cmd": "edits"}, self.chords_check, 400)
        elif job["ways"]:
            self.chords_baseline()          # the menu didn't do it: try Ctrl+Alt+Y
        else:
            self.chords_done("the script didn't run. Keep this window off the piano "
                             "roll's top-left corner.")

    def chords_done(self, problem):
        """One piano roll is finished (problem = '' when it worked): next, or wrap up."""
        job = self.chord_job
        role, channel, _ = job["rolls"].pop(0)
        if problem:
            job["problems"].append("%s: %s" % (channel["name"], problem))
        if job["rolls"]:
            _, channel, notes = job["rolls"][0]
            if pianoroll.write_script(notes):
                self.ask({"cmd": "pianoRoll", "pianoRoll": {
                    "channel": channel["index"], "name": channel["name"]}}, self.roll_opened)
                return
        self.chord_job = None
        self.button.config(state="normal")
        link.send({"cmd": "closePianoRoll"})
        if self.refocus:
            self.root.after(150, self.root.focus_force)
        if job["problems"]:
            self.say(job["text"] + "\n" + "\n".join(job["problems"]), bad=True)
        else:
            self.say(job["text"])

    def wait(self):
        request_id, context, waited = self.pending
        res = link.response(request_id)
        if res is None and waited < TIMEOUT_MS:
            self.pending = (request_id, context, waited + 30)
            self.root.after(30, self.wait)
            return
        self.pending = None
        self.button.config(state="normal")
        if res is None:
            link.cancel()
            self.say("FL Studio didn't answer in time.", bad=True)
        elif not res.get("ok"):
            self.say(ERRORS.get(res.get("error"), "FL error: %s"
                                % (res.get("detail") or res.get("error"))), bad=True)
        elif context["beat"] is None:
            self.say("Restored the previous beat.")
            if context["rolls"]:
                self.last_rolls[res["pattern"]] = {r: n for r, _, n in context["rolls"]}
                self.run_rolls(res, "Restored the previous beat.", context["rolls"])
        else:
            beat, missing, rolls = context["beat"], context["missing"], context["rolls"]
            pattern = res["pattern"]
            self.history.append((pattern, res["prev"], self.last_rolls.get(pattern)))
            del self.history[:-50]
            wrote = [role for role, _, _ in rolls]
            parts = [name for name, on in (("808", self.bass_on.get() and "bass" not in missing),
                                           ("chords", "chords" in wrote),
                                           ("synth", "pad" in wrote)) if on]
            text = "%s  #%s  \u2192  Pattern %s" % (beat.genre_name, beat.tag, pattern)
            if parts:
                text += "  \u00b7  %s in %s" % (" + ".join(parts), context["label"])
            if rolls:       # say where they went: those channels are named by preset
                text += "\n" + "  \u00b7  ".join(
                    "%s \u2192 %s" % ("synth" if role == "pad" else role, ch["name"])
                    for role, ch, _ in rolls)
            if missing:
                text += "\nNo channel for: %s" % ", ".join(missing)
            for w in res.get("warnings") or []:
                text += "\n" + w
            self.say(text)
            if rolls:
                # Keep what an earlier beat wrote to a roll this one didn't touch.
                self.last_rolls[pattern] = dict(self.last_rolls.get(pattern, {}),
                                                **{r: n for r, _, n in rolls})
                self.run_rolls(res, text, rolls)
        self.back_btn.config(state="normal" if self.history else "disabled")

    def close(self):
        self.settings.update({k: v.get() for k, v in self.opts.items()})
        self.settings.update(bass=self.bass_on.get(), chords=self.chords_on.get(),
                             synth=self.synth_on.get(),
                             key=self.key.get(),
                             scale=self.scale.get())
        self.settings.update(genre=self.genre.get(), hotkey=self.hotkey,
                             geometry="+%d+%d" % (self.root.winfo_x(), self.root.winfo_y()))
        try:
            link.save_settings(self.settings)
        finally:
            link.close()
            self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
