"""Pattern Seeker - beats, songs and a rack for FL Studio, one click each.

A small always-on-top window on the same engine as the MCP server. The controls
at the top say what to write (genre, key, tempo, parts); the tabs say where:

    Beat   NEW BEAT (or the global hotkey) writes a groove on the current pattern.
    Song   NEW SONG lays a pattern per section out in the playlist; JAZZ BALLAD
           writes a whole ballad; a pattern can be added to the song by hand.
    Rack   the channels with their part and mixer insert; build a genre's kit,
           route channels to inserts, EQ the mix, add a sound, rename a channel.
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
from seeker.mapping import detect_role, map_rack

AUTO = "Auto (fits tempo)"
BG, PANEL, FG, DIM, ACCENT, BAD = "#23272b", "#2e3338", "#e8eaec", "#8b949e", "#e8793a", "#e05555"
FONT = ("Segoe UI", 9)
NOT_ANSWERING = ("FL Studio isn't answering. In FL: Options > MIDI settings > Input "
                 "'Pattern Seeker In': Controller type 'Pattern Seeker', Enable, pick a port "
                 "number. Output 'Pattern Seeker Out': same port number.")
MOUSE = "FL comes to the front and the mouse moves for a few seconds - hands off until it's done."
MODS = {"ctrl": 0x2, "alt": 0x1, "shift": 0x4, "win": 0x8}
TYPING = ("Entry", "TEntry", "TCombobox", "Spinbox", "Listbox", "Treeview", "Button",
          "Checkbutton", "TNotebook")     # widgets that use Space / Return / Backspace themselves


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


def number(text, what, kind=float):
    """'' -> None, '90' -> 90; anything else is explained."""
    text = str(text).strip()
    if not text:
        return None
    try:
        return kind(text)
    except ValueError:
        raise SeekerError("%s must be a %snumber." % (what, "whole " if kind is int else ""))


# ---- what the engine did, in words ------------------------------------------
def troubles(result):
    """Every problem in a result, wherever the engine put it."""
    out = list(result.get("problems") or [])
    out += (result.get("built") or {}).get("problems") or []
    for p in result.get("patterns") or []:
        out += ["%s: %s" % (p["section"], w) for w in p["problems"]]
    return out


def notes_of(result):
    """Warnings: worth reading, but nothing failed."""
    out = list(result.get("warnings") or [])
    out += (result.get("arrangement") or {}).get("warnings") or []
    for p in result.get("patterns") or []:
        out += p["warnings"]
    return out


def chords_line(progression):
    return "  ".join(c["chord"] for c in progression or [])


def added_line(built):
    names = [a["name"] for a in (built or {}).get("added") or []]
    return "Added: " + ", ".join(names) if names else ""


def missing_line(parts):
    names = ["synth" if m == "pad" else m for m in parts if m not in ("openhat", "perc")]
    return ("No channel for: %s  (tick Build rack to add them)" % ", ".join(names)
            if names else "")


def beat_text(beat):
    """The status lines for a beat the engine wrote."""
    written = beat["written"]
    bass = "808" if "808" in written.get("bass", "") else "bass"
    parts = [name for name, role in ((bass, "bass"), ("chords", "chords"), ("synth", "pad"),
                                     ("guitar", "guitar")) if role in written]
    text = "%s  #%s  →  Pattern %s" % (beat["genre"], beat["tag"], beat["pattern"])
    if parts:
        text += "  ·  %s in %s" % (" + ".join(parts), beat["key"])
    rolls = [(label, written[role]) for label, role in (("chords", "chords"), ("synth", "pad"),
                                                        ("guitar", "guitar")) if role in written]
    if rolls:       # say where they went: those channels are named by preset
        text += "\n" + "  ·  ".join("%s → %s" % r for r in rolls)
    lines = [chords_line(beat.get("progression")), added_line(beat.get("built")),
             missing_line(beat["noChannelFor"])]
    return "\n".join([text] + [l for l in lines if l] + notes_of(beat) + troubles(beat))


def song_text(song):
    """A song: one line per section with its bars, pattern and chords."""
    if "form" in song:
        return ballad_text(song)
    lines = ["%s  ·  %s  ·  %g BPM  ·  %s" % (song["genre"], song["key"], song["tempo"],
                                             song["structure"])]
    by_pattern = {p["pattern"]: p for p in song["patterns"]}
    for row in song["arrangement"]["sections"]:
        lines.append("%s  bars %d-%d  ·  Pattern %d  ·  %s" % (
            row["section"], row["bar"], row["bar"] + row["bars"] - 1, row["pattern"],
            chords_line(by_pattern[row["pattern"]]["progression"])))
    missing = []
    for p in song["patterns"]:
        missing += [m for m in p["noChannelFor"] if m not in missing]
    lines += [added_line(song.get("built")), missing_line(missing),
              "On track %d, FL in song mode." % song["arrangement"]["track"]]
    return "\n".join([l for l in lines if l] + notes_of(song) + troubles(song))


def ballad_text(song):
    lines = ["%s  ·  %s  ·  %g BPM  ·  seed %s" % (song["genre"], song["key"], song["tempo"],
                                                  song["seed"])]
    for sec, row in zip(song["sections"], song["arrangement"]["sections"]):
        lines.append("%s  bars %d-%d  ·  Pattern %d" % (
            sec["section"], row["bar"], row["bar"] + row["bars"] - 1, sec["pattern"]))
        lines.append("   " + " | ".join(sec["chords"]))
    if song["noChannelFor"]:
        lines.append("No channel for: %s  (tick Build rack)" % ", ".join(song["noChannelFor"]))
    lines.append(added_line(song.get("built")))
    return "\n".join([l for l in lines if l] + notes_of(song) + troubles(song))


def arrange_text(laid):
    lines = ["Pattern %d  →  bars %d-%d on track %d  (%d clip%s)" % (
        s["pattern"], s["bar"], s["bar"] + s["bars"] - 1, laid["track"], s["clips"],
        "" if s["clips"] == 1 else "s") for s in laid["sections"]]
    return "\n".join(lines + laid["warnings"])


def build_text(built):
    lines = ["%s kit" % built["genre"]]
    for a in built["added"]:
        lines.append("+ %s  (%s)%s" % (a["name"], a["sound"].split("/")[-1],
                                       "  → insert %s" % a["insert"] if a.get("insert") else ""))
    if built["kept"]:
        lines.append("Already there: " + ", ".join(sorted(set(built["kept"].values()))))
    if not built["added"] and not built["problems"]:
        lines.append("Nothing to add.")
    elif built["added"]:
        lines.append("Sounds were picked by name, not by ear - swap any you don't like.")
    return "\n".join(lines + built["problems"])


def route_text(done):
    if not done["routed"]:
        return "\n".join(["Every channel already has its own mixer insert."] + done["warnings"])
    return "\n".join(["%s  →  insert %d" % (r["channel"], r["insert"]) for r in done["routed"]]
                     + done["warnings"])


def eq_text(done):
    lines = ["%s EQ" % done["genre"]]
    for ch in done["channels"]:
        lines.append("%s (insert %d):  %s" % (ch["channel"], ch["insert"],
                                             ";  ".join(b for b in ch["bands"] if b)))
        lines += ch["warnings"]
    if not done["channels"] and not done["problems"]:
        lines.append("No part of this genre in the rack.")
    return "\n".join(lines + done["problems"])


def added_text(made):
    text = "Added %s  (%s)  as channel %d" % (made["name"], made["sound"], made["channel"])
    if made.get("insert"):
        text += "  →  insert %d" % made["insert"]
    text += "\nNew Beat writes its %s part there." % made["role"] if made.get("role") else \
        "\nNew Beat leaves it alone (name it Kick, Snare, Hat, Bass, Piano, Pad... to use it)."
    return "\n".join([text] + made["warnings"])


def rack_rows(channels):
    """[(index, name, part, insert)] - the parts as fl_status reports them."""
    roles = {ch["index"]: role for role, ch in map_rack(channels).items()}
    return [(ch["index"], ch["name"], roles.get(ch["index"]) or detect_role(ch["name"]) or "",
             ch.get("insert") or "master") for ch in channels]


TEXT = {"beat": beat_text, "song": song_text, "ballad": ballad_text, "arrange": arrange_text,
        "build": build_text, "route": route_text, "eq": eq_text, "add": added_text}


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
        self.pattern = None      # the pattern selected in FL, from the heartbeat
        self.rack = None         # the rows the Rack tab shows now
        self.buttons = []        # everything that starts an engine call

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
        flat = dict(bordercolor=BG, lightcolor=BG, darkcolor=BG)
        style.configure("TNotebook", background=BG, borderwidth=0, **flat)
        style.configure("TNotebook.Tab", background=PANEL, foreground=DIM, padding=(14, 4),
                        font=FONT, borderwidth=0, **flat)
        style.map("TNotebook.Tab", background=[("selected", ACCENT)],
                  foreground=[("selected", "white")])
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG,
                        borderwidth=0, rowheight=20, font=FONT, **flat)
        style.configure("Treeview.Heading", background=BG, foreground=DIM, font=FONT,
                        borderwidth=0)
        style.map("Treeview", background=[("selected", "#4a5058")],
                  foreground=[("selected", FG)])
        root.option_add("*TCombobox*Listbox.background", PANEL)
        root.option_add("*TCombobox*Listbox.foreground", FG)

        self.status = tk.Label(root, bg=BG, fg=DIM, anchor="w", justify="left",
                               wraplength=380, font=FONT)
        self.status.pack(fill="x", padx=12, pady=(10, 4))

        # ---- what to write: shared by the beat, the song and the rack -------
        self.names = [AUTO] + sorted(g["name"] for g in GENRES.values())
        self.by_name = {g["name"]: k for k, g in GENRES.items()}
        self.genre = tk.StringVar(value=self.settings.get("genre", AUTO))
        if self.genre.get() not in self.names:
            self.genre.set(AUTO)
        ttk.Combobox(root, textvariable=self.genre, values=self.names, state="readonly",
                     height=len(self.names), font=("Segoe UI", 10)).pack(fill="x", padx=12)

        row = self.row(root, pady=(8, 0))
        self.label(row, "Key", first=True)
        self.key = tk.StringVar(value=self.settings.get("key", "C"))
        if self.key.get() not in KEYS:
            self.key.set("C")
        ttk.Combobox(row, textvariable=self.key, values=KEYS, state="readonly",
                     width=3, height=12, font=FONT).pack(side="left", padx=(4, 0))
        self.scale = tk.StringVar(value=self.settings.get("scale", "Minor"))
        if self.scale.get() not in ("Minor", "Major"):
            self.scale.set("Minor")
        ttk.Combobox(row, textvariable=self.scale, values=("Minor", "Major"),
                     state="readonly", width=6, font=FONT).pack(side="left", padx=(4, 0))
        self.label(row, "Tempo")
        self.tempo = self.entry(row, "tempo", "", 5)
        self.label(row, "BPM (empty = FL's)", dim=True, gap=4)

        self.opts = {}
        row = self.row(root, pady=(6, 0))
        for key, label, default in (("drums", "Drums", True), ("bass", "Bass", True),
                                    ("chords", "Chords", True), ("synth", "Pad", True),
                                    ("guitar", "Guitar", True)):
            self.check(row, key, label, default)
        row = self.row(root, pady=(2, 8))
        for key, label, default in (("passing", "Passing chord", False),
                                    ("build", "Build rack", False),
                                    ("setTempo", "Genre's tempo", False)):
            self.check(row, key, label, default)

        # ---- where it goes ----------------------------------------------------
        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill="x", padx=12)
        beat, song, rack = (tk.Frame(self.tabs, bg=BG) for _ in range(3))
        for frame, title in ((beat, "Beat"), (song, "Song"), (rack, "Rack")):
            self.tabs.add(frame, text=title)
        try:
            self.tabs.select(int(self.settings.get("tab", 0)))
        except (tk.TclError, ValueError, TypeError):
            pass
        # a notebook is as tall as its tallest tab: make it fit the one showing
        self.tabs.bind("<<NotebookTabChanged>>", lambda e: self.root.after_idle(self.fit_tab))

        self.button = self.big(beat, "NEW BEAT", self.new_beat, height=2, size=16)
        row = self.row(beat, padx=0, pady=(0, 8))
        self.check(row, "autoPlay", "Play", True)
        self.check(row, "newPattern", "New pattern", False)

        row = self.row(song, padx=0, pady=(10, 0))
        self.label(row, "Structure", first=True)
        self.structure = self.entry(row, "structure", "ABABCB", 10)
        self.label(row, "Bars each")
        self.bars = self.entry(row, "bars", "8", 3)
        row = self.row(song, padx=0, pady=(6, 0))
        self.label(row, "Track", first=True)
        self.track = self.entry(row, "track", "1", 3)
        self.label(row, "Start bar")
        self.start_bar = self.entry(row, None, "", 4)
        self.label(row, "(empty = song's end)", dim=True, gap=4)
        self.label(self.row(song, padx=0, pady=(4, 0)),
                   "A verse (no pad)  ·  B chorus  ·  C bridge (no drums)", dim=True, first=True)
        self.big(song, "NEW SONG", self.new_song)
        row = self.row(song, padx=0, pady=(0, 8))
        self.small(row, "Jazz ballad", self.new_ballad, first=True)
        self.label(row, "Seed", gap=6)
        self.seed = self.entry(row, None, "", 10)
        self.small(row, "Add pattern to song", self.add_pattern)

        self.tree = ttk.Treeview(rack, columns=("n", "name", "part", "insert"),
                                 show="headings", height=7, selectmode="browse")
        for col, title, width in (("n", "#", 28), ("name", "Channel", 170), ("part", "Part", 70),
                                  ("insert", "Insert", 60)):
            self.tree.heading(col, text=title, anchor="w")
            self.tree.column(col, width=width, anchor="w", stretch=col == "name")
        self.tree.pack(fill="x", pady=(10, 6))
        row = self.row(rack, padx=0)
        self.small(row, "Build kit", self.build, first=True)
        self.small(row, "Route to mixer", self.route)
        self.small(row, "EQ the mix", self.mix_eq)
        row = self.row(rack, padx=0, pady=(8, 0))
        self.label(row, "Sound", first=True)
        self.search = self.entry(row, None, "", 20)
        self.search.bind("<Return>", lambda e: self.find())
        self.kind = tk.StringVar(value="all")
        ttk.Combobox(row, textvariable=self.kind, values=("all", "instrument", "sample"),
                     state="readonly", width=10, font=FONT).pack(side="left", padx=(4, 0))
        self.small(row, "Find", self.find)
        self.found = tk.Listbox(rack, height=5, bg=PANEL, fg=FG, selectbackground="#4a5058",
                                selectforeground=FG, relief="flat", highlightthickness=0,
                                font=FONT, exportselection=False, activestyle="none")
        self.found.pack(fill="x", pady=(6, 6))
        row = self.row(rack, padx=0, pady=(0, 8))
        self.label(row, "Name", first=True)
        self.name = self.entry(row, None, "", 16)
        self.small(row, "Add channel", self.add)
        self.small(row, "Rename selected", self.rename)

        # ---- undo, and what happened --------------------------------------------
        row = self.row(root, pady=(8, 0))
        self.back_btn = tk.Button(row, text="◀ Back", command=self.back, bg=PANEL, fg=FG,
                                  activebackground=PANEL, activeforeground=FG,
                                  relief="flat", font=FONT, state="disabled")
        self.back_btn.pack(side="left")
        self.info = tk.Text(root, bg=BG, fg=FG, height=9, width=56, wrap="word", relief="flat",
                            highlightthickness=0, font=FONT, cursor="arrow", takefocus=0)
        self.info.pack(fill="x", padx=12, pady=(6, 10))

        root.bind("<space>", lambda e: self.key_press(e, self.new_beat))
        root.bind("<Return>", lambda e: self.key_press(e, self.new_beat))
        root.bind("<BackSpace>", lambda e: self.key_press(e, self.back))
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

    # ---- widgets ------------------------------------------------------------
    def row(self, parent, padx=12, pady=0):
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="x", padx=padx, pady=pady)
        return frame

    def label(self, row, text, first=False, dim=False, gap=10):
        tk.Label(row, text=text, bg=BG, fg=DIM if dim else FG,
                 font=FONT).pack(side="left", padx=(0 if first else gap, 0))

    def entry(self, row, setting, default, width):
        """A text field; `setting` is the settings.json key it is remembered under."""
        box = tk.Entry(row, width=width, bg=PANEL, fg=FG, insertbackground=FG, relief="flat",
                       font=FONT)
        box.insert(0, str(self.settings.get(setting, default)) if setting else default)
        box.setting = setting
        box.pack(side="left", padx=(4, 0), ipady=2)
        return box

    def check(self, row, key, label, default):
        var = tk.BooleanVar(value=self.settings.get(key, default))
        self.opts[key] = var
        tk.Checkbutton(row, text=label, variable=var, bg=BG, fg=FG, selectcolor=PANEL,
                       activebackground=BG, activeforeground=FG,
                       font=FONT).pack(side="left", padx=(0, 6))

    def big(self, parent, text, command, height=1, size=13):
        button = tk.Button(parent, text=text, command=command, bg=ACCENT, fg="white",
                           activebackground="#f08a4b", activeforeground="white", relief="flat",
                           font=("Segoe UI", size, "bold"), cursor="hand2", height=height)
        button.pack(fill="x", pady=10)
        self.buttons.append(button)
        return button

    def small(self, row, text, command, first=False):
        button = tk.Button(row, text=text, command=command, bg=PANEL, fg=FG,
                           activebackground=PANEL, activeforeground=FG, relief="flat",
                           font=FONT, cursor="hand2", padx=8)
        button.pack(side="left", padx=(0 if first else 6, 0))
        self.buttons.append(button)
        return button

    def fit_tab(self):
        self.root.update_idletasks()    # the tab's own size is known only once laid out
        self.tabs.configure(
            height=self.tabs.nametowidget(self.tabs.select()).winfo_reqheight())

    def key_press(self, event, action):
        if event.widget.winfo_class() not in TYPING:
            action()

    # ---- status -------------------------------------------------------
    def say(self, text, bad=False):
        self.info.config(state="normal", fg=BAD if bad else FG)
        self.info.delete("1.0", "end")
        self.info.insert("1.0", text)
        self.info.config(state="disabled")

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
                self.pattern = hb["pattern"]
                self.status.config(
                    text="● FL connected  ·  Pattern %s  ·  %g BPM  ·  %d channels"
                         % (hb["pattern"], round(hb["tempo"], 1), len(hb["channels"])),
                    fg="#6cc070")
                self.show_rack(hb["channels"])
        self.root.after(50 if self.busy else 400, self.tick)

    def show_rack(self, channels):
        rows = rack_rows(channels)
        if rows == self.rack:
            return
        picked = self.tree.selection()
        self.rack = rows
        self.tree.delete(*self.tree.get_children())
        for r in rows:
            self.tree.insert("", "end", iid=str(r[0]), values=r)
        if picked and self.tree.exists(picked[0]):
            self.tree.selection_set(picked[0])

    # ---- actions: the engine does the work on a worker thread -----------
    def run(self, kind, call, notice=""):
        """Start engine call `call()`; `finished` gets its result. Every control is
        read before this: tkinter may only be touched from the main thread."""
        if self.busy:
            return
        self.busy = True
        self.refocus = self.root.focus_displayof() is not None
        for b in self.buttons + [self.back_btn]:
            b.config(state="disabled")
        if notice:
            self.say(notice)

        def work():
            try:
                self.events.put((kind, call(), None))
            except SeekerError as e:
                self.events.put((kind, None, str(e)))
            except Exception as e:      # never leave the window stuck on busy
                self.events.put((kind, None, "Unexpected error: %s" % e))

        threading.Thread(target=work, daemon=True).start()

    def music(self):
        """The shared controls, as the arguments new_beat and new_song both take."""
        o = self.opts
        return dict(genre=self.by_name.get(self.genre.get()) or "auto", key=self.key.get(),
                    scale=self.scale.get(), bass=o["bass"].get(), chords=o["chords"].get(),
                    pad=o["synth"].get(), guitar=o["guitar"].get(),
                    passing=o["passing"].get(), build=o["build"].get(),
                    set_tempo=o["setTempo"].get(), tempo=number(self.tempo.get(), "Tempo"))

    def place(self):
        """The Song tab's playlist track and start bar."""
        return dict(track=number(self.track.get(), "Track", int) or 1,
                    start_bar=number(self.start_bar.get(), "Start bar", int))

    def need_genre(self, what):
        genre = self.by_name.get(self.genre.get())
        if not genre:
            raise SeekerError("Pick a genre first: %s depends on the genre's sounds." % what)
        return genre

    def start(self, kind, prepare, notice=""):
        """Read the controls with `prepare()` (it returns the engine call), then run it."""
        if self.busy:
            return
        try:
            call = prepare()
        except SeekerError as e:
            self.say(str(e), bad=True)
            return
        self.run(kind, call, notice)

    def new_beat(self):
        def prepare():
            args = dict(self.music(), drums=self.opts["drums"].get(),
                        play=self.opts["autoPlay"].get(),
                        new_pattern=self.opts["newPattern"].get())
            return lambda: self.engine.new_beat(**args)
        self.start("beat", prepare)

    def new_song(self):
        def prepare():
            args = dict(self.music(), structure=self.structure.get(),
                        bars=number(self.bars.get(), "Bars", int) or 8, **self.place())
            return lambda: self.engine.new_song(**args)
        self.start("song", prepare, "Writing the song. " + MOUSE)

    def new_ballad(self):
        def prepare():
            args = dict(key=self.key.get(), tempo=number(self.tempo.get(), "Tempo") or 66,
                        build=self.opts["build"].get(),
                        seed=number(self.seed.get(), "Seed", int), **self.place())
            return lambda: self.engine.new_ballad(**args)
        self.start("ballad", prepare, "Writing the ballad (40 bars, in a major key). " + MOUSE)

    def add_pattern(self):
        def prepare():
            if self.pattern is None:
                raise SeekerError("FL Studio isn't connected.")
            section = {"pattern": self.pattern, "bars": number(self.bars.get(), "Bars", int)}
            where = self.place()
            return lambda: self.engine.arrange([section], **where)
        self.start("arrange", prepare, "Placing the pattern. " + MOUSE)

    def build(self):
        def prepare():
            genre = self.need_genre("the kit")
            parts = [p for p, key in (("drums", "drums"), ("bass", "bass"), ("chords", "chords"),
                                      ("pad", "synth"), ("guitar", "guitar"))
                     if self.opts[key].get()]
            if not parts:
                raise SeekerError("Every part is switched off - tick the ones to build.")
            return lambda: self.engine.build_rack(genre, parts)
        self.start("build", prepare, "Building the kit: a few seconds per channel, and FL "
                                     "comes to the front. Channels can't be removed from here.")

    def route(self):
        self.start("route", lambda: self.engine.route_channels)

    def mix_eq(self):
        def prepare():
            genre = self.need_genre("the EQ")
            return lambda: self.engine.mix_eq(genre)
        self.start("eq", prepare)

    def find(self):
        def prepare():
            search, kind = self.search.get(), self.kind.get()
            return lambda: self.engine.list_sounds(search, kind, 100)
        self.start("sounds", prepare)

    def add(self):
        def prepare():
            picked = self.found.curselection()
            if not picked:
                raise SeekerError("Find a sound and pick it in the list first.")
            sound, name = self.found.get(picked[0]), self.name.get().strip() or None
            return lambda: self.engine.add_channel(sound, name)
        self.start("add", prepare, "Loading the sound: FL comes to the front. "
                                   "The channel can't be removed from here.")

    def rename(self):
        def prepare():
            picked, name = self.tree.selection(), self.name.get().strip()
            if not picked or not name:
                raise SeekerError("Pick a channel in the list and type its new name. A style "
                                  "word says what it suits: Rock Kick, 808 Bass, Cello.")
            index = int(picked[0])
            return lambda: self.engine.set_channel(index, name=name)
        self.start("rename", prepare)

    def back(self):
        if self.engine.can_go_back:
            self.run("back", self.engine.back)

    def finished(self, kind, result, error):
        self.busy = False
        for b in self.buttons:
            b.config(state="normal")
        self.back_btn.config(state="normal" if self.engine.can_go_back else "disabled")
        if self.refocus:
            self.root.after(150, self.root.focus_force)
        if error:
            if "isn't answering" in error and not link.problem():
                error = NOT_ANSWERING   # the window's own wording: it holds the ports itself
            if "build=true" in error:   # the engine words it for the MCP tools
                error += "\nHere: tick Build rack (or Rack > Build kit)."
            self.say(error, bad=True)
        elif kind == "back":
            text = ("Took %d clips out of the playlist." % result["removedClips"]
                    if "removedClips" in result else "Restored the previous beat.")
            self.say("\n".join([text] + result["problems"]), bad=bool(result["problems"]))
        elif kind == "sounds":
            self.found.delete(0, "end")
            for s in result["sounds"]:
                self.found.insert("end", s["id"])
            self.say("%d sounds found%s." % (result["total"], ", the first %d shown - add a "
                                             "word to narrow it" % result["shown"]
                                             if result["total"] > result["shown"] else ""))
        elif kind == "rename":
            self.say("\n".join(["Channel %d is now %s." % (result["channel"], result["name"])]
                               + result["warnings"]))
        else:
            self.say(TEXT[kind](result), bad=bool(troubles(result)))

    def close(self):
        self.settings.update({k: v.get() for k, v in self.opts.items()})
        for box in (self.tempo, self.structure, self.bars, self.track):
            self.settings[box.setting] = box.get().strip()
        try:
            self.settings["tab"] = self.tabs.index("current")
        except tk.TclError:
            pass
        self.settings.update(key=self.key.get(), scale=self.scale.get(),
                             genre=self.genre.get(), hotkey=self.hotkey,
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
