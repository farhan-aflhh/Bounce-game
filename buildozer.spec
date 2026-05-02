[app]
title = Bounce
package.name = bounce
package.domain = org.example

source.dir = .
source.include_exts = py,png,jpg,kv,atlas

version = 1.0

requirements = python3,kivy

orientation = landscape
fullscreen = 1

# Android specific
android.api = 33
android.minapi = 21
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True

# No special permissions needed
android.permissions =

[buildozer]
log_level = 2
warn_on_root = 1
