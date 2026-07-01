[app]
title = Nexus
package.name = nexus
package.domain = org.nexusapp

source.dir = .
source.include_exts = py,png,jpg,kv,atlas

version = 1.0

requirements = python3,kivy==2.2.1,kivymd==1.1.1,supabase,plyer,certifi,httpx,websockets,pydantic,pyjnius

orientation = portrait
fullscreen = 0

[buildozer]
log_level = 2
warn_on_root = 1

[android]
android.permissions = INTERNET, ACCESS_NETWORK_STATE, POST_NOTIFICATIONS
android.api = 33
android.minapi = 24
android.ndk = 28c
android.archs = arm64-v8a
android.accept_sdk_license = True
android.ndk_path = /usr/local/lib/android/sdk/ndk/28.3.13750724
android.sdk_path = /usr/local/lib/android/sdk
