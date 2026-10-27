"""PuppyClicker SSE to XToys START/STOP desktop bridge."""
import json
import os
import sys
import subprocess
import queue
import threading
import time
import tkinter as tk
from collections import deque
from pathlib import Path
from tkinter import messagebox
import customtkinter as ctk

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name('.env'))

SETTINGS_PATH = Path(__file__).with_name("settings.json")

def load_settings():
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return {"click_seconds": min(10., max(.5, float(data.get("click_seconds", 2)))),
                "max_remaining": min(120., max(5., float(data.get("max_remaining", 60)))),
                "language": data.get("language", "en") if data.get("language") in TRANSLATIONS else "en", "theme": data.get("theme", os.getenv("PUPPY_THEME", "lavender")), "channel": data.get("channel", "Both") if data.get("channel") in ("A", "B", "Both") else "Both", "intensity_a": min(100, max(0, int(data.get("intensity_a", 30)))), "intensity_b": min(100, max(0, int(data.get("intensity_b", 30))))}
    except (OSError, ValueError, TypeError):
        return {"click_seconds": 2., "max_remaining": 60., "language": "en", "theme": os.getenv("PUPPY_THEME", "lavender"), "channel": "Both", "intensity_a": 30, "intensity_b": 30}

# External localisation and theme files live alongside this script.
BASE_DIR = Path(__file__).resolve().parent
LOCALES_DIR = BASE_DIR / "locales"
THEMES_DIR = BASE_DIR / "themes"

def load_locales():
    languages = {}
    for path in sorted(LOCALES_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "subtitle" in data and "log_messages" in data:
                languages[path.stem] = data
        except (OSError, ValueError) as exc:
            print(f"Skipping invalid translation {path.name}: {exc}")
    if "en" not in languages:
        raise RuntimeError("Missing valid locales/en.json")
    return languages

TRANSLATIONS = load_locales()

def load_theme(theme_name=None):
    theme_name = theme_name or load_settings()["theme"]
    if not theme_name.replace("-", "").replace("_", "").isalnum():
        raise ValueError("Invalid theme name")
    path = THEMES_DIR / (theme_name + ".json")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("colours"), dict):
        raise ValueError("Theme requires a colours object")
    # Backward compatibility: older themes used hex-coded colour names.
    legacy = {
        "colour_101218": "window_background",
        "colour_13161d": "log_background",
        "colour_171321": "channel_selected_text",
        "colour_1c2029": "card_background",
        "colour_20172f": "primary_button_text",
        "colour_2b233d": "countdown_card_background",
        "colour_2c303a": "input_background",
        "colour_30323c": "channel_unselected_background",
        "colour_343044": "dropdown_background",
        "colour_414352": "channel_unselected_hover",
        "colour_4d405e": "progress_track",
        "colour_4e4b5a": "input_border",
        "colour_54446f": "dropdown_button",
        "colour_69558a": "dropdown_button_hover",
        "colour_713e49": "emergency_button",
        "colour_8c4c59": "emergency_button_hover",
        "colour_b9b6c8": "subtitle_text",
        "colour_bba0ea": "primary_button",
        "colour_c7c9d4": "log_text",
        "colour_c9a7ff": "accent",
        "colour_cba8ff": "countdown_progress",
        "colour_cbbde2": "countdown_caption",
        "colour_d0b7ff": "primary_button_hover",
        "colour_d6c5f4": "connection_status_text",
        "colour_d7c6ee": "click_count_text",
        "colour_d8c0ff": "intensity_value_text",
        "colour_e4e4ed": "body_text",
        "colour_e5d4ff": "slider_thumb",
        "colour_f0e9ff": "app_title_text",
        "colour_f6edff": "countdown_text",
        "colour_ffe3e7": "emergency_button_text",
        "colour_ffffff": "switch_thumb",
    }
    colours = data["colours"]
    for old_key, semantic_key in legacy.items():
        if semantic_key not in colours and old_key in colours:
            colours[semantic_key] = colours[old_key]
    return data

LEGACY_COLOURS = {
    "colour_101218": "window_background",
    "colour_13161d": "log_background",
    "colour_171321": "channel_selected_text",
    "colour_1c2029": "card_background",
    "colour_20172f": "primary_button_text",
    "colour_2b233d": "countdown_card_background",
    "colour_2c303a": "input_background",
    "colour_30323c": "channel_unselected_background",
    "colour_343044": "dropdown_background",
    "colour_414352": "channel_unselected_hover",
    "colour_4d405e": "progress_track",
    "colour_4e4b5a": "input_border",
    "colour_54446f": "dropdown_button",
    "colour_69558a": "dropdown_button_hover",
    "colour_713e49": "emergency_button",
    "colour_8c4c59": "emergency_button_hover",
    "colour_b9b6c8": "subtitle_text",
    "colour_bba0ea": "primary_button",
    "colour_c7c9d4": "log_text",
    "colour_c9a7ff": "accent",
    "colour_cba8ff": "countdown_progress",
    "colour_cbbde2": "countdown_caption",
    "colour_d0b7ff": "primary_button_hover",
    "colour_d6c5f4": "connection_status_text",
    "colour_d7c6ee": "click_count_text",
    "colour_d8c0ff": "intensity_value_text",
    "colour_e4e4ed": "body_text",
    "colour_e5d4ff": "slider_thumb",
    "colour_f0e9ff": "app_title_text",
    "colour_f6edff": "countdown_text",
    "colour_ffe3e7": "emergency_button_text",
    "colour_ffffff": "switch_thumb",
}
REQUIRED_COLOURS = set(LEGACY_COLOURS.values())
THEME = load_theme()

def theme_colour(key):
    return THEME["colours"][key]

def theme_font(role="body", size=None, weight=None):
    """Resolve a font role from the selected external theme."""
    fonts = THEME.get("fonts", {})
    if not isinstance(fonts, dict):
        fonts = {}
    defaults = fonts.get("default", {})
    options = dict(defaults) if isinstance(defaults, dict) else {}
    role_options = fonts.get(role, {})
    if isinstance(role_options, dict):
        options.update(role_options)
    return ctk.CTkFont(
        family=options.get("family", "Segoe UI"),
        size=int(size if size is not None else options.get("size", 14)),
        weight=weight if weight is not None else options.get("weight", "normal"),
        slant=options.get("slant", "roman"),
    )



def translate_log(message, language):
    table = TRANSLATIONS.get(language, TRANSLATIONS["en"]).get("log_messages", {})
    if message in table:
        return table[message]
    prefixes = {
        "Click received; remaining ": "Smellur móttekinn; eftir ",
        "Timing updated: ": "Tímastillingum breytt: ",
        "Stream error: ": "Villa í straumi: ",
        "START FAILED: ": "START MISTÓKST: ",
        "STOP FAILED: ": "STOP MISTÓKST: ",
        "START webhook not configured": "START-vefkrókur ekki stilltur",
        "STOP webhook not configured": "STOP-vefkrókur ekki stilltur"
    }
    if language == "is":
        for original, translated in prefixes.items():
            if message.startswith(original):
                return translated + message[len(original):]
        return message.replace("(delivery not verified)", "(afhending óstaðfest)")
    return message

TICK = 0.1


class Bridge:
    def __init__(self, events):
        self.events = events
        settings = load_settings()
        self.click_seconds = settings["click_seconds"]
        self.max_remaining = settings["max_remaining"]
        self.channel = settings["channel"]
        self.intensity_a = settings["intensity_a"]
        self.intensity_b = settings["intensity_b"]
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.dnd = False
        self.armed = False  # fail closed on launch
        self.active = False
        self.deadline = 0.0
        self.total_clicks = 0
        self.connected = False
        self.seen = set()
        self.seen_order = deque(maxlen=5000)
        self.http = requests.Session()
        self.worker = threading.Thread(target=self.run, daemon=True)
        self.ticker = threading.Thread(target=self.tick, daemon=True)

    def emit(self, message):
        self.events.put(('log', message))

    def config_ok(self):
        return all(os.getenv(k, '').strip() for k in (
            'PUPPY_API_KEY', 'PUPPY_STREAM_URL', 'XTOYS_START_URL', 'XTOYS_STOP_URL'))

    def save_settings(self):
        data = load_settings()
        data.update(click_seconds=self.click_seconds, max_remaining=self.max_remaining, channel=self.channel, intensity_a=self.intensity_a, intensity_b=self.intensity_b)
        SETTINGS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def send_webhook(self, action):
        url = os.getenv('XTOYS_' + action + '_URL', '').strip() or (os.getenv('XTOYS_START_URL', '').strip() if action == 'UPDATE' else '')
        if not url:
            self.emit(f'{action} webhook not configured')
            return False
        method = os.getenv('XTOYS_METHOD', 'POST').strip().upper()
        if method not in ('GET', 'POST'):
            self.emit('Invalid webhook method')
            return False
        raw = os.getenv('XTOYS_' + action + '_JSON', '').strip()
        try:
            payload = json.loads(raw) if raw else {}
            if action in ('START', 'UPDATE'):
                payload.update(action='puppy_' + action.lower(), channel=self.channel, intensity_a=self.intensity_a, intensity_b=self.intensity_b)
            elif action == 'STOP':
                payload['action'] = 'puppy_stop'
            response = requests.request(method, url, json=payload if method == 'POST' else None,
                                        timeout=5, allow_redirects=False)
            response.raise_for_status()
            self.emit(f'{action} HTTP {response.status_code} (delivery not verified)')
            return True
        except (requests.RequestException, ValueError) as exc:
            self.emit(f'{action} FAILED: {exc}')
            return False

    def halt(self, reason, latch=False):
        # Lock prevents START racing with STOP or DND.
        with self.lock:
            was_active = self.active
            self.active = False
            self.deadline = 0
            if latch:
                self.armed = False
            # Send STOP even when state is uncertain: START might have timed out.
            if was_active or latch:
                self.send_webhook('STOP')
            self.emit(reason)

    def set_dnd(self, enabled):
        with self.lock:
            self.dnd = bool(enabled)
            if enabled:
                self.halt('DND enabled: timer cleared', latch=False)
            else:
                self.emit('DND disabled')

    def set_enabled(self, enabled):
        if not enabled:
            self.halt('Bridge switched OFF: timer cleared', latch=True)
            return
        self.arm()

    def arm(self):
        with self.lock:
            if not self.config_ok():
                self.emit('Missing .env configuration; cannot arm')
                return
            if self.dnd:
                self.emit('Disable DND before arming')
                return
            self.armed = True
            self.emit('Bridge armed')

    def update_timing(self, click_seconds, max_remaining):
        with self.lock:
            self.click_seconds = click_seconds
            self.max_remaining = max_remaining
            if self.active:
                self.deadline = min(self.deadline, time.monotonic() + max_remaining)
            self.save_settings()
            self.emit(f"Timing updated: {click_seconds:g}s/click, {max_remaining:g}s maximum remaining")

    def update_output(self, channel, intensity_a, intensity_b):
        with self.lock:
            self.channel = channel
            self.intensity_a = intensity_a
            self.intensity_b = intensity_b
            self.save_settings()
            if self.active and self.armed and not self.dnd:
                if not self.send_webhook("UPDATE"):
                    self.halt("UPDATE failed: stopped and disabled", latch=True)
            self.emit("Output settings saved")

    def emergency(self):
        self.halt('EMERGENCY STOP: bridge disarmed', latch=True)

    def click(self, event_id):
        with self.lock:
            if event_id is not None:
                event_id = str(event_id)
                if event_id in self.seen:
                    return
                if len(self.seen_order) == self.seen_order.maxlen:
                    self.seen.discard(self.seen_order.popleft())
                self.seen.add(event_id)
                self.seen_order.append(event_id)
            if self.dnd or not self.armed or not self.connected:
                return
            now = time.monotonic()
            if not self.active:
                # Mark active before attempting START so a timeout can still cause STOP.
                self.active = True
                self.deadline = now + min(self.click_seconds, self.max_remaining)
                if not self.send_webhook('START'):
                    self.halt('START failed: disarmed', latch=True)
                    return
            else:
                self.deadline = min(max(self.deadline, now) + self.click_seconds,
                                    now + self.max_remaining)
            self.total_clicks += 1
            self.emit(f'Click received; remaining {max(0, self.deadline - time.monotonic()):.1f}s')

    def handle_message(self, event_type, data, sse_id):
        try:
            obj = json.loads(data)
        except (TypeError, ValueError):
            return
        if not isinstance(obj, dict):
            return
        if event_type not in ('alert', 'message'):
            return
        body = obj.get('data', obj.get('payload', obj))
        if not isinstance(body, dict):
            return
        if body.get('kind') != 'click':
            return
        if body.get('dndSuppressed') is True:
            return
        # Do not treat a missing ID as proof of uniqueness; SSE IDs are an alternative.
        self.click(body.get('id') or obj.get('id') or sse_id)

    def run(self):
        retry = 2
        while not self.stop_event.is_set():
            if not self.config_ok():
                self.emit('Configure .env and restart to connect')
                return
            key = os.getenv('PUPPY_API_KEY', '')
            key = key.strip()
            try:
                with requests.get(os.getenv('PUPPY_STREAM_URL'),
                                  params={'key': key},
                                  headers={'Accept': 'text/event-stream'},
                                  stream=True, timeout=(15, 90)) as response:
                    response.raise_for_status()
                    if 'text/event-stream' not in response.headers.get('Content-Type', ''):
                        raise ValueError('Stream did not return text/event-stream')
                    with self.lock:
                        self.connected = True
                    self.emit('PuppyClicker stream connected')
                    retry = 2
                    event_type, event_id, data_lines = 'message', None, []
                    for raw in response.iter_lines(decode_unicode=True, chunk_size=1):
                        if self.stop_event.is_set():
                            break
                        if raw is None:
                            continue
                        if isinstance(raw, bytes):
                            raw = raw.decode('utf-8', errors='replace')
                        line = raw.rstrip('\r')
                        if not line:
                            if data_lines:
                                self.handle_message(event_type, '\n'.join(data_lines), event_id)
                            event_type, event_id, data_lines = 'message', None, []
                        elif line.startswith('event:'):
                            event_type = line[6:].strip()
                        elif line.startswith('id:'):
                            event_id = line[3:].strip()
                        elif line.startswith('data:'):
                            data_lines.append(line[5:].lstrip(' '))
            except (requests.RequestException, ValueError) as exc:
                self.emit(f'Stream error: {exc}')
            finally:
                with self.lock:
                    self.connected = False
                    self.halt('Stream disconnected; stopped and disarmed', latch=True)
            if self.stop_event.wait(retry):
                break
            retry = min(retry * 2, 30)

    def tick(self):
        while not self.stop_event.wait(TICK):
            with self.lock:
                if self.active and time.monotonic() >= self.deadline:
                    self.halt('Countdown expired: STOP', latch=False)

    def shutdown(self):
        self.stop_event.set()
        self.halt('Application closing', latch=True)


class Panel:
    """Material You-inspired interface; the original bridge engine is unchanged."""
    def __init__(self):
        ctk.set_appearance_mode(THEME.get("appearance", "dark"))
        ctk.set_default_color_theme("blue")
        self.root = ctk.CTk(fg_color=theme_colour("window_background"))
        self.root.title("PuppyClicker · XToys")
        self.root.geometry("760x880")
        self.root.minsize(630, 740)
        self.events = queue.Queue()
        self.bridge = Bridge(self.events)
        self.language = load_settings()["language"]
        self.channel_var = tk.StringVar(value=self.bridge.channel)
        self.click_var = tk.StringVar(value=f"{self.bridge.click_seconds:g}")
        self.cap_var = tk.StringVar(value=f"{self.bridge.max_remaining:g}")
        self.a_var = tk.IntVar(value=self.bridge.intensity_a)
        self.b_var = tk.IntVar(value=self.bridge.intensity_b)
        self.enabled_var = tk.BooleanVar(value=False)
        self.dnd_var = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="—")
        self.remaining = tk.StringVar(value="0.0 s")
        self.count = tk.StringVar(value="0")
        self.widgets = {}
        self.scroll = self.make_scroll()
        self.build()
        self.apply_language()
        self._theme_file = THEMES_DIR / (load_settings()["theme"] + ".json")
        self._theme_stamp = self.theme_stamp()
        self._theme_error_stamp = None
        self._theme_update_pending = False
        self.root.after(600, self.watch_theme)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.bridge.worker.start()
        self.bridge.ticker.start()
        self.root.after(100, self.refresh)

    def make_scroll(self):
        # Recreate the whole scrolling canvas on theme changes, not its
        # individual children: this avoids stale canvas windows/white strips.
        scroll = ctk.CTkScrollableFrame(
            self.root, fg_color=theme_colour("window_background"),
            corner_radius=0, scrollbar_fg_color=theme_colour("window_background")
        )
        scroll.pack(fill="both", expand=True, padx=22, pady=16)
        return scroll

    def card(self, parent, color=None):
        f=ctk.CTkFrame(parent, fg_color=color or theme_colour("card_background"), corner_radius=24)
        f.pack(fill="x", pady=(0,12))
        return f

    def label(self, parent, text="", size=None, color=None, weight=None, textvariable=None, role="body"):
        options = {"font": theme_font(role, size, weight), "text_color": color or theme_colour("body_text")}
        if textvariable is not None:
            options["textvariable"] = textvariable
        else:
            options["text"] = text
        return ctk.CTkLabel(parent, **options)

    def build(self):
        header=ctk.CTkFrame(self.scroll,fg_color="transparent")
        header.pack(fill="x",pady=(0,16))
        self.label(header,"PuppyClicker",color=theme_colour("app_title_text"),role="title").pack(side="left")
        self.language_codes={("English" if code=="en" else "Íslenska" if code=="is" else code):code for code in TRANSLATIONS}
        self.language_var=tk.StringVar(value=next((name for name,code in self.language_codes.items() if code==self.language),"English"))
        ctk.CTkOptionMenu(header,values=list(self.language_codes),variable=self.language_var,
                          command=self.change_language, width=128,corner_radius=14,
                          fg_color=theme_colour("dropdown_background"),button_color=theme_colour("dropdown_button"),button_hover_color=theme_colour("dropdown_button_hover"),font=theme_font("dropdown")).pack(side="right")
        # Discover themes from themes/*.json; selection is stored in settings.json.
        self.theme_names = {}
        for path in sorted(THEMES_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data.get("colours"), dict) and all(
                    key in data["colours"] or any(
                        old_name in data["colours"] and new_name == key
                        for old_name, new_name in LEGACY_COLOURS.items()
                    ) for key in REQUIRED_COLOURS
                ):
                    display = str(data.get("name") or path.stem)
                    if display in self.theme_names:
                        display += f" ({path.stem})"
                    self.theme_names[display] = path.stem
            except (OSError, ValueError, TypeError):
                continue
        current_theme = getattr(self, "_selected_theme", load_settings()["theme"])
        selected_theme = next((name for name, code in self.theme_names.items()
                               if code == current_theme), current_theme)
        self.theme_var = tk.StringVar(value=selected_theme)
        ctk.CTkOptionMenu(
            header, values=list(self.theme_names), variable=self.theme_var,
            command=self.change_theme, width=180, corner_radius=14,
            fg_color=theme_colour("dropdown_background"),
            text_color=theme_colour("body_text"),
            button_color=theme_colour("dropdown_button"),
            button_hover_color=theme_colour("dropdown_button_hover"),font=theme_font("dropdown")
        ).pack(side="right", padx=(0, 8))
        self.subtitle=self.label(self.scroll,color=theme_colour("subtitle_text"),role="caption")
        self.subtitle.pack(anchor="w",pady=(0,14))

        hero=self.card(self.scroll,theme_colour("countdown_card_background"))
        top=ctk.CTkFrame(hero,fg_color="transparent")
        top.pack(fill="x",padx=22,pady=(20,2))
        self.connection=self.label(top,color=theme_colour("connection_status_text"),role="status")
        self.connection.pack(side="left")
        self.switch=ctk.CTkSwitch(top,text="",variable=self.enabled_var,command=self.toggle_enabled,
                                  progress_color=theme_colour("accent"),button_color=theme_colour("switch_thumb"),width=48)
        self.switch.pack(side="right")
        self.timer_label=self.label(hero,color=theme_colour("countdown_caption"),role="caption")
        self.timer_label.pack(anchor="w",padx=22,pady=(12,0))
        self.label(hero,textvariable=self.remaining,color=theme_colour("countdown_text"),role="countdown").pack(anchor="w",padx=20)
        self.progress=ctk.CTkProgressBar(hero,height=9,corner_radius=10,progress_color=theme_colour("countdown_progress"),fg_color=theme_colour("progress_track"))
        self.progress.pack(fill="x",padx=22,pady=(6,18))
        self.progress.set(0)
        self.label(hero,textvariable=self.count,color=theme_colour("click_count_text"),role="caption").pack(anchor="w",padx=22,pady=(0,18))

        safety=self.card(self.scroll)
        line=ctk.CTkFrame(safety,fg_color="transparent")
        line.pack(fill="x",padx=20,pady=18)
        self.dnd_label=self.label(line,role="control_heading")
        self.dnd_label.pack(side="left")
        ctk.CTkSwitch(line,text="",variable=self.dnd_var,command=self.toggle_dnd,
                      progress_color=theme_colour("accent"),button_color=theme_colour("switch_thumb")).pack(side="right")
        self.emergency_button=ctk.CTkButton(safety,text="",command=self.emergency,height=46,corner_radius=17,
                          fg_color=theme_colour("emergency_button"),hover_color=theme_colour("emergency_button_hover"),text_color=theme_colour("emergency_button_text"),font=theme_font("button"))
        self.emergency_button.pack(fill="x",padx=18,pady=(0,18))

        output=self.card(self.scroll)
        self.output_title=self.label(output,role="section_heading")
        self.output_title.pack(anchor="w",padx=20,pady=(18,10))
        self.channel_menu=ctk.CTkSegmentedButton(output,values=["A","B","Both"],variable=self.channel_var,
                            selected_color=theme_colour("primary_button"),selected_hover_color=theme_colour("primary_button_hover"),unselected_color=theme_colour("channel_unselected_background"),
                            unselected_hover_color=theme_colour("channel_unselected_hover"),text_color=theme_colour("channel_selected_text"),font=theme_font("button"))
        self.channel_menu.pack(fill="x",padx=20,pady=(0,12))
        self.a_label=self.label(output,role="caption")
        self.a_label.pack(anchor="w",padx=20)
        self.a_value=self.label(output,f"{self.a_var.get()}%",color=theme_colour("intensity_value_text"),role="value")
        self.a_value.pack(anchor="e",padx=20)
        self.a_slider=ctk.CTkSlider(output,from_=0,to=100,number_of_steps=100,command=lambda x:self.update_slider("a",x),progress_color=theme_colour("accent"),button_color=theme_colour("slider_thumb"))
        self.a_slider.pack(fill="x",padx=20,pady=(0,12));self.a_slider.set(self.a_var.get())
        self.b_label=self.label(output,role="caption")
        self.b_label.pack(anchor="w",padx=20)
        self.b_value=self.label(output,f"{self.b_var.get()}%",color=theme_colour("intensity_value_text"),role="value")
        self.b_value.pack(anchor="e",padx=20)
        self.b_slider=ctk.CTkSlider(output,from_=0,to=100,number_of_steps=100,command=lambda x:self.update_slider("b",x),progress_color=theme_colour("accent"),button_color=theme_colour("slider_thumb"))
        self.b_slider.pack(fill="x",padx=20,pady=(0,15));self.b_slider.set(self.b_var.get())
        self.output_apply=ctk.CTkButton(output,command=self.apply_output,corner_radius=15,height=40,fg_color=theme_colour("primary_button"),hover_color=theme_colour("primary_button_hover"),text_color=theme_colour("primary_button_text"),font=theme_font("button"))
        self.output_apply.pack(fill="x",padx=20,pady=(0,18))

        timing=self.card(self.scroll)
        self.timing_title=self.label(timing,role="section_heading")
        self.timing_title.pack(anchor="w",padx=20,pady=(18,12))
        for key,var in (("per_click",self.click_var),("maximum",self.cap_var)):
            row=ctk.CTkFrame(timing,fg_color="transparent")
            row.pack(fill="x",padx=20,pady=5)
            l=self.label(row,role="caption")
            l.pack(side="left")
            self.widgets[key]=l
            ctk.CTkEntry(row,textvariable=var,width=85,height=38,corner_radius=12,fg_color=theme_colour("input_background"),border_color=theme_colour("input_border"),font=theme_font("input")).pack(side="right")
        self.timing_apply=ctk.CTkButton(timing,command=self.apply_timing,corner_radius=15,height=40,fg_color=theme_colour("primary_button"),hover_color=theme_colour("primary_button_hover"),text_color=theme_colour("primary_button_text"),font=theme_font("button"))
        self.timing_apply.pack(fill="x",padx=20,pady=(14,18))

        logs=self.card(self.scroll)
        self.log_title=self.label(logs,role="section_heading")
        self.log_title.pack(anchor="w",padx=20,pady=(18,10))
        self.log=ctk.CTkTextbox(logs,height=145,fg_color=theme_colour("log_background"),text_color=theme_colour("log_text"),corner_radius=16,font=theme_font("log"))
        self.log.pack(fill="x",padx=18,pady=(0,18))
        self.log.configure(state="disabled")

    def t(self,key):
        return TRANSLATIONS.get(self.language, TRANSLATIONS["en"]).get(key, TRANSLATIONS["en"].get(key, key))

    def apply_language(self):
        self.subtitle.configure(text=self.t("subtitle"))
        self.timer_label.configure(text=self.t("timing"))
        self.dnd_label.configure(text=self.t("dnd"))
        self.emergency_button.configure(text=self.t("emergency"))
        self.output_title.configure(text=self.t("output"))
        self.a_label.configure(text=self.t("intensity_a"))
        self.b_label.configure(text=self.t("intensity_b"))
        self.output_apply.configure(text=self.t("apply"))
        self.timing_title.configure(text=self.t("timing"))
        self.widgets["per_click"].configure(text=self.t("per_click"))
        self.widgets["maximum"].configure(text=self.t("maximum"))
        self.timing_apply.configure(text=self.t("apply"))
        self.log_title.configure(text=self.t("log"))

    def change_language(self, value):
        self.language=self.language_codes.get(value, "en")
        self.apply_language()
        try:
            settings=load_settings();settings["language"]=self.language
            SETTINGS_PATH.write_text(json.dumps(settings,indent=2,ensure_ascii=False),encoding="utf-8")
        except OSError as exc:
            messagebox.showerror(self.t("save_title"),str(exc))

    def theme_stamp(self):
        try:
            st = self._theme_file.stat()
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def apply_theme_live(self, theme_name):
        """Apply a theme without touching the running bridge or countdown."""
        global THEME
        updated = load_theme(theme_name)
        if not all(k in updated["colours"] for k in REQUIRED_COLOURS):
            raise ValueError("Theme is missing required colour entries")
        import re
        for key in REQUIRED_COLOURS:
            value = updated["colours"][key]
            if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                raise ValueError(f"Invalid hex colour for {key}: {value!r}")
        fonts = updated.get("fonts", {})
        if not isinstance(fonts, dict):
            raise ValueError("fonts must be an object")
        for role, options in fonts.items():
            if not isinstance(options, dict):
                raise ValueError(f"Font role {role} must be an object")
            if "size" in options and (not isinstance(options["size"], int) or options["size"] <= 0):
                raise ValueError(f"Invalid font size for {role}")
            if options.get("weight", "normal") not in ("normal", "bold"):
                raise ValueError(f"Invalid font weight for {role}")
            if options.get("slant", "roman") not in ("roman", "italic"):
                raise ValueError(f"Invalid font slant for {role}")

        old_log = self.log.get("1.0", "end-1c")
        try:
            scroll_position = self.scroll._parent_canvas.yview()[0]
        except (AttributeError, tk.TclError):
            scroll_position = 0.0
        old_scroll = self.scroll
        self._selected_theme = theme_name
        THEME = updated
        ctk.set_appearance_mode(updated.get("appearance", "dark"))
        self.root.configure(fg_color=theme_colour("window_background"))
        # Remove the entire old scrollable canvas, including its internal
        # window and all drawing primitives, before making the new one.
        old_scroll.destroy()
        self.scroll = self.make_scroll()
        self.widgets.clear()
        self.build()
        self.apply_language()
        self.log.configure(state="normal")
        self.log.insert("end", old_log)
        self.log.see("end")
        self.log.configure(state="disabled")
        self.root.after_idle(lambda: self.restore_scroll(scroll_position))

    def restore_scroll(self, position):
        try:
            if self.scroll.winfo_exists():
                self.scroll._parent_canvas.yview_moveto(position)
        except (AttributeError, tk.TclError):
            pass

    def watch_theme(self):
        try:
            stamp = self.theme_stamp()
            if stamp is not None and stamp != self._theme_stamp and not self._theme_update_pending:
                try:
                    self.apply_theme_live(self._theme_file.stem)
                except (OSError, ValueError, TypeError, KeyError, tk.TclError) as exc:
                    if stamp != self._theme_error_stamp:
                        print(f"Theme edit not applied: {exc}")
                    self._theme_error_stamp = stamp
                else:
                    self._theme_stamp = stamp
                    self._theme_error_stamp = None
        finally:
            if self.root.winfo_exists():
                self.root.after(600, self.watch_theme)

    def change_theme(self, value):
        selected = self.theme_names.get(value)
        if not selected or self._theme_update_pending:
            return
        # CTkOptionMenu may still be processing its click; defer destruction
        # until after its callback AND CustomTkinter's queued focus_set callbacks
        # have finished. Rebuilding earlier destroys the label they target.
        self._theme_update_pending = True
        self.root.after(750, lambda: self.finish_theme_change(selected))

    def finish_theme_change(self, selected):
        try:
            self.apply_theme_live(selected)
            settings = load_settings()
            settings["theme"] = selected
            SETTINGS_PATH.write_text(
                json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            self._theme_file = THEMES_DIR / (selected + ".json")
            self._theme_stamp = self.theme_stamp()
            self._theme_error_stamp = None
        except (OSError, ValueError, TypeError, KeyError, tk.TclError) as exc:
            messagebox.showerror("Theme error", str(exc))
        finally:
            self._theme_update_pending = False

    def update_slider(self, which, value):
        number=int(round(value))
        if which=="a":
            self.a_var.set(number);self.a_value.configure(text=f"{number}%")
        else:
            self.b_var.set(number);self.b_value.configure(text=f"{number}%")

    def toggle_enabled(self):
        self.bridge.set_enabled(bool(self.enabled_var.get()))
        with self.bridge.lock:
            self.enabled_var.set(self.bridge.armed)

    def toggle_dnd(self):
        self.bridge.set_dnd(bool(self.dnd_var.get()))
        with self.bridge.lock:
            self.enabled_var.set(self.bridge.armed)

    def emergency(self):
        self.bridge.emergency()
        self.enabled_var.set(False)

    def apply_output(self):
        try:
            channel=self.channel_var.get();a=self.a_var.get();b=self.b_var.get()
            if channel not in ("A","B","Both") or not (0<=a<=100 and 0<=b<=100):
                raise ValueError
            self.bridge.update_output(channel,a,b)
        except (ValueError,tk.TclError):
            messagebox.showerror(self.t("save_title"),"Select A, B or Both and use 0–100%.")
        except OSError as exc:
            messagebox.showerror(self.t("save_title"),str(exc))

    def apply_timing(self):
        try:
            click=float(self.click_var.get().replace(",",".")); cap=float(self.cap_var.get().replace(",","."))
            if not (0.5<=click<=10 and 5<=cap<=120):raise ValueError
            self.bridge.update_timing(click,cap)
        except (ValueError,OverflowError):
            messagebox.showerror(self.t("invalid_title"),self.t("invalid_message"))
        except OSError as exc:
            messagebox.showerror(self.t("save_title"),str(exc))

    def refresh(self):
        while True:
            try:_,message=self.events.get_nowait()
            except queue.Empty:break
            self.log.configure(state="normal")
            self.log.insert("end",time.strftime("%H:%M:%S ")+translate_log(message,self.language)+"\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        with self.bridge.lock:
            remaining=max(0.,self.bridge.deadline-time.monotonic()) if self.bridge.active else 0.
            connected,dnd,armed,clicks=self.bridge.connected,self.bridge.dnd,self.bridge.armed,self.bridge.total_clicks
            cap=self.bridge.max_remaining
        self.enabled_var.set(armed)
        self.connection.configure(text=self.t("connected" if connected else "disconnected")+"  ·  "+self.t("dnd_status" if dnd else "armed" if armed else "disarmed"))
        self.remaining.set(self.t("remaining").format(value=remaining))
        self.count.set(self.t("count").format(value=clicks))
        self.progress.set(min(1.,remaining/max(1.,cap)))
        self.root.after(100,self.refresh)

    def close(self):
        self.bridge.shutdown()
        self.root.destroy()

if __name__ == '__main__':
    Panel().root.mainloop()
