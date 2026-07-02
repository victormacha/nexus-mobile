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
# pra COMPILAR o app pro Android (resolve erro do Cython/"cgi").
#
# kivy / kivymd SEM "==versão": travar a versão fazia o buildozer procurar
# um pacote pré-compilado (wheel) pro Android que não existe pra 2.2.1,
# e ele falhava em vez de compilar do zero. Sem a trava, ele compila
# a versão padrão do zero, que é o caminho mais confiável.
requirements = python3==3.11.9,hostpython3==3.11.9,kivy,kivymd,requests,plyer,certifi,pyjnius

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
