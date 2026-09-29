[app]
title = AI Design Studio
package.name = aidesignstudio
package.domain = com.yourcompany
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas
version = 1.0

requirements = python3,kivy,pillow,requests,urllib3,chardet,idna,certifi,pyjnius

orientation = portrait
fullscreen = 0
android.permissions = INTERNET, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE
android.api = 31
android.minapi = 24
android.ndk_api = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
