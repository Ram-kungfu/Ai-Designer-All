[app]

title = AI Design Studio
package.name = aidesignstudio
package.domain = com.aidesign.studio
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.1

requirements = python3,kivy==2.3.0,pillow,requests,urllib3,chardet,idna,certifi

orientation = portrait
fullscreen = 0
android.permissions = INTERNET, ACCESS_NETWORK_STATE

android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a

# यह लाइन सबसे ज़रूरी है, यह ऑटोमैटिक लाइसेंस एक्सेप्ट करेगी
android.accept_sdk_license = True

p4a.branch = master

[buildozer]
log_level = 2
warn_on_root = 1
