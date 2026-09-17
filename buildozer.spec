[app]
title = SelfLearningTrader Ultimate
package.name = selflearningtrader
package.domain = org.selflearningtrader
source.dir = app
source.include_exts = py,json,csv,md
version = 1.0.0
requirements = python3,kivy==2.3.1,numpy,certifi
orientation = portrait
fullscreen = 0
android.api = 34
android.minapi = 24
android.ndk = 28c
android.permissions = INTERNET
android.archs = arm64-v8a
android.accept_sdk_license = True

p4a.fork = kivy
p4a.branch = develop
p4a.local_recipes = p4a-recipes
# Use the current Kivy/p4a recipe stack with the supported Cython version

[buildozer]
log_level = 2
warn_on_root = 1
