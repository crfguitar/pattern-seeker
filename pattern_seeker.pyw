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

from seeker import link
from seeker.engine import Engine, SeekerError
from seeker.generator import KEYS
from seeker.library import GENRES

AUTO = "Auto (fits tempo)"
BG, PANEL, FG, DIM, ACCENT, BAD = "#23272b", "#2e3338", "#e8eaec", "#8b949e", "#e8793a", "#e05555"
NOT_ANSWERING = ("FL Studio isn't answering. In FL: Options > MIDI settings > Input "
                 "'Pattern Seeker In': Controller type 'Pattern Seeker', Enable, pick a port "
                 "number. Output 'Pattern Seeker Out': same port number.")
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


def beat_text(beat):
    """The status lines for a beat the engine wrote."""
    written = beat["written"]
    parts = [name for name, role in (("808", "bass"), ("chords", "chords"), ("synth", "pad"))
             if role in written]
    text = "%s  #%s  →  Pattern %s" % (beat["genre"], beat["tag"], beat["pattern"])
    if parts:
        text += "  ·  %s in %s" % (" + ".join(parts), beat["key"])
    rolls = [(label, written[role]) for label, role in (("chords", "chords"), ("synth", "pad"))
             if role in written]
    if rolls:       # say where they went: those channels are named by preset
        text += "\n" + "  ·  ".join("%s → %s" % r for r in rolls)
    missing = ["synth" if m == "pad" else m for m in beat["noChannelFor"]
               if m not in ("openhat", "perc")]
    if missing:
        text += "\nNo channel for: %s" % ", ".join(missing)
    for w in beat["warnings"] + beat["problems"]:
        text += "\n" + w
    return text


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
        self.engine = Engine()
        self.busy = False        # an engine call is running on the worker thread
        self.refocus = False     # give the keyboard back to this window afterwards
        self.events = queue.Queue()     # hotkey events and finished engine calls
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
            elif isinstance(ev, tuple):
                self.finished(*ev)
        seen = self.engine.peek()       # None while a beat is being written
        if seen is not None:
            hb, problem = seen
            if not hb:
                self.status.config(text="● " + (problem or "FL Studio not answering"),
                                   fg=BAD)
            elif hb.get("version") != link.script_version():
                self.status.config(text="● FL is running an old script - reload it",
                                   fg=BAD)
            else:
                self.status.config(
                    text="● FL connected  ·  Pattern %s  ·  %g BPM"
                         % (hb["pattern"], round(hb["tempo"], 1)), fg="#6cc070")
        self.root.after(50 if self.busy else 400, self.tick)

    # ---- actions: the engine does the work on a worker thread -----------
    def run(self, kind, call):
        if self.busy:
            return
        self.busy = True
        self.refocus = self.root.focus_displayof() is not None
        self.button.config(state="disabled")
        self.back_btn.config(state="disabled")

        def work():
            try:
                self.events.put((kind, call(), None))
            except SeekerError as e:
                self.events.put((kind, None, str(e)))
            except Exception as e:      # never leave the window stuck on busy
                self.events.put((kind, None, "Unexpected error: %s" % e))

        threading.Thread(target=work, daemon=True).start()

    def new_beat(self):
        # Read every control here: tkinter may only be touched from this thread.
        args = dict(
            genre=self.by_name.get(self.genre.get()) or "auto", key=self.key.get(),
            scale=self.scale.get(), bass=self.bass_on.get(), chords=self.chords_on.get(),
            pad=self.synth_on.get(), play=self.opts["autoPlay"].get(),
            set_tempo=self.opts["setTempo"].get(), new_pattern=self.opts["newPattern"].get())
        self.run("beat", lambda: self.engine.new_beat(**args))

    def back(self):
        if self.engine.can_go_back:
            self.run("back", self.engine.back)

    def finished(self, kind, result, error):
        self.busy = False
        self.button.config(state="normal")
        self.back_btn.config(state="normal" if self.engine.can_go_back else "disabled")
        if self.refocus:
            self.root.after(150, self.root.focus_force)
        if error:
            if "isn't answering" in error and not link.problem():
                error = NOT_ANSWERING   # the window's own wording: it holds the ports itself
            self.say(error, bad=True)
        elif kind == "back":
            text = "Restored the previous beat."
            self.say("\n".join([text] + result["problems"]), bad=bool(result["problems"]))
        else:
            self.say(beat_text(result), bad=bool(result["problems"]))

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
