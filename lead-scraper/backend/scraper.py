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
                "--lang=pt-BR",
            ],
        )

        context = await browser.new_context(
            user_agent=USER_AGENT,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1280, "height": 900},
            extra_http_headers={"Accept-Language": "pt-BR,pt;q=0.9"},
        )

        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined })"
        )

        page = await context.new_page()

        try:
            # Usar URL direta de busca do Google Maps
            query = f"{nicho} em {localizacao}"
            encoded = query.replace(" ", "+")
            url = f"https://www.google.com/maps/search/{encoded}/?hl=pt-BR"

            session["status"] = "Abrindo Google Maps..."
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await _delay(2.0, 3.0)

            # --- Tratar tela de consentimento de cookies (muito comum em VPS/Docker) ---
            session["status"] = "Verificando consentimento..."
            await _aceitar_consentimento(page)

            # --- Aguardar os resultados aparecerem ---
            session["status"] = "Aguardando resultados do Google Maps..."
            feed_encontrado = await _aguardar_feed(page)

            if not feed_encontrado:
                # Tentar URL alternativa se o feed não aparecer
                session["status"] = "Tentando URL alternativa..."
                url2 = f"https://maps.google.com/maps?q={encoded}&hl=pt-BR"
                await page.goto(url2, wait_until="domcontentloaded", timeout=30000)
                await _delay(2.0, 3.0)
                await _aceitar_consentimento(page)
                feed_encontrado = await _aguardar_feed(page)

            if not feed_encontrado:
                session["status"] = "Feed de resultados não encontrado. O Google pode estar bloqueando ou não há resultados para essa busca."
                return resultados

            # --- Coletar resultados ---
            resultados = await _collect_results(page, max_resultados, session)

        except Exception as exc:
            session["status"] = f"Erro no scraping: {str(exc)[:120]}"

        finally:
            await browser.close()

    return resultados


async def _aceitar_consentimento(page) -> bool:
    """
    Tenta aceitar/fechar telas de consentimento de cookies do Google.
    Retorna True se encontrou e clicou em algo.
    """
    seletores_aceitar = [
        # Botão "Aceitar tudo" em português
        'button[aria-label*="Aceitar tudo"]',
        'button[aria-label*="Accept all"]',
        # Formulário de consentimento do Google
        'form[action*="consent"] button',
        # Botões com texto "Aceitar"
        'button:has-text("Aceitar tudo")',
        'button:has-text("Accept all")',
        'button:has-text("Aceitar")',
        'button:has-text("I agree")',
        # ID específico do botão de consentimento
        '#L2AGLb',
        'button.tHlp8d',
    ]

    for sel in seletores_aceitar:
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
    """Aguarda o feed de resultados aparecer. Retorna True se encontrou."""
    try:
        await page.wait_for_selector('div[role="feed"]', timeout=timeout)
        return True
    except PlaywrightTimeout:
        return False


def _chave_unica(dados: dict) -> str:
    """
    Gera uma chave de identidade única baseada nos dados extraídos.
    Usa nome + telefone como chave primária.
    Fallback: nome + endereço. Último recurso: só o nome.
    Tudo normalizado (minúsculas, sem espaços extras, só alfanumérico).
    """
    def _norm(s: str) -> str:
        if not s:
            return ""
        # Minúsculas, remove tudo que não é letra/número/espaço, colapsa espaços
        s = s.lower().strip()
        s = re.sub(r"[^\w\s]", "", s)
        s = re.sub(r"\s+", " ", s)
        return s

    nome = _norm(dados.get("nome") or "")
    telefone = re.sub(r"\D", "", dados.get("telefone") or "")  # só dígitos
    endereco = _norm(dados.get("endereco") or "")

    if nome and telefone:
        return f"{nome}|tel:{telefone}"
    if nome and endereco:
        return f"{nome}|end:{endereco[:40]}"
    return f"nome:{nome}"


async def _collect_results(page, max_resultados: int, session: dict) -> list[dict]:
    resultados = []
    # Dois níveis de deduplicação:
    # 1. cards_vistos → evita re-clicar no mesmo card durante o scroll
    # 2. chaves_extraidas → evita adicionar o mesmo negócio mesmo que venha de cards diferentes
    cards_vistos: set = set()
    chaves_extraidas: set = set()
    tentativas_sem_novos = 0

    while len(resultados) < max_resultados and tentativas_sem_novos < 8:
        # Tentar seletores de card em ordem de prioridade
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

                # Ignorar cards vazios ou separadores
                if len(card_text) < 3:
                    continue

                # Nível 1: evitar re-clicar no mesmo card
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

                # Nível 2: evitar duplicata baseada nos dados reais extraídos
                chave = _chave_unica(dados)
                if chave in chaves_extraidas:
                    continue  # mesmo negócio, pular silenciosamente
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

        # Scroll no feed para carregar mais
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

    # Aguardar painel de detalhes
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
        el = await page.query_selector('button[aria-label*="avalia"] span, [aria-label*="reviews"]')
        if el:
            label = await el.get_attribute("aria-label") or ""
            text = await el.inner_text()
            nums = re.findall(r"[\d]+", (label + text).replace(".", "").replace(",", ""))
            if nums:
                dados["num_avaliacoes"] = nums[0]

        # Endereço
        for sel in [
            'button[data-item-id*="address"] .Io6YTe',
            '[aria-label*="Endereço"] .Io6YTe',
            '[data-item-id*="address"] .Io6YTe',
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
            '[aria-label*="phone"] .Io6YTe',
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
