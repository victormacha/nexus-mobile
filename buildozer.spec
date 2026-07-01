[app]
title = Nexus
package.name = nexus
package.domain = org.nexusapp

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ico

version = 1.0

# ── Bibliotecas ────────────────────────────────────────────────────
requirements = python3,kivy==2.3.0,kivymd==1.2.0,supabase,plyer,certifi,httpx,websockets,pydantic,pyjnius

orientation = portrait
fullscreen = 0

# Descomente após colocar icon.png e presplash.png na pasta raiz:
# icon.filename = %(source.dir)s/icon.png
# presplash.filename = %(source.dir)s/presplash.png

[buildozer]
log_level = 2
warn_on_root = 1

[android]
android.permissions = INTERNET, ACCESS_NETWORK_STATE, POST_NOTIFICATIONS
android.api = 33
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
