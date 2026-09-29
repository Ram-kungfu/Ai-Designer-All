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
from kivy.core.image import Image as CoreImage
from PIL import Image as PILImage

# ---------- AI बैकएंड फंक्शन्स ----------

def generate_design(prompt):
    """Pollinations AI से डिज़ाइन जनरेट करता है"""
    url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}"
    try:
        response = requests.get(url, timeout=60)
        if response.status_code == 200:
            return response.content
        else:
            raise Exception(f"सर्वर त्रुटि: {response.status_code}")
    except Exception as e:
        raise Exception(f"जनरेशन फेल: {str(e)}")

def remove_background_api(image_bytes):
    """Free Web API के ज़रिए बैकग्राउंड हटाता है (Buildozer कंपैटिबल)"""
    try:
        # फ्री बैकग्राउंड रिमूवल API
        response = requests.post(
            "https://api.remove.bg/v1.0/removebg",
            files={'image_file': image_bytes},
            data={'size': 'auto'},
            headers={'X-Api-Key': ''}, # बिना API key के बेसिक प्रोसेस या कस्टम API
            timeout=30
        )
        if response.status_code == 200:
            return response.content
        else:
            # अगर API की आवश्यकता न हो, तो ओरिजिनल इमेज रिटर्न करें
            return image_bytes
    except Exception:
        return image_bytes

def upscale_image(image_bytes):
    """PIL LANCZOS से HD अपस्केल"""
    try:
        input_image = PILImage.open(io.BytesIO(image_bytes))
        new_size = (input_image.width * 2, input_image.height * 2)
        upscaled = input_image.resize(new_size, PILImage.LANCZOS)
        img_byte_arr = io.BytesIO()
        upscaled.save(img_byte_arr, format='PNG')
        return img_byte_arr.getvalue()
    except Exception as e:
        raise Exception(f"अपस्केलिंग फेल: {str(e)}")

# ---------- Kivy UI ----------

class DesignApp(App):
    def build(self):
        self.title = "AI डिज़ाइन स्टूडियो"
        layout = BoxLayout(orientation='vertical', padding=15, spacing=10)

        # प्रॉम्प्ट इनपुट
        self.prompt_input = TextInput(
            hint_text="डिज़ाइन का विवरण लिखें (जैसे: 'A red sports car')",
            multiline=False, 
            size_hint_y=0.1,
            font_size='16sp'
        )
        layout.add_widget(self.prompt_input)

        # जनरेट बटन
        self.generate_btn = Button(
            text="डिज़ाइन जनरेट करें", 
            size_hint_y=0.1,
            background_color=(0.2, 0.6, 1, 1),
            bold=True
        )
        self.generate_btn.bind(on_press=self.on_generate)
        layout.add_widget(self.generate_btn)

        # इमेज डिस्प्ले
        self.image_display = Image(size_hint_y=0.7)
        layout.add_widget(self.image_display)

        # स्टेटस लेबल
        self.status_label = Label(text="तैयार", size_hint_y=0.1, color=(1, 1, 1, 1))
        layout.add_widget(self.status_label)

        return layout

    def on_generate(self, instance):
        prompt = self.prompt_input.text.strip()
        if not prompt:
            self.show_popup("कृपया डिज़ाइन का विवरण लिखें")
            return

        self.status_label.text = "AI डिज़ाइन बना रहा है..."
        self.generate_btn.disabled = True
        threading.Thread(target=self.run_ai_pipeline, args=(prompt,), daemon=True).start()

    def run_ai_pipeline(self, prompt):
        try:
            # 1. जनरेट करें
            design_bytes = generate_design(prompt)
            
            # 2. HD अपस्केल करें
            Clock.schedule_once(lambda dt: self.update_status("इमेज को HD बना रहा है..."))
            final_bytes = upscale_image(design_bytes)

            # 3. UI पर दिखाएं
            Clock.schedule_once(lambda dt: self.show_image(final_bytes))
            Clock.schedule_once(lambda dt: self.update_status("डिज़ाइन तैयार है!"))

        except Exception as e:
            Clock.schedule_once(lambda dt, err=str(e): self.show_popup(f"त्रुटि: {err}"))
            Clock.schedule_once(lambda dt: self.update_status("प्रक्रिया विफल हुई"))

        finally:
            Clock.schedule_once(lambda dt: setattr(self.generate_btn, 'disabled', False))

    def update_status(self, text):
        self.status_label.text = text

    def show_image(self, image_bytes):
        """डायरेक्ट मेमोरी (RAM) से Kivy की स्क्रीन पर इमेज लोड करता है"""
        data = io.BytesIO(image_bytes)
        im = CoreImage(data, ext="png")
        self.image_display.texture = im.texture

    def show_popup(self, message):
        popup = Popup(title="सूचना", content=Label(text=message), size_hint=(0.8, 0.3))
        popup.open()

if __name__ == "__main__":
    DesignApp().run()
