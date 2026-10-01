import os
import io
import time
import base64
import threading
import requests
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.text import Label as CoreLabel
from kivy.metrics import dp
from kivy.graphics import Color, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.uix.slider import Slider
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.utils import platform, escape_markup
from PIL import Image as PILImage, ImageOps, ImageFilter

# ================= यहाँ अपनी keys डालिए =================
REMOVEBG_KEY = "tTqBYQZHyFSMgQW6Mkzf2sSc"
GEMINI_KEY = "PASTE_GEMINI_KEY"            # फ़ोटो बदलने के लिए (aistudio.google.com)
GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image"
VECTORIZER_ID = "PASTE_VECTORIZER_ID"      # वैकल्पिक (vectorizer.ai/api)
VECTORIZER_SECRET = "PASTE_VECTORIZER_SECRET"
# =========================================================

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


def bi(hi, en, sep=" / "):
    if not HAS_FONT:
        return en
    return f"[font={FONT_PATH}]{hi}[/font]{sep}{en}"


def key_ok(v):
    return bool(v) and not v.startswith("PASTE")


# ---------------- इमेज हेल्पर ----------------

def load_pil(data):
    im = PILImage.open(io.BytesIO(data))
    try:
        im = ImageOps.exif_transpose(im)
    except Exception:
        pass
    im = im.convert("RGBA")
    im.thumbnail((2048, 2048), PILImage.LANCZOS)
    return im


def to_bytes(img, fmt="PNG"):
    out = io.BytesIO()
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


# ---------------- AI / API ----------------

def generate_design(prompt):
    full = prompt + ", isolated on plain white background, sticker design, high detail"
    url = ("https://image.pollinations.ai/prompt/" + requests.utils.quote(full)
           + "?width=1024&height=1024&nologo=true")
    r = requests.get(url, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        raise Exception(f"Design generation error {r.status_code}")
    return load_pil(r.content)


def gemini_edit(img, prompt):
    if not key_ok(GEMINI_KEY):
        raise Exception("GEMINI_KEY not set in main.py")
    jpg = to_bytes(flatten_white(img), "JPEG")
    payload = {
        "contents": [{"parts": [
            {"text": prompt + ". Keep it high quality and print ready."},
            {"inline_data": {"mime_type": "image/jpeg",
                             "data": base64.b64encode(jpg).decode()}},
        ]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           + GEMINI_IMAGE_MODEL + ":generateContent")
    r = requests.post(url, params={"key": GEMINI_KEY}, json=payload, timeout=180)
    data = r.json()
    for cand in data.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            inl = part.get("inlineData") or part.get("inline_data")
            if inl and inl.get("data"):
                return load_pil(base64.b64decode(inl["data"]))
    msg = data.get("error", {}).get("message", "No image returned")
    raise Exception("Gemini: " + msg[:200])


def remove_background(img):
    r = requests.post(
        "https://api.remove.bg/v1.0/removebg",
        files={"image_file": ("img.png", to_bytes(img, "PNG"))},
        data={"size": "auto"},
        headers={"X-Api-Key": REMOVEBG_KEY}, timeout=120)
    if r.status_code == 200:
        return load_pil(r.content)
    try:
        msg = r.json()["errors"][0]["title"]
    except Exception:
        msg = f"HTTP {r.status_code}"
    raise Exception("remove.bg: " + msg)


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
    """Android: Download/AIDesign में सेव. return (label, uri)"""
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


def mk_btn(hi, en, cb, h=52, color=None):
    b = Button(text=bi(hi, en, sep="\n"), markup=True, halign="center",
               size_hint_y=None, height=dp(h))
    if color:
        b.background_color = color
    b.bind(on_press=cb)
    return b


def mk_label(hi, en, h=30):
    return Label(text=bi(hi, en), markup=True, size_hint_y=None, height=dp(h))


class DesignApp(App):
    base = None
    final = None
    history = []
    last_uri = None
    last_mime = "application/pdf"
    camera_uri = None

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

        pv = Preview(size_hint_y=None, height=dp(300), padding=dp(2))
        self.preview = Image()
        pv.add_widget(self.preview)
        root.add_widget(pv)

        root.add_widget(mk_label("2) क्या बदलना/बनाना है (English बेहतर)",
                                 "2) What to change/create", 34))
        self.prompt_input = TextInput(
            hint_text="e.g. make it a cartoon lion logo, red tshirt design",
            multiline=True, size_hint_y=None, height=dp(80))
        root.add_widget(self.prompt_input)
        r2 = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(8))
        for hi, en, cb, col in [
                ("AI डिज़ाइन / बदलाव", "AI Design / Edit", self.on_ai, (0.2, 0.6, 1, 1)),
                ("बैकग्राउंड काटें", "Cut Background", self.on_cut, (0.9, 0.5, 0.1, 1))]:
            b = Button(text=bi(hi, en, sep="\n"), markup=True, halign="center",
                       background_color=col)
            b.bind(on_press=cb)
            r2.add_widget(b)
            self.action_btns.append(b)
        root.add_widget(r2)
        ub = mk_btn("पिछला वापस (Undo)", "Undo", self.on_undo, 44)
        root.add_widget(ub)

        root.add_widget(mk_label("3) टेक्स्ट लिखें", "3) Add text", 34))
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

        self.size_sl = self._slider(root, "आकार", "Size", 3, 40, 9)
        self.x_sl = self._slider(root, "बाएँ-दाएँ", "Left-Right", 0, 100, 50)
        self.y_sl = self._slider(root, "ऊपर-नीचे", "Up-Down", 0, 100, 85)

        r3 = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        b1 = Button(text=bi("टेक्स्ट जोड़ें", "Add Text", sep="\n"),
                    markup=True, halign="center")
        b1.bind(on_press=self.on_add_text)
        b2 = Button(text=bi("टेक्स्ट हटाएँ", "Remove Text", sep="\n"),
                    markup=True, halign="center")
        b2.bind(on_press=self.on_remove_text)
        r3.add_widget(b1)
        r3.add_widget(b2)
        root.add_widget(r3)

        root.add_widget(mk_label("4) सेव / भेजें", "4) Save / Send", 34))
        r4 = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        for hi, en, kind in [("PNG सेव", "Save PNG", "png"),
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
        root.add_widget(mk_btn("पिछली फ़ाइल शेयर करें", "Share last file",
                               self.share_last, 52, (0.2, 0.7, 0.3, 1)))

        self.status = Label(text=bi("तैयार", "Ready"), markup=True,
                            size_hint_y=None, height=dp(40))
        root.add_widget(self.status)

        if platform == "android":
            try:
                from android import activity
                activity.bind(on_activity_result=self._on_result)
            except Exception:
                pass
        return scroll

    def _slider(self, root, hi, en, mn, mx, val):
        row = BoxLayout(size_hint_y=None, height=dp(40))
        row.add_widget(Label(text=bi(hi, en), markup=True,
                             size_hint_x=None, width=dp(130)))
        sl = Slider(min=mn, max=mx, value=val)
        row.add_widget(sl)
        root.add_widget(row)
        return sl

    # ---------- helpers ----------
    def popup(self, msg):
        c = Label(text=msg, markup=True, halign="center")
        c.bind(size=lambda w, s: setattr(w, "text_size", s))
        Popup(title="Info", content=c, size_hint=(0.88, 0.4)).open()

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
        Clock.schedule_once(lambda dt: (self.popup(msg),
                                        self.done(bi("फेल", "Failed"))))

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
            self.history = self.history[-6:]
        self.base = img
        self.final = None
        self.refresh_preview()

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
            self.set_base(img, push=False)
            self.done(bi("फ़ोटो लोड हो गई", "Photo loaded"))
        except Exception as e:
            self.popup("Load error: " + escape_markup(str(e)))

    # ---------- AI / कटिंग ----------
    def on_ai(self, *a):
        prompt = self.prompt_input.text.strip()
        if not prompt:
            self.popup(bi("पहले प्रॉम्प्ट लिखें", "Write a prompt first"))
            return
        self.busy(bi("AI काम कर रहा है...", "AI is working..."))
        threading.Thread(target=self._ai_worker, args=(prompt, self.base),
                         daemon=True).start()

    def _ai_worker(self, prompt, base):
        try:
            img = generate_design(prompt) if base is None else gemini_edit(base, prompt)
            Clock.schedule_once(lambda dt: self.set_base(img))
            Clock.schedule_once(lambda dt: self.done(bi("हो गया!", "Done!")))
        except Exception as e:
            self.fail(e)

    def on_cut(self, *a):
        if self.base is None:
            self.popup(bi("पहले फ़ोटो चुनें या डिज़ाइन बनाएँ",
                          "Pick a photo or create a design first"))
            return
        self.busy(bi("बैकग्राउंड हटा रहा है...", "Removing background..."))
        threading.Thread(target=self._cut_worker, args=(self.base,),
                         daemon=True).start()

    def _cut_worker(self, base):
        try:
            img = remove_background(base)
            Clock.schedule_once(lambda dt: self.set_base(img))
            Clock.schedule_once(lambda dt: self.done(bi("कटिंग हो गई!", "Cut done!")))
        except Exception as e:
            self.fail(e)

    def on_undo(self, *a):
        if self.history:
            self.base = self.history.pop()
            self.final = None
            self.refresh_preview()

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
                data = to_bytes(enhance_for_print(img), "PNG")
                name, mime = "design_%d.png" % stamp, "image/png"
            elif kind == "pdf":
                data = make_pdf(enhance_for_print(img))
                name, mime = "design_%d.pdf" % stamp, "application/pdf"
            else:
                data = vectorize_pdf(to_bytes(img, "PNG"))
                name, mime = "design_vector_%d.pdf" % stamp, "application/pdf"
            Clock.schedule_once(lambda dt: self._finish_save(name, data, mime))
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
