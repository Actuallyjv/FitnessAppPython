"""Small reusable Kivy widgets and helpers."""
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

PURPLE = (0.37, 0.15, 0.58, 1)
YELLOW = (1, 0.82, 0.1, 1)
CARD = (0.16, 0.16, 0.2, 1)
BG = (0.09, 0.09, 0.11, 1)
GREEN = (0.2, 0.7, 0.4, 1)
RED = (0.85, 0.25, 0.25, 1)

# Code 39 patterns: 9 elements (bar, space, bar, ...), 'w' = wide, 'n' = narrow.
CODE39 = {
    "0": "nnnwwnwnn", "1": "wnnwnnnnw", "2": "nnwwnnnnw", "3": "wnwwnnnnn", "4": "nnnwwnnnw",
    "5": "wnnwwnnnn", "6": "nnwwwnnnn", "7": "nnnwnnwnw", "8": "wnnwnnwnn", "9": "nnwwnnwnn",
    "G": "nnnnnwwnw", "M": "wnwnnnnwn", "Y": "wwnnwnnnn", "*": "nwnnwnwnn",
}


def code39_bars(text):
    """Return a list of (is_bar, width_units) for a Code 39 barcode of `text`."""
    out = []
    for i, ch in enumerate(f"*{text}*"):
        if i:
            out.append((False, 1))  # inter-character gap
        for j, e in enumerate(CODE39[ch]):
            out.append((j % 2 == 0, 3 if e == "w" else 1))
    return out


class Barcode(Widget):
    def __init__(self, text, **kw):
        super().__init__(size_hint_y=None, height=dp(90), **kw)
        self.text = text
        self.bind(pos=self._draw, size=self._draw)

    def _draw(self, *_):
        self.canvas.clear()
        bars = code39_bars(self.text)
        units = sum(w for _, w in bars)
        u = self.width / units
        with self.canvas:
            Color(1, 1, 1, 1)
            Rectangle(pos=self.pos, size=self.size)
            Color(0, 0, 0, 1)
            x = self.x
            for is_bar, w in bars:
                if is_bar:
                    Rectangle(pos=(x, self.y + dp(6)), size=(w * u, self.height - dp(12)))
                x += w * u


def label(text, size=15, color=(1, 1, 1, 1), bold=False, halign="left", **kw):
    lb = Label(text=text, font_size=dp(size), color=color, bold=bold, halign=halign,
               size_hint_y=None, markup=True, **kw)
    lb.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
    lb.bind(texture_size=lambda w, v: setattr(w, "height", v[1] + dp(6)))
    return lb


def button(text, cb=None, color=PURPLE, height=44, **kw):
    b = Button(text=text, size_hint_y=None, height=dp(height), background_normal="",
               background_color=color, **kw)
    if cb:
        b.bind(on_release=lambda *_: cb())
    return b


def field(hint="", text="", password=False, multiline=False, input_filter=None, **kw):
    return TextInput(hint_text=hint, text=text, password=password, multiline=multiline,
                     input_filter=input_filter, size_hint_y=None, height=dp(42), write_tab=False, **kw)


def spinner(values, text=None, **kw):
    values = list(values)
    return Spinner(text=text if text is not None else (values[0] if values else ""), values=values,
                   size_hint_y=None, height=dp(42), background_normal="", background_color=(0.3, 0.3, 0.38, 1), **kw)


def bar(value, maximum=100, color=GREEN):
    pb = ProgressBar(max=maximum, value=min(value, maximum), size_hint_y=None, height=dp(10))
    return pb


class Card(BoxLayout):
    def __init__(self, title=None, **kw):
        super().__init__(orientation="vertical", size_hint_y=None, padding=dp(12), spacing=dp(6), **kw)
        self.bind(minimum_height=self.setter("height"), pos=self._bg, size=self._bg)
        if title:
            self.add_widget(label(title, 17, YELLOW, bold=True))

    def _bg(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*CARD)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(10)])

    def row(self, *widgets, height=44):
        r = BoxLayout(size_hint_y=None, height=dp(height), spacing=dp(6))
        for w in widgets:
            r.add_widget(w)
        self.add_widget(r)
        return r


def scroll_column():
    sv = ScrollView(do_scroll_x=False)
    col = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(10), padding=dp(10))
    col.bind(minimum_height=col.setter("height"))
    sv.add_widget(col)
    return sv, col


def popup(title, body, height=0.5):
    p = Popup(title=title, content=body, size_hint=(0.92, height), auto_dismiss=True)
    p.open()
    return p


def message(title, text):
    box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
    box.add_widget(label(text, 15))
    p = popup(title, box, 0.35)
    box.add_widget(button("OK", p.dismiss))
    return p


def form(title, fields, on_submit, submit_text="Save"):
    """fields: list of (key, hint, kwargs). on_submit receives {key: text}; return False to stay open."""
    box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
    inputs = {}
    for key, hint, kw in fields:
        inputs[key] = field(hint, **kw)
        box.add_widget(inputs[key])
    p = popup(title, box, min(0.9, 0.22 + 0.1 * len(fields)))

    def submit():
        if on_submit({k: w.text for k, w in inputs.items()}) is not False:
            p.dismiss()

    box.add_widget(button(submit_text, submit))
    return p
