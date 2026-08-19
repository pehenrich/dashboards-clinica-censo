# -*- coding: utf-8 -*-
"""
login_outlook.py
Abre uma janela do Chrome com um perfil dedicado e persistente, apontada pro
Outlook Web. Rode isso UMA VEZ, faça o login manualmente (com MFA se pedir),
e feche a janela quando terminar -- a sessão fica salva em
email_browser_profile/ e é reaproveitada pelo envio automático depois.
"""
import os
from playwright.sync_api import sync_playwright

PERFIL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "email_browser_profile")

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        PERFIL_DIR,
        channel="chrome",
        headless=False,
        viewport={"width": 1280, "height": 900},
    )
    page = ctx.new_page()
    page.goto("https://outlook.office.com/mail/")
    print("Janela aberta. Faça login com suporte@icds.org.br (e MFA, se pedir).")
    print("A sessão fica salva no perfil automaticamente conforme você usa.")
    # Fica de pé até o processo ser encerrado externamente (o cookie/sessão já
    # é gravado em disco pelo Chrome continuamente, não só ao fechar).
    import time
    while True:
        time.sleep(5)
