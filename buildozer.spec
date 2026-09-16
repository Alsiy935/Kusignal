[app]
title = SelfLearningTrader Ultimate
package.name = selflearningtrader
package.domain = org.selflearningtrader
source.dir = app
source.include_exts = py,json,csv,md
version = 1.0.0
requirements = python3,kivy==2.3.0,numpy==1.26.5,pandas==2.2.3,requests==2.32.3,scikit-learn==1.5.2,joblib==1.4.2
orientation = portrait
fullscreen = 0

android.api = 35
android.minapi = 24
android.ndk = 27c
android.permissions = INTERNET
android.archs = arm64-v8a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
