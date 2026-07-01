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
    """
    Função principal do scraper.
    Abre o Google Maps, busca o nicho na localização e coleta dados de cada empresa.
    Retorna lista de dicts com os dados extraídos.
    """
    resultados = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        context = await browser.new_context(
            user_agent=USER_AGENT,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1280, "height": 900},
        )

        # Ocultar que é Playwright (evitar detecção como bot)
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined })"
        )

        page = await context.new_page()

        try:
            query = f"{nicho} em {localizacao}"
            url = f"https://www.google.com.br/maps/search/{query.replace(' ', '+')}"

            session["status"] = "Abrindo Google Maps..."
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await _delay(2.0, 3.5)

            # Verificar e tentar resolver CAPTCHA se presente
            await _handle_captcha(page)

            # Aceitar cookies se necessário
            try:
                accept_btn = await page.query_selector(
                    'button[aria-label*="Aceitar"], button[aria-label*="Accept"], form[action*="consent"] button'
                )
                if accept_btn:
                    await accept_btn.click()
                    await _delay(1.0, 2.0)
            except Exception:
                pass

            # Aguardar o feed de resultados aparecer
            session["status"] = f"Aguardando resultados do Google Maps..."
            try:
                await page.wait_for_selector('div[role="feed"]', timeout=20000)
            except PlaywrightTimeout:
                session["status"] = "Timeout aguardando resultados. Verifique o nicho/localização."
                return resultados

            # Coletar resultados fazendo scroll no painel lateral
            resultados = await _collect_results(page, max_resultados, session)

        except Exception as exc:
            session["status"] = f"Erro no scraping: {str(exc)[:100]}"

        finally:
            await browser.close()

    return resultados


async def _collect_results(page, max_resultados: int, session: dict) -> list[dict]:
    """
    Itera sobre os cards do feed, clica em cada um para abrir o painel de detalhes
    e extrai os dados. Continua fazendo scroll até atingir max_resultados.
    """
    resultados = []
    ids_processados = set()
    tentativas_sem_novos = 0
    scroll_count = 0

    while len(resultados) < max_resultados and tentativas_sem_novos < 8:
        # Selecionar cards individuais no feed
        cards = await page.query_selector_all('div[role="feed"] > div[jsaction*="mouseover"]')

        if not cards:
            # Tentar seletor alternativo
            cards = await page.query_selector_all('div[role="feed"] > div[tabindex]')

        novos_nesta_rodada = 0

        for card in cards:
            if len(resultados) >= max_resultados:
                break

            try:
                # Usar o texto do card como ID único para evitar duplicatas
                card_text = await card.inner_text()
                card_id = hash(card_text[:80].strip())

                if card_id in ids_processados or not card_text.strip():
                    continue

                # Rolar o card para a view antes de clicar
                await card.scroll_into_view_if_needed()
                await _delay(0.3, 0.7)

                # Clicar no card para abrir o painel de detalhes
                await card.click()
                await _delay(1.2, 2.0)

                # Extrair dados do painel de detalhes lateral
                dados = await _extract_detail_panel(page)

                if dados and dados.get("nome"):
                    resultados.append(dados)
                    ids_processados.add(card_id)
                    novos_nesta_rodada += 1

                    # Atualizar sessão em tempo real
                    session["processados"] = len(resultados)
                    session["total"] = max(max_resultados, len(resultados))
                    session["status"] = f"Coletando resultados... ({len(resultados)}/{max_resultados})"
                    session["resultados"] = list(resultados)

            except Exception:
                # Silenciosamente pular cards com problema
                continue

        if novos_nesta_rodada == 0:
            tentativas_sem_novos += 1
        else:
            tentativas_sem_novos = 0

        # Scroll no painel lateral para carregar mais resultados
        try:
            feed = await page.query_selector('div[role="feed"]')
            if feed:
                await feed.evaluate("el => { el.scrollTop += 800; }")
                scroll_count += 1
                await _delay(1.5, 2.5)

                # Verificar se chegou ao fim do feed
                end_marker = await page.query_selector('div[role="feed"] span[class*="HlvSq"]')
                if end_marker:
                    break
        except Exception:
            break

    return resultados


async def _extract_detail_panel(page) -> dict | None:
    """
    Extrai dados do painel lateral de detalhes de uma empresa no Google Maps.
    Usa múltiplos seletores como fallback para resistir a mudanças no DOM do Google.
    """
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

    # Aguardar o painel de detalhes carregar
    try:
        await page.wait_for_selector(
            '.DUwDvf, .lMbq3e h1, [class*="fontHeadlineLarge"]', timeout=6000
        )
    except PlaywrightTimeout:
        return None

    await _delay(0.3, 0.6)

    try:
        # Nome da empresa — vários seletores possíveis
        for sel in ['.DUwDvf', '.lMbq3e h1', 'h1.fontHeadlineLarge', '[data-attrid="title"]']:
            el = await page.query_selector(sel)
            if el:
                dados["nome"] = (await el.inner_text()).strip()
                break

        # Categoria do negócio
        for sel in ['.DkEaL', '.skqShb', '[jsaction*="category"]', 'button[jsaction*="category"]']:
            el = await page.query_selector(sel)
            if el:
                text = (await el.inner_text()).strip()
                if text and len(text) < 80:
                    dados["categoria"] = text
                    break

        # Avaliação média (ex: "4.7")
        for sel in [
            '.F7nice > span > span[aria-hidden="true"]',
            '.ceNzKf',
            '[aria-label*="estrela"] span',
        ]:
            el = await page.query_selector(sel)
            if el:
                text = (await el.inner_text()).strip()
                if re.match(r"^\d[\.,]\d$", text):
                    dados["avaliacao"] = text.replace(",", ".")
                    break

        # Número de avaliações
        for sel in [
            'button[aria-label*="avalia"] span.F7nice',
            '[jsaction*="reviews"]',
            'span[aria-label*="avaliações"]',
            'span[aria-label*="reviews"]',
        ]:
            el = await page.query_selector(sel)
            if el:
                label = await el.get_attribute("aria-label") or ""
                text = await el.inner_text()
                nums = re.findall(r"[\d\.]+", (label + text).replace(".", "").replace(",", ""))
                if nums:
                    dados["num_avaliacoes"] = nums[0]
                    break

        # Endereço — priorizar o data-item-id
        for sel in [
            'button[data-item-id*="address"] .Io6YTe',
            '[aria-label*="Endereço"] .Io6YTe',
            'button[data-tooltip*="Copiar endereço"] .Io6YTe',
            '[data-item-id*="address"]',
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
            '[aria-label*="Telefone"] .Io6YTe',
            'button[data-tooltip*="Copiar número"] .Io6YTe',
            '[data-item-id*="phone"]',
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
            '[aria-label*="Site"] a',
            'a[aria-label*="Site:"]',
            'a[data-tooltip*="Abrir site"]',
        ]:
            el = await page.query_selector(sel)
            if el:
                href = await el.get_attribute("href") or ""
                text = (await el.inner_text()).strip()
                # O Google às vezes usa redirect — pegar o domínio real
                url_match = re.search(r"https?://(?:www\.)?([^/&\s]+)", href)
                if url_match:
                    dados["site"] = href
                elif text and "." in text:
                    dados["site"] = f"https://{text}" if not text.startswith("http") else text
                break

    except Exception:
        pass

    return dados if dados.get("nome") else None


async def _handle_captcha(page, max_tentativas: int = 3):
    """Detecta CAPTCHA e aguarda / recarrega até resolver (máx 3 tentativas)."""
    for _ in range(max_tentativas):
        captcha = await page.query_selector(
            'form#captcha-form, iframe[src*="recaptcha"], #recaptcha'
        )
        if not captcha:
            return
        await asyncio.sleep(10)
        await page.reload(wait_until="domcontentloaded")
        await asyncio.sleep(3)


async def _delay(min_s: float = 1.5, max_s: float = 3.5):
    """Delay aleatório para simular comportamento humano."""
    await asyncio.sleep(random.uniform(min_s, max_s))
