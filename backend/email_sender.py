# -*- coding: utf-8 -*-
"""
email_sender.py
Envio de e-mail via automação do Outlook Web (não usa SMTP) -- necessário
porque o tenant Microsoft 365 do ICDS tem "SMTP AUTH" desabilitado e não há
acesso de administrador pra habilitar. A sessão fica salva em
email_browser_profile/ (login feito manualmente uma vez por
login_outlook_setup.py); esse módulo só reabre essa sessão e automatiza o
preenchimento do e-mail.

Frágil por natureza (depende da UI do Outlook Web, que pode mudar) -- por
isso todo erro é capturado e devolvido em vez de propagado, igual ao padrão
já usado em whatsapp_sender.py.
"""
import os

PERFIL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "email_browser_profile")


def enviar_email(destinatarios, assunto, corpo_texto, anexo_path=None, timeout_ms=45000):
    """
    destinatarios: string ou lista de e-mails.
    corpo_texto: texto simples (uma linha por parágrafo).
    anexo_path: caminho local de um arquivo pra anexar (opcional).
    Retorna {"ok": bool, "erro": str|None}.
    """
    if isinstance(destinatarios, str):
        destinatarios = [d.strip() for d in destinatarios.split(",") if d.strip()]
    if not destinatarios:
        return {"ok": False, "erro": "Nenhum destinatário informado"}
    if not os.path.isdir(PERFIL_DIR):
        return {"ok": False, "erro": "Sessão do Outlook Web não configurada (rode login_outlook_setup.py)"}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "erro": "playwright não instalado"}

    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                PERFIL_DIR, channel="chrome", headless=True,
                viewport={"width": 1280, "height": 900},
            )
            try:
                page = ctx.new_page()
                page.goto("https://outlook.office.com/mail/", wait_until="load", timeout=timeout_ms)
                page.wait_for_timeout(4000)

                if "login.microsoftonline.com" in page.url or "login.live.com" in page.url:
                    return {"ok": False, "erro": "Sessão expirada — precisa logar de novo (rode login_outlook_setup.py)"}

                page.get_by_role("button", name="Novo email").click(timeout=timeout_ms)
                page.wait_for_timeout(1500)

                campo_para = page.locator('div[aria-label="Para"]').first
                campo_para.click(timeout=timeout_ms)
                for dest in destinatarios:
                    page.keyboard.type(dest)
                    page.wait_for_timeout(800)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(400)

                # Fecha o dropdown de sugestoes de contato, que as vezes fica
                # aberto sobre o campo Assunto e bloqueia o clique.
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)

                campo_assunto = page.get_by_placeholder("Adicionar um assunto")
                campo_assunto.click(timeout=timeout_ms, force=True)
                campo_assunto.fill(assunto)

                corpo = page.locator('div[aria-label*="Corpo da mensagem"], div[role="textbox"][contenteditable="true"]').last
                corpo.click()
                for linha in corpo_texto.split("\n"):
                    page.keyboard.type(linha)
                    page.keyboard.press("Enter")

                if anexo_path and os.path.exists(anexo_path):
                    page.locator('[aria-label*="Anexar arquivo"]').first.click(timeout=timeout_ms)
                    page.wait_for_timeout(800)
                    with page.expect_file_chooser(timeout=timeout_ms) as fc_info:
                        page.get_by_text("Navegar neste computador", exact=False).click()
                    fc_info.value.set_files(anexo_path)
                    page.wait_for_timeout(3000)

                page.locator('[aria-label*="Enviar"]').first.click(timeout=timeout_ms)
                page.wait_for_timeout(3000)
                return {"ok": True, "erro": None}
            finally:
                ctx.close()
    except Exception as e:
        return {"ok": False, "erro": f"{type(e).__name__}: {e}"}


if __name__ == "__main__":
    r = enviar_email("suporte@icds.org.br", "[TESTE] email_sender.py", "Teste do módulo de envio.\nPode ignorar.")
    print(r)
