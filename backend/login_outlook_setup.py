# -*- coding: utf-8 -*-
"""
login_outlook_setup.py
Rode isto manualmente sempre que a sessão do Outlook Web expirar (o
email_sender.py avisa isso quando acontece). Abre uma janela REAL do Chrome
(precisa estar numa sessão com tela, ex: RDP) -- faça o login com
suporte@icds.org.br (e MFA, se pedir) e deixe a janela aberta até a caixa de
entrada carregar. Depois volte aqui e aperte Ctrl+C pra fechar; a sessão já
fica salva em disco em email_browser_profile/ automaticamente.

Uso:
  python login_outlook_setup.py
"""
import os
import time
from playwright.sync_api import sync_playwright

PERFIL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "email_browser_profile")

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        PERFIL_DIR, channel="chrome", headless=False,
        viewport={"width": 1280, "height": 900},
    )
    page = ctx.new_page()
    page.goto("https://outlook.office.com/mail/")
    print("Janela aberta. Faça login com suporte@icds.org.br (e MFA, se pedir).")
    print("A sessão é salva automaticamente. Pressione Ctrl+C aqui quando terminar.")
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        pass
    ctx.close()
    print("Sessão salva em", PERFIL_DIR)
