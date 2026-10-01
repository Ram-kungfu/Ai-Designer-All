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
VECTORIZER_ID = "vktcf6i92nbgp2f"
VECTORIZER_SECRET = "tovebgr66k30if7i3a0or1fiml2qr8804k222sfnnd0p3lu395gn"
GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image"
GEMINI_TEXT_MODEL = "gemini-3.5-flash"
FLIP_TEXT = False   # टेक्स्ट उल्टा दिखे तो True कर दें
# ==============================================

Window.softinput_mode = "below_target"

BASE = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(BASE, "NotoSansDevanagari-Regular.ttf")
HAS_FONT = os.path.exists(FONT_PATH)

COLORS = {
    "White": (255, 255, 255), "Black": (0, 0, 0), "Red": (230, 30, 30),
    "Yellow": (255, 220, 0), "Blue": (20, 80, 220), "Green": (20, 160, 60),
    "Orange": (255, 140, 0), "Purple": (150, 50, 200),
    "Pink": (255, 105, 180), "Cyan": (0, 200, 200),
}
# कैनवास: (पिक्सेल साइज़, Gemini aspect, Pollinations साइज़)
CANVAS_META = {
    "Portrait 2:3": ((2000, 3000), "2:3", (1024, 1536)),
    "Square 1:1": ((2400, 2400), "1:1", (1024, 1024)),
    "Landscape 3:2": ((3000, 2000), "3:2", (1536, 1024)),
}
BG_COLORS = {
    "Transparent": None, "White": (255, 255, 255, 255),
    "Black": (0, 0, 0, 255), "Red": (200, 30, 30, 255),
    "Blue": (20, 60, 180, 255), "Green": (20, 140, 60, 255),
    "Yellow": (250, 220, 40, 255),
}
BG_SUFFIX = (". Background design only, vibrant, professional, no people, "
             "no text, empty space in the center.")
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


def flatten_on(img, rgb=(255, 255, 255)):
    bg = PILImage.new("RGB", img.size, rgb)
    bg.paste(img, mask=img.convert("RGBA").split()[3])
    return bg


def flatten_white(img):
    return flatten_on(img, (255, 255, 255))


def sharpen(img):
    r, g, b, a = img.convert("RGBA").split()
    rgb = PILImage.merge("RGB", (r, g, b)).filter(
        ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=3))
    r, g, b = rgb.split()
    return PILImage.merge("RGBA", (r, g, b, a))


def enhance_local(img, target=3000):
    rgba = img.convert("RGBA")
    long_side = max(rgba.size)
    if long_side < target:
        s = min(4.0, target / float(long_side))
        rgba = rgba.resize((int(rgba.width * s), int(rgba.height * s)),
                           PILImage.LANCZOS)
    return sharpen(rgba)


def make_pdf(rgb_img):
    out = io.BytesIO()
    rgb_img.save(out, "PDF", resolution=300.0)
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


def gemini_edit(img, prompt, mode="full"):
    """mode='object': सिर्फ़ बताया हुआ बदलाव, शेप/पारदर्शिता वही रहती है"""
    if mode == "object":
        full_prompt = (
            prompt + ". IMPORTANT: Only change what is described (for example "
            "the color of the specified object). Keep the shape, details, "
            "position and everything else exactly the same. Plain white "
            "background.")
    else:
        full_prompt = prompt + ". Keep it high quality and print ready."
    data = gemini_call(GEMINI_IMAGE_MODEL,
                       [{"text": full_prompt}, img_part(img)],
                       {"responseModalities": ["TEXT", "IMAGE"]})
    out = gemini_image_from(data)
    if out is None:
        raise Exception("Gemini returned no image")
    out = out.convert("RGBA")
    if mode == "object":
        a = img.convert("RGBA").split()[3]
        if out.size != img.size:
            out = out.resize(img.size, PILImage.LANCZOS)
        out.putalpha(a)
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
    r, g, b, a = img.convert("RGBA").split()
    a = a.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.7))
    return PILImage.merge("RGBA", (r, g, b, a))


def extract_person(img):
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
        return enhance_local(img, 3000), "Local (DeepAI: " + str(e)[:70] + ")"


def vectorize_pdf(img_rgba):
    if not (key_ok(VECTORIZER_ID) and key_ok(VECTORIZER_SECRET)):
        raise Exception("Vectorizer keys not set")
    flat = flatten_white(img_rgba)
    px = flat.width * flat.height
    if px > 3000000:
        s = (3000000.0 / px) ** 0.5
        flat = flat.resize((int(flat.width * s), int(flat.height * s)),
                           PILImage.LANCZOS)
    r = requests.post(
        "https://api.vectorizer.ai/api/v1/vectorize",
        files={"image": ("design.png", to_bytes(flat, "PNG"))},
        data={"output.file_format": "pdf"},
        auth=(VECTORIZER_ID, VECTORIZER_SECRET), timeout=240)
    if r.status_code == 200:
        return r.content
    raise Exception(f"Vectorizer {r.status_code}: {r.text[:120]}")


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


def make_text_image(text, color, outline, px=260):
    """टेक्स्ट को पारदर्शी RGBA इमेज (लेयर) में बदलता है"""
    mask = render_text_block(text, px)
    if mask is None:
        raise Exception("Text render failed")
    pad = int(px * 0.2) if outline != "No outline" else int(px * 0.05)
    mask = ImageOps.expand(mask, border=pad, fill=0)
    txt = PILImage.new("RGBA", mask.size, color + (255,))
    txt.putalpha(mask)
    if outline != "No outline":
        oc = (0, 0, 0) if outline.startswith("Black") else (255, 255, 255)
        om = mask.filter(ImageFilter.GaussianBlur(max(1, px / 18.0))).point(
            lambda v: 255 if v > 8 else 0).filter(ImageFilter.GaussianBlur(1))
        ol = PILImage.new("RGBA", mask.size, oc + (255,))
        ol.putalpha(om)
        out = PILImage.alpha_composite(ol, txt)
    else:
        out = txt
    bbox = out.getbbox()
    if bbox:
        out = out.crop(bbox)
    return out


# ---------------- लेयर सिस्टम ----------------

def new_layer(img, name, kind="image", fill=False, src=None,
              size=60.0, x=50.0, y=50.0):
    return {"img": img, "src": src, "name": name, "kind": kind, "fill": fill,
            "size": float(size), "x": float(x), "y": float(y), "rot": 0.0,
            "visible": True, "hist": [], "prev": None}


def layer_prev(L):
    if L["prev"] is None:
        p = L["img"].copy()
        p.thumbnail((1100, 1100), PILImage.LANCZOS)
        L["prev"] = p
    return L["prev"]


def fit_pct(img, wh):
    cw, ch = wh
    ar = img.width / float(img.height)
    return max(5.0, min(95.0, 95.0 * cw / (ar * ch)))


_CHK = {}


def checker(size):
    if size not in _CHK:
        w, h = size
        im = PILImage.new("RGBA", size, (215, 215, 215, 255))
        d = ImageDraw.Draw(im)
        t = 20
        for yy in range(0, h, t):
            for xx in range(0, w, t):
                if ((xx // t) + (yy // t)) % 2 == 0:
                    d.rectangle((xx, yy, xx + t - 1, yy + t - 1),
                                fill=(245, 245, 245, 255))
        _CHK.clear()
        _CHK[size] = im
    return _CHK[size]


def render_canvas(layers, canvas_wh, bg_rgba, scale, use_prev):
    W, H = canvas_wh
    cw, ch = max(1, int(W * scale)), max(1, int(H * scale))
    out = PILImage.new("RGBA", (cw, ch), bg_rgba if bg_rgba else (0, 0, 0, 0))
    for L in layers:
        if not L["visible"]:
            continue
        img = layer_prev(L) if use_prev else L["img"]
        if img is None:
            continue
        if L["fill"]:
            r = max(cw / float(img.width), ch / float(img.height))
            nw = max(1, int(img.width * r + 0.5))
            nh = max(1, int(img.height * r + 0.5))
            im2 = img.resize((nw, nh), PILImage.LANCZOS)
            l, t = (nw - cw) // 2, (nh - ch) // 2
            im2 = im2.crop((l, t, l + cw, t + ch))
            out = PILImage.alpha_composite(out, im2)
            continue
        th = max(2, int(ch * L["size"] / 100.0))
        r = th / float(img.height)
        tw = max(2, int(img.width * r))
        im2 = img.resize((tw, th), PILImage.LANCZOS)
        if abs(L["rot"]) > 0.01:
            im2 = im2.rotate(L["rot"], expand=True, resample=PILImage.BICUBIC)
        tmp = PILImage.new("RGBA", (cw, ch), (0, 0, 0, 0))
        px = int(cw * L["x"] / 100.0 - im2.width / 2.0)
        py = int(ch * L["y"] / 100.0 - im2.height / 2.0)
        tmp.paste(im2, (px, py))
        out = PILImage.alpha_composite(out, tmp)
    return out


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
            Color(0.15, 0.15, 0.15, 1)
            self.rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd, size=self._upd)

    def _upd(self, *a):
        self.rect.pos = self.pos
        self.rect.size = self.size


def mk_label(hi, en, h=30):
    return Label(text=bi(hi, en), markup=True, size_hint_y=None, height=dp(h))


# ---- लेयर पर चलने वाले काम (thread में) ----
def op_extract(im):
    cut, src, note = extract_person(im)
    return cut, src, note


def op_cut(im):
    cut = remove_background(im)
    return cut, align_src(im, cut), ""


def op_plain(im, tol):
    return remove_plain_bg(im, tol), im.convert("RGBA"), ""


def op_hd(im):
    hd, src = hd_upscale(im)
    return hd, None, "[" + src + "]"


class DesignApp(App):

    def build(self):
        self.title = "AI Design Studio"
        self.layers = []
        self.sel = None
        self._syncing = False
        self._pv_ev = None
        self.camera_uri = None
        self.last_uri = None
        self.last_mime = "application/pdf"
        self.action_btns = []
        self.lsliders = {}

        scroll = ScrollView()
        root = BoxLayout(orientation="vertical", size_hint_y=None,
                         padding=dp(10), spacing=dp(8))
        root.bind(minimum_height=root.setter("height"))
        scroll.add_widget(root)

        # ===== 1) फ़ोटो =====
        root.add_widget(mk_label("1) फ़ोटो चुनें (कई एक साथ)",
                                 "1) Choose photos (many)", 32))
        self._row(root, [("गैलरी (कई)", "Gallery (multi)", self.pick_gallery, None),
                         ("कैमरा", "Camera", self.pick_camera, None)])

        pv = Preview(size_hint_y=None, height=dp(360), padding=dp(2))
        self.preview = Image(nocache=True)
        pv.add_widget(self.preview)
        root.add_widget(pv)

        # ===== 2) कैनवास =====
        root.add_widget(mk_label("2) कैनवास", "2) Canvas", 30))
        crow = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        self.canvas_sp = Spinner(text="Portrait 2:3",
                                 values=list(CANVAS_META.keys()))
        self.canvas_sp.bind(text=lambda *a: self.schedule_preview())
        self.cbg_sp = Spinner(text="Transparent", values=list(BG_COLORS.keys()))
        self.cbg_sp.bind(text=lambda *a: self.schedule_preview())
        crow.add_widget(self.canvas_sp)
        crow.add_widget(self.cbg_sp)
        root.add_widget(crow)

        # ===== 3) लेयर =====
        root.add_widget(mk_label("3) लेयर चुनें और सेट करें",
                                 "3) Select & arrange layer", 32))
        self.layer_sp = Spinner(text="No layers", values=[],
                                size_hint_y=None, height=dp(48))
        self.layer_sp.bind(text=self._on_layer_pick)
        root.add_widget(self.layer_sp)
        self._row(root, [("ऊपर", "Up", self.on_up, None),
                         ("नीचे", "Down", self.on_down, None),
                         ("छिपाएँ/दिखाएँ", "Hide/Show", self.on_vis, None),
                         ("हटाएँ", "Delete", self.on_delete, (0.8, 0.2, 0.2, 1))],
                  track=False, h=52)
        self._row(root, [("फ़िट करें", "Fit", self.on_fit, None),
                         ("बैकग्राउंड बनाएँ", "Use as BG (fill)", self.on_fill, None)],
                  track=False, h=52)
        self._lslider(root, "आकार", "Size", 5, 140, 60, "size")
        self._lslider(root, "बाएँ-दाएँ", "Left-Right", -10, 110, 50, "x")
        self._lslider(root, "ऊपर-नीचे", "Up-Down", -10, 110, 50, "y")
        self._lslider(root, "घुमाव", "Rotate", -180, 180, 0, "rot")

        # ===== 4) कटिंग =====
        root.add_widget(mk_label("4) चुनी लेयर की कटिंग / HD",
                                 "4) Cut / HD (selected layer)", 32))
        self._row(root, [
            ("व्यक्ति अलग करें", "Extract Person", self.on_extract, (0.9, 0.5, 0.1, 1)),
            ("बैकग्राउंड काटें (AI)", "Cut BG (AI)", self.on_cut, (0.7, 0.4, 0.1, 1))])
        self.tol_sl = self._slider(root, "सहनशीलता", "Tolerance", 5, 120, 40)
        self._row(root, [
            ("सादा बैकग्राउंड हटाएँ", "Remove Plain BG", self.on_plain, (0.6, 0.3, 0.6, 1)),
            ("करेक्शन करें", "Edit / Correct", self.open_editor, (0.1, 0.6, 0.5, 1))])
        self._row(root, [("HD बनाएँ", "Make HD", self.on_hd, (0.2, 0.6, 1, 1)),
                         ("इस लेयर का Undo", "Layer Undo", self.on_layer_undo, None)],
                  track=False)

        # ===== 5) AI =====
        root.add_widget(mk_label("5) AI डिज़ाइन", "5) AI design", 32))
        root.add_widget(Label(text=bi("पीछे का डिज़ाइन कैसा हो (English/Hinglish)",
                                      "Describe the background design"),
                              markup=True, size_hint_y=None, height=dp(26)))
        self.bg_prompt = TextInput(
            hint_text="e.g. purple gold luxury poster background",
            multiline=True, size_hint_y=None, height=dp(64))
        root.add_widget(self.bg_prompt)
        self._row(root, [
            ("AI बैकग्राउंड बनाएँ", "AI Background", self.on_ai_bg, (0.2, 0.4, 0.9, 1)),
            ("AUTO: अलग+HD+बैकग्राउंड", "AUTO: Cut+HD+BG", self.on_auto, (0.1, 0.7, 0.3, 1))],
            h=60)
        root.add_widget(Label(text=bi("चुनी लेयर में क्या बदलना है",
                                      "What to change in selected layer"),
                              markup=True, size_hint_y=None, height=dp(26)))
        self.edit_prompt = TextInput(
            hint_text="e.g. change shirt color to red  /  golden texture",
            multiline=True, size_hint_y=None, height=dp(64))
        root.add_widget(self.edit_prompt)
        self._row(root, [
            ("ऑब्जेक्ट/रंग बदलें", "Change Object/Color", self.on_ai_object, (0.9, 0.4, 0.1, 1)),
            ("पूरा AI एडिट", "Full AI Edit", self.on_ai_full, (0.5, 0.2, 0.7, 1))], h=60)

        # ===== 6) टेक्स्ट =====
        root.add_widget(mk_label("6) टेक्स्ट (नई लेयर बनती है)",
                                 "6) Text (becomes a layer)", 32))
        self.hi_input = TextInput(
            hint_text=("यहाँ हिंदी में लिखें" if HAS_FONT else "Hindi text"),
            font_name=(FONT_PATH if HAS_FONT else "Roboto"),
            multiline=True, size_hint_y=None, height=dp(60))
        root.add_widget(self.hi_input)
        self.en_input = TextInput(
            hint_text="Write English text here", multiline=True,
            size_hint_y=None, height=dp(60))
        root.add_widget(self.en_input)
        trow = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        self.color_sp = Spinner(text="White", values=list(COLORS.keys()))
        self.outline_sp = Spinner(
            text="Black outline",
            values=["No outline", "Black outline", "White outline"])
        trow.add_widget(self.color_sp)
        trow.add_widget(self.outline_sp)
        root.add_widget(trow)
        self.tsize_sl = self._slider(root, "टेक्स्ट आकार", "Text size", 3, 30, 9)
        self._row(root, [("टेक्स्ट जोड़ें", "Add Text", self.on_add_text,
                          (0.1, 0.6, 0.5, 1))], track=False)

        # ===== 7) सेव =====
        root.add_widget(mk_label("7) सेव / भेजें", "7) Save / Send", 32))
        self._row(root, [("PNG सेव (शर्ट प्रिंट)", "Save PNG",
                          lambda *_: self.export("png"), None),
                         ("PDF सेव", "Save PDF",
                          lambda *_: self.export("pdf"), None)], h=56)
        self._row(root, [("वेक्टर PDF (शार्प)", "Vector PDF",
                          lambda *_: self.export("vector"), None)], h=52)
        self._row(root, [("पिछली फ़ाइल शेयर करें", "Share last file",
                          self.share_last, (0.2, 0.7, 0.3, 1))],
                  track=False, h=52)

        self.status = Label(text=bi("तैयार", "Ready"), markup=True,
                            size_hint_y=None, height=dp(70))
        self.status.bind(size=lambda w, s: setattr(w, "text_size", s))
        root.add_widget(self.status)

        if platform == "android":
            try:
                from android import activity
                activity.bind(on_activity_result=self._on_result)
            except Exception:
                pass
        Clock.schedule_once(lambda dt: self.refresh_preview(), 0.3)
        return scroll

    # ---------- UI helpers ----------
    def _row(self, root, items, track=True, h=56):
        row = BoxLayout(size_hint_y=None, height=dp(h), spacing=dp(6))
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
                             size_hint_x=None, width=dp(140)))
        sl = Slider(min=mn, max=mx, value=val)
        row.add_widget(sl)
        root.add_widget(row)
        return sl

    def _lslider(self, root, hi, en, mn, mx, val, key):
        sl = self._slider(root, hi, en, mn, mx, val)
        sl.bind(value=lambda inst, v, k=key: self._on_layer_slider(k, v))
        self.lsliders[key] = sl

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

    # ---------- कैनवास / preview ----------
    def canvas_wh(self):
        return CANVAS_META[self.canvas_sp.text][0]

    def bg_rgba(self):
        return BG_COLORS[self.cbg_sp.text]

    def schedule_preview(self, *a):
        if self._pv_ev is not None:
            self._pv_ev.cancel()
        self._pv_ev = Clock.schedule_once(lambda dt: self.refresh_preview(), 0.12)

    def refresh_preview(self):
        try:
            W, H = self.canvas_wh()
            s = 900.0 / max(W, H)
            out = render_canvas(self.layers, (W, H), self.bg_rgba(), s, True)
            shown = PILImage.alpha_composite(checker(out.size), out)
            path = os.path.join(self.user_data_dir, "preview.png")
            shown.convert("RGB").save(path, "PNG")
            self.preview.source = path
            self.preview.reload()
        except Exception as e:
            self.status.text = "Preview error: " + escape_markup(str(e))[:120]

    # ---------- लेयर मैनेजमेंट ----------
    def index_of(self, L):
        for i, x in enumerate(self.layers):
            if x is L:
                return i
        return -1

    def update_layers_ui(self, select=None):
        self._syncing = True
        self.layer_sp.values = ["%d: %s" % (i + 1, L["name"])
                                for i, L in enumerate(self.layers)]
        self._syncing = False
        if select is None and self.layers:
            select = self.sel if self.index_of(self.sel) >= 0 else self.layers[-1]
        self._set_sel(select)
        self.refresh_preview()

    def _set_sel(self, L):
        self.sel = L
        self._syncing = True
        if L is None or self.index_of(L) < 0:
            self.sel = None
            self.layer_sp.text = "No layers"
        else:
            self.layer_sp.text = "%d: %s" % (self.index_of(L) + 1, L["name"])
            for key, sl in self.lsliders.items():
                sl.value = L[key]
        self._syncing = False

    def _on_layer_pick(self, inst, text):
        if self._syncing:
            return
        try:
            i = int(text.split(":")[0]) - 1
            if 0 <= i < len(self.layers):
                self._set_sel(self.layers[i])
        except Exception:
            pass

    def _on_layer_slider(self, key, v):
        if self._syncing or self.sel is None:
            return
        self.sel[key] = float(v)
        self.schedule_preview()

    def add_layer(self, L, bottom=False):
        if bottom:
            self.layers.insert(0, L)
        else:
            self.layers.append(L)
        self.update_layers_ui(select=L)

    def need_sel(self):
        if self.sel is None:
            self.popup(bi("पहले फ़ोटो चुनें और लेयर सेलेक्ट करें",
                          "Choose photos and select a layer first"))
            return None
        return self.sel

    def on_up(self, *a):
        L = self.sel
        i = self.index_of(L) if L else -1
        if 0 <= i < len(self.layers) - 1:
            self.layers[i], self.layers[i + 1] = self.layers[i + 1], self.layers[i]
            self.update_layers_ui(select=L)

    def on_down(self, *a):
        L = self.sel
        i = self.index_of(L) if L else -1
        if i > 0:
            self.layers[i], self.layers[i - 1] = self.layers[i - 1], self.layers[i]
            self.update_layers_ui(select=L)

    def on_vis(self, *a):
        L = self.sel
        if L:
            L["visible"] = not L["visible"]
            self.refresh_preview()

    def on_delete(self, *a):
        L = self.sel
        i = self.index_of(L) if L else -1
        if i >= 0:
            self.layers.pop(i)
            self.sel = None
            self.update_layers_ui(select=None)

    def on_fit(self, *a):
        L = self.need_sel()
        if L is None:
            return
        L["size"] = fit_pct(L["img"], self.canvas_wh())
        L["x"], L["y"], L["rot"] = 50.0, 50.0, 0.0
        self._set_sel(L)
        self.refresh_preview()

    def on_fill(self, *a):
        L = self.need_sel()
        if L is None:
            return
        if L["fill"]:
            L["fill"] = False
        else:
            for x in self.layers:
                x["fill"] = False
            L["fill"] = True
            self.layers.pop(self.index_of(L))
            self.layers.insert(0, L)
        self.update_layers_ui(select=L)

    # ---------- फ़ोटो चुनना (कई) ----------
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
            intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, True)
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            chooser = Intent.createChooser(
                intent, cast("java.lang.CharSequence", String("Select photos")))
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
        uris = []
        try:
            if request_code == REQ_GALLERY and intent is not None:
                clip = intent.getClipData()
                if clip is not None:
                    for i in range(clip.getItemCount()):
                        uris.append(clip.getItemAt(i).getUri())
                else:
                    u = intent.getData()
                    if u is not None:
                        uris.append(u)
            elif request_code == REQ_CAMERA and self.camera_uri is not None:
                uris.append(self.camera_uri)
        except Exception:
            pass
        if uris:
            Clock.schedule_once(lambda dt: self._load_uris(uris[:8]))

    def _load_uris(self, uris):
        blobs = []
        for u in uris:
            try:
                blobs.append(read_uri_bytes(u))
            except Exception as e:
                self.popup("Read error: " + escape_markup(str(e)))
        if not blobs:
            return
        self.busy(bi("फ़ोटो लोड हो रही हैं...", "Loading photos..."))
        threading.Thread(target=self._decode_worker, args=(blobs,),
                         daemon=True).start()

    def _decode_worker(self, blobs):
        try:
            imgs = [load_pil(b) for b in blobs]
            self.ui(lambda: self._add_images(imgs))
        except Exception as e:
            self.fail(e)

    def _add_images(self, imgs):
        spots = [(50, 50), (30, 32), (70, 68), (30, 70), (70, 30), (50, 50)]
        wh = self.canvas_wh()
        last = None
        for img in imgs:
            n = len(self.layers)
            fit = fit_pct(img, wh)
            first = (n == 0)
            sx, sy = spots[n % len(spots)] if not first else (50, 50)
            L = new_layer(img, "Photo %d" % (n + 1),
                          size=(fit if first else fit * 0.5), x=sx, y=sy)
            self.layers.append(L)
            last = L
        self.update_layers_ui(select=last)
        self.done(bi("%d फ़ोटो जुड़ गईं (कुल %d लेयर)" % (len(imgs), len(self.layers)),
                     "%d photo(s) added (%d layers)" % (len(imgs), len(self.layers))))

    # ---------- चुनी लेयर पर काम ----------
    def run_layer_op(self, hi, en, fn, ok_hi, ok_en):
        L = self.need_sel()
        if L is None:
            return
        self.busy(bi(hi, en))
        img = L["img"]

        def work():
            try:
                res = fn(img)
                self.ui(lambda: self._apply_result(L, res, ok_hi, ok_en))
            except Exception as e:
                self.fail(e)

        threading.Thread(target=work, daemon=True).start()

    def _push_hist(self, L):
        L["hist"].append(L["img"])
        L["hist"] = L["hist"][-3:]

    def _apply_result(self, L, res, ok_hi, ok_en):
        new_img, new_src, note = res
        self._push_hist(L)
        L["img"] = new_img
        if new_src is not None:
            L["src"] = new_src
        L["prev"] = None
        self.refresh_preview()
        msg = bi(ok_hi, ok_en)
        if note:
            msg += "\n" + escape_markup(str(note))
        self.done(msg)

    def on_extract(self, *a):
        self.run_layer_op("व्यक्ति अलग कर रहा है...", "Extracting person...",
                          op_extract, "व्यक्ति अलग हो गया", "Person extracted")

    def on_cut(self, *a):
        self.run_layer_op("बैकग्राउंड हटा रहा है...", "Removing background...",
                          op_cut, "कटिंग हो गई!", "Cut done!")

    def on_plain(self, *a):
        tol = int(self.tol_sl.value)
        self.run_layer_op("सादा बैकग्राउंड हटा रहा है...", "Removing plain BG...",
                          lambda im, t=tol: op_plain(im, t),
                          "हो गया. बचा हिस्सा 'करेक्शन करें' से ठीक करें",
                          "Done. Fix leftovers with Edit / Correct")

    def on_hd(self, *a):
        self.run_layer_op("HD बना रहा है...", "Making HD...",
                          op_hd, "HD हो गया", "HD done")

    def on_layer_undo(self, *a):
        L = self.need_sel()
        if L is None:
            return
        if L["hist"]:
            L["img"] = L["hist"].pop()
            L["prev"] = None
            self.refresh_preview()
            self.status.text = bi("वापस हो गया", "Undone")

    def _need_edit_prompt(self):
        p = self.edit_prompt.text.strip()
        if not p:
            self.popup(bi("क्या बदलना है वह लिखें", "Write what to change"))
        return p

    def on_ai_object(self, *a):
        if self.need_sel() is None:
            return
        p = self._need_edit_prompt()
        if not p:
            return
        self.run_layer_op("AI बदलाव कर रहा है...", "AI changing...",
                          lambda im, pr=p: (gemini_edit(im, pr, "object"), None, ""),
                          "बदलाव हो गया!", "Change done!")

    def on_ai_full(self, *a):
        if self.need_sel() is None:
            return
        p = self._need_edit_prompt()
        if not p:
            return
        self.run_layer_op("AI एडिट कर रहा है...", "AI editing...",
                          lambda im, pr=p: (gemini_edit(im, pr, "full"), None, ""),
                          "एडिट हो गया!", "Edit done!")

    # ---------- AI बैकग्राउंड / AUTO ----------
    def _bg_prompt(self):
        p = self.bg_prompt.text.strip()
        if not p:
            self.popup(bi("पहले बैकग्राउंड का विवरण लिखें",
                          "Write the background description first"))
        return p

    def _set_fill_layer(self, bg_img):
        self.layers = [x for x in self.layers if not x["fill"]]
        F = new_layer(bg_img, "AI Background", fill=True)
        self.layers.insert(0, F)
        self.update_layers_ui(select=self.sel)

    def on_ai_bg(self, *a):
        p = self._bg_prompt()
        if not p:
            return
        meta = CANVAS_META[self.canvas_sp.text]
        self.busy(bi("बैकग्राउंड बना रहा है...", "Creating background..."))
        threading.Thread(target=self._bg_worker, args=(p, meta),
                         daemon=True).start()

    def _bg_worker(self, prompt, meta):
        try:
            _, aspect, (w, h) = meta
            bg = generate_image(prompt + BG_SUFFIX, aspect, w, h)
            self.ui(lambda: self._set_fill_layer(bg))
            self.ui(lambda: self.done(bi("बैकग्राउंड तैयार", "Background ready")))
        except Exception as e:
            self.fail(e)

    def on_auto(self, *a):
        L = self.need_sel()
        if L is None:
            return
        p = self._bg_prompt()
        if not p:
            return
        meta = CANVAS_META[self.canvas_sp.text]
        self.busy(bi("AUTO चल रहा है...", "AUTO running..."))
        threading.Thread(target=self._auto_worker, args=(L, p, meta),
                         daemon=True).start()

    def _commit(self, L, img, src):
        self._push_hist(L)
        L["img"] = img
        if src is not None:
            L["src"] = src
        L["prev"] = None
        self.refresh_preview()

    def _auto_worker(self, L, prompt, meta):
        try:
            _, aspect, (w, h) = meta
            self.say(bi("1/3 व्यक्ति अलग कर रहा है...", "1/3 Extracting person..."))
            cut, src, note = extract_person(L["img"])
            self.ui(lambda: self._commit(L, cut, src))
            self.say(bi("2/3 HD बना रहा है...", "2/3 Making HD..."))
            hd, hsrc = hd_upscale(cut)
            self.ui(lambda: self._commit(L, hd, None))
            self.say(bi("3/3 बैकग्राउंड बना रहा है...", "3/3 Creating background..."))
            bg = generate_image(prompt + BG_SUFFIX, aspect, w, h)

            def finish():
                L["size"], L["x"], L["y"], L["rot"] = 74.0, 50.0, 60.0, 0.0
                self._set_fill_layer(bg)
                self._set_sel(L)
                self.done(bi("पूरा हुआ!", "All done!")
                          + "  [HD: " + escape_markup(hsrc) + "]"
                          + (("\n" + escape_markup(note)) if note else ""))

            self.ui(finish)
        except Exception as e:
            self.fail(e)

    # ---------- करेक्शन एडिटर ----------
    def open_editor(self, *a):
        L = self.need_sel()
        if L is None:
            return
        target = L["img"]
        src = align_src(L["src"], target) if L["src"] is not None else None
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
            self._push_hist(L)
            L["img"] = res
            L["prev"] = None
            self.refresh_preview()
            self.status.text = bi("करेक्शन लागू हुआ", "Correction applied")

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

    # ---------- टेक्स्ट ----------
    def on_add_text(self, *a):
        text = (self.hi_input.text + "\n" + self.en_input.text).strip()
        if not text:
            self.popup(bi("टेक्स्ट लिखें", "Write some text"))
            return
        try:
            img = make_text_image(text, COLORS[self.color_sp.text],
                                  self.outline_sp.text)
            lines = max(1, len([l for l in text.split("\n") if l.strip()]))
            size = min(80.0, self.tsize_sl.value * lines)
            name = "Text: " + text.replace("\n", " ")[:14]
            L = new_layer(img, name, kind="text", size=size, x=50, y=88)
            self.add_layer(L)
            self.status.text = bi("टेक्स्ट लेयर जुड़ गई", "Text layer added")
        except Exception as e:
            self.popup("Text error: " + escape_markup(str(e)))

    # ---------- एक्सपोर्ट ----------
    def export(self, kind):
        if not self.layers:
            self.popup(bi("पहले फ़ोटो चुनें", "Choose photos first"))
            return
        snap = [dict(L) for L in self.layers]
        wh = self.canvas_wh()
        bg = self.bg_rgba()
        self.busy(bi("फ़ाइल बना रहा है...", "Preparing file..."))
        threading.Thread(target=self._export_worker, args=(kind, snap, wh, bg),
                         daemon=True).start()

    def _export_worker(self, kind, snap, wh, bg):
        try:
            full = render_canvas(snap, wh, bg, 1.0, False)
            stamp = int(time.time())
            if kind == "png":
                data = to_bytes(sharpen(full), "PNG", dpi=300)
                name, mime = "design_%d.png" % stamp, "image/png"
            elif kind == "pdf":
                flat = flatten_on(sharpen(full), bg[:3] if bg else (255, 255, 255))
                data = make_pdf(flat)
                name, mime = "design_%d.pdf" % stamp, "application/pdf"
            else:
                data = vectorize_pdf(full)
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
