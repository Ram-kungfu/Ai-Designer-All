import os
import io
import threading
import requests
from datetime import datetime
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.slider import Slider
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.progressbar import ProgressBar
from kivy.clock import Clock
from kivy.core.window import Window
from PIL import Image as PILImage, ImageDraw, ImageFont, ImageEnhance, ImageOps

# ============================================================
# ---------- AI बैकएंड फंक्शन्स ----------
# ============================================================

def generate_design(prompt, width=1024, height=1024):
    """Pollinations AI से फ्री डिज़ाइन जनरेट करें"""
    try:
        url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}?width={width}&height={height}&nologo=true"
        response = requests.get(url, timeout=90)
        if response.status_code == 200 and len(response.content) > 1000:
            return response.content
        raise Exception(f"सर्वर एरर: {response.status_code}")
    except Exception as e:
        raise Exception(f"डिज़ाइन जनरेशन फेल: {str(e)}")


def remove_background(image_bytes):
    """
    फ्री API की मदद से बैकग्राउंड हटाएं।
    नोट: rembg को हटा दिया गया है क्योंकि यह Android पर कंपाइल नहीं होता।
    फिलहाल यह ओरिजिनल इमेज लौटाता है ताकि ऐप क्रैश न हो।
    """
    try:
        # यहाँ आप भविष्य में कोई फ्री बैकग्राउंड रिमूवल API जोड़ सकते हैं
        # जैसे remove.bg का फ्री टियर या कोई और सेवा
        return image_bytes
    except Exception as e:
        return image_bytes


def upscale_image(image_bytes, scale=2):
    """इमेज को बड़ा और साफ करें"""
    try:
        img = PILImage.open(io.BytesIO(image_bytes)).convert("RGBA")
        new_size = (img.width * scale, img.height * scale)
        upscaled = img.resize(new_size, PILImage.LANCZOS)
        buf = io.BytesIO()
        upscaled.save(buf, format='PNG')
        return buf.getvalue()
    except Exception as e:
        raise Exception(f"अपस्केलिंग फेल: {str(e)}")


def get_font(size):
    """फॉन्ट लोड करें - Android और डेस्कटॉप दोनों के लिए"""
    font_paths = [
        "/system/fonts/Roboto-Bold.ttf",
        "/system/fonts/Roboto-Regular.ttf",
        "/system/fonts/DroidSans-Bold.ttf",
        "Roboto-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except:
            continue
    return ImageFont.load_default()


def add_text_to_image(image_bytes, text, position="bottom", font_size=60,
                      text_color=(255, 255, 255, 255),
                      stroke_color=(0, 0, 0, 255), stroke_width=3):
    """डिज़ाइन पर टेक्स्ट लिखें"""
    try:
        img = PILImage.open(io.BytesIO(image_bytes)).convert("RGBA")
        draw = ImageDraw.Draw(img)
        font = get_font(font_size)

        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        x = max(10, (img.width - tw) // 2)
        if position == "top":
            y = 30
        elif position == "center":
            y = (img.height - th) // 2
        else:
            y = img.height - th - 50

        if stroke_width > 0:
            for dx in range(-stroke_width, stroke_width + 1):
                for dy in range(-stroke_width, stroke_width + 1):
                    if dx != 0 or dy != 0:
                        draw.text((x + dx, y + dy), text, font=font, fill=stroke_color)

        draw.text((x, y), text, font=font, fill=text_color)

        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()
    except Exception as e:
        raise Exception(f"टेक्स्ट जोड़ने में फेल: {str(e)}")


def rotate_image(image_bytes, angle):
    """इमेज को घुमाएं"""
    try:
        img = PILImage.open(io.BytesIO(image_bytes))
        rotated = img.rotate(-angle, expand=True)
        buf = io.BytesIO()
        rotated.save(buf, format='PNG')
        return buf.getvalue()
    except Exception as e:
        raise Exception(f"रोटेट फेल: {str(e)}")


def flip_image(image_bytes, direction="horizontal"):
    """इमेज को उल्टा करें"""
    try:
        img = PILImage.open(io.BytesIO(image_bytes))
        if direction == "horizontal":
            flipped = ImageOps.mirror(img)
        else:
            flipped = ImageOps.flip(img)
        buf = io.BytesIO()
        flipped.save(buf, format='PNG')
        return buf.getvalue()
    except Exception as e:
        raise Exception(f"फ्लिप फेल: {str(e)}")


def adjust_brightness(image_bytes, factor=1.0):
    """ब्राइटनेस बदलें"""
    try:
        img = PILImage.open(io.BytesIO(image_bytes)).convert("RGBA")
        enhancer = ImageEnhance.Brightness(img)
        result = enhancer.enhance(factor)
        buf = io.BytesIO()
        result.save(buf, format='PNG')
        return buf.getvalue()
    except Exception as e:
        raise Exception(f"ब्राइटनेस फेल: {str(e)}")


def adjust_contrast(image_bytes, factor=1.0):
    """कंट्रास्ट बदलें"""
    try:
        img = PILImage.open(io.BytesIO(image_bytes)).convert("RGBA")
        enhancer = ImageEnhance.Contrast(img)
        result = enhancer.enhance(factor)
        buf = io.BytesIO()
        result.save(buf, format='PNG')
        return buf.getvalue()
    except Exception as e:
        raise Exception(f"कंट्रास्ट फेल: {str(e)}")


def apply_filter(image_bytes, filter_type="none"):
    """कलर फिल्टर लगाएं"""
    try:
        img = PILImage.open(io.BytesIO(image_bytes)).convert("RGBA")
        if filter_type == "grayscale":
            gray = ImageOps.grayscale(img)
            result = PILImage.merge("RGBA", (gray, gray, gray, img.split()[3]))
        elif filter_type == "sepia":
            gray = ImageOps.grayscale(img)
            sepia = ImageOps.colorize(gray, "#704214", "#C0A080")
            result = sepia.convert("RGBA")
        elif filter_type == "invert":
            rgb = img.convert("RGB")
            inv = ImageOps.invert(rgb)
            result = inv.convert("RGBA")
        else:
            result = img
        buf = io.BytesIO()
        result.save(buf, format='PNG')
        return buf.getvalue()
    except Exception as e:
        raise Exception(f"फिल्टर फेल: {str(e)}")


def convert_to_svg(image_bytes):
    """इमेज को SVG वेक्टर में बदलें (कटिंग के लिए)"""
    try:
        img = PILImage.open(io.BytesIO(image_bytes)).convert("RGBA")
        max_size = 500
        if max(img.size) > max_size:
            ratio = max_size / max(img.size)
            img = img.resize((int(img.width * ratio), int(img.height * ratio)))

        width, height = img.size
        pixels = img.load()

        svg_parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">']
        svg_parts.append('<rect width="100%" height="100%" fill="white"/>')

        step = 4
        for y in range(0, height, step):
            for x in range(0, width, step):
                r, g, b, a = pixels[x, y]
                if a > 128:
                    svg_parts.append(f'<rect x="{x}" y="{y}" width="{step}" height="{step}" fill="rgb({r},{g},{b})"/>')

        svg_parts.append('</svg>')
        svg_content = ''.join(svg_parts)
        return svg_content.encode('utf-8')
    except Exception as e:
        raise Exception(f"SVG कन्वर्ज़न फेल: {str(e)}")


def save_to_gallery(image_bytes):
    """इमेज को Pictures फोल्डर में सेव करें"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ai_design_{timestamp}.png"

        paths = [
            "/storage/emulated/0/Pictures",
            "/sdcard/Pictures",
            os.path.expanduser("~/Pictures"),
            os.getcwd(),
        ]
        for folder in paths:
            try:
                if not os.path.exists(folder):
                    os.makedirs(folder, exist_ok=True)
                full_path = os.path.join(folder, filename)
                with open(full_path, "wb") as f:
                    f.write(image_bytes)
                return full_path
            except:
                continue
        raise Exception("कोई भी पाथ काम नहीं किया")
    except Exception as e:
        raise Exception(f"सेव फेल: {str(e)}")


# ============================================================
# ---------- KIVY UI ----------
# ============================================================

class DesignApp(App):

    def build(self):
        self.title = "AI Design Studio - Complete"
        Window.size = (400, 700)

        self.original_bytes = None
        self.current_bytes = None
        self.history = []
        self.scale_factor = 2

        root = BoxLayout(orientation='vertical', padding=5, spacing=5)

        tabs = TabbedPanel(do_default_tab=False)
        tabs.tab_width = 100
        tabs.tab_height = 40

        tab1 = TabbedPanelItem(text="डिज़ाइन")
        tab1.content = self.build_design_tab()
        tabs.add_widget(tab1)

        tab2 = TabbedPanelItem(text="एडिट")
        tab2.content = self.build_edit_tab()
        tabs.add_widget(tab2)

        tab3 = TabbedPanelItem(text="टेक्स्ट")
        tab3.content = self.build_text_tab()
        tabs.add_widget(tab3)

        tab4 = TabbedPanelItem(text="फिल्टर")
        tab4.content = self.build_filter_tab()
        tabs.add_widget(tab4)

        tabs.default_tab = tab1
        root.add_widget(tabs)

        self.image_display = Image(size_hint_y=0.35)
        root.add_widget(self.image_display)

        self.status_label = Label(text="तैयार", size_hint_y=0.05)
        root.add_widget(self.status_label)

        self.progress = ProgressBar(max=100, value=0, size_hint_y=0.04)
        root.add_widget(self.progress)

        return root

    def build_design_tab(self):
        scroll = ScrollView()
        layout = BoxLayout(orientation='vertical', padding=8, spacing=8, size_hint_y=None)
        layout.bind(minimum_height=layout.setter('height'))

        layout.add_widget(Label(text="AI डिज़ाइन बनाएं", size_hint_y=None, height=30, bold=True))

        self.prompt_input = TextInput(
            hint_text="जैसे: 'एक शेर का लोगो, वेक्टर स्टाइल, सफेद बैकग्राउंड'",
            multiline=True, size_hint_y=None, height=80
        )
        layout.add_widget(self.prompt_input)

        layout.add_widget(Label(text="डिज़ाइन साइज़:", size_hint_y=None, height=25))
        self.size_spinner = Spinner(
            text='1024 x 1024',
            values=('512 x 512', '768 x 768', '1024 x 1024', '1280 x 1280'),
            size_hint_y=None, height=40
        )
        layout.add_widget(self.size_spinner)

        layout.add_widget(Label(text="HD अपस्केल:", size_hint_y=None, height=25))
        self.upscale_spinner = Spinner(
            text='2x (तेज़)',
            values=('1x (कोई नहीं)', '2x (तेज़)', '3x (मध्यम)', '4x (धीमा)'),
            size_hint_y=None, height=40
        )
        layout.add_widget(self.upscale_spinner)

        self.generate_btn = Button(
            text="🚀 डिज़ाइन जनरेट करें",
            size_hint_y=None, height=55,
            background_color=(0.2, 0.6, 1, 1), bold=True
        )
        self.generate_btn.bind(on_press=self.on_generate)
        layout.add_widget(self.generate_btn)

        self.save_btn = Button(
            text="💾 फाइनल सेव करें (Gallery)",
            size_hint_y=None, height=50,
            background_color=(1, 0.5, 0.2, 1), bold=True
        )
        self.save_btn.bind(on_press=self.on_save)
        layout.add_widget(self.save_btn)

        self.svg_btn = Button(
            text="✂️ SVG (कटिंग फाइल) बनाएं",
            size_hint_y=None, height=50,
            background_color=(0.6, 0.3, 0.8, 1), bold=True
        )
        self.svg_btn.bind(on_press=self.on_svg)
        layout.add_widget(self.svg_btn)

        self.share_btn = Button(
            text="📤 WhatsApp पर शेयर करें",
            size_hint_y=None, height=45,
            background_color=(0.2, 0.8, 0.3, 1)
        )
        self.share_btn.bind(on_press=self.on_share)
        layout.add_widget(self.share_btn)

        return scroll_wrap(layout)

    def build_edit_tab(self):
        scroll = ScrollView()
        layout = BoxLayout(orientation='vertical', padding=8, spacing=8, size_hint_y=None)
        layout.bind(minimum_height=layout.setter('height'))

        layout.add_widget(Label(text="इमेज एडिट करें", size_hint_y=None, height=30, bold=True))

        layout.add_widget(Label(text="घुमाएं (Rotate):", size_hint_y=None, height=25))
        rot_row = GridLayout(cols=4, size_hint_y=None, height=45, spacing=5)
        for angle in [0, 90, 180, 270]:
            btn = Button(text=f"{angle}°")
            btn.bind(on_press=lambda x, a=angle: self.on_rotate(a))
            rot_row.add_widget(btn)
        layout.add_widget(rot_row)

        layout.add_widget(Label(text="उल्टा करें (Flip):", size_hint_y=None, height=25))
        flip_row = GridLayout(cols=2, size_hint_y=None, height=45, spacing=5)
        h_btn = Button(text="↔️ हॉरिज़ॉन्टल")
        h_btn.bind(on_press=lambda x: self.on_flip("horizontal"))
        v_btn = Button(text="↕️ वर्टिकल")
        v_btn.bind(on_press=lambda x: self.on_flip("vertical"))
        flip_row.add_widget(h_btn)
        flip_row.add_widget(v_btn)
        layout.add_widget(flip_row)

        layout.add_widget(Label(text="ब्राइटनेस:", size_hint_y=None, height=25))
        self.brightness_slider = Slider(min=0.3, max=2.0, value=1.0, size_hint_y=None, height=40)
        layout.add_widget(self.brightness_slider)
        b_btn = Button(text="ब्राइटनेस लगाएं", size_hint_y=None, height=40)
        b_btn.bind(on_press=lambda x: self.on_brightness(self.brightness_slider.value))
        layout.add_widget(b_btn)

        layout.add_widget(Label(text="कंट्रास्ट:", size_hint_y=None, height=25))
        self.contrast_slider = Slider(min=0.3, max=2.0, value=1.0, size_hint_y=None, height=40)
        layout.add_widget(self.contrast_slider)
        c_btn = Button(text="कंट्रास्ट लगाएं", size_hint_y=None, height=40)
        c_btn.bind(on_press=lambda x: self.on_contrast(self.contrast_slider.value))
        layout.add_widget(c_btn)

        undo_row = GridLayout(cols=2, size_hint_y=None, height=50, spacing=5)
        undo_btn = Button(text="↩️ अनडू", background_color=(0.8, 0.6, 0.2, 1))
        undo_btn.bind(on_press=self.on_undo)
        reset_btn = Button(text="🔄 रीसेट", background_color=(0.8, 0.2, 0.2, 1))
        reset_btn.bind(on_press=self.on_reset)
        undo_row.add_widget(undo_btn)
        undo_row.add_widget(reset_btn)
        layout.add_widget(undo_row)

        return scroll_wrap(layout)

    def build_text_tab(self):
        scroll = ScrollView()
        layout = BoxLayout(orientation='vertical', padding=8, spacing=8, size_hint_y=None)
        layout.bind(minimum_height=layout.setter('height'))

        layout.add_widget(Label(text="डिज़ाइन पर टेक्स्ट लिखें", size_hint_y=None, height=30, bold=True))

        layout.add_widget(Label(text="मुख्य टेक्स्ट (Main):", size_hint_y=None, height=25))
        self.main_text_input = TextInput(
            hint_text="जैसे: MY BRAND",
            multiline=False, size_hint_y=None, height=45
        )
        layout.add_widget(self.main_text_input)

        self.main_pos = Spinner(
            text='bottom', values=('top', 'center', 'bottom'),
            size_hint_y=None, height=40
        )
        layout.add_widget(self.main_pos)

        layout.add_widget(Label(text="सेकेंडरी टेक्स्ट (Tagline):", size_hint_y=None, height=25))
        self.sub_text_input = TextInput(
            hint_text="जैसे: Best Quality Since 1990",
            multiline=False, size_hint_y=None, height=45
        )
        layout.add_widget(self.sub_text_input)

        self.sub_pos = Spinner(
            text='top', values=('top', 'center', 'bottom'),
            size_hint_y=None, height=40
        )
        layout.add_widget(self.sub_pos)

        layout.add_widget(Label(text="फॉन्ट साइज़:", size_hint_y=None, height=25))
        self.font_slider = Slider(min=20, max=200, value=80, size_hint_y=None, height=40)
        layout.add_widget(self.font_slider)
        self.font_value_label = Label(text="80", size_hint_y=None, height=25)
        layout.add_widget(self.font_value_label)
        self.font_slider.bind(value=lambda x, v: setattr(self.font_value_label, 'text', str(int(v))))

        layout.add_widget(Label(text="टेक्स्ट कलर:", size_hint_y=None, height=25))
        self.text_color_spinner = Spinner(
            text='White',
            values=('White', 'Black', 'Red', 'Blue', 'Green', 'Yellow', 'Orange', 'Pink'),
            size_hint_y=None, height=40
        )
        layout.add_widget(self.text_color_spinner)

        layout.add_widget(Label(text="आउटलाइन कलर:", size_hint_y=None, height=25))
        self.stroke_color_spinner = Spinner(
            text='Black',
            values=('None', 'Black', 'White', 'Red', 'Blue'),
            size_hint_y=None, height=40
        )
        layout.add_widget(self.stroke_color_spinner)

        add_btn = Button(
            text="✅ टेक्स्ट जोड़ें",
            size_hint_y=None, height=55,
            background_color=(0.2, 0.8, 0.4, 1), bold=True
        )
        add_btn.bind(on_press=self.on_add_text)
        layout.add_widget(add_btn)

        both_btn = Button(
            text="⚡ दोनों टेक्स्ट एक साथ जोड़ें",
            size_hint_y=None, height=50,
            background_color=(0.4, 0.4, 0.9, 1), bold=True
        )
        both_btn.bind(on_press=self.on_add_both_text)
        layout.add_widget(both_btn)

        return scroll_wrap(layout)

    def build_filter_tab(self):
        layout = BoxLayout(orientation='vertical', padding=8, spacing=8)

        layout.add_widget(Label(text="कलर फिल्टर लगाएं", size_hint_y=None, height=30, bold=True))

        for name, key in [("कोई नहीं (Original)", "none"),
                          ("ब्लैक एंड व्हाइट", "grayscale"),
                          ("सेपिया (पुराना लुक)", "sepia"),
                          ("इनवर्ट (उल्टा रंग)", "invert")]:
            btn = Button(text=name, size_hint_y=None, height=50)
            btn.bind(on_press=lambda x, k=key: self.on_filter(k))
            layout.add_widget(btn)

        return layout

    def push_history(self):
        if self.current_bytes:
            self.history.append(self.current_bytes)
            if len(self.history) > 20:
                self.history.pop(0)

    def set_progress(self, value):
        Clock.schedule_once(lambda dt: setattr(self.progress, 'value', value))

    def update_status(self, text):
        Clock.schedule_once(lambda dt: setattr(self.status_label, 'text', text))

    def show_image(self, image_bytes):
        try:
            with open("temp_design.png", "wb") as f:
                f.write(image_bytes)
            Clock.schedule_once(lambda dt: self._refresh_image())
        except Exception as e:
            self.show_popup(f"इमेज दिखाने में फेल: {str(e)}")

    def _refresh_image(self):
        self.image_display.source = ""
        self.image_display.source = "temp_design.png"
        self.image_display.reload()

    def show_popup(self, message):
        Clock.schedule_once(lambda dt: Popup(
            title="सूचना",
            content=Label(text=message),
            size_hint=(0.9, 0.4)
        ).open())

    def toggle_buttons(self, enabled):
        Clock.schedule_once(lambda dt: setattr(self.generate_btn, 'disabled', not enabled))

    def on_generate(self, instance):
        prompt = self.prompt_input.text.strip()
        if not prompt:
            self.show_popup("कृपया डिज़ाइन का विवरण लिखें")
            return

        size_str = self.size_spinner.text
        w, h = [int(x.strip()) for x in size_str.split("x")]

        up_text = self.upscale_spinner.text
        if up_text.startswith("1x"):
            self.scale_factor = 1
        elif up_text.startswith("2x"):
            self.scale_factor = 2
        elif up_text.startswith("3x"):
            self.scale_factor = 3
        else:
            self.scale_factor = 4

        self.update_status("AI डिज़ाइन बना रहा है...")
        self.set_progress(10)
        self.toggle_buttons(False)
        threading.Thread(target=self._generate_thread, args=(prompt, w, h)).start()

    def _generate_thread(self, prompt, w, h):
        try:
            self.update_status("डिज़ाइन जनरेट हो रहा है...")
            self.set_progress(20)
            design_bytes = generate_design(prompt, w, h)

            self.update_status("बैकग्राउंड हटा रहा है...")
            self.set_progress(50)
            cutout = remove_background(design_bytes)

            self.update_status("HD बना रहा है...")
            self.set_progress(75)
            final = upscale_image(cutout, self.scale_factor)

            self.original_bytes = final
            self.current_bytes = final
            self.history = [final]
            self.set_progress(100)
            self.show_image(final)
            self.update_status("डिज़ाइन तैयार! अब टेक्स्ट जोड़ें।")
        except Exception as e:
            self.show_popup(f"त्रुटि: {str(e)}")
            self.update_status("फेल")
            self.set_progress(0)
        finally:
            self.toggle_buttons(True)

    def _parse_color(self, name):
        colors = {
            "White": (255, 255, 255, 255),
            "Black": (0, 0, 0, 255),
            "Red": (255, 0, 0, 255),
            "Blue": (0, 0, 255, 255),
            "Green": (0, 200, 0, 255),
            "Yellow": (255, 255, 0, 255),
            "Orange": (255, 140, 0, 255),
            "Pink": (255, 105, 180, 255),
            "None": (0, 0, 0, 0),
        }
        return colors.get(name, (255, 255, 255, 255))

    def on_add_text(self, instance):
        if not self.current_bytes:
            self.show_popup("पहले डिज़ाइन जनरेट करें")
            return
        text = self.main_text_input.text.strip()
        if not text:
            self.show_popup("कृपया टेक्स्ट लिखें")
            return

        self.push_history()
        pos = self.main_pos.text
        size = int(self.font_slider.value)
        tcolor = self._parse_color(self.text_color_spinner.text)
        scolor = self._parse_color(self.stroke_color_spinner.text)
        sw = 0 if self.stroke_color_spinner.text == "None" else 3

        self.update_status("टेक्स्ट जोड़ रहा है...")
        threading.Thread(target=self._text_thread,
                         args=(text, pos, size, tcolor, scolor, sw)).start()

    def _text_thread(self, text, pos, size, tcolor, scolor, sw):
        try:
            new_bytes = add_text_to_image(self.current_bytes, text, pos, size, tcolor, scolor, sw)
            self.current_bytes = new_bytes
            self.show_image(new_bytes)
            self.update_status("टेक्स्ट जुड़ गया!")
        except Exception as e:
            self.show_popup(f"त्रुटि: {str(e)}")

    def on_add_both_text(self, instance):
        if not self.current_bytes:
            self.show_popup("पहले डिज़ाइन जनरेट करें")
            return
        main = self.main_text_input.text.strip()
        sub = self.sub_text_input.text.strip()
        if not main and not sub:
            self.show_popup("कम से कम एक टेक्स्ट लिखें")
            return

        self.push_history()
        size = int(self.font_slider.value)
        tcolor = self._parse_color(self.text_color_spinner.text)
        scolor = self._parse_color(self.stroke_color_spinner.text)
        sw = 0 if self.stroke_color_spinner.text == "None" else 3

        self.update_status("दोनों टेक्स्ट जोड़ रहा है...")
        threading.Thread(target=self._both_text_thread,
                         args=(main, sub, size, tcolor, scolor, sw)).start()

    def _both_text_thread(self, main, sub, size, tcolor, scolor, sw):
        try:
            img_bytes = self.current_bytes
            if main:
                img_bytes = add_text_to_image(img_bytes, main, self.main_pos.text,
                                              size, tcolor, scolor, sw)
            if sub:
                img_bytes = add_text_to_image(img_bytes, sub, self.sub_pos.text,
                                              int(size * 0.6), tcolor, scolor, sw)
            self.current_bytes = img_bytes
            self.show_image(img_bytes)
            self.update_status("दोनों टेक्स्ट जुड़ गए!")
        except Exception as e:
            self.show_popup(f"त्रुटि: {str(e)}")

    def on_rotate(self, angle):
        if not self.current_bytes:
            self.show_popup("पहले डिज़ाइन बनाएं")
            return
        self.push_history()
        try:
            self.current_bytes = rotate_image(self.current_bytes, angle)
            self.show_image(self.current_bytes)
            self.update_status(f"{angle}° घुमा दिया")
        except Exception as e:
            self.show_popup(str(e))

    def on_flip(self, direction):
        if not self.current_bytes:
            self.show_popup("पहले डिज़ाइन बनाएं")
            return
        self.push_history()
        try:
            self.current_bytes = flip_image(self.current_bytes, direction)
            self.show_image(self.current_bytes)
            self.update_status("उल्टा कर दिया")
        except Exception as e:
            self.show_popup(str(e))

    def on_brightness(self, factor):
        if not self.current_bytes:
            self.show_popup("पहले डिज़ाइन बनाएं")
            return
        self.push_history()
        try:
            self.current_bytes = adjust_brightness(self.current_bytes, factor)
            self.show_image(self.current_bytes)
            self.update_status("ब्राइटनेस बदल दी")
        except Exception as e:
            self.show_popup(str(e))

    def on_contrast(self, factor):
        if not self.current_bytes:
            self.show_popup("पहले डिज़ाइन बनाएं")
            return
        self.push_history()
        try:
            self.current_bytes = adjust_contrast(self.current_bytes, factor)
            self.show_image(self.current_bytes)
            self.update_status("कंट्रास्ट बदल दिया")
        except Exception as e:
            self.show_popup(str(e))

    def on_filter(self, filter_type):
        if not self.current_bytes:
            self.show_popup("पहले डिज़ाइन बनाएं")
            return
        self.push_history()
        try:
            self.current_bytes = apply_filter(self.current_bytes, filter_type)
            self.show_image(self.current_bytes)
            self.update_status(f"फिल्टर लगा दिया: {filter_type}")
        except Exception as e:
            self.show_popup(str(e))

    def on_undo(self, instance):
        if len(self.history) > 1:
            self.history.pop()
            self.current_bytes = self.history[-1]
            self.show_image(self.current_bytes)
            self.update_status("अनडू हो गया")
        else:
            self.show_popup("और पीछे नहीं जा सकते")

    def on_reset(self, instance):
        if self.original_bytes:
            self.current_bytes = self.original_bytes
            self.history = [self.original_bytes]
            self.show_image(self.current_bytes)
            self.update_status("रीसेट हो गया")

    def on_save(self, instance):
        if not self.current_bytes:
            self.show_popup("पहले डिज़ाइन बनाएं")
            return
        try:
            path = save_to_gallery(self.current_bytes)
            self.show_popup(f"✅ सेव हो गया:\n{path}")
            self.update_status("गैलरी में सेव हो गया")
        except Exception as e:
            self.show_popup(str(e))

    def on_svg(self, instance):
        if not self.current_bytes:
            self.show_popup("पहले डिज़ाइन बनाएं")
            return
        self.update_status("SVG बना रहा है...")
        threading.Thread(target=self._svg_thread).start()

    def _svg_thread(self):
        try:
            svg_bytes = convert_to_svg(self.current_bytes)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"design_{timestamp}.svg"
            saved = False
            for folder in ["/storage/emulated/0/Pictures", "/sdcard/Pictures", os.getcwd()]:
                try:
                    os.makedirs(folder, exist_ok=True)
                    full = os.path.join(folder, filename)
                    with open(full, "wb") as f:
                        f.write(svg_bytes)
                    self.show_popup(f"✅ SVG सेव:\n{full}")
                    saved = True
                    break
                except:
                    continue
            if not saved:
                self.show_popup("SVG सेव नहीं हो सका")
            self.update_status("SVG तैयार!")
        except Exception as e:
            self.show_popup(str(e))

    def on_share(self, instance):
        if not self.current_bytes:
            self.show_popup("पहले डिज़ाइन बनाएं")
            return
        try:
            path = save_to_gallery(self.current_bytes)
            try:
                from jnius import autoclass
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                Intent = autoclass('android.content.Intent')
                Uri = autoclass('android.net.Uri')
                File = autoclass('java.io.File')

                intent = Intent(Intent.ACTION_SEND)
                intent.setType("image/png")
                uri = Uri.fromFile(File(path))
                intent.putExtra(Intent.EXTRA_STREAM, uri)
                PythonActivity.mActivity.startActivity(Intent.createChooser(intent, "Share via"))
            except:
                self.show_popup(f"शेयर के लिए सेव हो गया:\n{path}")
            self.update_status("शेयर तैयार")
        except Exception as e:
            self.show_popup(str(e))


def scroll_wrap(layout):
    scroll = ScrollView()
    scroll.add_widget(layout)
    return scroll


if __name__ == "__main__":
    DesignApp().run()
