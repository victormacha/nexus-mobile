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
#
# python3==3.11.9 / hostpython3==3.11.9: trava a versão do Python usada
# pra COMPILAR o app pro Android. Sem isso, o buildozer pega a versão
# mais nova do Python (3.14), que não é compatível com o Cython antigo
# que o Kivy 2.2.1 precisa (dá erro "No module named 'cgi'").
requirements = python3==3.11.9,hostpython3==3.11.9,kivy==2.2.1,kivymd==1.1.1,requests,plyer,certifi,pyjnius

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
