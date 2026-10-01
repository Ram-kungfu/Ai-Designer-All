import os
import io
import json
import time
import base64
import threading
import requests
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.text import Label as CoreLabel
from kivy.metrics import dp
from kivy.graphics import Color, Rectangle, Line
from kivy.graphics.texture import Texture
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.stencilview import StencilView
from kivy.uix.modalview import ModalView
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.uix.slider import Slider
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.utils import platform, escape_markup
from PIL import (Image as PILImage, ImageOps, ImageFilter, ImageDraw,
                 ImageChops)

# ================= आपकी keys =================
REMOVEBG_KEY = "tTqBYQZHyFSMgQW6Mkzf2sSc"
DEEPAI_KEY = "89091b06-226d-414a-94c4-347457d9c8c1"
GEMINI_KEY = "AQ.Ab8RN6JE6Qll-WBJezPVuTr9ntLAhQTbS7yZDef6oetjPaTF_g"
GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image"
GEMINI_TEXT_MODEL = "gemini-3.5-flash"
VECTORIZER_ID = "PASTE_VECTORIZER_ID"          # वैकल्पिक
VECTORIZER_SECRET = "PASTE_VECTORIZER_SECRET"  # वैकल्पिक
FLIP_TEXT = False   # अगर टेक्स्ट उल्टा दिखे तो True कर दें
# ==============================================

Window.softinput_mode = "below_target"

BASE = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(BASE, "NotoSansDevanagari-Regular.ttf")
HAS_FONT = os.path.exists(FONT_PATH)

COLORS = {
    "White": (255, 255, 255), "Black": (0, 0, 0), "Red": (230, 30, 30),
    "Yellow": (255, 220, 0), "Blue": (20, 80, 220),
    "Green": (20, 160, 60), "Orange": (255, 140, 0),
}
REQ_GALLERY = 4101
REQ_CAMERA = 4102
GEM_URL = "https://generativelanguage.googleapis.com/v1beta/models/"


def bi(hi, en, sep=" / "):
    if not HAS_FONT:
        return en
    return f"[font={FONT_PATH}]{hi}[/font]{sep}{en}"


def key_ok(v):
    return bool(v) and not v.startswith("PASTE")


# ---------------- इमेज हेल्पर ----------------

def load_pil(data, maxside=2048):
    im = PILImage.open(io.BytesIO(data))
    try:
        im = ImageOps.exif_transpose(im)
    except Exception:
        pass
    im = im.convert("RGBA")
    im.thumbnail((maxside, maxside), PILImage.LANCZOS)
    return im


def to_bytes(img, fmt="PNG", dpi=None):
    out = io.BytesIO()
    if dpi:
        img.save(out, fmt, dpi=(dpi, dpi))
    else:
        img.save(out, fmt)
    return out.getvalue()


def flatten_white(img):
    bg = PILImage.new("RGB", img.size, (255, 255, 255))
    bg.paste(img, mask=img.convert("RGBA").split()[3])
    return bg


def enhance_for_print(img, target=3000):
    rgba = img.convert("RGBA")
    long_side = max(rgba.size)
    if long_side < target:
        s = min(4.0, target / float(long_side))
        rgba = rgba.resize((int(rgba.width * s), int(rgba.height * s)),
                           PILImage.LANCZOS)
    r, g, b, a = rgba.split()
    rgb = PILImage.merge("RGB", (r, g, b)).filter(
        ImageFilter.UnsharpMask(radius=1.6, percent=110, threshold=3))
    r, g, b = rgb.split()
    return PILImage.merge("RGBA", (r, g, b, a))


def make_pdf(img):
    out = io.BytesIO()
    flatten_white(img).save(out, "PDF", resolution=300.0)
    return out.getvalue()


def align_src(src, target):
    s = src.convert("RGBA")
    if s.size != target.size:
        s = s.resize(target.size, PILImage.LANCZOS)
    return s


# ---------------- Gemini ----------------

def gemini_call(model, parts, gen_config=None, timeout=180):
    if not key_ok(GEMINI_KEY):
        raise Exception("GEMINI_KEY not set")
    payload = {"contents": [{"parts": parts}]}
    if gen_config:
        payload["generationConfig"] = gen_config
    r = requests.post(GEM_URL + model + ":generateContent",
                      headers={"x-goog-api-key": GEMINI_KEY},
                      json=payload, timeout=timeout)
    try:
        data = r.json()
    except Exception:
        raise Exception(f"Gemini HTTP {r.status_code}")
    if r.status_code != 200:
        raise Exception("Gemini: " + str(
            data.get("error", {}).get("message", r.status_code))[:200])
    return data


def gemini_image_from(data):
    for cand in data.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            inl = part.get("inlineData") or part.get("inline_data")
            if inl and inl.get("data"):
                return load_pil(base64.b64decode(inl["data"]))
    return None


def img_part(img):
    jpg = to_bytes(flatten_white(img), "JPEG")
    return {"inline_data": {"mime_type": "image/jpeg",
                            "data": base64.b64encode(jpg).decode()}}


def gemini_edit(img, prompt):
    data = gemini_call(GEMINI_IMAGE_MODEL,
                       [{"text": prompt + ". Keep it high quality and print ready."},
                        img_part(img)],
                       {"responseModalities": ["TEXT", "IMAGE"]})
    out = gemini_image_from(data)
    if out is None:
        raise Exception("Gemini returned no image")
    return out


def gemini_person_box(img):
    q = ("Find the portrait photo of the main person (face, hair, shoulders "
         "and upper body) inside this image. Ignore text, logos and graphics. "
         "Return ONLY JSON like {\"box_2d\":[ymin,xmin,ymax,xmax]} with "
         "values normalized from 0 to 1000.")
    data = gemini_call(GEMINI_TEXT_MODEL, [{"text": q}, img_part(img)],
                       {"responseMimeType": "application/json"}, 90)
    text = ""
    for part in data["candidates"][0]["content"]["parts"]:
        text += part.get("text", "")
    obj = json.loads(text)
    if isinstance(obj, list):
        obj = obj[0]
    box = obj.get("box_2d") or obj.get("box")
    ymin, xmin, ymax, xmax = [float(v) / 1000.0 for v in box]
    return ymin, xmin, ymax, xmax


# ---------------- बाकी APIs ----------------

def generate_design(prompt, w=1024, h=1024):
    url = ("https://image.pollinations.ai/prompt/" + requests.utils.quote(prompt)
           + f"?width={w}&height={h}&nologo=true")
    r = requests.get(url, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        raise Exception(f"Design generation error {r.status_code}")
    return load_pil(r.content)


def generate_image(prompt, aspect="2:3", w=1024, h=1536):
    if key_ok(GEMINI_KEY):
        try:
            cfg = {"responseModalities": ["TEXT", "IMAGE"],
                   "imageConfig": {"aspectRatio": aspect}}
            try:
                data = gemini_call(GEMINI_IMAGE_MODEL, [{"text": prompt}], cfg)
            except Exception:
                data = gemini_call(GEMINI_IMAGE_MODEL, [{"text": prompt}],
                                   {"responseModalities": ["TEXT", "IMAGE"]})
            img = gemini_image_from(data)
            if img is not None:
                return img
        except Exception:
            pass
    return generate_design(prompt, w, h)


def remove_background(img, person=False):
    data = {"size": "auto"}
    if person:
        data["type"] = "person"
    r = requests.post(
        "https://api.remove.bg/v1.0/removebg",
        files={"image_file": ("img.png", to_bytes(img, "PNG"))},
        data=data, headers={"X-Api-Key": REMOVEBG_KEY}, timeout=120)
    if r.status_code == 200:
        return load_pil(r.content)
    try:
        msg = r.json()["errors"][0]["title"]
    except Exception:
        msg = f"HTTP {r.status_code}"
    raise Exception("remove.bg: " + msg)


def remove_plain_bg(img, tol=40):
    """सादा/एक रंग का बैकग्राउंड हटाता है (AI के बिना, लोगो/स्टिकर के लिए)"""
    im = img.convert("RGBA")
    rgb = im.convert("RGB")
    w, h = im.size
    bgc = rgb.getpixel((0, 0))
    diff = ImageChops.difference(rgb, PILImage.new("RGB", im.size, bgc))
    r, g, b = diff.split()
    d = ImageChops.lighter(ImageChops.lighter(r, g), b)
    sim = d.point(lambda v: 255 if v <= tol else 0)
    s = 256.0 / max(w, h)
    sw, sh = max(2, int(w * s)), max(2, int(h * s))
    small = sim.resize((sw, sh), PILImage.NEAREST)
    for pt in [(0, 0), (sw - 1, 0), (0, sh - 1), (sw - 1, sh - 1)]:
        if small.getpixel(pt) == 255:
            ImageDraw.floodfill(small, pt, 128)
    conn = small.point(lambda v: 255 if v == 128 else 0)
    conn = conn.filter(ImageFilter.MaxFilter(3))
    conn = conn.resize((w, h), PILImage.NEAREST)
    mask = ImageChops.darker(conn, sim)
    mask = mask.filter(ImageFilter.GaussianBlur(0.8))
    new_a = ImageChops.multiply(im.split()[3], ImageChops.invert(mask))
    im.putalpha(new_a)
    return im


def clean_edges(img):
    """किनारे की 1 पिक्सेल की झालर हटाता है"""
    r, g, b, a = img.convert("RGBA").split()
    a = a.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.7))
    return PILImage.merge("RGBA", (r, g, b, a))


def extract_person(img):
    """पोस्टर/फ़ोटो में से सिर्फ़ व्यक्ति. return (cut, aligned_source, note)"""
    work = img
    note = ""
    try:
        ymin, xmin, ymax, xmax = gemini_person_box(img)
        m = 0.03
        l = max(0, int((xmin - m) * img.width))
        t = max(0, int((ymin - m) * img.height))
        r = min(img.width, int((xmax + m) * img.width))
        b = min(img.height, int((ymax + m) * img.height))
        if r - l > 40 and b - t > 40:
            work = img.crop((l, t, r, b))
        else:
            note = "crop box too small"
    except Exception as e:
        note = "auto-crop skipped: " + str(e)[:60]
    cut = remove_background(work, person=True)
    return cut, align_src(work, cut), note


def hd_upscale(img):
    rgba = img.convert("RGBA")
    alpha = rgba.split()[3]
    src = rgba.convert("RGB")
    if max(src.size) > 1200:
        s = 1200.0 / max(src.size)
        src = src.resize((int(src.width * s), int(src.height * s)),
                         PILImage.LANCZOS)
    try:
        if not key_ok(DEEPAI_KEY):
            raise Exception("DEEPAI_KEY not set")
        r = requests.post("https://api.deepai.org/api/torch-srgan",
                          files={"image": ("in.png", to_bytes(src, "PNG"))},
                          headers={"api-key": DEEPAI_KEY}, timeout=180)
        data = r.json()
        url = data.get("output_url")
        if not url:
            raise Exception(str(data.get("err") or data)[:100])
        out = requests.get(url, timeout=180)
        hd = load_pil(out.content, 4096).convert("RGBA")
        hd.putalpha(alpha.resize(hd.size, PILImage.LANCZOS))
        return hd, "DeepAI"
    except Exception as e:
        return enhance_for_print(img, 3000), "Local (DeepAI: " + str(e)[:70] + ")"


def vectorize_pdf(png_bytes):
    if not (key_ok(VECTORIZER_ID) and key_ok(VECTORIZER_SECRET)):
        raise Exception("Vectorizer keys not set in main.py")
    r = requests.post(
        "https://api.vectorizer.ai/api/v1/vectorize",
        files={"image": ("design.png", png_bytes)},
        data={"output.file_format": "pdf"},
        auth=(VECTORIZER_ID, VECTORIZER_SECRET), timeout=180)
    if r.status_code == 200:
        return r.content
    raise Exception(f"Vectorizer {r.status_code}: {r.text[:120]}")


# ---------------- डिज़ाइन बनाना ----------------

def compose_design(bg, person, size_pct, xpct, ypct):
    bg = bg.convert("RGBA")
    if bg.height < 3000:
        s = 3072.0 / bg.height
        bg = bg.resize((int(bg.width * s), 3072), PILImage.LANCZOS)
    p = person.convert("RGBA")
    ph = int(bg.height * size_pct / 100.0)
    r = ph / float(p.height)
    pw = int(p.width * r)
    if pw > bg.width * 0.98:
        r = bg.width * 0.98 / p.width
        pw, ph = int(p.width * r), int(p.height * r)
    p = p.resize((max(1, pw), max(1, ph)), PILImage.LANCZOS)
    x0 = int(bg.width * xpct / 100.0 - pw / 2.0)
    y0 = int(bg.height * ypct / 100.0 - ph / 2.0)
    a = p.split()[3]
    sh = a.filter(ImageFilter.GaussianBlur(max(2, ph / 70.0))).point(
        lambda v: int(v * 0.45))
    out = bg.copy()
    out.paste(PILImage.new("RGBA", p.size, (0, 0, 0, 255)),
              (x0 + int(pw * 0.02), y0 + int(ph * 0.02)), sh)
    out.paste(p, (x0, y0), a)
    return out


# ---------------- टेक्स्ट रेंडर (हिंदी + English) ----------------

def _is_deva(ch):
    return "\u0900" <= ch <= "\u097F" or ch in ("\u200c", "\u200d")


def split_runs(line):
    runs = []
    for ch in line:
        if _is_deva(ch):
            kind = True
        elif ch.isalnum():
            kind = False
        else:
            kind = None
        if kind is None:
            if runs:
                runs[-1][1] += ch
            else:
                runs.append([False, ch])
        elif runs and runs[-1][0] == kind:
            runs[-1][1] += ch
        else:
            runs.append([kind, ch])
    return runs


def render_run(text, is_deva, px):
    font = FONT_PATH if (is_deva and HAS_FONT) else "Roboto"
    cl = CoreLabel(text=text, font_size=px, font_name=font, color=(1, 1, 1, 1))
    cl.refresh()
    tex = cl.texture
    if tex is None or tex.width < 2:
        return PILImage.new("L", (max(2, px // 3), px), 0)
    w, h = tex.size
    im = PILImage.frombytes("RGBA", (w, h), tex.pixels)
    if FLIP_TEXT:
        im = im.transpose(PILImage.FLIP_TOP_BOTTOM)
    return im.split()[3]


def render_line(line, px):
    masks = [render_run(t, d, px) for d, t in split_runs(line)]
    if not masks:
        return None
    w = sum(m.width for m in masks)
    h = max(m.height for m in masks)
    out = PILImage.new("L", (w, h), 0)
    x = 0
    for m in masks:
        out.paste(m, (x, (h - m.height) // 2))
        x += m.width
    return out


def render_text_block(text, px):
    ims = [render_line(l, px) for l in text.split("\n") if l.strip()]
    ims = [i for i in ims if i is not None]
    if not ims:
        return None
    gap = int(px * 0.2)
    w = max(i.width for i in ims)
    h = sum(i.height for i in ims) + gap * (len(ims) - 1)
    out = PILImage.new("L", (w, h), 0)
    y = 0
    for i in ims:
        out.paste(i, ((w - i.width) // 2, y))
        y += i.height + gap
    return out


def apply_text(base, text, color, outline, size_pct, xpct, ypct):
    img = base.copy().convert("RGBA")
    px = max(14, int(img.height * size_pct / 100.0))
    mask = render_text_block(text, px)
    if mask is None:
        return img
    maxw = int(img.width * 0.95)
    if mask.width > maxw:
        r = maxw / float(mask.width)
        mask = mask.resize((maxw, max(1, int(mask.height * r))), PILImage.LANCZOS)
    pad = int(px * 0.2) if outline != "No outline" else 0
    if pad:
        mask = ImageOps.expand(mask, border=pad, fill=0)
    x0 = int(img.width * xpct / 100.0 - mask.width / 2.0)
    y0 = int(img.height * ypct / 100.0 - mask.height / 2.0)
    x0 = max(0, min(img.width - mask.width, x0))
    y0 = max(0, min(img.height - mask.height, y0))
    if pad:
        oc = (0, 0, 0) if outline.startswith("Black") else (255, 255, 255)
        om = mask.filter(ImageFilter.GaussianBlur(max(1, px / 18.0))).point(
            lambda v: 255 if v > 8 else 0)
        img.paste(PILImage.new("RGBA", mask.size, oc + (255,)), (x0, y0), om)
    img.paste(PILImage.new("RGBA", mask.size, color + (255,)), (x0, y0), mask)
    return img


# ---------------- फ़ाइल सेव ----------------

def save_file(app, name, data, mime):
    if platform == "android":
        try:
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            ContentValues = autoclass("android.content.ContentValues")
            Downloads = autoclass("android.provider.MediaStore$Downloads")
            values = ContentValues()
            values.put("_display_name", name)
            values.put("mime_type", mime)
            values.put("relative_path", "Download/AIDesign")
            resolver = PythonActivity.mActivity.getContentResolver()
            uri = resolver.insert(Downloads.EXTERNAL_CONTENT_URI, values)
            pfd = resolver.openFileDescriptor(uri, "w")
            fd = pfd.detachFd()
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            return "Download/AIDesign/" + name, uri
        except Exception:
            pass
    path = os.path.join(app.user_data_dir, name)
    with open(path, "wb") as f:
        f.write(data)
    return path, None


def read_uri_bytes(uri):
    from jnius import autoclass
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    resolver = PythonActivity.mActivity.getContentResolver()
    pfd = resolver.openFileDescriptor(uri, "r")
    fd = pfd.detachFd()
    with os.fdopen(fd, "rb") as f:
        return f.read()


# ---------------- करेक्शन एडिटर ----------------

_MASKS = {}


def _circle_mask(r):
    if r not in _MASKS:
        m = PILImage.new("L", (2 * r + 1, 2 * r + 1), 0)
        ImageDraw.Draw(m).ellipse((0, 0, 2 * r, 2 * r), fill=255)
        _MASKS[r] = m
    return _MASKS[r]


def brush_apply(img, src, mode, x, y, r):
    r = max(1, int(r))
    x, y = int(x), int(y)
    bx0, by0 = x - r, y - r
    l, t = max(0, bx0), max(0, by0)
    rr, bb = min(img.width, x + r + 1), min(img.height, y + r + 1)
    if rr <= l or bb <= t:
        return
    m = _circle_mask(r).crop((l - bx0, t - by0, rr - bx0, bb - by0))
    if mode == "erase":
        img.paste((0, 0, 0, 0), (l, t, rr, bb), m)
    elif src is not None:
        img.paste(src.crop((l, t, rr, bb)), (l, t), m)


class EditCanvas(StencilView):
    def __init__(self, full, src, **kw):
        super().__init__(**kw)
        self.full = full.convert("RGBA")
        self.src = src
        self.fw, self.fh = self.full.size
        self.ds = min(1.0, 1100.0 / max(self.fw, self.fh))
        dw, dh = max(1, int(self.fw * self.ds)), max(1, int(self.fh * self.ds))
        self.disp0 = self.full.resize((dw, dh), PILImage.LANCZOS)
        self.disp_src = (src.resize((dw, dh), PILImage.LANCZOS)
                         if src is not None else None)
        self.disp = self.disp0.copy()
        self.ops = []
        self.cur = None
        self.mode = "erase"
        self.radius = max(3, int(self.fw * 0.02))
        self.zoom = 1.0
        self.pan = [0.0, 0.0]
        self.s = 1.0
        self.ox = self.oy = 0.0
        self.bg_choices = [(0.8, 0.8, 0.8), (1, 1, 1), (0, 0, 0), (0, 0.7, 0.2)]
        self.bg_i = 0
        self.tex = Texture.create(size=(dw, dh), colorfmt="rgba")
        self.tex.flip_vertical()
        with self.canvas:
            self.bg_color = Color(*self.bg_choices[0], 1)
            self.bg_rect = Rectangle(pos=self.pos, size=self.size)
            Color(1, 1, 1, 1)
            self.img_rect = Rectangle(texture=self.tex, pos=(0, 0), size=(10, 10))
            Color(1, 0.2, 0.2, 1)
            self.cursor = Line(circle=(0, 0, 0), width=1.5)
        self.bind(pos=self.relayout, size=self.relayout)
        self.update_tex()
        self.relayout()

    def relayout(self, *a):
        fit = min(self.width / float(self.fw), self.height / float(self.fh))
        self.s = max(1e-6, fit * self.zoom)
        iw, ih = self.fw * self.s, self.fh * self.s
        self.ox = self.x + (self.width - iw) / 2.0 + self.pan[0]
        self.oy = self.y + (self.height - ih) / 2.0 + self.pan[1]
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size
        self.img_rect.pos = (self.ox, self.oy)
        self.img_rect.size = (iw, ih)

    def update_tex(self):
        self.tex.blit_buffer(self.disp.tobytes(), colorfmt="rgba",
                             bufferfmt="ubyte")
        self.canvas.ask_update()

    def to_img(self, tx, ty):
        return (tx - self.ox) / self.s, self.fh - (ty - self.oy) / self.s

    def add_point(self, ix, iy):
        c = self.cur
        c["pts"].append((ix, iy))
        brush_apply(self.disp, self.disp_src, c["mode"],
                    ix * self.ds, iy * self.ds, max(1, c["r"] * self.ds))

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        touch.grab(self)
        if self.mode == "move":
            return True
        self.cur = {"mode": self.mode, "r": self.radius, "pts": []}
        ix, iy = self.to_img(*touch.pos)
        self.cur["last"] = (ix, iy)
        self.add_point(ix, iy)
        self.cursor.circle = (touch.x, touch.y, self.radius * self.s)
        self.update_tex()
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return False
        if self.mode == "move":
            self.pan[0] += touch.dx
            self.pan[1] += touch.dy
            self.relayout()
            return True
        if self.cur is None:
            return True
        ix, iy = self.to_img(*touch.pos)
        lx, ly = self.cur["last"]
        dist = ((ix - lx) ** 2 + (iy - ly) ** 2) ** 0.5
        step = max(1.0, self.cur["r"] * 0.35)
        n = max(1, int(dist / step))
        for i in range(1, n + 1):
            f = i / float(n)
            self.add_point(lx + (ix - lx) * f, ly + (iy - ly) * f)
        self.cur["last"] = (ix, iy)
        self.cursor.circle = (touch.x, touch.y, self.radius * self.s)
        self.update_tex()
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return False
        touch.ungrab(self)
        if self.cur is not None and self.cur["pts"]:
            self.ops.append(("stroke", self.cur))
        self.cur = None
        return True

    def zoom_by(self, f):
        self.zoom = max(1.0, min(8.0, self.zoom * f))
        if self.zoom == 1.0:
            self.pan = [0.0, 0.0]
        self.relayout()

    def next_backdrop(self):
        self.bg_i = (self.bg_i + 1) % len(self.bg_choices)
        self.bg_color.rgba = (*self.bg_choices[self.bg_i], 1)

    def do_clean(self):
        self.ops.append(("clean", None))
        self.disp = clean_edges(self.disp)
        self.update_tex()

    def undo(self):
        if not self.ops:
            return
        self.ops.pop()
        self.disp = self.disp0.copy()
        for kind, c in self.ops:
            if kind == "stroke":
                for (x, y) in c["pts"]:
                    brush_apply(self.disp, self.disp_src, c["mode"],
                                x * self.ds, y * self.ds, max(1, c["r"] * self.ds))
            else:
                self.disp = clean_edges(self.disp)
        self.update_tex()

    def result(self):
        out = self.full.copy()
        for kind, c in self.ops:
            if kind == "stroke":
                for (x, y) in c["pts"]:
                    brush_apply(out, self.src, c["mode"], x, y, c["r"])
            else:
                out = clean_edges(out)
        return out


# ---------------- UI ----------------

class Preview(BoxLayout):
    def __init__(self, **kw):
        super().__init__(**kw)
        with self.canvas.before:
            Color(0.85, 0.85, 0.85, 1)
            self.rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd, size=self._upd)

    def _upd(self, *a):
        self.rect.pos = self.pos
        self.rect.size = self.size


def mk_label(hi, en, h=30):
    return Label(text=bi(hi, en), markup=True, size_hint_y=None, height=dp(h))


class DesignApp(App):
    base = None
    person = None
    person_src = None
    bg = None
    final = None
    history = []
    last_uri = None
    last_mime = "application/pdf"
    camera_uri = None
    photo_loaded = False

    def build(self):
        self.title = "AI Design Studio"
        self.action_btns = []
        scroll = ScrollView()
        root = BoxLayout(orientation="vertical", size_hint_y=None,
                         padding=dp(10), spacing=dp(8))
        root.bind(minimum_height=root.setter("height"))
        scroll.add_widget(root)

        root.add_widget(mk_label("1) फ़ोटो चुनें", "1) Choose photo", 32))
        row = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        for hi, en, cb in [("गैलरी", "Gallery", self.pick_gallery),
                           ("कैमरा", "Camera", self.pick_camera)]:
            b = Button(text=bi(hi, en, sep="\n"), markup=True, halign="center")
            b.bind(on_press=cb)
            row.add_widget(b)
            self.action_btns.append(b)
        root.add_widget(row)

        pv = Preview(size_hint_y=None, height=dp(320), padding=dp(2))
        self.preview = Image()
        pv.add_widget(self.preview)
        root.add_widget(pv)

        root.add_widget(mk_label("2) कटिंग और करेक्शन", "2) Cutting & correction", 34))
        self._row(root, [
            ("व्यक्ति अलग करें", "Extract Person", self.on_extract, (0.9, 0.5, 0.1, 1)),
            ("बैकग्राउंड काटें (AI)", "Cut Background (AI)", self.on_cut, (0.7, 0.4, 0.1, 1))])
        self.tol_sl = self._slider(root, "सहनशीलता", "Tolerance", 5, 120, 40)
        self._row(root, [
            ("सादा बैकग्राउंड हटाएँ", "Remove Plain BG", self.on_plain, (0.6, 0.3, 0.6, 1)),
            ("करेक्शन करें", "Edit / Correct", self.open_editor, (0.1, 0.6, 0.5, 1))])
        self._row(root, [
            ("HD बनाएँ", "Make HD", self.on_hd, (0.2, 0.6, 1, 1)),
            ("पिछला वापस", "Undo", self.on_undo, None)], track=False)

        root.add_widget(mk_label("3) नया डिज़ाइन (English/Hinglish)",
                                 "3) New design", 34))
        self.prompt_input = TextInput(
            hint_text="e.g. purple gold luxury achiever poster background",
            multiline=True, size_hint_y=None, height=dp(80))
        root.add_widget(self.prompt_input)
        auto = Button(
            text=bi("AUTO: व्यक्ति अलग + HD + नया डिज़ाइन",
                    "AUTO: Person + HD + New Design", sep="\n"),
            markup=True, halign="center", size_hint_y=None, height=dp(64),
            background_color=(0.1, 0.7, 0.3, 1))
        auto.bind(on_press=self.on_auto)
        root.add_widget(auto)
        self.action_btns.append(auto)
        self._row(root, [
            ("नया डिज़ाइन", "New Design", self.on_design, (0.2, 0.4, 0.9, 1)),
            ("AI से फ़ोटो बदलें", "AI Edit photo", self.on_ai_edit, None)])
        self.p_size = self._slider(root, "व्यक्ति आकार", "Person size", 30, 95, 74)
        self.p_x = self._slider(root, "व्यक्ति बाएँ-दाएँ", "Person L-R", 0, 100, 50)
        self.p_y = self._slider(root, "व्यक्ति ऊपर-नीचे", "Person U-D", 0, 100, 60)

        root.add_widget(mk_label("4) टेक्स्ट लिखें", "4) Add text", 34))
        self.hi_input = TextInput(
            hint_text=("यहाँ हिंदी में लिखें" if HAS_FONT else "Hindi text"),
            font_name=(FONT_PATH if HAS_FONT else "Roboto"),
            multiline=True, size_hint_y=None, height=dp(70))
        root.add_widget(self.hi_input)
        self.en_input = TextInput(
            hint_text="Write English text here", multiline=True,
            size_hint_y=None, height=dp(70))
        root.add_widget(self.en_input)
        self.color_sp = Spinner(text="White", values=list(COLORS.keys()),
                                size_hint_y=None, height=dp(44))
        root.add_widget(self.color_sp)
        self.outline_sp = Spinner(
            text="Black outline",
            values=["No outline", "Black outline", "White outline"],
            size_hint_y=None, height=dp(44))
        root.add_widget(self.outline_sp)
        self.size_sl = self._slider(root, "आकार", "Size", 3, 40, 6)
        self.x_sl = self._slider(root, "बाएँ-दाएँ", "Left-Right", 0, 100, 50)
        self.y_sl = self._slider(root, "ऊपर-नीचे", "Up-Down", 0, 100, 90)
        self._row(root, [("टेक्स्ट जोड़ें", "Add Text", self.on_add_text, None),
                         ("टेक्स्ट हटाएँ", "Remove Text", self.on_remove_text, None)],
                  track=False)

        root.add_widget(mk_label("5) सेव / भेजें", "5) Save / Send", 34))
        r4 = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(8))
        for hi, en, kind in [("PNG सेव (शर्ट प्रिंट)", "Save PNG (transparent)", "png"),
                             ("PDF सेव", "Save PDF", "pdf")]:
            b = Button(text=bi(hi, en, sep="\n"), markup=True, halign="center")
            b.bind(on_press=lambda inst, k=kind: self.export(k))
            r4.add_widget(b)
            self.action_btns.append(b)
        root.add_widget(r4)
        vb = Button(text=bi("वेक्टर PDF (बिल्कुल शार्प)", "Vector PDF (ultra sharp)",
                            sep="\n"), markup=True, halign="center",
                    size_hint_y=None, height=dp(52))
        vb.bind(on_press=lambda inst: self.export("vector"))
        root.add_widget(vb)
        self.action_btns.append(vb)
        sb = Button(text=bi("पिछली फ़ाइल शेयर करें", "Share last file", sep="\n"),
                    markup=True, halign="center", size_hint_y=None,
                    height=dp(52), background_color=(0.2, 0.7, 0.3, 1))
        sb.bind(on_press=self.share_last)
        root.add_widget(sb)

        self.status = Label(text=bi("तैयार", "Ready"), markup=True,
                            size_hint_y=None, height=dp(60))
        self.status.bind(size=lambda w, s: setattr(w, "text_size", s))
        root.add_widget(self.status)

        if platform == "android":
            try:
                from android import activity
                activity.bind(on_activity_result=self._on_result)
            except Exception:
                pass
        return scroll

    def _row(self, root, items, track=True):
        row = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(8))
        for hi, en, cb, col in items:
            b = Button(text=bi(hi, en, sep="\n"), markup=True, halign="center")
            if col:
                b.background_color = col
            b.bind(on_press=cb)
            row.add_widget(b)
            if track:
                self.action_btns.append(b)
        root.add_widget(row)

    def _slider(self, root, hi, en, mn, mx, val):
        row = BoxLayout(size_hint_y=None, height=dp(40))
        row.add_widget(Label(text=bi(hi, en), markup=True,
                             size_hint_x=None, width=dp(150)))
        sl = Slider(min=mn, max=mx, value=val)
        row.add_widget(sl)
        root.add_widget(row)
        return sl

    # ---------- helpers ----------
    def popup(self, msg):
        c = Label(text=msg, markup=True, halign="center")
        c.bind(size=lambda w, s: setattr(w, "text_size", s))
        Popup(title="Info", content=c, size_hint=(0.88, 0.4)).open()

    def ui(self, fn):
        Clock.schedule_once(lambda dt: fn())

    def say(self, msg):
        self.ui(lambda: setattr(self.status, "text", msg))

    def busy(self, msg):
        self.status.text = msg
        for b in self.action_btns:
            b.disabled = True

    def done(self, msg):
        self.status.text = msg
        for b in self.action_btns:
            b.disabled = False

    def fail(self, e):
        msg = bi("त्रुटि", "Error", sep=": ") + "\n" + escape_markup(str(e))[:300]
        self.ui(lambda: (self.popup(msg), self.done(bi("फेल", "Failed"))))

    def refresh_preview(self):
        img = self.final if self.final is not None else self.base
        if img is None:
            return
        path = os.path.join(self.user_data_dir, "preview.png")
        p = img.copy()
        p.thumbnail((1200, 1200))
        p.save(path, "PNG")
        self.preview.source = path
        self.preview.reload()

    def set_base(self, img, push=True):
        if push and self.base is not None:
            self.history.append(self.base)
            self.history = self.history[-4:]
        self.base = img
        self.final = None
        self.refresh_preview()

    def _set_person_base(self, person, base, src=None, clear_bg=True):
        self.person = person
        if src is not None:
            self.person_src = src
        if clear_bg:
            self.bg = None
        self.photo_loaded = False
        self.set_base(base)

    def _need_base(self):
        if self.base is None:
            self.popup(bi("पहले फ़ोटो चुनें", "Choose a photo first"))
            return False
        return True

    def _prompt(self):
        p = self.prompt_input.text.strip()
        if not p:
            self.popup(bi("पहले डिज़ाइन का विवरण लिखें",
                          "Write the design description first"))
        return p

    # ---------- फ़ोटो चुनना ----------
    def pick_gallery(self, *a):
        if platform != "android":
            self.popup("Android only")
            return
        try:
            from jnius import autoclass, cast
            Intent = autoclass("android.content.Intent")
            String = autoclass("java.lang.String")
            PA = autoclass("org.kivy.android.PythonActivity")
            intent = Intent(Intent.ACTION_GET_CONTENT)
            intent.setType("image/*")
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            chooser = Intent.createChooser(
                intent, cast("java.lang.CharSequence", String("Select photo")))
            PA.mActivity.startActivityForResult(chooser, REQ_GALLERY)
        except Exception as e:
            self.popup("Gallery error: " + escape_markup(str(e)))

    def pick_camera(self, *a):
        if platform != "android":
            self.popup("Android only")
            return
        try:
            from jnius import autoclass, cast
            Intent = autoclass("android.content.Intent")
            MediaStore = autoclass("android.provider.MediaStore")
            Media = autoclass("android.provider.MediaStore$Images$Media")
            ContentValues = autoclass("android.content.ContentValues")
            PA = autoclass("org.kivy.android.PythonActivity")
            values = ContentValues()
            values.put("_display_name", "design_%d.jpg" % int(time.time()))
            values.put("mime_type", "image/jpeg")
            values.put("relative_path", "Pictures/AIDesign")
            resolver = PA.mActivity.getContentResolver()
            uri = resolver.insert(Media.EXTERNAL_CONTENT_URI, values)
            self.camera_uri = uri
            intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE)
            intent.putExtra(MediaStore.EXTRA_OUTPUT,
                            cast("android.os.Parcelable", uri))
            intent.addFlags(3)
            PA.mActivity.startActivityForResult(intent, REQ_CAMERA)
        except Exception as e:
            self.popup("Camera error: " + escape_markup(str(e)))

    def _on_result(self, request_code, result_code, intent):
        if request_code not in (REQ_GALLERY, REQ_CAMERA) or result_code != -1:
            return
        uri = None
        if request_code == REQ_GALLERY and intent is not None:
            uri = intent.getData()
        elif request_code == REQ_CAMERA:
            uri = self.camera_uri
        if uri is not None:
            Clock.schedule_once(lambda dt: self._load_uri(uri))

    def _load_uri(self, uri):
        try:
            img = load_pil(read_uri_bytes(uri))
            self.history = []
            self.person = None
            self.person_src = None
            self.bg = None
            self.photo_loaded = True
            self.set_base(img, push=False)
            self.done(bi("फ़ोटो लोड हो गई", "Photo loaded"))
        except Exception as e:
            self.popup("Load error: " + escape_markup(str(e)))

    # ---------- AUTO ----------
    def on_auto(self, *a):
        if not self._need_base():
            return
        prompt = self._prompt()
        if not prompt:
            return
        self.busy(bi("AUTO चल रहा है...", "AUTO running..."))
        threading.Thread(
            target=self._auto_worker,
            args=(prompt, self.base, self.p_size.value, self.p_x.value,
                  self.p_y.value), daemon=True).start()

    def _auto_worker(self, prompt, img, size, x, y):
        try:
            self.say(bi("1/3 व्यक्ति अलग कर रहा है...", "1/3 Extracting person..."))
            cut, src, note = extract_person(img)
            self.ui(lambda: self._set_person_base(cut, cut, src=src))
            self.say(bi("2/3 HD बना रहा है...", "2/3 Making HD..."))
            hd, hsrc = hd_upscale(cut)
            self.ui(lambda: self._set_person_base(hd, hd))
            self.say(bi("3/3 नया डिज़ाइन बना रहा है...", "3/3 Creating design..."))
            bg = generate_image(
                prompt + ". Poster background design only, vibrant, professional, "
                "no people, no text, empty space in the center.")
            out = compose_design(bg, hd, size, x, y)
            self.ui(lambda: setattr(self, "bg", bg))
            self.ui(lambda: self._set_person_base(hd, out, clear_bg=False))
            msg = bi("पूरा हुआ!", "All done!") + "  [HD: " + escape_markup(hsrc) + "]"
            if note:
                msg += "\n" + escape_markup(note)
            self.ui(lambda: self.done(msg))
        except Exception as e:
            self.fail(e)

    # ---------- कटिंग ----------
    def on_extract(self, *a):
        if not self._need_base():
            return
        self.busy(bi("व्यक्ति अलग कर रहा है...", "Extracting person..."))
        threading.Thread(target=self._extract_worker, args=(self.base,),
                         daemon=True).start()

    def _extract_worker(self, img):
        try:
            cut, src, note = extract_person(img)
            self.ui(lambda: self._set_person_base(cut, cut, src=src))
            msg = bi("व्यक्ति अलग हो गया", "Person extracted")
            if note:
                msg += "\n" + escape_markup(note)
            self.ui(lambda: self.done(msg))
        except Exception as e:
            self.fail(e)

    def on_cut(self, *a):
        if not self._need_base():
            return
        self.busy(bi("बैकग्राउंड हटा रहा है...", "Removing background..."))
        threading.Thread(target=self._cut_worker, args=(self.base,),
                         daemon=True).start()

    def _cut_worker(self, img):
        try:
            cut = remove_background(img)
            src = align_src(img, cut)
            self.ui(lambda: self._set_person_base(cut, cut, src=src))
            self.ui(lambda: self.done(bi("कटिंग हो गई!", "Cut done!")))
        except Exception as e:
            self.fail(e)

    def on_plain(self, *a):
        if not self._need_base():
            return
        self.busy(bi("सादा बैकग्राउंड हटा रहा है...", "Removing plain background..."))
        threading.Thread(target=self._plain_worker,
                         args=(self.base, int(self.tol_sl.value)),
                         daemon=True).start()

    def _plain_worker(self, img, tol):
        try:
            out = remove_plain_bg(img, tol)
            src = img.convert("RGBA")
            self.ui(lambda: self._set_person_base(out, out, src=src))
            self.ui(lambda: self.done(bi(
                "हो गया. बचा हुआ हिस्सा 'करेक्शन करें' से ठीक करें",
                "Done. Fix leftovers with 'Edit / Correct'")))
        except Exception as e:
            self.fail(e)

    # ---------- HD / डिज़ाइन ----------
    def on_hd(self, *a):
        if not self._need_base():
            return
        self.busy(bi("HD बना रहा है...", "Making HD..."))
        is_person = self.person is not None and self.base is self.person
        threading.Thread(target=self._hd_worker, args=(self.base, is_person),
                         daemon=True).start()

    def _hd_worker(self, img, is_person):
        try:
            hd, src = hd_upscale(img)
            if is_person:
                self.ui(lambda: self._set_person_base(hd, hd))
            else:
                self.ui(lambda: self.set_base(hd))
            self.ui(lambda: self.done(bi("HD हो गया", "HD done")
                                      + "  [" + escape_markup(src) + "]"))
        except Exception as e:
            self.fail(e)

    def on_design(self, *a):
        prompt = self._prompt()
        if not prompt:
            return
        if self.person is None and self.photo_loaded:
            self.popup(bi("पहले 'व्यक्ति अलग करें' दबाइए, ताकि आपकी फ़ोटो डिज़ाइन में लगे",
                          "Press 'Extract Person' first so your photo is used"))
            return
        self.busy(bi("डिज़ाइन बना रहा है...", "Creating design..."))
        threading.Thread(
            target=self._design_worker,
            args=(prompt, self.person, self.p_size.value, self.p_x.value,
                  self.p_y.value), daemon=True).start()

    def _design_worker(self, prompt, person, size, x, y):
        try:
            if person is not None:
                bg = generate_image(
                    prompt + ". Poster background design only, vibrant, "
                    "professional, no people, no text, empty space in the center.")
                out = compose_design(bg, person, size, x, y)
                self.ui(lambda: setattr(self, "bg", bg))
            else:
                out = generate_image(prompt + ". High quality, print ready design.")
            self.ui(lambda: self.set_base(out))
            self.ui(lambda: self.done(bi("डिज़ाइन तैयार", "Design ready")))
        except Exception as e:
            self.fail(e)

    def on_ai_edit(self, *a):
        if not self._need_base():
            return
        prompt = self._prompt()
        if not prompt:
            return
        self.busy(bi("AI बदलाव कर रहा है...", "AI editing..."))
        threading.Thread(target=self._edit_worker, args=(prompt, self.base),
                         daemon=True).start()

    def _edit_worker(self, prompt, img):
        try:
            out = gemini_edit(img, prompt)
            self.ui(lambda: self.set_base(out))
            self.ui(lambda: self.done(bi("हो गया!", "Done!")))
        except Exception as e:
            self.fail(e)

    def on_undo(self, *a):
        if self.history:
            self.base = self.history.pop()
            self.final = None
            self.refresh_preview()

    # ---------- करेक्शन एडिटर ----------
    def open_editor(self, *a):
        target = self.person if self.person is not None else self.base
        if target is None:
            self.popup(bi("पहले फ़ोटो चुनें और काटें", "Choose and cut a photo first"))
            return
        src = None
        if self.person is not None and self.person_src is not None:
            src = align_src(self.person_src, target)
        ed = EditCanvas(target, src)
        view = ModalView(size_hint=(1, 1), auto_dismiss=False)
        box = BoxLayout(orientation="vertical", padding=dp(6), spacing=dp(6))

        modes = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(6))

        def set_mode(m):
            ed.mode = m

        for hi, en, m in [("मिटाएँ", "Erase", "erase"),
                          ("वापस लाएँ", "Restore", "restore"),
                          ("खिसकाएँ", "Move", "move")]:
            tb = ToggleButton(text=bi(hi, en, sep="\n"), markup=True,
                              halign="center", group="editmode",
                              allow_no_selection=False,
                              state="down" if m == "erase" else "normal")
            if m == "restore" and src is None:
                tb.disabled = True
            tb.bind(on_press=lambda inst, mm=m: set_mode(mm))
            modes.add_widget(tb)
        box.add_widget(modes)

        tools = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        for text, cb in [("Zoom +", lambda *_: ed.zoom_by(1.5)),
                         ("Zoom -", lambda *_: ed.zoom_by(1 / 1.5)),
                         ("Backdrop", lambda *_: ed.next_backdrop()),
                         ("Clean Edges", lambda *_: ed.do_clean())]:
            b = Button(text=text)
            b.bind(on_press=cb)
            tools.add_widget(b)
        box.add_widget(tools)

        brow = BoxLayout(size_hint_y=None, height=dp(40))
        brow.add_widget(Label(text=bi("ब्रश", "Brush"), markup=True,
                               size_hint_x=None, width=dp(90)))
        bs = Slider(min=0.5, max=10, value=2)
        bs.bind(value=lambda inst, v: setattr(
            ed, "radius", max(2, int(ed.fw * v / 200.0))))
        brow.add_widget(bs)
        box.add_widget(brow)

        box.add_widget(ed)

        def done_cb(*_):
            try:
                res = ed.result()
            except Exception as e:
                self.popup("Edit error: " + escape_markup(str(e)))
                return
            view.dismiss()
            self._apply_edit(res)

        bottom = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(6))
        ub = Button(text=bi("वापस", "Undo", sep="\n"), markup=True, halign="center")
        ub.bind(on_press=lambda *_: ed.undo())
        cb_ = Button(text=bi("रद्द", "Cancel", sep="\n"), markup=True, halign="center")
        cb_.bind(on_press=lambda *_: view.dismiss())
        db = Button(text=bi("हो गया", "Done", sep="\n"), markup=True,
                    halign="center", background_color=(0.1, 0.7, 0.3, 1))
        db.bind(on_press=done_cb)
        for w in (ub, cb_, db):
            bottom.add_widget(w)
        box.add_widget(bottom)

        view.add_widget(box)
        view.open()

    def _apply_edit(self, edited):
        try:
            if self.person is not None:
                was_person_base = self.base is self.person
                self.person = edited
                if was_person_base:
                    self.set_base(edited)
                elif self.bg is not None:
                    self.set_base(compose_design(
                        self.bg, edited, self.p_size.value,
                        self.p_x.value, self.p_y.value))
                else:
                    self.refresh_preview()
            else:
                self.set_base(edited)
            self.status.text = bi("करेक्शन लागू हुआ", "Correction applied")
        except Exception as e:
            self.popup("Apply error: " + escape_markup(str(e)))

    # ---------- टेक्स्ट ----------
    def on_add_text(self, *a):
        if self.base is None:
            self.popup(bi("पहले फ़ोटो या डिज़ाइन चाहिए", "Need a photo or design first"))
            return
        text = (self.hi_input.text + "\n" + self.en_input.text).strip()
        if not text:
            self.popup(bi("टेक्स्ट लिखें", "Write some text"))
            return
        try:
            self.final = apply_text(
                self.base, text, COLORS[self.color_sp.text], self.outline_sp.text,
                self.size_sl.value, self.x_sl.value, self.y_sl.value)
            self.refresh_preview()
            self.status.text = bi("टेक्स्ट जुड़ गया", "Text added")
        except Exception as e:
            self.popup("Text error: " + escape_markup(str(e)))

    def on_remove_text(self, *a):
        self.final = None
        self.refresh_preview()

    # ---------- एक्सपोर्ट ----------
    def export(self, kind):
        img = self.final if self.final is not None else self.base
        if img is None:
            self.popup(bi("पहले कुछ बनाएँ", "Create something first"))
            return
        self.busy(bi("फ़ाइल बना रहा है...", "Preparing file..."))
        threading.Thread(target=self._export_worker, args=(kind, img.copy()),
                         daemon=True).start()

    def _export_worker(self, kind, img):
        try:
            stamp = int(time.time())
            if kind == "png":
                data = to_bytes(enhance_for_print(img), "PNG", dpi=300)
                name, mime = "design_%d.png" % stamp, "image/png"
            elif kind == "pdf":
                data = make_pdf(enhance_for_print(img))
                name, mime = "design_%d.pdf" % stamp, "application/pdf"
            else:
                data = vectorize_pdf(to_bytes(img, "PNG"))
                name, mime = "design_vector_%d.pdf" % stamp, "application/pdf"
            self.ui(lambda: self._finish_save(name, data, mime))
        except Exception as e:
            self.fail(e)

    def _finish_save(self, name, data, mime):
        try:
            label, uri = save_file(self, name, data, mime)
            self.last_uri = uri
            self.last_mime = mime
            self.done(bi("सेव हो गया", "Saved"))
            self.popup(bi("सेव हो गया", "Saved") + "\n" + escape_markup(label))
        except Exception as e:
            self.fail(e)

    def share_last(self, *a):
        if platform != "android" or self.last_uri is None:
            self.popup(bi("पहले कोई फ़ाइल सेव करें", "Save a file first"))
            return
        try:
            from jnius import autoclass, cast
            Intent = autoclass("android.content.Intent")
            String = autoclass("java.lang.String")
            PA = autoclass("org.kivy.android.PythonActivity")
            intent = Intent(Intent.ACTION_SEND)
            intent.setType(self.last_mime)
            intent.putExtra(Intent.EXTRA_STREAM,
                            cast("android.os.Parcelable", self.last_uri))
            intent.addFlags(1)
            chooser = Intent.createChooser(
                intent, cast("java.lang.CharSequence", String("Share")))
            PA.mActivity.startActivity(chooser)
        except Exception as e:
            self.popup("Share error: " + escape_markup(str(e)))


if __name__ == "__main__":
    DesignApp().run()
