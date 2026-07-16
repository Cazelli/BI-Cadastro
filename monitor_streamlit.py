from __future__ import annotations

import asyncio
import html
import os
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.async_api import Locator, Page, async_playwright


URL = os.getenv(
    "STREAMLIT_URL",
    "https://mobiflex-bi-cadastral.streamlit.app/",
)
EMAIL_DESTINO = (
    os.getenv("EMAIL_DESTINO", "").strip()
    or "pedro.cazelli@essenzsolucoes.com"
)
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
TIMEZONE = ZoneInfo(os.getenv("MONITOR_TIMEZONE", "America/Sao_Paulo"))
SCREENSHOT_PATH = Path("monitor_streamlit_error.png")

WAKE_BUTTON_NAMES = (
    "Yes, get this app back up!",
    "Yes, get this app back up",
    "Wake up",
    "Acordar",
)
ERROR_TEXTS = (
    "there was an error",
    "there was a problem",
    "this app has gone over its resource limits",
    "app is not running",
    "page not found",
    "internal server error",
    "connection error",
)


def required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"A variável de ambiente {name} não foi configurada.")
    return value


def current_time() -> datetime:
    return datetime.now(TIMEZONE)


def format_time(moment: datetime) -> str:
    return moment.strftime("%d/%m/%Y %H:%M:%S %Z")


def send_email(subject: str, body: str) -> None:
    sender = required_environment("EMAIL_REMETENTE")
    password = required_environment("EMAIL_SENHA")

    message = MIMEMultipart()
    message["From"] = sender
    message["To"] = EMAIL_DESTINO
    message["Subject"] = subject
    message.attach(MIMEText(body, "html", "utf-8"))

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.login(sender, password)
        server.send_message(message)


def send_wake_email(detected_at: datetime) -> None:
    timestamp = format_time(detected_at)
    send_email(
        "⚠️ App Streamlit estava dormindo — acordado com sucesso",
        f"""
        <html><body>
        <p>Olá, Pedro!</p>
        <p>O monitoramento identificou que o app Streamlit estava
        <b>inativo (sleeping)</b>.</p>
        <p><b>Horário da detecção:</b> {html.escape(timestamp)}</p>
        <p><b>URL:</b> <a href="{html.escape(URL)}">{html.escape(URL)}</a></p>
        <p>O botão para despertar o app foi acionado automaticamente e o
        carregamento foi confirmado.</p>
        <br><p>— Agente de Monitoramento</p>
        </body></html>
        """,
    )


def send_error_email(detected_at: datetime, error: str) -> None:
    timestamp = format_time(detected_at)
    send_email(
        "❌ Erro no Agente de Monitoramento Streamlit",
        f"""
        <html><body>
        <p>Olá, Pedro!</p>
        <p>O agente encontrou um <b>erro inesperado</b> durante a execução.</p>
        <p><b>Horário:</b> {html.escape(timestamp)}</p>
        <p><b>URL:</b> <a href="{html.escape(URL)}">{html.escape(URL)}</a></p>
        <p><b>Descrição:</b></p>
        <pre style="background:#f4f4f4;padding:10px;border-radius:5px;">{html.escape(error)}</pre>
        <p>Consulte também os logs e o artefato de captura de tela da execução
        no GitHub Actions.</p>
        <br><p>— Agente de Monitoramento</p>
        </body></html>
        """,
    )


async def find_wake_button(page: Page) -> Locator | None:
    for name in WAKE_BUTTON_NAMES:
        button = page.get_by_role("button", name=name, exact=False)
        if await button.count() and await button.first.is_visible():
            return button.first
    return None


async def page_summary(page: Page) -> tuple[str, str]:
    title = (await page.title()).strip()
    body = (await page.locator("body").inner_text(timeout=15_000)).strip()
    return title, body


async def confirm_page_is_available(page: Page) -> None:
    title, body = await page_summary(page)
    normalized_content = f"{title}\n{body}".lower()
    print(
        f"Página carregada: título={title!r}; URL final={page.url}; "
        f"conteúdo={body[:200]!r}"
    )

    matching_error = next(
        (text for text in ERROR_TEXTS if text in normalized_content),
        None,
    )
    if matching_error:
        raise RuntimeError(
            f"A página exibiu uma mensagem de erro: {matching_error!r}."
        )
    if not title and not body:
        raise RuntimeError("A página respondeu, mas não apresentou conteúdo.")


async def wait_until_app_is_ready(page: Page) -> None:
    # Não depende de seletores internos do Streamlit, que podem mudar e não
    # existem na tela de login. Aguarda o botão de suspensão desaparecer e
    # aceita como disponível qualquer página válida do app ou de autenticação.
    for _ in range(24):
        await page.wait_for_timeout(5_000)
        if await find_wake_button(page) is None:
            await confirm_page_is_available(page)
            return
    raise RuntimeError("O app continuou na tela de suspensão por 120 segundos.")


async def check_site() -> str:
    detected_at = current_time()
    print(f"[{format_time(detected_at)}] Verificando {URL}")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(
            viewport={"width": 1440, "height": 1000},
            locale="pt-BR",
        )
        try:
            response = await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=90_000,
            )
            if response is not None and response.status >= 400:
                raise RuntimeError(f"O site retornou HTTP {response.status}.")

            # A tela de suspensão do Streamlit pode ser renderizada alguns
            # segundos depois do primeiro HTML.
            await page.wait_for_timeout(5_000)
            wake_button = await find_wake_button(page)
            if wake_button is None:
                await confirm_page_is_available(page)
                print(f"[{format_time(current_time())}] App ativo.")
                return "active"

            print(f"[{format_time(current_time())}] App dormindo; despertando.")
            await wake_button.click(timeout=15_000)
            await wait_until_app_is_ready(page)
            send_wake_email(detected_at)
            print(f"[{format_time(current_time())}] App despertado; e-mail enviado.")
            return "awakened"
        except Exception:
            try:
                await page.screenshot(path=str(SCREENSHOT_PATH), full_page=True)
            except Exception as screenshot_error:
                print(f"Não foi possível salvar a captura: {screenshot_error}")
            raise
        finally:
            await browser.close()


async def main() -> int:
    detected_at = current_time()
    try:
        await check_site()
        return 0
    except Exception as error:
        error_message = f"{type(error).__name__}: {error}"
        print(f"[{format_time(current_time())}] ERRO: {error_message}")
        try:
            send_error_email(detected_at, error_message)
            print("E-mail de erro enviado.")
        except Exception as email_error:
            print(f"Falha adicional ao enviar o e-mail: {email_error}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
