import asyncio
import random
import re
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


async def scrape_google_maps(
    nicho: str, localizacao: str, max_resultados: int, session: dict
) -> list[dict]:
    resultados = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
            ],
        )

        context = await browser.new_context(
            user_agent=USER_AGENT,
            # Sem locale fixo — deixa o Google Maps usar o idioma da região buscada
            viewport={"width": 1280, "height": 900},
        )

        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined })"
        )

        page = await context.new_page()

        try:
            query = f"{nicho} em {localizacao}"
            encoded = query.replace(" ", "+")

            # Sem hl=pt-BR — deixa o Google servir no idioma local da busca
            # Isso garante que aria-labels estejam no idioma correto da região
            url = f"https://www.google.com/maps/search/{encoded}/"

            session["status"] = "Abrindo Google Maps..."
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await _delay(2.0, 3.0)

            # Trata consentimento de cookies (múltiplos idiomas)
            session["status"] = "Verificando consentimento..."
            await _aceitar_consentimento(page)

            # Aguarda o feed de resultados
            session["status"] = "Aguardando resultados do Google Maps..."
            feed_encontrado = await _aguardar_feed(page)

            if not feed_encontrado:
                session["status"] = "Tentando URL alternativa..."
                url2 = f"https://maps.google.com/maps?q={encoded}"
                await page.goto(url2, wait_until="domcontentloaded", timeout=30000)
                await _delay(2.0, 3.0)
                await _aceitar_consentimento(page)
                feed_encontrado = await _aguardar_feed(page)

            if not feed_encontrado:
                session["status"] = "Feed de resultados não encontrado. Verifique o nicho/localização."
                return resultados

            resultados = await _collect_results(page, max_resultados, session)

        except Exception as exc:
            session["status"] = f"Erro no scraping: {str(exc)[:120]}"

        finally:
            await browser.close()

    return resultados


async def _aceitar_consentimento(page) -> bool:
    """
    Aceita telas de consentimento de cookies do Google em vários idiomas.
    """
    seletores = [
        '#L2AGLb',                               # ID fixo do botão do Google
        'button.tHlp8d',
        'form[action*="consent"] button',
        # Português
        'button:has-text("Aceitar tudo")',
        'button:has-text("Aceitar")',
        'button[aria-label*="Aceitar tudo"]',
        # Inglês
        'button:has-text("Accept all")',
        'button:has-text("I agree")',
        'button[aria-label*="Accept all"]',
        # Espanhol
        'button:has-text("Aceptar todo")',
        'button:has-text("Aceptar")',
        # Francês
        'button:has-text("Tout accepter")',
        'button:has-text("Accepter")',
        # Alemão
        'button:has-text("Alle akzeptieren")',
        # Italiano
        'button:has-text("Accetta tutto")',
    ]

    for sel in seletores:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                await _delay(1.5, 2.5)
                return True
        except Exception:
            continue

    return False


async def _aguardar_feed(page, timeout: int = 20000) -> bool:
    try:
        await page.wait_for_selector('div[role="feed"]', timeout=timeout)
        return True
    except PlaywrightTimeout:
        return False


def _chave_unica(dados: dict) -> str:
    """Gera chave de identidade única para deduplicação baseada nos dados extraídos."""
    def _norm(s: str) -> str:
        if not s:
            return ""
        s = s.lower().strip()
        s = re.sub(r"[^\w\s]", "", s)
        s = re.sub(r"\s+", " ", s)
        return s

    nome = _norm(dados.get("nome") or "")
    telefone = re.sub(r"\D", "", dados.get("telefone") or "")
    endereco = _norm(dados.get("endereco") or "")

    if nome and telefone:
        return f"{nome}|tel:{telefone}"
    if nome and endereco:
        return f"{nome}|end:{endereco[:40]}"
    return f"nome:{nome}"


async def _collect_results(page, max_resultados: int, session: dict) -> list[dict]:
    resultados = []
    cards_vistos: set = set()
    chaves_extraidas: set = set()
    tentativas_sem_novos = 0

    while len(resultados) < max_resultados and tentativas_sem_novos < 8:
        cards = await page.query_selector_all('div[role="feed"] > div[jsaction*="mouseover"]')
        if not cards:
            cards = await page.query_selector_all('div[role="feed"] > div[tabindex]')
        if not cards:
            cards = await page.query_selector_all('div[role="feed"] > div')

        novos_nesta_rodada = 0

        for card in cards:
            if len(resultados) >= max_resultados:
                break

            try:
                card_text = await card.inner_text()
                card_text = card_text.strip()

                if len(card_text) < 3:
                    continue

                card_id = hash(card_text[:120])
                if card_id in cards_vistos:
                    continue
                cards_vistos.add(card_id)

                await card.scroll_into_view_if_needed()
                await _delay(0.3, 0.6)

                await card.click()
                await _delay(1.2, 2.0)

                dados = await _extract_detail_panel(page)

                if not dados or not dados.get("nome"):
                    continue

                chave = _chave_unica(dados)
                if chave in chaves_extraidas:
                    continue
                chaves_extraidas.add(chave)

                resultados.append(dados)
                novos_nesta_rodada += 1

                session["processados"] = len(resultados)
                session["total"] = max(max_resultados, len(resultados))
                session["status"] = f"Coletando resultados... ({len(resultados)}/{max_resultados})"
                session["resultados"] = list(resultados)

            except Exception:
                continue

        if novos_nesta_rodada == 0:
            tentativas_sem_novos += 1
        else:
            tentativas_sem_novos = 0

        try:
            feed = await page.query_selector('div[role="feed"]')
            if feed:
                await feed.evaluate("el => { el.scrollTop += 800; }")
                await _delay(1.5, 2.5)
        except Exception:
            break

    return resultados


async def _extract_detail_panel(page) -> dict | None:
    dados = {
        "nome": None,
        "avaliacao": None,
        "num_avaliacoes": None,
        "endereco": None,
        "telefone": None,
        "site": None,
        "categoria": None,
        "whatsapp": None,
    }

    try:
        await page.wait_for_selector(
            '.DUwDvf, .lMbq3e h1, [class*="fontHeadlineLarge"]', timeout=6000
        )
    except PlaywrightTimeout:
        return None

    await _delay(0.2, 0.5)

    try:
        # Nome
        for sel in ['.DUwDvf', '.lMbq3e h1', 'h1[class*="fontHeadline"]']:
            el = await page.query_selector(sel)
            if el:
                dados["nome"] = (await el.inner_text()).strip()
                break

        # Categoria
        for sel in ['.DkEaL', '.skqShb']:
            el = await page.query_selector(sel)
            if el:
                text = (await el.inner_text()).strip()
                if text and len(text) < 80:
                    dados["categoria"] = text
                    break

        # Avaliação
        for sel in ['.F7nice > span > span[aria-hidden="true"]', '.ceNzKf']:
            el = await page.query_selector(sel)
            if el:
                text = (await el.inner_text()).strip()
                if re.match(r"^\d[\.,]\d$", text):
                    dados["avaliacao"] = text.replace(",", ".")
                    break

        # Número de avaliações
        el = await page.query_selector(
            'button[aria-label*="avalia"] span, button[aria-label*="review"] span, '
            'button[aria-label*="Review"] span'
        )
        if el:
            label = await el.get_attribute("aria-label") or ""
            text = await el.inner_text()
            nums = re.findall(r"\d+", (label + text).replace(".", "").replace(",", ""))
            if nums:
                dados["num_avaliacoes"] = nums[0]

        # -------------------------------------------------------
        # Endereço, Telefone e Site usam data-item-id que é
        # INDEPENDENTE DE IDIOMA — funciona em qualquer país.
        # Aria-labels são mantidos como fallback multilíngue.
        # -------------------------------------------------------

        # Endereço
        for sel in [
            'button[data-item-id*="address"] .Io6YTe',
            '[data-item-id*="address"] .Io6YTe',
            # Fallbacks multilíngues
            '[aria-label*="Endereço"] .Io6YTe',   # PT
            '[aria-label*="Address"] .Io6YTe',     # EN
            '[aria-label*="Dirección"] .Io6YTe',   # ES
            '[aria-label*="Adresse"] .Io6YTe',     # FR/DE
            'button[data-item-id*="address"]',
        ]:
            el = await page.query_selector(sel)
            if el:
                text = (await el.inner_text()).strip()
                if text and len(text) > 5:
                    dados["endereco"] = text
                    break

        # Telefone
        for sel in [
            'button[data-item-id*="phone"] .Io6YTe',
            '[data-item-id*="phone"] .Io6YTe',
            # Fallbacks multilíngues
            '[aria-label*="Telefone"] .Io6YTe',    # PT
            '[aria-label*="Phone"] .Io6YTe',        # EN
            '[aria-label*="Teléfono"] .Io6YTe',    # ES
            '[aria-label*="Téléphone"] .Io6YTe',   # FR
            '[aria-label*="Telefon"] .Io6YTe',     # DE
            'button[data-item-id*="phone"]',
        ]:
            el = await page.query_selector(sel)
            if el:
                text = (await el.inner_text()).strip()
                if text and re.search(r"\d", text):
                    dados["telefone"] = text
                    break

        # Site
        for sel in [
            'a[data-item-id*="authority"]',
            # Fallbacks multilíngues
            '[aria-label*="Site"] a',               # PT
            '[aria-label*="Website"] a',             # EN
            '[aria-label*="Sitio web"] a',           # ES
            '[aria-label*="Site web"] a',            # FR
            '[aria-label*="Webseite"] a',            # DE
            'a[aria-label*="Site:"]',
            'a[aria-label*="Website:"]',
        ]:
            el = await page.query_selector(sel)
            if el:
                href = await el.get_attribute("href") or ""
                text = (await el.inner_text()).strip()
                if href.startswith("http"):
                    dados["site"] = href
                elif text and "." in text:
                    dados["site"] = f"https://{text}"
                break

    except Exception:
        pass

    return dados if dados.get("nome") else None


async def _delay(min_s: float = 1.5, max_s: float = 3.5):
    await asyncio.sleep(random.uniform(min_s, max_s))
