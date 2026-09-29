[app]
title = AI Design Studio
package.name = aidesignstudio
package.domain = com.yourcompany
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,ttf,otf
source.exclude_dirs = tests, bin, .git, .github
version = 1.0

requirements = python3,kivy==2.3.0,pillow,requests,rembg,urllib3,chardet,idna,certifi,fonttools,numpy,scipy,onnxruntime,pyjnius

orientation = portrait
fullscreen = 0
window_softinput_mode = below_target

android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,ACCESS_NETWORK_STATE
android.api = 31
android.minapi = 21
android.ndk_api = 21
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True
android.accept_sdk_license = True

android.logcat_filters = *:S python:D

[buildozer]
log_level = 2
warn_on_root = 1
