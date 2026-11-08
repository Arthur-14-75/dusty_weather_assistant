import re
from langchain_core.tools import tool
from pathlib import Path
from typing import Literal, Optional
from pydantic import BaseModel, Field
from playwright.async_api import async_playwright
import os


DOWNLOADS_DIR = Path(__file__).resolve().parent.parent / "NOTAMS"

async def navigate_and_download_notams_pdf(mode: str, departure_airfield: str, arrival_airfield: str, directory: str = str(DOWNLOADS_DIR)) -> str:
    "Cette fonction utilise le client MCP Playwright pour naviguer sur le site Sofia Briefing, générer le dossier NOTAM pour le vol spécifié et télécharger le fichier PDF correspondant."

    target_arrival = arrival_airfield if mode == "trajet" else departure_airfield

    async with async_playwright() as playwright:
        user_data_dir = Path("./.chrome-aeroweb-profile")
        context = await playwright.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=False,        # Ouvre la fenêtre Chrome visible à l'écran
                    slow_mo=500,           # Pause de 500 ms entre chaque action (clic, frappe)
                    channel="chrome"       # Utilise le Chrome natif installé sur ta machine
                )
        
        page = await context.new_page()
        
        # 1. Gestion des permissions via CDP directement sur le contexte
        cdp_session = await context.new_cdp_session(page)
        await cdp_session.send(
                "Browser.setPermission",
                {
                    "permission": {"name": "geolocation"},
                    "setting": "denied",
                    "origin": "https://sofia-briefing.aviation-civile.gouv.fr/sofia/pages/homepage.html",
                },
            )

        await page.wait_for_load_state("domcontentloaded")

        # 2. Navigation vers la page de préparation de vol et saisie des informations de vol

        await page.pause()
        await page.locator("button[type='submit'], button#login, input[type='submit']").first.click()


        