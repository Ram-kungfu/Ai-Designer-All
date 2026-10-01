import os
import io
import threading
import requests
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.clock import Clock
from PIL import Image as PILImage, ImageDraw

FONT = "NotoSansDevanagari-Regular.ttf"
if not os.path.exists(FONT):
    FONT = "Roboto"


def generate_design(prompt):
    full_prompt = prompt + ", isolated on plain white background, sticker design"
    url = ("https://image.pollinations.ai/prompt/"
           + requests.utils.quote(full_prompt)
           + "?width=768&height=768&nologo=true")
    try:
        response = requests.get(
            url, timeout=90, headers={"User-Agent": "Mozilla/5.0"})
        if response.status_code == 200:
            return response.content
        raise Exception(f"Error: {response.status_code}")
    except Exception as e:
        raise Exception(f"डिज़ाइन जनरेशन फेल: {str(e)}")


def remove_background(image_bytes):
    """सफ़ेद बैकग्राउंड को कोनों से हटाता है (हल्का, बिना rembg)"""
    try:
        img = PILImage.open(io.BytesIO(image_bytes)).convert("RGBA")
        w, h = img.size
        for pt in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
            ImageDraw.floodfill(img, pt, (255, 255, 255, 0), thresh=40)
        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()
    except Exception as e:
        raise Exception(f"बैकग्राउंड रिमूवल फेल: {str(e)}")


def upscale_image(image_bytes):
    try:
        img = PILImage.open(io.BytesIO(image_bytes))
        new_size = (img.width * 2, img.height * 2)
        up = img.resize(new_size, PILImage.LANCZOS)
        out = io.BytesIO()
        up.save(out, format="PNG")
        return out.getvalue()
    except Exception as e:
        raise Exception(f"अपस्केलिंग फेल: {str(e)}")


class DesignApp(App):
    def build(self):
        self.title = "AI डिज़ाइन स्टूडियो"
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)

        self.prompt_input = TextInput(
            hint_text="डिज़ाइन का विवरण लिखें (जैसे: 'एक शेर का लोगो')",
            multiline=False, size_hint_y=0.1, font_name=FONT)
        layout.add_widget(self.prompt_input)

        self.generate_btn = Button(
            text="डिज़ाइन जनरेट करें", size_hint_y=0.1,
            background_color=(0.2, 0.6, 1, 1), font_name=FONT)
        self.generate_btn.bind(on_press=self.on_generate)
        layout.add_widget(self.generate_btn)

        self.image_display = Image(size_hint_y=0.6)
        layout.add_widget(self.image_display)

        self.status_label = Label(text="तैयार", size_hint_y=0.1, font_name=FONT)
        layout.add_widget(self.status_label)
        return layout

    def on_generate(self, instance):
        prompt = self.prompt_input.text.strip()
        if not prompt:
            self.show_popup("कृपया डिज़ाइन का विवरण लिखें")
            return
        self.status_label.text = "AI डिज़ाइन बना रहा है..."
        self.generate_btn.disabled = True
        threading.Thread(target=self.run_ai_pipeline, args=(prompt,),
                         daemon=True).start()

    def run_ai_pipeline(self, prompt):
        try:
            design_bytes = generate_design(prompt)
            Clock.schedule_once(lambda dt: self.update_status("बैकग्राउंड हटा रहा है..."))
            cutout_bytes = remove_background(design_bytes)
            Clock.schedule_once(lambda dt: self.update_status("HD बना रहा है..."))
            final_bytes = upscale_image(cutout_bytes)
            Clock.schedule_once(lambda dt: self.show_image(final_bytes))
            Clock.schedule_once(lambda dt: self.update_status("तैयार!"))
        except Exception as e:
            msg = f"त्रुटि: {str(e)}"
            Clock.schedule_once(lambda dt: self.show_popup(msg))
            Clock.schedule_once(lambda dt: self.update_status("फेल"))
        finally:
            Clock.schedule_once(
                lambda dt: setattr(self.generate_btn, 'disabled', False))

    def update_status(self, text):
        self.status_label.text = text

    def show_image(self, image_bytes):
        path = os.path.join(self.user_data_dir, "temp_design.png")
        with open(path, "wb") as f:
            f.write(image_bytes)
        self.image_display.source = path
        self.image_display.reload()

    def show_popup(self, message):
        Popup(title="सूचना", title_font=FONT,
              content=Label(text=message, font_name=FONT),
              size_hint=(0.8, 0.3)).open()


if __name__ == "__main__":
    DesignApp().run()
