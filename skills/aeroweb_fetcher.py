import re
from langchain_core.tools import tool
from pathlib import Path
from typing import Literal, Optional
from pydantic import BaseModel, Field
from playwright.async_api import async_playwright
import os


AEROWEB_LOGIN_URL = "https://aviation.meteo.fr/login.php"
AEROWEB_USER = os.getenv("AEROWEB_USER")
AEROWEB_PASSWORD = os.getenv("AEROWEB_PASSWORD")
DOWNLOADS_DIR = Path(__file__).resolve().parent.parent / "bulletins"

async def navigate_and_download_aeroweb_pdf(mode: str, departure_airfield: str, arrival_airfield: str, directory: str = str(DOWNLOADS_DIR)) -> str:
    """
    Cette fonction utilise le client MCP Playwright pour naviguer sur le site Aeroweb,
    se connecter avec les identifiants fournis, générer le dossier météo pour le vol
    spécifié et télécharger le fichier PDF correspondant.
    """
    # Implémentation fictive pour l'exemple
    # Dans une vraie implémentation, vous utiliseriez Playwright pour automatiser la navigation et le téléchargement
    

    target_arrival = arrival_airfield if mode == "trajet" else departure_airfield

    async with async_playwright() as playwright:
        """Cette fonction a pour but de télécharger le dossier météo du vol souhaité sur Aeroweb grâce au MCP Playwritght"""

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
                "origin": "https://aviation.meteo.fr",
            },
        )

        await page.goto(AEROWEB_LOGIN_URL)
        await page.wait_for_load_state("domcontentloaded")

        #1. Gestion des identifiants de connexion
        login_input = page.locator("input[name='login'], input#login, input[type='text']").first
        if await login_input.count() > 0 and await login_input.is_visible():
            await login_input.fill(AEROWEB_USER)
            await page.locator("input[name='password'], input#password, input[type='password']").first.fill(AEROWEB_PASSWORD)
            await page.locator("button[type='submit'], button#login, input[type='submit']").first.click()
            await page.wait_for_load_state("networkidle")

        #2. Sélection du type de vol

        await page.wait_for_load_state("domcontentloaded")


        if mode == "local":
            local_radio = page.get_by_role("row", name="Vol local (80MN)").get_by_role("radio").first
            await local_radio.click()

            # Saisie terrain
            input_terrain = page.locator("#aero_depart_loc").first
            await input_terrain.fill(departure_airfield)

            # Validation
            await page.locator("#cellVolLocalOuvert").get_by_role("link").filter(has_text=re.compile(r"^$")).first.click()
        else :
            trajet_radio = page.get_by_role("row", name="Trajet").get_by_role("radio")
            await trajet_radio.check()

            # Attendre que le champ de départ devienne visible suite au dépliement de la ligne
            depart_input = page.locator("#aero_depart_trajet").first
            await depart_input.wait_for(state="visible", timeout=10000)

            # Saisie des aérodromes
            await depart_input.fill(departure_airfield)

            arrivee_input = page.locator("#aero_arrivee_trajet").first
            await arrivee_input.fill(arrival_airfield)

            # Validation du formulaire pour charger les résultats
            await page.get_by_role("link").filter(has_text=re.compile(r"^$")).nth(5).first.click()
            await page.wait_for_load_state("networkidle")
        
        
        await page.wait_for_load_state("networkidle")

        #await page.pause()

        async with context.expect_page() as popup_info:
            await page.get_by_role("link", name="Affichage au format PDF").nth(1).first.click()

        #await page.pause()
        popup = await popup_info.value
        await popup.wait_for_load_state("load")
        
        #récupération de l'URL directe du PDF

        pdf_url = popup.url
        
        # Téléchargement direct sans passer par l'UI/hover
        response = await popup.request.get(pdf_url)

        destination_dir = Path(directory)
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination_path = destination_dir / f"bulletin_{departure_airfield}_{arrival_airfield}.pdf"

        destination_path.write_bytes(await response.body())

        await popup.close()
        await context.close()
        return str(destination_path)

