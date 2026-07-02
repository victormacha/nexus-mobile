[app]
title = Nexus
package.name = nexus
package.domain = org.nexusapp
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0

# ── MUDANÇA PRINCIPAL ──────────────────────────────────────────────
# Removidos: supabase, httpx, websockets, pydantic
# (essas libs não compilam pro Android — pydantic-core é Rust e trava o p4a)
# Adicionado: requests (usado pelo supabase_shim.py, compila sem problema)
requirements = python3,kivy==2.2.1,kivymd==1.1.1,requests,plyer,certifi,pyjnius

orientation = portrait
fullscreen = 0

[buildozer]
log_level = 2
warn_on_root = 1

[android]
android.permissions = INTERNET, ACCESS_NETWORK_STATE, POST_NOTIFICATIONS
android.api = 33
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True
p4a.branch = v2024.01.21
