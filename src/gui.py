"""Desktop UI: pick which actions run, set the activity level, start/stop, watch the log."""

from __future__ import annotations

import logging
import queue
import threading
import time
import tkinter as tk

from src.hotkeys import HotkeyManager
from src.main import LOG_FMT, _run_actions
from src.power import PowerManager
from src.scheduler import Intensity

BG = "#FFFFFF"
CARD = "#F7F7F7"
BORDER = "#E2E2E2"
KEYCAP = "#EBEBEB"
TEXT = "#111111"
MUTED = "#5F5F5F"  # 6:1 on CARD
DISABLED = "#A3A3A3"
TRACK_OFF = "#D4D4D4"
GO = "#15803D"
STOP = "#B91C1C"
FONT = ("Segoe UI", 11)
FONT_SMALL = ("Segoe UI", 9)
FONT_BOLD = ("Segoe UI Semibold", 11)
FONT_HEAD = ("Segoe UI Semibold", 12)

LEVELS = (Intensity.LOW, Intensity.MED, Intensity.HIGH)
# (ACTIONS key, label, hint, on by default)
FEATURES = (
    ("move", "Mouse Movement", "Small random nudges", True),
    ("click", "Mouse Clicks", "Clicks inside a safe zone", False),
    ("scroll", "Scrolling", "Small scroll steps", True),
    ("tabs", "Tab Switching", "Ctrl+Tab in the active window", False),
    ("apps", "App Switching", "Alt+Tab to the next app", False),
    ("keys", "Keyboard Activity", "", True),
)
HOW_TO = (
    ("Choose what runs",
     "Turn on the actions you want in Automation Settings. Mouse Clicks, Tab Switching and App Switching "
     "are off by default because they change what's on your screen."),
    ("Set the pace",
     "Drag Activity Level. Low acts every 3–12 s, Med every 2–8 s, High about every 1–4 s. "
     "Micro-breaks add short pauses every few minutes so the activity isn't constant."),
    ("Know what the keyboard does",
     "Keyboard Activity presses navigation and media keys (arrows, Page Up/Down, F5, volume, play/pause), "
     "so it can change your volume or refresh a page. With Advanced Mode on it types short words "
     "like \"ok\" into whatever window is focused instead."),
    ("Start",
     "Press Start or Ctrl+Shift+Space. The timer at the top shows it's running; settings lock until you stop."),
    ("Stop",
     "Press Stop, Esc (while this window is focused), Ctrl+Shift+Esc (this also opens Task Manager), "
     "or Ctrl+Alt+Shift for an emergency stop."),
    ("While it runs",
     "Your PC won't go to sleep; normal sleep settings come back when you stop. Every action is listed in "
     "Activity Log and saved to %LOCALAPPDATA%\\reminder\\reminder.log."),
)
# Must match src/hotkeys.py.
SHORTCUTS = (
    (("Ctrl", "Shift", "Space"), "Start"),
    (("Ctrl", "Shift", "Esc"), "Stop"),
    (("Ctrl", "Alt", "Shift"), "Emergency Stop"),
)


class _QueueHandler(logging.Handler):
    """Hand log lines from the worker thread to the Tk thread."""

    def __init__(self, q: "queue.Queue[str]") -> None:
        super().__init__()
        self.q = q

    def emit(self, record: logging.LogRecord) -> None:
        self.q.put(self.format(record))


class Switch(tk.Canvas):
    """Pill on/off switch bound to a BooleanVar; click or Space toggles it."""

    W, H, P = 40, 22, 2

    def __init__(self, parent: tk.Misc, var: tk.BooleanVar) -> None:
        bg = parent.cget("bg")
        super().__init__(parent, width=self.W + 2 * self.P, height=self.H + 2 * self.P, bg=bg, cursor="hand2",
                         takefocus=1, highlightthickness=1, highlightbackground=bg, highlightcolor=TEXT)
        self.var = var
        self.bind("<Button-1>", self._flip)
        self.bind("<space>", self._flip)
        var.trace_add("write", lambda *_: self.draw())
        self.draw()

    def _flip(self, _event: object = None) -> None:
        if self.cget("state") != "disabled":
            self.var.set(not self.var.get())

    def draw(self) -> None:
        on, off = self.var.get(), self.cget("state") == "disabled"
        track = (DISABLED if off else TEXT) if on else (KEYCAP if off else TRACK_OFF)
        p, w, h = self.P, self.W, self.H
        self.delete("all")
        self.create_oval(p, p, p + h, p + h, fill=track, outline="")
        self.create_oval(p + w - h, p, p + w, p + h, fill=track, outline="")
        self.create_rectangle(p + h / 2, p, p + w - h / 2, p + h, fill=track, outline="")
        x = p + w - h + 3 if on else p + 3
        self.create_oval(x, p + 3, x + h - 6, p + h - 3, fill=BG, outline="")


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.worker: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.started_at = 0.0
        self.log_q: "queue.Queue[str]" = queue.Queue()

        handler = _QueueHandler(self.log_q)
        handler.setFormatter(logging.Formatter(LOG_FMT, "%H:%M:%S"))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.DEBUG)

        root.title("reminder")
        root.configure(bg=BG, padx=20, pady=16)
        root.minsize(860, 680)
        root.columnconfigure((0, 1), weight=1, uniform="col")
        root.rowconfigure(0, weight=1)
        left = tk.Frame(root, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        right = tk.Frame(root, bg=BG)
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        # Left column: mode, actions, level, start.
        header = tk.Frame(left, bg=BG)
        header.pack(fill="x", pady=(0, 8))
        tk.Label(header, text="reminder", font=("Segoe UI Semibold", 22), fg=TEXT, bg=BG).pack(side="left")
        self.help_win: tk.Toplevel | None = None
        tk.Button(header, text="How to use", font=FONT, fg=TEXT, bg=BG, activebackground=CARD, relief="solid",
                  bd=1, padx=10, cursor="hand2", command=self.show_help).pack(side="right")
        self.status = tk.Label(header, font=FONT_BOLD, bg=BG)
        self.status.pack(side="right", padx=(0, 12))

        self.switches: list[Switch] = []
        self.advanced = tk.BooleanVar(value=False)
        self._toggle_row(left, "Advanced Mode", "", self.advanced)

        card = self._card(left, "Automation Settings")
        self.features: dict[str, tk.BooleanVar] = {}
        for key, label, hint, default in FEATURES:
            self.features[key] = tk.BooleanVar(value=default)
            sw, hint_label = self._toggle_row(card, label, hint, self.features[key])
            if key == "keys":
                self.key_actions, self.keys_hint = sw, hint_label
        self.enable_key_actions = self.features["keys"]
        self.breaks = tk.BooleanVar(value=True)
        self._toggle_row(card, "Micro-breaks", "Short pauses every few minutes", self.breaks)

        level = tk.Frame(left, bg=BG)
        level.pack(fill="x", pady=(4, 12))
        level.columnconfigure(1, weight=1)
        tk.Label(level, text="Activity Level", font=FONT, fg=TEXT, bg=BG).grid(row=1, column=0, sticky="w", padx=(0, 16))
        names = tk.Frame(level, bg=BG)
        names.grid(row=0, column=1, sticky="ew")
        self.level = tk.IntVar(value=1)
        self.level_labels = []
        for i, (name, anchor) in enumerate(zip(LEVELS, ("w", "center", "e"))):
            names.columnconfigure(i, weight=1)
            lbl = tk.Label(names, text=name.capitalize(), font=FONT_SMALL, fg=MUTED, bg=BG, cursor="hand2")
            lbl.grid(row=0, column=i, sticky=anchor if anchor != "center" else "")
            lbl.bind("<Button-1>", lambda _e, i=i: self.scale.cget("state") != "disabled" and self.level.set(i))
            self.level_labels.append(lbl)
        self.scale = tk.Scale(level, from_=0, to=2, orient="horizontal", variable=self.level, showvalue=False,
                              bg=TEXT, activebackground=TEXT, troughcolor=TRACK_OFF, sliderlength=40, width=8,
                              bd=0, sliderrelief="flat", highlightthickness=1, highlightbackground=BG,
                              highlightcolor=TEXT, cursor="hand2")
        self.scale.grid(row=1, column=1, sticky="ew")

        self.toggle = tk.Button(left, font=FONT_BOLD, fg=BG, relief="flat", cursor="hand2", pady=10,
                                command=self.on_toggle)
        self.toggle.pack(fill="x")
        self.error = tk.Label(left, font=FONT_SMALL, fg=STOP, bg=BG, anchor="w")
        self.error.pack(fill="x", pady=(4, 0))

        # Right column: shortcuts, permissions, log.
        keys = self._card(right, "Keyboard Shortcuts")
        grid = tk.Frame(keys, bg=CARD)
        grid.pack(anchor="w")
        for r, (combo, action) in enumerate(SHORTCUTS):
            caps = tk.Frame(grid, bg=CARD)
            caps.grid(row=r, column=0, sticky="w", pady=4)
            for cap in combo:
                tk.Label(caps, text=cap, font=FONT_SMALL, fg=TEXT, bg=KEYCAP, padx=6, pady=2).pack(side="left", padx=(0, 4))
            tk.Label(grid, text=action, font=FONT, fg=MUTED, bg=CARD).grid(row=r, column=1, sticky="w", padx=(12, 0))

        perms = self._card(right, "Permissions")
        tk.Label(perms, font=FONT, fg=MUTED, bg=CARD, justify="left", anchor="w", wraplength=340,
                 text="Shortcuts don't reach windows running as administrator. "
                      "If they don't work there, run reminder as administrator too.").pack(fill="x")

        log_card = self._card(right, "Activity Log", expand=True)
        self.log = tk.Text(log_card, height=8, font=("Consolas", 9), bg=BG, fg=TEXT, relief="flat",
                           highlightthickness=1, highlightbackground=BORDER, padx=8, pady=6,
                           state="disabled", wrap="none")
        self.log.pack(fill="both", expand=True)

        self._hotkey_start = threading.Event()
        self.hotkeys = HotkeyManager(on_start=self._hotkey_start.set, on_stop=self.stop,
                                     on_emergency=self.on_emergency)
        self.hotkeys.start()

        root.bind("<Escape>", lambda _e: self.stop())
        root.bind("<F1>", lambda _e: self.show_help())
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._render()
        self._poll()

    @staticmethod
    def _card(parent: tk.Frame, title: str, expand: bool = False) -> tk.Frame:
        card = tk.Frame(parent, bg=CARD, padx=16, pady=14, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="both" if expand else "x", expand=expand, pady=(0, 14))
        tk.Label(card, text=title, font=FONT_HEAD, fg=TEXT, bg=CARD).pack(anchor="w", pady=(0, 8))
        return card

    def _toggle_row(self, parent: tk.Frame, label: str, hint: str,
                    var: tk.BooleanVar) -> tuple[Switch, tk.Label]:
        bg = parent.cget("bg")
        row = tk.Frame(parent, bg=bg)
        row.pack(fill="x", pady=(2, 6))
        row.columnconfigure(0, weight=1)
        tk.Label(row, text=label, font=FONT, fg=TEXT, bg=bg).grid(row=0, column=0, sticky="w")
        hint_label = tk.Label(row, text=hint, font=FONT_SMALL, fg=MUTED, bg=bg)
        if hint or label == "Keyboard Activity":
            hint_label.grid(row=1, column=0, sticky="w", padx=(14, 0))
        sw = Switch(row, var)
        sw.grid(row=0, column=1, rowspan=2)
        self.switches.append(sw)
        return sw, hint_label

    def show_help(self) -> None:
        if self.help_win is not None and self.help_win.winfo_exists():
            self.help_win.lift()
            return
        win = self.help_win = tk.Toplevel(self.root, bg=BG, padx=24, pady=20)
        win.title("How to use reminder")
        win.transient(self.root)
        win.resizable(False, False)
        tk.Label(win, text="How to use", font=("Segoe UI Semibold", 16), fg=TEXT, bg=BG).pack(anchor="w", pady=(0, 14))
        for i, (title, body) in enumerate(HOW_TO, start=1):
            row = tk.Frame(win, bg=BG)
            row.pack(fill="x", pady=(0, 12))
            tk.Label(row, text=str(i), font=FONT_BOLD, fg=BG, bg=TEXT, width=2).pack(side="left", anchor="n", padx=(0, 12))
            text = tk.Frame(row, bg=BG)
            text.pack(side="left", fill="x")
            tk.Label(text, text=title, font=FONT_BOLD, fg=TEXT, bg=BG).pack(anchor="w")
            tk.Label(text, text=body, font=FONT, fg=MUTED, bg=BG, wraplength=460, justify="left").pack(anchor="w")
        close = tk.Button(win, text="Got it", font=FONT_BOLD, fg=BG, bg=TEXT, activebackground=TEXT,
                          activeforeground=BG, relief="flat", padx=20, pady=6, cursor="hand2", command=win.destroy)
        close.pack(anchor="e", pady=(4, 0))
        win.bind("<Escape>", lambda _e: win.destroy())
        close.focus_set()

    @property
    def running(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def _worker(self, enabled: set[str], breaks: bool, mode: str, intensity: str) -> None:
        with PowerManager():
            try:
                _run_actions(self.stop_event, mode=mode, intensity=intensity, enabled=enabled, breaks=breaks)
            except Exception as exc:
                logging.error("Fatal error: %s", exc)
        logging.info("Stopped; normal sleep restored.")

    def start(self) -> None:
        if self.running:
            return
        enabled = {key for key, var in self.features.items() if var.get()}
        if not enabled:
            self.error.config(text="Turn on at least one action.")
            return
        self.error.config(text="")
        mode = "advanced" if self.advanced.get() else "basic"
        intensity = LEVELS[self.level.get()]
        self.stop_event.clear()
        self.started_at = time.time()
        logging.info("Started | %s | mode=%s intensity=%s", ",".join(sorted(enabled)), mode, intensity)
        self.worker = threading.Thread(target=self._worker, args=(enabled, self.breaks.get(), mode, intensity),
                                       daemon=True)
        self.worker.start()
        self._render()

    def stop(self) -> None:
        self.stop_event.set()

    def on_toggle(self) -> None:
        self.stop() if self.running else self.start()

    def on_emergency(self) -> None:
        self.stop()
        logging.warning("Emergency stop requested.")

    def on_close(self) -> None:
        self.stop()
        self.hotkeys.stop()
        if self.worker:
            self.worker.join(timeout=2.0)
        self.root.destroy()

    def _render(self) -> None:
        if self.running and self.stop_event.is_set():
            self.status.config(text="● Stopping…", fg=MUTED)
        elif self.running:
            up = int(time.time() - self.started_at)
            self.status.config(text=f"● Running  {up // 3600:02d}:{up // 60 % 60:02d}:{up % 60:02d}", fg=GO)
        else:
            self.status.config(text="● Stopped", fg=MUTED)
        bg, label = (STOP, "Stop  (Esc)") if self.running else (TEXT, "Start")
        self.toggle.config(text=label, bg=bg, activebackground=bg, activeforeground=BG)
        idle = "disabled" if self.running else "normal"
        for sw in self.switches:
            if sw.cget("state") != idle:
                sw.config(state=idle)
                sw.draw()
        self.scale.config(state=idle, bg=DISABLED if self.running else TEXT)
        style = "Natural typing" if self.advanced.get() else "Navigation & media keys"
        self.keys_hint.config(text=f"Keyboard style: {style}")

    def _poll(self) -> None:
        if self._hotkey_start.is_set():  # set from the hotkey thread; Tk calls must stay on this one
            self._hotkey_start.clear()
            self.start()
        lines = []
        while not self.log_q.empty():
            lines.append(self.log_q.get_nowait())
        if lines:
            self.log.config(state="normal")
            self.log.insert("end", "\n".join(lines) + "\n")
            self.log.delete("1.0", "end-500l")  # keep the last 500 lines
            self.log.see("end")
            self.log.config(state="disabled")
        self._render()
        self.root.after(250, self._poll)


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
