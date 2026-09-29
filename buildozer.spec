[app]

title = AI Design Studio
package.name = aidesignstudio
package.domain = com.aidesign.studio
source.dir = .
source.include_exts = py,png,jpg,kv,atlas

version = 0.1

# requirements से rembg को हटा दिया गया है ताकि Buildozer का बिल्ड फेल न हो
requirements = python3,kivy==2.3.0,pillow,requests,urllib3,chardet,idna,certifi

orientation = portrait
fullscreen = 0

# Android Permissions
android.permissions = INTERNET, ACCESS_NETWORK_STATE

# Target API Configurations
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a

# Python for Android settings
p4a.branch = master

[buildozer]
log_level = 2
warn_on_root = 1
