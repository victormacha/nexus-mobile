"""
Nexus Mobile — App de gestão de tarefas em equipe
Versão Android/iOS feita com Kivy + KivyMD, usando o mesmo backend Supabase
do Nexus Desktop.

Build: veja README.md / buildozer.spec na mesma pasta.
"""
import hashlib
import threading
from datetime import datetime, date, time as dtime

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition

from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDRaisedButton, MDIconButton, MDFlatButton
from kivymd.uix.textfield import MDTextField
from kivymd.uix.card import MDCard
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.toolbar import MDTopAppBar
from kivymd.uix.navigationdrawer import MDNavigationLayout, MDNavigationDrawer
from kivymd.uix.list import MDList, OneLineListItem, IconLeftWidget, OneLineIconListItem
from kivymd.uix.selectioncontrol import MDSwitch
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.pickers import MDDatePicker, MDTimePicker
from kivymd.uix.dialog import MDDialog
from kivymd.uix.snackbar import Snackbar

from supabase_shim import sb

# Notificações locais (Android / iOS / desktop p/ testes)
try:
    from plyer import notification as local_notify
    PLYER_OK = True
except Exception:
    PLYER_OK = False

# ── Supabase ─────────────────────────────────────────────────────────
# O cliente "sb" agora vem do supabase_shim.py (não muda em nada o resto
# do código: sb.table(...).select()/.eq()/.insert()/.execute() etc.
# continuam funcionando exatamente igual).

# ── Helpers ───────────────────────────────────────────────────────────
def hash_senha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def notif_local(titulo, mensagem):
    if PLYER_OK:
        try:
            local_notify.notify(title=titulo, message=mensagem, app_name="Nexus", timeout=6)
        except Exception:
            pass


def criar_notificacao(usuario_id, titulo, mensagem):
    try:
        sb.table("notificacoes").insert({
            "usuario_id": usuario_id, "titulo": titulo,
            "mensagem": mensagem, "lida": False
        }).execute()
        notif_local(titulo, mensagem)
    except Exception:
        pass


def run_async(fn, on_done=None):
    """Roda fn() numa thread separada (chamadas de rede) e devolve o
    resultado pra thread principal via Clock, pra nunca travar a UI."""
    def _worker():
        try:
            result = fn()
            err = None
        except Exception as e:
            result = None
            err = e
        if on_done:
            Clock.schedule_once(lambda dt: on_done(result, err))
    threading.Thread(target=_worker, daemon=True).start()


COR_PRIMARIA = (0.12, 0.42, 0.65, 1)
COR_PERIGO = (0.42, 0.18, 0.18, 1)
COR_SUCESSO = (0.17, 0.42, 0.31, 1)
COR_FUNDO_CARD = (0.13, 0.13, 0.13, 1)


# ════════════════════════════════════════════════════════════════════
# LOGIN
# ════════════════════════════════════════════════════════════════════
class LoginScreen(MDScreen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.name = "login"
        root = MDBoxLayout(orientation="vertical", padding=dp(32), spacing=dp(12))

        root.add_widget(MDLabel(text="📋", font_style="H2", halign="center", size_hint_y=None, height=dp(80)))
        root.add_widget(MDLabel(text="Nexus", font_style="H4", halign="center", bold=True, size_hint_y=None, height=dp(40)))
        root.add_widget(MDLabel(text="Faça login para continuar", halign="center", theme_text_color="Secondary",
                                 size_hint_y=None, height=dp(28)))

        root.add_widget(MDBoxLayout(size_hint_y=None, height=dp(24)))

        self.ent_login = MDTextField(hint_text="Usuário", size_hint_y=None, height=dp(48))
        self.ent_senha = MDTextField(hint_text="Senha", password=True, size_hint_y=None, height=dp(48))
        root.add_widget(self.ent_login)
        root.add_widget(self.ent_senha)

        self.lbl_erro = MDLabel(text="", theme_text_color="Custom", text_color=(1, 0.42, 0.42, 1),
                                 halign="center", size_hint_y=None, height=dp(24))
        root.add_widget(self.lbl_erro)

        btn = MDRaisedButton(text="Entrar", size_hint=(1, None), height=dp(48), md_bg_color=COR_PRIMARIA)
        btn.bind(on_release=lambda *_: self._entrar())
        root.add_widget(btn)

        root.add_widget(MDBoxLayout())  # espaçador
        self.add_widget(root)

    def _entrar(self):
        login = self.ent_login.text.strip().lower()
        senha = self.ent_senha.text
        if not login or not senha:
            self.lbl_erro.text = "Preencha todos os campos."
            return
        self.lbl_erro.text = "Entrando..."

        def consulta():
            return sb.table("usuarios").select("*, grupo:grupo_id(id,nome)") \
                     .eq("login", login).eq("senha", hash_senha(senha)).execute()

        def feito(res, err):
            if err:
                self.lbl_erro.text = f"Erro: {err}"
                return
            if res.data:
                app = MDApp.get_running_app()
                app.entrar(res.data[0])
                self.ent_senha.text = ""
                self.lbl_erro.text = ""
            else:
                self.lbl_erro.text = "Usuário ou senha incorretos."

        run_async(consulta, feito)


# ════════════════════════════════════════════════════════════════════
# TELA PRINCIPAL (drawer + conteúdo trocável, igual ao desktop)
# ════════════════════════════════════════════════════════════════════
class MainScreen(MDScreen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.name = "main"
        self.usuario = None
        self.nivel = "membro"
        self.grupo = {}
        self._filtro_grupo_id = None
        self._status_atual = "Pendentes"
        self._build_layout()

    # ── montagem do shell (toolbar + drawer + área de conteúdo) ──────
    def _build_layout(self):
        self.nav_layout = MDNavigationLayout()
        sm = ScreenManager()
        shell = MDScreen()
        body = MDBoxLayout(orientation="vertical")

        self.toolbar = MDTopAppBar(
            title="Nexus",
            left_action_items=[["menu", lambda *_: self.drawer.set_state("open")]],
            elevation=4,
        )
        body.add_widget(self.toolbar)

        self.content_area = MDScrollView()
        self.content_box = MDBoxLayout(orientation="vertical", size_hint_y=None,
                                        padding=dp(16), spacing=dp(10))
        self.content_box.bind(minimum_height=self.content_box.setter("height"))
        self.content_area.add_widget(self.content_box)
        body.add_widget(self.content_area)

        shell.add_widget(body)
        sm.add_widget(shell)
        self.nav_layout.add_widget(sm)

        self.drawer = MDNavigationDrawer()
        drawer_box = MDBoxLayout(orientation="vertical", padding=dp(8))
        self.lbl_drawer_user = MDLabel(text="", bold=True, size_hint_y=None, height=dp(28), padding=(dp(8), 0))
        self.lbl_drawer_info = MDLabel(text="", theme_text_color="Secondary", font_style="Caption",
                                        size_hint_y=None, height=dp(22), padding=(dp(8), 0))
        drawer_box.add_widget(self.lbl_drawer_user)
        drawer_box.add_widget(self.lbl_drawer_info)
        drawer_scroll = MDScrollView()
        self.drawer_list = MDList()
        drawer_scroll.add_widget(self.drawer_list)
        drawer_box.add_widget(drawer_scroll)
        self.drawer.add_widget(drawer_box)
        self.nav_layout.add_widget(self.drawer)

        self.add_widget(self.nav_layout)

    # ── chamado depois do login ──────────────────────────────────────
    def set_usuario(self, usuario):
        self.usuario = usuario
        self.nivel = usuario.get("nivel", "membro")
        self.grupo = usuario.get("grupo") or {}
        nivel_label = {"nexus": "👑 Nexus", "adm": "🔧 Administrador", "membro": "👤 Membro"}.get(self.nivel, "")
        grupo_nome = self.grupo.get("nome", "") if self.grupo else ""
        self.lbl_drawer_user.text = usuario.get("nome", "")
        self.lbl_drawer_info.text = f"{nivel_label} · {grupo_nome}" if grupo_nome else nivel_label
        self._build_drawer_items()
        self.nav("minhas")
        Clock.schedule_once(lambda dt: self.popup_pendentes(), 0.6)
        Clock.schedule_interval(self.checar_horarios, 60)
        Clock.schedule_interval(self.atualizar_badge, 30)
        self.atualizar_badge(0)

    def _drawer_item(self, icone, texto, callback):
        item = OneLineIconListItem(text=texto, on_release=lambda *_: (callback(), self.drawer.set_state("close")))
        item.add_widget(IconLeftWidget(icon=icone))
        return item

    def _build_drawer_items(self):
        self.drawer_list.clear_widgets()
        itens = [
            ("home", "Minhas Tarefas", lambda: self.nav("minhas")),
            ("clipboard-text", "Tarefas do Grupo", lambda: self.nav("grupo")),
            ("plus-circle", "Nova Tarefa", lambda: self.nav("nova_tarefa")),
            ("bell", "Notificações", lambda: self.nav("notificacoes")),
            ("key", "Alterar Senha", lambda: self.nav("alterar_senha")),
        ]
        if self.nivel == "nexus":
            itens += [
                ("domain", "Grupos", lambda: self.nav("grupos")),
                ("account-group", "Usuários", lambda: self.nav("usuarios")),
                ("flask", "Teste Notificação", lambda: self.nav("teste")),
            ]
        elif self.nivel == "adm":
            itens += [("account-group", "Minha Equipe", lambda: self.nav("usuarios"))]

        for icone, texto, cb in itens:
            self.drawer_list.add_widget(self._drawer_item(icone, texto, cb))
        self.drawer_list.add_widget(self._drawer_item("logout", "Sair", self._sair))

    def _sair(self):
        app = MDApp.get_running_app()
        app.sair()

    def nav(self, view):
        self.content_box.clear_widgets()
        getattr(self, f"view_{view}")()

    def _titulo(self, texto):
        self.content_box.add_widget(MDLabel(text=texto, font_style="H5", bold=True,
                                             size_hint_y=None, height=dp(40)))

    def _erro(self, texto):
        self.content_box.add_widget(MDLabel(text=texto, theme_text_color="Custom",
                                             text_color=(1, 0.42, 0.42, 1),
                                             size_hint_y=None, height=dp(30)))

    # ── Minhas Tarefas / Tarefas do Grupo ────────────────────────────
    def view_minhas(self):
        self._renderizar_lista("Minhas Tarefas", "minhas")

    def view_grupo(self):
        if self.nivel == "nexus":
            self._renderizar_lista("Todas as Tarefas (Nexus)", "todas")
        elif self.nivel == "adm" and self.grupo:
            self._renderizar_lista(f"Tarefas — {self.grupo.get('nome','')}", "grupo")
        else:
            self._renderizar_lista("Tarefas do Grupo", "grupo")

    def _renderizar_lista(self, titulo, modo):
        self._titulo(titulo)
        self._status_atual = "Pendentes"

        status_row = MDBoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        self._status_btns = {}
        for status in ["Pendentes", "Concluídas", "Todas"]:
            b = MDFlatButton(text=status, md_bg_color=COR_PRIMARIA if status == "Pendentes" else (0, 0, 0, 0))
            b.bind(on_release=lambda inst, s=status, m=modo: self._trocar_status(s, m))
            status_row.add_widget(b)
            self._status_btns[status] = b
        self.content_box.add_widget(status_row)

        self.lista_box = MDBoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
        self.lista_box.bind(minimum_height=self.lista_box.setter("height"))
        self.content_box.add_widget(self.lista_box)

        self._atualizar_lista("Pendentes", modo)

    def _trocar_status(self, status, modo):
        self._status_atual = status
        for s, b in self._status_btns.items():
            b.md_bg_color = COR_PRIMARIA if s == status else (0, 0, 0, 0)
        self._atualizar_lista(status, modo)

    def _atualizar_lista(self, status, modo):
        self.lista_box.clear_widgets()
        self.lista_box.add_widget(MDLabel(text="Carregando...", theme_text_color="Secondary",
                                           size_hint_y=None, height=dp(30)))

        def consulta():
            q = sb.table("tarefas").select(
                "*, criador:criado_por(id,nome,grupo_id), responsavel:atribuido_a(id,nome)"
            )
            if modo == "minhas":
                q = q.eq("atribuido_a", self.usuario["id"])
            elif modo == "grupo":
                if self.grupo and self.grupo.get("id"):
                    membros = sb.table("usuarios").select("id").eq("grupo_id", self.grupo["id"]).execute().data
                    ids_m = [m["id"] for m in membros]
                    if ids_m:
                        q = q.in_("atribuido_a", ids_m)
                    else:
                        return []
            elif modo == "todas":
                if self._filtro_grupo_id:
                    membros = sb.table("usuarios").select("id").eq("grupo_id", self._filtro_grupo_id).execute().data
                    ids_m = [m["id"] for m in membros]
                    if ids_m:
                        q = q.in_("atribuido_a", ids_m)
            if status == "Pendentes":
                q = q.eq("concluida", False)
            elif status == "Concluídas":
                q = q.eq("concluida", True)
            return q.order("data_prazo").execute().data

        def feito(tarefas, err):
            self.lista_box.clear_widgets()
            if err:
                self._erro_lista(f"Erro: {err}")
                return
            if not tarefas:
                self.lista_box.add_widget(MDLabel(text="Nenhuma tarefa encontrada.",
                                                   theme_text_color="Secondary",
                                                   size_hint_y=None, height=dp(40)))
                return
            hoje = date.today().isoformat()
            for t in tarefas:
                self.lista_box.add_widget(self._task_card(t, hoje, status, modo))

        run_async(consulta, feito)

    def _erro_lista(self, msg):
        self.lista_box.add_widget(MDLabel(text=msg, theme_text_color="Custom",
                                           text_color=(1, 0.42, 0.42, 1),
                                           size_hint_y=None, height=dp(30)))

    def _task_card(self, t, hoje, status, modo):
        vencida = (t["data_prazo"] < hoje) and not t["concluida"]
        criador = t.get("criador", {}).get("nome", "—") if isinstance(t.get("criador"), dict) else "—"
        responsavel = t.get("responsavel", {}).get("nome", "—") if isinstance(t.get("responsavel"), dict) else "—"
        horario = t.get("horario")
        h_txt = f"🕐 {str(horario)[:5]}" if horario else "🗓 Dia todo"
        cor = (1, 0.42, 0.42, 1) if vencida else ((0.3, 0.73, 0.31, 1) if t["concluida"] else (0.3, 0.6, 0.85, 1))

        card = MDCard(orientation="vertical", padding=dp(12), spacing=dp(4), size_hint_y=None,
                       md_bg_color=COR_FUNDO_CARD, radius=[10], line_color=cor)
        card.bind(minimum_height=card.setter("height"))

        card.add_widget(MDLabel(text=t["titulo"], bold=True, size_hint_y=None, height=dp(24)))
        if t.get("descricao"):
            lbl_desc = MDLabel(text=t["descricao"], theme_text_color="Secondary", size_hint_y=None)
            lbl_desc.bind(texture_size=lambda inst, val: setattr(inst, "height", val[1]))
            card.add_widget(lbl_desc)

        meta = f"📅 {t['data_prazo']}  {h_txt}\n👤 {responsavel}  ✏️ Por {criador}"
        if vencida:
            meta += "  ⚠️ VENCIDA"
        card.add_widget(MDLabel(text=meta, theme_text_color="Custom", text_color=cor,
                                 font_style="Caption", size_hint_y=None, height=dp(38)))

        acoes = MDBoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        if not t["concluida"]:
            b = MDFlatButton(text="✓ Concluir", md_bg_color=COR_SUCESSO)
            b.bind(on_release=lambda *_: self._concluir(t, status, modo))
            acoes.add_widget(b)
        pode_excluir = (self.nivel in ["nexus", "adm"] or
                        (isinstance(t.get("criador"), dict) and t["criador"].get("id") == self.usuario["id"]))
        if pode_excluir:
            b = MDFlatButton(text="🗑 Excluir", md_bg_color=COR_PERIGO)
            b.bind(on_release=lambda *_: self._excluir_tarefa(t["id"], status, modo))
            acoes.add_widget(b)
        card.add_widget(acoes)
        return card

    def _concluir(self, tarefa, status, modo):
        def acao():
            sb.table("tarefas").update({"concluida": True}).eq("id", tarefa["id"]).execute()
            criador_id = tarefa.get("criador", {}).get("id") if isinstance(tarefa.get("criador"), dict) else None
            resp_nome = tarefa.get("responsavel", {}).get("nome", "") if isinstance(tarefa.get("responsavel"), dict) else ""
            if criador_id and criador_id != self.usuario["id"]:
                criar_notificacao(criador_id, "✅ Tarefa Concluída", f"{resp_nome} concluiu: {tarefa['titulo']}")
            if self.grupo and self.grupo.get("id"):
                adms = sb.table("usuarios").select("id").eq("grupo_id", self.grupo["id"]).eq("nivel", "adm").execute().data
                for adm in adms:
                    if adm["id"] not in [self.usuario["id"], criador_id]:
                        criar_notificacao(adm["id"], "✅ Tarefa Concluída", f"{resp_nome} concluiu: {tarefa['titulo']}")
            return True

        run_async(acao, lambda r, e: self._atualizar_lista(status, modo))

    def _excluir_tarefa(self, tid, status, modo):
        def confirmar(*_):
            self._dialog.dismiss()
            run_async(lambda: sb.table("tarefas").delete().eq("id", tid).execute(),
                      lambda r, e: self._atualizar_lista(status, modo))

        self._dialog = MDDialog(
            title="Confirmar",
            text="Excluir esta tarefa?",
            buttons=[
                MDFlatButton(text="Cancelar", on_release=lambda *_: self._dialog.dismiss()),
                MDFlatButton(text="Excluir", text_color=(1, 0.42, 0.42, 1), on_release=confirmar),
            ],
        )
        self._dialog.open()

    # ── Nova Tarefa ───────────────────────────────────────────────────
    def view_nova_tarefa(self):
        self._titulo("Nova Tarefa")
        self._nt_data_sel = None
        self._nt_hora_sel = dtime(8, 0)
        self._nt_dia_todo = True
        self._nt_resp_id = None
        self._nt_resp_nome = None

        ent_titulo = MDTextField(hint_text="Título *", size_hint_y=None, height=dp(48))
        self.content_box.add_widget(ent_titulo)

        ent_desc = MDTextField(hint_text="Descrição", multiline=True, size_hint_y=None, height=dp(70))
        self.content_box.add_widget(ent_desc)

        # responsável
        btn_resp = MDRaisedButton(text="👤 Selecionar responsável", size_hint=(1, None), height=dp(44))
        self.content_box.add_widget(btn_resp)

        def abrir_resp(*_):
            def consulta():
                if self.nivel == "nexus":
                    return sb.table("usuarios").select("id,nome").order("nome").execute().data
                gid = self.grupo.get("id") if self.grupo else None
                if gid:
                    return sb.table("usuarios").select("id,nome").eq("grupo_id", gid).order("nome").execute().data
                return [{"id": self.usuario["id"], "nome": self.usuario["nome"]}]

            def feito(usuarios, err):
                if err or not usuarios:
                    Snackbar(text="Não foi possível carregar usuários.").open()
                    return
                menu_items = [{
                    "text": u["nome"],
                    "on_release": lambda nome=u["nome"], uid=u["id"]: selecionar(nome, uid),
                } for u in usuarios]
                self._menu_resp = MDDropdownMenu(caller=btn_resp, items=menu_items, width_mult=4)
                self._menu_resp.open()

            def selecionar(nome, uid):
                self._nt_resp_nome, self._nt_resp_id = nome, uid
                btn_resp.text = f"👤 {nome}"
                self._menu_resp.dismiss()

            run_async(consulta, feito)

        btn_resp.bind(on_release=abrir_resp)

        # data
        btn_data = MDRaisedButton(text="📅 Selecionar data *", size_hint=(1, None), height=dp(44))
        self.content_box.add_widget(btn_data)

        def on_date_save(instance, value, date_range):
            self._nt_data_sel = value
            btn_data.text = f"📅 {value.strftime('%d/%m/%Y')}"

        def abrir_data(*_):
            picker = MDDatePicker()
            picker.bind(on_save=on_date_save)
            picker.open()

        btn_data.bind(on_release=abrir_data)

        # horário
        row_horario = MDBoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        switch_dia_todo = MDSwitch(active=True)
        row_horario.add_widget(switch_dia_todo)
        row_horario.add_widget(MDLabel(text="Dia todo (sem horário fixo)", size_hint_x=None, width=dp(220)))
        self.content_box.add_widget(row_horario)

        btn_hora = MDRaisedButton(text="🕐 08:00", size_hint=(1, None), height=dp(44), disabled=True)
        self.content_box.add_widget(btn_hora)

        def on_time_save(instance, time_obj):
            self._nt_hora_sel = time_obj
            btn_hora.text = f"🕐 {time_obj.strftime('%H:%M')}"

        def abrir_hora(*_):
            picker = MDTimePicker()
            picker.bind(on_save=on_time_save)
            picker.open()

        btn_hora.bind(on_release=abrir_hora)

        def on_switch(inst, val):
            self._nt_dia_todo = val
            btn_hora.disabled = val

        switch_dia_todo.bind(active=on_switch)

        lbl_msg = MDLabel(text="", theme_text_color="Custom", text_color=(1, 0.42, 0.42, 1),
                           size_hint_y=None, height=dp(30))
        self.content_box.add_widget(lbl_msg)

        def salvar(*_):
            titulo = ent_titulo.text.strip()
            desc = ent_desc.text.strip()
            if not titulo:
                lbl_msg.text = "Título é obrigatório."; return
            if not self._nt_data_sel:
                lbl_msg.text = "Selecione uma data."; return
            if not self._nt_resp_id:
                lbl_msg.text = "Selecione um responsável."; return

            horario = None if self._nt_dia_todo else self._nt_hora_sel.strftime("%H:%M:00")
            resp_id, resp_nome = self._nt_resp_id, self._nt_resp_nome

            def acao():
                sb.table("tarefas").insert({
                    "titulo": titulo, "descricao": desc,
                    "criado_por": self.usuario["id"],
                    "atribuido_a": resp_id,
                    "data_prazo": self._nt_data_sel.isoformat(),
                    "horario": horario,
                    "concluida": False,
                }).execute()
                h_info = f" às {horario[:5]}" if horario else " (dia todo)"
                if resp_id != self.usuario["id"]:
                    criar_notificacao(resp_id, "📋 Nova Tarefa Atribuída",
                                       f"{self.usuario['nome']} atribuiu: {titulo} — "
                                       f"{self._nt_data_sel.strftime('%d/%m/%Y')}{h_info}")
                return True

            def feito(r, err):
                if err:
                    lbl_msg.text = f"Erro: {err}"; return
                Snackbar(text=f"Tarefa criada para {resp_nome}!").open()
                self.nav("minhas")

            run_async(acao, feito)

        btn_salvar = MDRaisedButton(text="💾 Salvar Tarefa", size_hint=(1, None), height=dp(48),
                                     md_bg_color=COR_PRIMARIA)
        btn_salvar.bind(on_release=salvar)
        self.content_box.add_widget(btn_salvar)

    # ── Notificações ──────────────────────────────────────────────────
    def view_notificacoes(self):
        self._titulo("🔔 Notificações")

        btn_todas = MDFlatButton(text="✔ Marcar todas como lidas")
        btn_todas.bind(on_release=lambda *_: self._marcar_todas_lidas())
        self.content_box.add_widget(btn_todas)

        self.notif_box = MDBoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
        self.notif_box.bind(minimum_height=self.notif_box.setter("height"))
        self.content_box.add_widget(self.notif_box)
        self._carregar_notificacoes()

    def _carregar_notificacoes(self):
        self.notif_box.clear_widgets()
        self.notif_box.add_widget(MDLabel(text="Carregando...", theme_text_color="Secondary",
                                           size_hint_y=None, height=dp(30)))

        def consulta():
            return sb.table("notificacoes").select("*").eq("usuario_id", self.usuario["id"]) \
                     .order("criado_em", desc=True).execute().data

        def feito(notifs, err):
            self.notif_box.clear_widgets()
            if err:
                self._erro_lista_em(self.notif_box, f"Erro: {err}"); return
            if not notifs:
                self.notif_box.add_widget(MDLabel(text="Nenhuma notificação.", theme_text_color="Secondary",
                                                   size_hint_y=None, height=dp(40)))
                return
            for n in notifs:
                self.notif_box.add_widget(self._notif_card(n))

        run_async(consulta, feito)

    def _erro_lista_em(self, box, msg):
        box.add_widget(MDLabel(text=msg, theme_text_color="Custom", text_color=(1, 0.42, 0.42, 1),
                                size_hint_y=None, height=dp(30)))

    def _notif_card(self, n):
        nao_lida = not n.get("lida", True)
        cor_borda = (0.3, 0.6, 0.85, 1) if nao_lida else (0.3, 0.3, 0.3, 1)
        card = MDCard(orientation="vertical", padding=dp(10), spacing=dp(2), size_hint_y=None,
                       md_bg_color=COR_FUNDO_CARD, radius=[8], line_color=cor_borda)
        card.bind(minimum_height=card.setter("height"))
        card.add_widget(MDLabel(text=n["titulo"], bold=True, size_hint_y=None, height=dp(22)))
        lbl_msg = MDLabel(text=n["mensagem"], theme_text_color="Secondary", size_hint_y=None)
        lbl_msg.bind(texture_size=lambda inst, val: setattr(inst, "height", val[1]))
        card.add_widget(lbl_msg)
        ts = (n.get("criado_em") or "")[:16].replace("T", " ")
        card.add_widget(MDLabel(text=ts, font_style="Caption", theme_text_color="Hint",
                                 size_hint_y=None, height=dp(18)))
        if nao_lida:
            b = MDFlatButton(text="Marcar como lido", size_hint_y=None, height=dp(32))
            b.bind(on_release=lambda *_: self._marcar_lida(n["id"]))
            card.add_widget(b)
        return card

    def _marcar_lida(self, nid):
        run_async(lambda: sb.table("notificacoes").update({"lida": True}).eq("id", nid).execute(),
                   lambda r, e: (self._carregar_notificacoes(), self.atualizar_badge(0)))

    def _marcar_todas_lidas(self):
        run_async(lambda: sb.table("notificacoes").update({"lida": True}).eq("usuario_id", self.usuario["id"]).execute(),
                   lambda r, e: (self._carregar_notificacoes(), self.atualizar_badge(0)))

    def atualizar_badge(self, dt):
        def consulta():
            return sb.table("notificacoes").select("id", count="exact") \
                     .eq("usuario_id", self.usuario["id"]).eq("lida", False).execute().count or 0

        def feito(n, err):
            if err:
                return
            for item in self.drawer_list.children:
                if "Notificações" in item.text:
                    item.text = f"Notificações ({n})" if n > 0 else "Notificações"

        run_async(consulta, feito)

    # ── Alterar Senha ─────────────────────────────────────────────────
    def view_alterar_senha(self):
        self._titulo("🔑 Alterar Senha")
        ent_atual = MDTextField(hint_text="Senha atual", password=True, size_hint_y=None, height=dp(48))
        ent_nova = MDTextField(hint_text="Nova senha", password=True, size_hint_y=None, height=dp(48))
        ent_conf = MDTextField(hint_text="Confirmar nova senha", password=True, size_hint_y=None, height=dp(48))
        for w in (ent_atual, ent_nova, ent_conf):
            self.content_box.add_widget(w)

        lbl_msg = MDLabel(text="", size_hint_y=None, height=dp(30))
        self.content_box.add_widget(lbl_msg)

        def salvar(*_):
            atual, nova, conf = ent_atual.text, ent_nova.text, ent_conf.text
            if not atual or not nova or not conf:
                lbl_msg.text = "Preencha todos os campos."
                lbl_msg.text_color = (1, 0.42, 0.42, 1); return
            if nova != conf:
                lbl_msg.text = "As novas senhas não coincidem."
                lbl_msg.text_color = (1, 0.42, 0.42, 1); return
            if len(nova) < 4:
                lbl_msg.text = "A nova senha deve ter pelo menos 4 caracteres."
                lbl_msg.text_color = (1, 0.42, 0.42, 1); return

            def acao():
                res = sb.table("usuarios").select("id").eq("id", self.usuario["id"]) \
                        .eq("senha", hash_senha(atual)).execute()
                if not res.data:
                    return "senha_incorreta"
                sb.table("usuarios").update({"senha": hash_senha(nova)}).eq("id", self.usuario["id"]).execute()
                return "ok"

            def feito(resultado, err):
                if err:
                    lbl_msg.text = f"Erro: {err}"; lbl_msg.text_color = (1, 0.42, 0.42, 1); return
                if resultado == "senha_incorreta":
                    lbl_msg.text = "Senha atual incorreta."; lbl_msg.text_color = (1, 0.42, 0.42, 1); return
                ent_atual.text = ent_nova.text = ent_conf.text = ""
                lbl_msg.text = "✅ Senha alterada com sucesso!"
                lbl_msg.text_color = (0.3, 0.73, 0.31, 1)

            run_async(acao, feito)

        btn = MDRaisedButton(text="💾 Salvar Nova Senha", size_hint=(1, None), height=dp(48),
                              md_bg_color=COR_PRIMARIA)
        btn.bind(on_release=salvar)
        self.content_box.add_widget(btn)

    # ── Grupos (Nexus) ────────────────────────────────────────────────
    def view_grupos(self):
        self._titulo("🏢 Gerenciar Grupos")
        self.grupos_box = MDBoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        self.grupos_box.bind(minimum_height=self.grupos_box.setter("height"))
        self.content_box.add_widget(self.grupos_box)
        self._recarregar_grupos()

        self.content_box.add_widget(MDLabel(text="Criar Novo Grupo", bold=True,
                                             size_hint_y=None, height=dp(32)))
        ent = MDTextField(hint_text="Nome do grupo", size_hint_y=None, height=dp(48))
        self.content_box.add_widget(ent)
        lbl_msg = MDLabel(text="", theme_text_color="Custom", text_color=(1, 0.42, 0.42, 1),
                           size_hint_y=None, height=dp(26))
        self.content_box.add_widget(lbl_msg)

        def criar(*_):
            nome = ent.text.strip()
            if not nome:
                lbl_msg.text = "Nome obrigatório."; return

            def feito(r, err):
                if err:
                    lbl_msg.text = f"Erro: {err}"; return
                ent.text = ""; lbl_msg.text = ""
                Snackbar(text=f"Grupo '{nome}' criado!").open()
                self._recarregar_grupos()

            run_async(lambda: sb.table("grupos").insert({"nome": nome}).execute(), feito)

        btn = MDRaisedButton(text="➕ Criar Grupo", size_hint=(1, None), height=dp(44), md_bg_color=COR_PRIMARIA)
        btn.bind(on_release=criar)
        self.content_box.add_widget(btn)

    def _recarregar_grupos(self):
        self.grupos_box.clear_widgets()

        def feito(grupos, err):
            self.grupos_box.clear_widgets()
            if err or not grupos:
                self.grupos_box.add_widget(MDLabel(text="Nenhum grupo cadastrado." if not err else f"Erro: {err}",
                                                     theme_text_color="Secondary", size_hint_y=None, height=dp(30)))
                return
            for g in grupos:
                row = MDBoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
                row.add_widget(MDLabel(text=f"🏢 {g['nome']}"))
                b = MDFlatButton(text="Excluir", md_bg_color=COR_PERIGO)
                b.bind(on_release=lambda *_, gid=g["id"]: self._excluir_grupo(gid))
                row.add_widget(b)
                self.grupos_box.add_widget(row)

        run_async(lambda: sb.table("grupos").select("*").order("nome").execute().data, feito)

    def _excluir_grupo(self, gid):
        run_async(lambda: sb.table("grupos").delete().eq("id", gid).execute(),
                   lambda r, e: self._recarregar_grupos())

    # ── Usuários (Nexus / ADM) ────────────────────────────────────────
    def view_usuarios(self):
        titulo = "👥 Usuários" if self.nivel == "nexus" else "👥 Minha Equipe"
        self._titulo(titulo)
        self.usuarios_box = MDBoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        self.usuarios_box.bind(minimum_height=self.usuarios_box.setter("height"))
        self.content_box.add_widget(self.usuarios_box)
        self._recarregar_usuarios()

        self.content_box.add_widget(MDLabel(text="Criar Novo Usuário", bold=True,
                                             size_hint_y=None, height=dp(32)))
        ent_nome = MDTextField(hint_text="Nome completo", size_hint_y=None, height=dp(48))
        ent_login = MDTextField(hint_text="Login (sem espaços, minúsculas)", size_hint_y=None, height=dp(48))
        ent_senha = MDTextField(hint_text="Senha", password=True, size_hint_y=None, height=dp(48))
        for w in (ent_nome, ent_login, ent_senha):
            self.content_box.add_widget(w)

        self._novo_u_grupo_id = self.grupo.get("id") if self.nivel == "adm" else None
        self._novo_u_grupo_nome = self.grupo.get("nome", "Sem grupo") if self.nivel == "adm" else "Sem grupo"
        self._novo_u_nivel = "membro"

        btn_grupo = MDRaisedButton(text=f"Grupo: {self._novo_u_grupo_nome}", size_hint=(1, None), height=dp(44),
                                    disabled=(self.nivel != "nexus"))
        self.content_box.add_widget(btn_grupo)

        def abrir_grupo(*_):
            def feito(grupos, err):
                if err:
                    return
                opcoes = [{"id": None, "nome": "Sem grupo"}] + grupos
                items = [{"text": g["nome"],
                          "on_release": lambda gid=g["id"], gn=g["nome"]: selecionar(gid, gn)} for g in opcoes]
                self._menu_grupo = MDDropdownMenu(caller=btn_grupo, items=items, width_mult=4)
                self._menu_grupo.open()

            def selecionar(gid, gnome):
                self._novo_u_grupo_id, self._novo_u_grupo_nome = gid, gnome
                btn_grupo.text = f"Grupo: {gnome}"
                self._menu_grupo.dismiss()

            run_async(lambda: sb.table("grupos").select("*").order("nome").execute().data, feito)

        if self.nivel == "nexus":
            btn_grupo.bind(on_release=abrir_grupo)

        niveis = ["membro", "adm"] if self.nivel == "nexus" else ["membro"]
        btn_nivel = MDRaisedButton(text="Nível: membro", size_hint=(1, None), height=dp(44),
                                    disabled=(self.nivel != "nexus"))
        self.content_box.add_widget(btn_nivel)

        def abrir_nivel(*_):
            items = [{"text": nv, "on_release": lambda n=nv: selecionar(n)} for nv in niveis]
            self._menu_nivel = MDDropdownMenu(caller=btn_nivel, items=items, width_mult=3)
            self._menu_nivel.open()

        def selecionar(n):
            self._novo_u_nivel = n
            btn_nivel.text = f"Nível: {n}"
            self._menu_nivel.dismiss()

        if self.nivel == "nexus":
            btn_nivel.bind(on_release=abrir_nivel)

        lbl_msg = MDLabel(text="", theme_text_color="Custom", text_color=(1, 0.42, 0.42, 1),
                           size_hint_y=None, height=dp(26))
        self.content_box.add_widget(lbl_msg)

        def criar(*_):
            nome = ent_nome.text.strip()
            login = ent_login.text.strip().lower()
            senha = ent_senha.text
            if not nome or not login or not senha:
                lbl_msg.text = "Preencha todos os campos."; return

            def feito(r, err):
                if err:
                    lbl_msg.text = f"Erro (login duplicado?): {err}"; return
                ent_nome.text = ent_login.text = ent_senha.text = ""
                lbl_msg.text = ""
                Snackbar(text=f"Usuário '{nome}' criado!").open()
                self._recarregar_usuarios()

            run_async(lambda: sb.table("usuarios").insert({
                "nome": nome, "login": login, "senha": hash_senha(senha),
                "nivel": self._novo_u_nivel, "grupo_id": self._novo_u_grupo_id,
                "admin": self._novo_u_nivel in ["nexus", "adm"],
            }).execute(), feito)

        btn = MDRaisedButton(text="➕ Criar Usuário", size_hint=(1, None), height=dp(44), md_bg_color=COR_PRIMARIA)
        btn.bind(on_release=criar)
        self.content_box.add_widget(btn)

    def _recarregar_usuarios(self):
        self.usuarios_box.clear_widgets()

        def consulta():
            if self.nivel == "nexus":
                return sb.table("usuarios").select("*, grupo:grupo_id(nome)").order("nome").execute().data
            return sb.table("usuarios").select("*, grupo:grupo_id(nome)") \
                     .eq("grupo_id", self.grupo["id"]).order("nome").execute().data

        def feito(usuarios, err):
            self.usuarios_box.clear_widgets()
            if err or not usuarios:
                self.usuarios_box.add_widget(MDLabel(text="Nenhum usuário." if not err else f"Erro: {err}",
                                                       theme_text_color="Secondary", size_hint_y=None, height=dp(30)))
                return
            for u in usuarios:
                icon = {"nexus": "👑", "adm": "🔧", "membro": "👤"}.get(u.get("nivel", "membro"), "👤")
                gnome = u.get("grupo", {}).get("nome", "Sem grupo") if isinstance(u.get("grupo"), dict) else "Sem grupo"
                row = MDBoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
                row.add_widget(MDLabel(text=f"{icon} {u['nome']} ({u['login']}) · {gnome}"))
                if u["id"] != self.usuario["id"] and u.get("nivel") != "nexus":
                    b = MDFlatButton(text="Excluir", md_bg_color=COR_PERIGO)
                    b.bind(on_release=lambda *_, uid=u["id"]: self._excluir_usuario(uid))
                    row.add_widget(b)
                self.usuarios_box.add_widget(row)

        run_async(consulta, feito)

    def _excluir_usuario(self, uid):
        def confirmar(*_):
            self._dialog.dismiss()

            def acao():
                sb.table("tarefas").delete().eq("atribuido_a", uid).execute()
                sb.table("tarefas").delete().eq("criado_por", uid).execute()
                sb.table("notificacoes").delete().eq("usuario_id", uid).execute()
                sb.table("usuarios").delete().eq("id", uid).execute()
                return True

            run_async(acao, lambda r, e: self._recarregar_usuarios())

        self._dialog = MDDialog(
            title="Confirmar",
            text="Excluir este usuário? As tarefas e notificações associadas a ele também serão removidas.",
            buttons=[
                MDFlatButton(text="Cancelar", on_release=lambda *_: self._dialog.dismiss()),
                MDFlatButton(text="Excluir", text_color=(1, 0.42, 0.42, 1), on_release=confirmar),
            ],
        )
        self._dialog.open()

    # ── Teste de Notificação (Nexus apenas) ──────────────────────────
    def view_teste(self):
        self._titulo("🧪 Teste de Notificações")
        self.content_box.add_widget(MDLabel(text="Toque num botão pra simular o tipo de notificação.",
                                             theme_text_color="Secondary", size_hint_y=None, height=dp(30)))
        lbl_status = MDLabel(text="", theme_text_color="Custom", text_color=(0.3, 0.73, 0.31, 1),
                              size_hint_y=None, height=dp(30))
        self.content_box.add_widget(lbl_status)

        hoje_fmt = date.today().strftime("%d/%m/%Y")
        testes = [
            ("📋 Nova tarefa atribuída", "📋 Nova Tarefa Atribuída",
             f"Fulano atribuiu a você: Revisar relatório mensal (prazo: {hoje_fmt} — Dia todo)"),
            ("📋 Nova tarefa com horário", "📋 Nova Tarefa Atribuída",
             f"Fulano atribuiu a você: Reunião de alinhamento (prazo: {hoje_fmt} às 14:30)"),
            ("⏰ Lembrete de horário", "⏰ Tarefa no horário agora!",
             "Sua tarefa 'Reunião de alinhamento' está programada para 14:30 hoje."),
            ("⚠️ Tarefa vencida (sua)", "⚠️ Tarefa Vencida",
             "Sua tarefa 'Enviar proposta ao cliente' venceu e ainda não foi concluída."),
            ("⚠️ Membro com tarefa atrasada", "⚠️ Membro com Tarefa Atrasada",
             "Estefani está com a tarefa 'Fechar planilha de custos' atrasada."),
            ("✅ Tarefa concluída por membro", "✅ Tarefa Concluída",
             "Estefani concluiu: Fechar planilha de custos."),
            ("✅ Tarefa concluída — visão ADM", "✅ Tarefa Concluída (ADM)",
             "Victor concluiu: Revisar relatório mensal. Notificação recebida como ADM do grupo."),
        ]

        def disparar(nome_btn, titulo_n, msg_n):
            criar_notificacao(self.usuario["id"], titulo_n, msg_n)
            self.atualizar_badge(0)
            lbl_status.text = f"✅ '{nome_btn}' disparada! Veja em Notificações."

        for nome, titulo_n, msg_n in testes:
            row = MDBoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
            row.add_widget(MDLabel(text=nome))
            b = MDFlatButton(text="▶ Testar")
            b.bind(on_release=lambda *_, n=nome, t=titulo_n, m=msg_n: disparar(n, t, m))
            row.add_widget(b)
            self.content_box.add_widget(row)

        def testar_popup(*_):
            hoje = date.today().isoformat()

            def acao():
                sb.table("tarefas").insert({
                    "titulo": "Tarefa de teste (pop-up)", "descricao": "Criada automaticamente pelo teste.",
                    "criado_por": self.usuario["id"], "atribuido_a": self.usuario["id"],
                    "data_prazo": hoje, "concluida": False, "horario": None,
                }).execute()
                return sb.table("tarefas").select("*, criador:criado_por(nome)") \
                         .eq("atribuido_a", self.usuario["id"]).eq("concluida", False) \
                         .lte("data_prazo", hoje).execute().data

            def feito(pendentes, err):
                if err:
                    lbl_status.text = f"Erro: {err}"; return
                lbl_status.text = "✅ Tarefa criada. Abrindo pop-up..."
                self.popup_pendentes(pendentes)

            run_async(acao, feito)

        row = MDBoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        row.add_widget(MDLabel(text="🚀 Criar tarefa para HOJE e testar pop-up"))
        b = MDFlatButton(text="▶ Testar")
        b.bind(on_release=testar_popup)
        row.add_widget(b)
        self.content_box.add_widget(row)

    # ── Pop-up de pendentes (ao abrir o app) ─────────────────────────
    def popup_pendentes(self, tarefas_extras=None):
        if tarefas_extras is not None:
            self._mostrar_popup(tarefas_extras)
            return

        def consulta():
            hoje = date.today().isoformat()
            return sb.table("tarefas").select("*, criador:criado_por(nome)") \
                     .eq("atribuido_a", self.usuario["id"]).eq("concluida", False) \
                     .lte("data_prazo", hoje).order("data_prazo").execute().data

        run_async(consulta, lambda pendentes, err: None if err else self._mostrar_popup(pendentes))

    def _mostrar_popup(self, pendentes):
        if not pendentes:
            return
        notif_local("📋 Nexus", f"Você tem {len(pendentes)} tarefa(s) pendente(s) hoje!")

        box = MDBoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None, padding=dp(4))
        box.bind(minimum_height=box.setter("height"))
        for t in pendentes:
            criador = t.get("criador", {}).get("nome", "—") if isinstance(t.get("criador"), dict) else "—"
            horario = t.get("horario", "")
            h_txt = f"🕐 {str(horario)[:5]}" if horario else "🗓 Dia todo"
            item_box = MDBoxLayout(orientation="vertical", size_hint_y=None, height=dp(54))
            item_box.add_widget(MDLabel(text=t["titulo"], bold=True, size_hint_y=None, height=dp(24)))
            item_box.add_widget(MDLabel(text=f"📅 {t['data_prazo']}  {h_txt}  ✏️ De: {criador}",
                                         theme_text_color="Custom", text_color=(1, 0.42, 0.42, 1),
                                         font_style="Caption", size_hint_y=None, height=dp(22)))
            box.add_widget(item_box)

        scroll = MDScrollView(size_hint_y=None, height=dp(280))
        scroll.add_widget(box)

        dialog = MDDialog(
            title="🔔 Tarefas Pendentes / Vencidas",
            type="custom",
            content_cls=scroll,
            buttons=[MDFlatButton(text="Entendido", on_release=lambda *_: dialog.dismiss())],
        )
        dialog.open()

    # ── Verificador de horários (a cada 60s) ─────────────────────────
    def checar_horarios(self, dt):
        def consulta():
            agora = datetime.now()
            hoje = agora.date().isoformat()
            h_atual = agora.strftime("%H:%M")
            res = sb.table("tarefas").select("*, responsavel:atribuido_a(id,nome)") \
                    .eq("atribuido_a", self.usuario["id"]).eq("concluida", False) \
                    .eq("data_prazo", hoje).not_.is_("horario", "null").execute()
            return res.data, h_atual

        def feito(resultado, err):
            if err or not resultado:
                return
            tarefas, h_atual = resultado
            for t in tarefas:
                h_tarefa = str(t.get("horario", ""))[:5]
                if h_tarefa == h_atual:
                    criar_notificacao(self.usuario["id"], f"⏰ Tarefa no horário: {t['titulo']}",
                                       f"Esta tarefa está programada para {h_tarefa} hoje.")

        run_async(consulta, feito)






# ════════════════════════════════════════════════════════════════════
# APP
# ════════════════════════════════════════════════════════════════════
class NexusApp(MDApp):
    def build(self):
        self.title = "Nexus"
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Blue"
        Window.softinput_mode = "below_target"  # teclado não cobre os campos

        self.sm = ScreenManager(transition=SlideTransition())
        self.login_screen = LoginScreen()
        self.main_screen = MainScreen()
        self.sm.add_widget(self.login_screen)
        self.sm.add_widget(self.main_screen)
        return self.sm

    def entrar(self, usuario):
        self.main_screen.set_usuario(usuario)
        self.sm.current = "main"

    def sair(self):
        self.sm.current = "login"


if __name__ == "__main__":
    NexusApp().run()
