[app]
title = SelfLearningTrader Ultimate
package.name = selflearningtrader
package.domain = org.selflearningtrader
source.dir = app
source.include_exts = py,json,csv,md
version = 1.0.0
requirements = python3,kivy==2.3.1,numpy,requests==2.32.3
orientation = portrait
fullscreen = 0
android.api = 35
android.minapi = 24
android.ndk = 28c
android.permissions = INTERNET
android.archs = arm64-v8a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
