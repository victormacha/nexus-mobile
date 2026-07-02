"""
supabase_shim.py
─────────────────────────────────────────────────────────────────────
Substituto leve do cliente oficial `supabase-py`, feito só com `requests`.

POR QUE ISSO EXISTE:
O pacote oficial `supabase` puxa httpx + websockets + gotrue + postgrest-py
+ realtime-py + pydantic (que usa pydantic-core, escrito em Rust). O
python-for-android (motor do buildozer) não consegue compilar essas libs
pra Android — é a causa nº1 de build quebrado ao usar Supabase com Kivy.

Este arquivo imita a MESMA sintaxe do cliente oficial:
    sb.table("tarefas").select("*").eq("id", 1).execute().data
...só que por baixo dos panos usa `requests` puro, chamando a API REST
(PostgREST) do Supabase diretamente. `requests` TEM receita pronta no
python-for-android, então compila sem drama.

COMO USAR:
No seu main.py, troque:

    from supabase import create_client, Client
    SUPABASE_URL = "..."
    SUPABASE_KEY = "..."
    sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

por:

    from supabase_shim import sb

(as credenciais já estão configuradas aqui embaixo)
─────────────────────────────────────────────────────────────────────
"""

import requests

# ── Credenciais do Supabase ────────────────────────────────────────
# Esta é a chave "anon"/"publishable" (pública), segura para ir dentro
# do app. NUNCA coloque aqui a chave "service_role"/secret.
SUPABASE_URL = "https://xieghxptvcwkcugunxib.supabase.co"
SUPABASE_KEY = "sb_publishable_c4RjoRWAJXPajevlGY5Awg_5NWU1f7n"

_TIMEOUT = 15  # segundos


class _Response:
    """Imita o objeto de resposta do supabase-py (.data e .count)."""
    __slots__ = ("data", "count")

    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Query:
    """Query builder encadeável, imitando a API do supabase-py."""

    def __init__(self, base_url, key, table):
        self._url = f"{base_url}/rest/v1/{table}"
        self._headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        self._params = {}
        self._method = "GET"
        self._body = None

    # ── leitura ──────────────────────────────────────────────────
    def select(self, columns="*", count=None):
        self._params["select"] = columns
        self._method = "GET"
        if count:
            self._headers["Prefer"] = f"count={count}"
        return self

    def eq(self, column, value):
        self._params[column] = f"eq.{value}"
        return self

    def in_(self, column, values):
        valores = ",".join(str(v) for v in values)
        self._params[column] = f"in.({valores})"
        return self

    def lte(self, column, value):
        self._params[column] = f"lte.{value}"
        return self

    def gte(self, column, value):
        self._params[column] = f"gte.{value}"
        return self

    def order(self, column, desc=False):
        self._params["order"] = f"{column}.{'desc' if desc else 'asc'}"
        return self

    def limit(self, n):
        self._params["limit"] = str(n)
        return self

    # ── escrita ──────────────────────────────────────────────────
    def insert(self, data):
        self._method = "POST"
        self._body = data
        self._headers["Prefer"] = "return=representation"
        return self

    def update(self, data):
        self._method = "PATCH"
        self._body = data
        self._headers["Prefer"] = "return=representation"
        return self

    def delete(self):
        self._method = "DELETE"
        self._headers["Prefer"] = "return=representation"
        return self

    # ── execução ─────────────────────────────────────────────────
    def execute(self):
        resp = requests.request(
            self._method,
            self._url,
            headers=self._headers,
            params=self._params,
            json=self._body,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()

        data = resp.json() if resp.content else []

        count = None
        content_range = resp.headers.get("content-range")
        if content_range and "/" in content_range:
            total = content_range.split("/")[-1]
            if total.isdigit():
                count = int(total)

        return _Response(data, count)


class SupabaseShim:
    """Substitui `Client` do supabase-py. Só implementa .table(), que é
    o único método usado no app (não há Auth/Storage/Realtime aqui)."""

    def __init__(self, url, key):
        self._url = url.rstrip("/")
        self._key = key

    def table(self, name):
        return _Query(self._url, self._key, name)


sb = SupabaseShim(SUPABASE_URL, SUPABASE_KEY)
