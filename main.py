import os
import io
import threading
import requests
from datetime import datetime
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.slider import Slider
from kivy.uix.progressbar import ProgressBar
from kivy.clock import Clock
from PIL import Image as PILImage, ImageDraw, ImageFont, ImageEnhance, ImageOps

# ============================================================
# ---------- AI बैकएंड फंक्शन्स ----------
# ============================================================

def generate_design(prompt, width=1024, height=1024):
    try:
        url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}?width={width}&height={height}&nologo=true"
        response = requests.get(url, timeout=90)
        if response.status_code == 200 and len(response.content) > 1000:
            return response.content
        raise Exception("Server Error")
    except Exception as e:
        raise Exception(f"Generation Fail: {str(e)}")

def get_font(size):
    font_paths = ["/system/fonts/Roboto-Bold.ttf", "Roboto-Bold.ttf"]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except:
            continue
    return ImageFont.load_default()

def add_text_to_image(image_bytes, text, position="bottom", font_size=60, text_color=(255, 255, 255, 255), stroke_color=(0, 0, 0, 255)):
    try:
        img = PILImage.open(io.BytesIO(image_bytes)).convert("RGBA")
        draw = ImageDraw.Draw(img)
        font = get_font(font_size)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = max(10, (img.width - tw) // 2)
        y = 30 if position == "top" else ((img.height - th) // 2 if position == "center" else img.height - th - 50)
        
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), text, font=font, fill=stroke_color)
        draw.text((x, y), text, font=font, fill=text_color)
        
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()
    except Exception as e:
        raise Exception(f"Text Fail: {str(e)}")

def save_to_gallery(image_bytes):
    try:
        filename = f"ai_design_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        for folder in ["/storage/emulated/0/Pictures", os.getcwd()]:
            try:
                if not os.path.exists(folder): os.makedirs(folder, exist_ok=True)
                path = os.path.join(folder, filename)
                with open(path, "wb") as f: f.write(image_bytes)
                return path
            except: continue
        raise Exception("Path Error")
    except Exception as e:
        raise Exception(f"Save Fail: {str(e)}")

# ============================================================
# ---------- KIVY UI ----------
# ============================================================

class DesignApp(App):
    def build(self):
        self.title = "AI Design Studio"
        self.original_bytes = None
        self.current_bytes = None

        root = BoxLayout(orientation='vertical', padding=10, spacing=10)

        self.prompt_input = TextInput(hint_text="Design description (e.g., Lion Logo, Vector)", multiline=False, size_hint_y=0.1)
        root.add_widget(self.prompt_input)

        self.generate_btn = Button(text="Generate Design", size_hint_y=0.1, background_color=(0.2, 0.6, 1, 1))
        self.generate_btn.bind(on_press=self.on_generate)
        root.add_widget(self.generate_btn)

        self.text_input = TextInput(hint_text="Text to add (e.g., MY BRAND)", multiline=False, size_hint_y=0.1)
        root.add_widget(self.text_input)

        self.text_btn = Button(text="Add Text", size_hint_y=0.1, background_color=(0.2, 0.8, 0.4, 1))
        self.text_btn.bind(on_press=self.on_add_text)
        root.add_widget(self.text_btn)

        self.save_btn = Button(text="Save to Gallery", size_hint_y=0.1, background_color=(1, 0.5, 0.2, 1))
        self.save_btn.bind(on_press=self.on_save)
        root.add_widget(self.save_btn)

        self.image_display = Image(size_hint_y=0.4)
        root.add_widget(self.image_display)

        self.status = Label(text="Ready", size_hint_y=0.1)
        root.add_widget(self.status)

        return root

    def show_popup(self, msg):
        Clock.schedule_once(lambda dt: Popup(title="Info", content=Label(text=msg), size_hint=(0.9, 0.3)).open())

    def update_status(self, text):
        Clock.schedule_once(lambda dt: setattr(self.status, 'text', text))

    def show_image(self, img_bytes):
        try:
            with open("temp.png", "wb") as f: f.write(img_bytes)
            Clock.schedule_once(lambda dt: self._refresh())
        except: pass

    def _refresh(self):
        self.image_display.source = ""
        self.image_display.source = "temp.png"
        self.image_display.reload()

    def on_generate(self, instance):
        prompt = self.prompt_input.text.strip()
        if not prompt: return self.show_popup("Enter description")
        self.update_status("Generating...")
        threading.Thread(target=self._gen_thread, args=(prompt,)).start()

    def _gen_thread(self, prompt):
        try:
            img = generate_design(prompt)
            self.original_bytes = img
            self.current_bytes = img
            self.show_image(img)
            self.update_status("Done!")
        except Exception as e:
            self.show_popup(str(e))
            self.update_status("Failed")

    def on_add_text(self, instance):
        if not self.current_bytes: return self.show_popup("Generate design first")
        text = self.text_input.text.strip()
        if not text: return self.show_popup("Enter text")
        self.update_status("Adding text...")
        threading.Thread(target=self._text_thread, args=(text,)).start()

    def _text_thread(self, text):
        try:
            img = add_text_to_image(self.current_bytes, text)
            self.current_bytes = img
            self.show_image(img)
            self.update_status("Text Added!")
        except Exception as e:
            self.show_popup(str(e))

    def on_save(self, instance):
        if not self.current_bytes: return self.show_popup("Nothing to save")
        try:
            path = save_to_gallery(self.current_bytes)
            self.show_popup(f"Saved: {path}")
        except Exception as e:
            self.show_popup(str(e))

if __name__ == "__main__":
    DesignApp().run()
