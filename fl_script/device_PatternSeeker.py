# name=Pattern Seeker
# url=https://github.com/

"""Pattern Seeker - FL Studio side.

A deliberately thin executor. The companion window (pattern_seeker.pyw) decides
WHAT beat to write; this script only knows how to put step-sequencer bits into
the channel rack and report what the rack looks like.

Transport is MIDI SysEx over two loopMIDI ports (FL's script interpreter blocks
file access, so a file mailbox cannot work):

    input  "Pattern Seeker In"   companion -> FL   requests
    output "Pattern Seeker Out"  FL -> companion   responses + a heartbeat (rack
                                                   snapshot) about once a second

The output must have the same port number as the input in FL's MIDI settings.
Packet layout (mirrored in seeker/wire.py):

    F0 7D 50 53  kind  id  index  total  <ascii json>  F7

FL rules that matter here: no threads, and nothing may raise out of a callback.
"""

SCRIPT_VERSION = 7

_ok = False
_err = ""

try:
    import json
    import time

    import channels
    import device
    import general
    import midi
    import mixer
    import patterns
    import transport
    import ui

    _ok = True
except Exception as _e:  # pragma: no cover - only happens inside a broken FL
    _err = str(_e)

HEARTBEAT_SECONDS = 1.0
SCAN_STEPS = 256      # how far we look for old steps to clear
MAX_STEPS = 1024
CT_GEN_PLUG = 2          # channels.getChannelType: a generator plugin
HW_DIRTY_EDIT = 0x20000  # OnRefresh flag FL 2026 sends when a script's edit lands (seen live)
DEFAULT_VELOCITY = 100
DEFAULT_PITCH = 60     # C5: a sampler channel plays its sample untransposed

MAGIC = b"\xF0\x7D\x50\x53"
K_REQUEST, K_RESPONSE, K_HEARTBEAT = 1, 2, 3
CHUNK = 800

_last_beat = 0.0
_velocity_broken = False
_edits = 0              # refreshes that carried HW_DIRTY_EDIT
_view_before = None     # (piano roll was visible, selected channel) before we opened it
_out_id = 0
_no_output_warned = False
_in_id = -1
_in_parts = {}


def _send(kind, payload):
    """Send one JSON message to the companion; False when no output port is linked."""
    global _out_id, _no_output_warned
    try:
        assigned = bool(device.isAssigned())
    except Exception:
        assigned = True
    if not assigned:
        if not _no_output_warned:
            _no_output_warned = True
            print("Pattern Seeker: no output port. In MIDI settings give the output "
                  "'Pattern Seeker Out' the same port number as this input.")
        return False
    _no_output_warned = False
    data = json.dumps(payload, separators=(",", ":")).encode("ascii")
    _out_id = (_out_id + 1) % 128
    total = max(1, -(-len(data) // CHUNK))
    for i in range(total):
        device.midiOutSysex(MAGIC + bytes((kind, _out_id, i, total))
                            + data[i * CHUNK:(i + 1) * CHUNK] + b"\xF7")
    return True


def _tempo():
    try:
        t = float(mixer.getCurrentTempo())
        return t / 1000.0 if t > 1000 else t
    except Exception:
        return 0.0


def _pattern_steps(pat):
    """Pattern length in 16th steps (0 when unknown/empty).

    The manual says getPatternLength counts beats; FL 2026 really returns steps
    (an empty pattern is 16, and drums out to step 1024 give 1024)."""
    try:
        return max(0, int(patterns.getPatternLength(pat)))
    except Exception:
        return 0


def _instrument(ch):
    """The plugin on an instrument channel ("FL Keys", "Sytrus"...), "" for
    samplers and the rest. Channel names follow the preset ("default",
    "Padilion"), so this is what tells the companion where the keys are."""
    try:
        if int(channels.getChannelType(ch)) != CT_GEN_PLUG:
            return ""
        import plugins
        return str(plugins.getPluginName(ch))
    except Exception:
        return ""


def _snapshot():
    pat = int(patterns.patternNumber())
    chans = []
    for i in range(int(channels.channelCount())):
        try:
            chans.append({"index": i, "name": str(channels.getChannelName(i)),
                          "plugin": _instrument(i)})
        except Exception:
            pass
    try:
        name = str(patterns.getPatternName(pat))
    except Exception:
        name = ""
    try:
        playing = bool(transport.isPlaying())
    except Exception:
        playing = False
    return {
        "version": SCRIPT_VERSION,
        "time": time.time(),
        "pattern": pat,
        "patternName": name,
        "patternSteps": _pattern_steps(pat),
        "tempo": _tempo(),
        "playing": playing,
        "channels": chans,
    }


def _heartbeat():
    global _last_beat
    _last_beat = time.time()
    try:
        _send(K_HEARTBEAT, _snapshot())
    except Exception as e:
        print("Pattern Seeker: heartbeat failed - %s" % e)


def _read_track(ch, scan):
    """Current step bits (trimmed to the last lit step), velocities and pitches."""
    bits = [1 if channels.getGridBit(ch, s) else 0 for s in range(scan)]
    last = 0
    for s in range(scan):
        if bits[s]:
            last = s + 1
    bits = bits[:last]
    out = []
    for param, default in ((midi.pVelocity, DEFAULT_VELOCITY), (midi.pPitch, DEFAULT_PITCH)):
        try:
            out.append([int(channels.getCurrentStepParam(ch, s, param)) if bits[s]
                        else default for s in range(last)])
        except Exception:
            out.append(None)
    return bits, out[0], out[1]


def _apply(req):
    global _velocity_broken
    tracks = req.get("tracks") or []
    warnings = []

    # The companion mapped roles from a heartbeat up to a second old. Refuse to
    # write if the rack was reordered since, rather than hit the wrong channel.
    count = int(channels.channelCount())
    for t in tracks:
        ch = int(t["channel"])
        if ch < 0 or ch >= count or str(channels.getChannelName(ch)) != t.get("name"):
            return {"ok": False, "error": "rack_changed"}

    try:
        if not general.safeToEdit():
            return {"ok": False, "error": "busy"}
    except Exception:
        pass

    if req.get("newPattern"):
        try:
            patterns.findFirstNextEmptyPat(midi.FFNEP_DontPromptName)
        except Exception as e:
            warnings.append("could not open a new pattern: %s" % e)

    pat = int(patterns.patternNumber())
    pat_steps = min(_pattern_steps(pat), MAX_STEPS)
    scan = max(SCAN_STEPS, pat_steps)

    prev = []
    for t in tracks:
        ch = int(t["channel"])
        bits = [1 if b else 0 for b in (t.get("bits") or [])][:MAX_STEPS]
        vel = t.get("vel")
        length = len(bits)
        pitch = t.get("pitch")
        old_bits, old_vel, old_pitch = _read_track(ch, scan)
        prev.append({"channel": ch, "name": t.get("name"),
                     "bits": old_bits, "vel": old_vel})
        if pitch and old_pitch is not None:
            prev[-1]["pitch"] = old_pitch   # only channels whose notes we change

        # Tile the beat under whatever else is in the pattern (a 4-bar melody
        # gets 4 bars of drums), unless the caller wants an exact restore.
        fill = length
        if req.get("fill") and length:
            # minSteps: the chords' four-bar cycle needs the drums to last as long.
            fill = max(length, min(MAX_STEPS, int(req.get("minSteps") or 0)),
                       ((pat_steps + 15) // 16) * 16)

        old = old_bits + [0] * (scan - len(old_bits))
        for s in range(max(scan, fill)):
            want = bits[s % length] if (length and s < fill) else 0
            have = old[s] if s < len(old) else 0
            if want != have:
                channels.setGridBit(ch, s, want)

        if not _velocity_broken and length:
            try:
                for s in range(fill):
                    if bits[s % length]:
                        v = DEFAULT_VELOCITY
                        if vel and (s % length) < len(vel):
                            v = int(vel[s % length])
                        channels.setStepParameterByIndex(
                            ch, pat, s, midi.pVelocity, max(1, min(127, v)))
            except Exception as e:
                _velocity_broken = True
                warnings.append("step velocities unavailable: %s" % e)

        if pitch and length:
            try:
                for s in range(fill):
                    i = s % length
                    if bits[i] and i < len(pitch):
                        channels.setStepParameterByIndex(
                            ch, pat, s, midi.pPitch, max(0, min(127, int(pitch[i]))))
            except Exception as e:
                warnings.append("808 notes not set: %s" % e)

    name = req.get("patternName")
    if name:
        try:
            current = str(patterns.getPatternName(pat))
            if req.get("newPattern") or current.startswith("Pattern ") \
                    or current.startswith("Seek ") or not current:
                patterns.setPatternName(pat, str(name)[:60])
        except Exception:
            pass

    bpm = req.get("tempo")
    if bpm:
        try:
            general.processRECEvent(
                midi.REC_Tempo, int(round(float(bpm) * 1000)),
                midi.REC_Control | midi.REC_UpdateControl)
        except Exception as e:
            warnings.append("tempo not set: %s" % e)

    try:
        general.saveUndo("Pattern Seeker beat", midi.UF_PR)
    except Exception:
        pass

    if req.get("autoPlay"):
        try:
            # Only in pattern mode - never start the whole song unasked.
            if not transport.isPlaying() and transport.getLoopMode() == 0:
                transport.start()
        except Exception:
            pass

    res = {"ok": True, "pattern": pat, "prev": prev, "warnings": warnings}
    if req.get("pianoRoll"):
        res["pianoRoll"] = _open_piano_roll(req["pianoRoll"])
    return res


def _open_piano_roll(target):
    """Point the piano roll at the chords channel and focus it, ready for the
    companion to run its piano-roll script. Returns "" or what went wrong.

    An open piano roll keeps showing its old channel when another is selected,
    so it is hidden first: select, then show, is what retargets it."""
    global _view_before
    try:
        ch = int(target["channel"])
        if ch < 0 or ch >= int(channels.channelCount()) \
                or str(channels.getChannelName(ch)) != target.get("name"):
            return "rack_changed"
        was_visible = bool(ui.getVisible(midi.widPianoRoll))
        if _view_before is None:        # a second open before the close keeps the first
            _view_before = (was_visible, int(channels.selectedChannel()))
        if was_visible:
            ui.hideWindow(midi.widPianoRoll)
        channels.selectOneChannel(ch)
        if int(channels.selectedChannel()) != ch:
            return "could not select the channel"
        ui.showWindow(midi.widPianoRoll)
        ui.setFocused(midi.widPianoRoll)
        return ""
    except Exception as e:
        return str(e)


def _close_piano_roll():
    """Put the piano roll and the channel selection back as they were."""
    global _view_before
    before, _view_before = _view_before, None
    if before is None:
        return
    was_visible, selected = before
    ui.hideWindow(midi.widPianoRoll)
    if 0 <= selected < int(channels.channelCount()):
        channels.selectOneChannel(selected)
    if was_visible:
        ui.showWindow(midi.widPianoRoll)


def _handle(req):
    global _last_beat
    try:
        cmd = req.get("cmd", "apply")
        if cmd == "apply":
            res = _apply(req)
        elif cmd == "pianoRoll":    # aim the piano roll at another channel
            res = {"ok": True, "pianoRoll": _open_piano_roll(req["pianoRoll"])}
        elif cmd == "edits":    # has the piano-roll script run since we last asked?
            res = {"ok": True, "edits": _edits}
        elif cmd == "closePianoRoll":
            _close_piano_roll()
            res = {"ok": True}
        elif cmd == "read":     # look, don't touch: used to check what FL stored
            bits, vel, pitch = _read_track(int(req["channel"]), SCAN_STEPS)
            res = {"ok": True, "bits": bits, "vel": vel, "pitch": pitch}
        else:
            res = {"ok": True}
    except Exception as e:
        res = {"ok": False, "error": "exception", "detail": str(e)}
    res["id"] = req.get("id")
    try:
        res["state"] = _snapshot()     # doubles as a fresh heartbeat
        _send(K_RESPONSE, res)
        _last_beat = time.time()
    except Exception as e:
        print("Pattern Seeker: could not answer - %s" % e)


def OnRefresh(flags):
    """A piano-roll script cannot tell anyone it ran (FL blocks its file and
    environment access too), but FL reports the edit it made: count those."""
    global _edits
    if flags & HW_DIRTY_EDIT:
        _edits += 1


def OnInit():
    if not _ok:
        print("Pattern Seeker: failed to load - %s" % _err)
        return
    try:
        print("Pattern Seeker: ready (v%d, SysEx link)" % SCRIPT_VERSION)
        try:
            print("Pattern Seeker: input port %s, output linked: %s"
                  % (device.getPortNumber(), bool(device.isAssigned())))
        except Exception as e:
            print("Pattern Seeker: could not read port info - %s" % e)
        print("Pattern Seeker: first heartbeat sent: %s" % _send(K_HEARTBEAT, _snapshot()))
    except Exception as e:
        print("Pattern Seeker: init error - %s" % e)


def OnDeInit():
    pass


def OnSysEx(event):
    global _in_id, _in_parts
    if not _ok:
        return
    try:
        data = getattr(event, "sysex", None)
        if data is None:
            return
        data = bytes(data)
        if len(data) < 9 or data[:4] != MAGIC:
            return                      # someone else's SysEx
        event.handled = True
        kind, msg_id, index, total = data[4:8]
        if kind != K_REQUEST:
            return
        if msg_id != _in_id or index == 0:
            _in_id, _in_parts = msg_id, {}
        _in_parts[index] = data[8:-1] if data[-1] == 0xF7 else data[8:]
        if len(_in_parts) < total:
            return
        raw = b"".join(_in_parts[i] for i in range(total))
        _in_id, _in_parts = -1, {}
        _handle(json.loads(raw.decode("ascii")))
    except Exception as e:
        print("Pattern Seeker: bad request - %s" % e)


def OnIdle():
    if not _ok:
        return
    try:
        if time.time() - _last_beat >= HEARTBEAT_SECONDS:
            _heartbeat()
    except Exception as e:
        print("Pattern Seeker: idle error - %s" % e)
