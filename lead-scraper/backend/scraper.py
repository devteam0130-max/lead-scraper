import asyncio
import random
import re
import unicodedata
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# -------------------------------------------------------
# Mapeamento nome completo → sigla de estado/região
# Permite que "California" bata com endereços que têm "CA"
# -------------------------------------------------------
_NOME_PARA_SIGLA = {
    # Estados USA
    "california": "ca", "texas": "tx", "new york": "ny", "florida": "fl",
    "illinois": "il", "georgia": "ga", "ohio": "oh", "michigan": "mi",
    "washington": "wa", "arizona": "az", "nevada": "nv", "oregon": "or",
    "colorado": "co", "massachusetts": "ma", "virginia": "va",
    "north carolina": "nc", "south carolina": "sc", "tennessee": "tn",
    "pennsylvania": "pa", "new jersey": "nj", "maryland": "md",
    "minnesota": "mn", "wisconsin": "wi", "missouri": "mo",
    # Estados Brasil
    "bahia": "ba", "sao paulo": "sp", "rio de janeiro": "rj",
    "minas gerais": "mg", "parana": "pr", "rio grande do sul": "rs",
    "santa catarina": "sc", "pernambuco": "pe", "ceara": "ce",
    "goias": "go", "para": "pa", "amazonas": "am", "maranhao": "ma",
    "espirito santo": "es", "mato grosso": "mt", "mato grosso do sul": "ms",
    "rio grande do norte": "rn", "alagoas": "al", "sergipe": "se",
    "paraiba": "pb", "piaui": "pi", "tocantins": "to", "rondonia": "ro",
    "amapa": "ap", "roraima": "rr", "acre": "ac", "distrito federal": "df",
    # Países
    "brasil": "br", "brazil": "br", "united states": "us",
    "united kingdom": "uk", "great britain": "gb",
}


def _norm_geo(s: str) -> str:
    """Remove acentos e converte para minúsculas."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def _termos_localizacao(localizacao: str) -> list[str]:
    """
    Extrai termos relevantes da localização, incluindo siglas equivalentes.
    Ex: "California" → ["california", "ca"]
    Ex: "São Paulo, SP" → ["sao", "paulo", "sp"]
    """
    IGNORAR = {"de", "do", "da", "dos", "das", "em", "no", "na", "e", "o", "a",
               "in", "at", "the", "of", "and", "los", "las", "el", "la"}
    termos = set()
    loc_norm = _norm_geo(localizacao)

    for t in localizacao.replace(",", " ").split():
        t_norm = _norm_geo(t.strip().rstrip(".,"))
        if len(t_norm) >= 2 and t_norm not in IGNORAR:
            termos.add(t_norm)

    # Adicionar siglas equivalentes a nomes completos
    for nome, sigla in _NOME_PARA_SIGLA.items():
        if nome in loc_norm:
            termos.add(sigla)
        if sigla in loc_norm.split():
            termos.add(nome)

    return list(termos)


def _termo_no_endereco(termo: str, endereco_norm: str) -> bool:
    """
    Verifica se um termo aparece no endereço de forma correta.
    Termos curtos (siglas como "ca", "sp", "ny"): word boundary — não bate
    em substrings de outras palavras (ex: "ca" NÃO bate em "angelica").
    Termos longos (ex: "california", "salvador"): substring simples.
    """
    if len(termo) <= 3:
        padrao = r"(?<![a-z])" + re.escape(termo) + r"(?![a-z])"
        return bool(re.search(padrao, endereco_norm))
    return termo in endereco_norm


def _cep_brasileiro(endereco: str) -> bool:
    """
    Detecta CEP brasileiro: XXXXX-XXX (3 dígitos após o hífen).
    ZIP americano zip+4 tem 4 dígitos — não é confundido.
    """
    return bool(re.search(r'\b\d{5}-\d{3}\b', endereco))


def _buscando_brasil(localizacao: str) -> bool:
    """Retorna True se a localização buscada é claramente no Brasil."""
    loc_norm = _norm_geo(localizacao)
    termos_br = ["brasil", "brazil", "sao paulo", "salvador", "rio de janeiro",
                 "belo horizonte", "fortaleza", "recife", "curitiba", "manaus",
                 "porto alegre", "brasilia", "goiania", "belem", "florianopolis"]
    return any(t in loc_norm for t in termos_br)


def _endereco_na_localizacao(endereco: str, localizacao: str) -> bool:
    """
    Filtro geográfico em duas etapas:

    1. Filtro negativo por CEP brasileiro (XXXXX-XXX):
       Rejeita enderecos com CEP brasileiro quando a busca nao e no Brasil.
       Resolve bairros SP com nomes como "Vila California", "Chacara California".

    2. Filtro positivo por termos:
       Verifica se o endereco contem termos da localizacao buscada.
       Usa word boundary para siglas curtas (<=3 chars).

    Sem endereco -> aceitar (dados insuficientes para rejeitar).
    """
    if not endereco or not endereco.strip() or not localizacao:
        return True

    # Etapa 1: rejeitar CEP brasileiro em busca nao-brasileira
    if _cep_brasileiro(endereco) and not _buscando_brasil(localizacao):
        return False

    endereco_norm = _norm_geo(endereco)
    termos = _termos_localizacao(localizacao)

    if not termos:
        return True

    return any(_termo_no_endereco(termo, endereco_norm) for termo in termos)


def _chave_unica(dados: dict) -> str:
    """Gera chave de identidade única para deduplicação baseada nos dados extraídos."""
    def _norm(s: str) -> str:
        if not s:
            return ""
        s = _norm_geo(s)
        s = re.sub(r"[^\w\s]", "", s)
        s = re.sub(r"\s+", " ", s)
        return s.strip()

    nome = _norm(dados.get("nome") or "")
    telefone = re.sub(r"\D", "", dados.get("telefone") or "")
    endereco = _norm(dados.get("endereco") or "")

    if nome and telefone:
        return f"{nome}|tel:{telefone}"
    if nome and endereco:
        return f"{nome}|end:{endereco[:40]}"
    return f"nome:{nome}"


async def scrape_google_maps(
    nicho: str, localizacao: str, max_resultados: int, session: dict
) -> list[dict]:
    """
    Função principal do scraper.
    Abre o Google Maps, busca o nicho na localização e coleta dados de cada empresa.
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
                "--disable-web-security",
            ],
        )

        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 900},
        )

        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined })"
        )

        page = await context.new_page()

        try:
            # Query sem preposição para funcionar em qualquer idioma
            query = f"{nicho} {localizacao}"
            encoded = query.replace(" ", "+")
            url = f"https://www.google.com/maps/search/{encoded}/"

            session["status"] = "Abrindo Google Maps..."
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Reduzido: 1.0s é suficiente para a página estabilizar
            await asyncio.sleep(1.0)

            session["status"] = "Verificando consentimento..."
            await _aceitar_consentimento(page)

            session["status"] = "Aguardando resultados..."
            feed_encontrado = await _aguardar_feed(page)

            if not feed_encontrado:
                session["status"] = "Tentando URL alternativa..."
                url2 = f"https://maps.google.com/maps?q={encoded}"
                await page.goto(url2, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(1.0)
                await _aceitar_consentimento(page)
                feed_encontrado = await _aguardar_feed(page)

            if not feed_encontrado:
                session["status"] = "Feed de resultados não encontrado. Verifique o nicho/localização."
                return resultados

            resultados = await _collect_results(page, max_resultados, session, localizacao)

        except Exception as exc:
            session["status"] = f"Erro no scraping: {str(exc)[:120]}"

        finally:
            await browser.close()

    return resultados


async def _aceitar_consentimento(page) -> bool:
    """Aceita telas de consentimento de cookies do Google em múltiplos idiomas."""
    seletores = [
        '#L2AGLb',
        'button.tHlp8d',
        'form[action*="consent"] button',
        'button:has-text("Aceitar tudo")',
        'button:has-text("Aceitar")',
        'button[aria-label*="Aceitar tudo"]',
        'button:has-text("Accept all")',
        'button:has-text("I agree")',
        'button[aria-label*="Accept all"]',
        'button:has-text("Aceptar todo")',
        'button:has-text("Tout accepter")',
        'button:has-text("Alle akzeptieren")',
        'button:has-text("Accetta tutto")',
    ]
    for sel in seletores:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                await asyncio.sleep(1.0)
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


async def _collect_results(
    page, max_resultados: int, session: dict, localizacao: str
) -> list[dict]:
    """
    Itera sobre os cards do feed e extrai dados de cada empresa.
    Melhorias v2:
    - Usa wait_for_selector após clique em vez de sleep fixo (2x mais rápido)
    - Verifica WhatsApp diretamente no perfil do Google Maps (evita visitar sites)
    - Filtro geográfico simplificado
    """
    resultados = []
    cards_vistos: set = set()
    chaves_extraidas: set = set()
    tentativas_sem_novos = 0
    filtrados_por_local = 0

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
                # Pequeno delay antes do clique para estabilizar scroll
                await asyncio.sleep(random.uniform(0.2, 0.4))

                # Capturar nome atual do painel ANTES de clicar
                # para detectar quando o painel muda (evita data mixing)
                nome_atual = ""
                try:
                    el_atual = await page.query_selector('.DUwDvf, .lMbq3e h1')
                    if el_atual:
                        nome_atual = (await el_atual.inner_text()).strip()
                except Exception:
                    pass

                await card.click()

                # Aguardar o painel carregar e MUDAR em relação ao card anterior
                # Isso evita extrair dados do painel ainda carregando do card anterior
                painel_ok = False
                for _ in range(12):  # até ~2.4s de espera
                    await asyncio.sleep(0.2)
                    try:
                        el = await page.query_selector('.DUwDvf, .lMbq3e h1')
                        if el:
                            nome_novo = (await el.inner_text()).strip()
                            if nome_novo and nome_novo != nome_atual:
                                painel_ok = True
                                break
                    except Exception:
                        pass

                if not painel_ok:
                    continue  # painel não carregou ou não mudou

                dados = await _extract_detail_panel(page)

                if not dados or not dados.get("nome"):
                    continue

                # Deduplicação por dados reais (não por texto do card)
                chave = _chave_unica(dados)
                if chave in chaves_extraidas:
                    continue
                chaves_extraidas.add(chave)

                # Filtro geográfico
                if not _endereco_na_localizacao(dados.get("endereco") or "", localizacao):
                    filtrados_por_local += 1
                    session["status"] = (
                        f"Coletando resultados... ({len(resultados)}/{max_resultados}) "
                        f"[{filtrados_por_local} fora da área ignorados]"
                    )
                    continue

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

        # Scroll no feed para carregar mais resultados
        try:
            feed = await page.query_selector('div[role="feed"]')
            if feed:
                await feed.evaluate("el => { el.scrollTop += 800; }")
                # Reduzido: 1.0s é suficiente (era 1.5-2.5s)
                await asyncio.sleep(random.uniform(0.8, 1.2))
        except Exception:
            break

    return resultados


async def _extract_detail_panel(page) -> dict | None:
    """
    Extrai dados do painel lateral de detalhes de uma empresa.
    Melhorias v2:
    - Tenta extrair WhatsApp diretamente do perfil GMaps (evita visita ao site)
    - Seletores language-agnostic via data-item-id (funciona em qualquer país)
    """
    dados = {
        "nome": None,
        "avaliacao": None,
        "num_avaliacoes": None,
        "endereco": None,
        "telefone": None,
        "site": None,
        "categoria": None,
        "whatsapp": None,  # preenchido aqui se disponível no GMaps
    }

    # Painel já foi aguardado em _collect_results, só um delay mínimo
    await asyncio.sleep(random.uniform(0.1, 0.3))

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

        # Endereço — data-item-id é language-agnostic
        for sel in [
            'button[data-item-id*="address"] .Io6YTe',
            '[data-item-id*="address"] .Io6YTe',
            '[aria-label*="Endereço"] .Io6YTe',
            '[aria-label*="Address"] .Io6YTe',
            '[aria-label*="Dirección"] .Io6YTe',
            '[aria-label*="Adresse"] .Io6YTe',
            'button[data-item-id*="address"]',
        ]:
            el = await page.query_selector(sel)
            if el:
                text = (await el.inner_text()).strip()
                if text and len(text) > 5:
                    dados["endereco"] = text
                    break

        # Telefone — data-item-id é language-agnostic
        for sel in [
            'button[data-item-id*="phone"] .Io6YTe',
            '[data-item-id*="phone"] .Io6YTe',
            '[aria-label*="Telefone"] .Io6YTe',
            '[aria-label*="Phone"] .Io6YTe',
            '[aria-label*="Teléfono"] .Io6YTe',
            '[aria-label*="Téléphone"] .Io6YTe',
            '[aria-label*="Telefon"] .Io6YTe',
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
            '[aria-label*="Site"] a',
            '[aria-label*="Website"] a',
            '[aria-label*="Sitio web"] a',
            '[aria-label*="Site web"] a',
            '[aria-label*="Webseite"] a',
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

        # MELHORIA: tentar extrair WhatsApp do próprio perfil do Google Maps
        # Muitas empresas têm o botão de WhatsApp diretamente no GMaps
        # Isso evita a necessidade de visitar o site externo
        wpp_gmaps = await _extract_whatsapp_from_gmaps(page)
        if wpp_gmaps:
            dados["whatsapp"] = wpp_gmaps

    except Exception:
        pass

    return dados if dados.get("nome") else None


async def _extract_whatsapp_from_gmaps(page) -> str | None:
    """
    Verifica se a empresa tem WhatsApp listado diretamente no Google Maps.
    Quando disponível, evita a necessidade de visitar o site externo.
    """
    # Seletores para o botão/link de WhatsApp no perfil do GMaps
    seletores_wpp = [
        'a[data-item-id*="whatsapp"]',
        '[aria-label*="WhatsApp"] a',
        '[aria-label*="Whatsapp"] a',
        'a[href*="wa.me"]',
        'a[href*="api.whatsapp"]',
        'a[href*="whatsapp.com/send"]',
        '[data-item-id*="whatsapp"] .Io6YTe',
    ]

    for sel in seletores_wpp:
        try:
            el = await page.query_selector(sel)
            if not el:
                continue

            href = await el.get_attribute("href") or ""
            text = (await el.inner_text()).strip()

            # Extrair número de wa.me/NUMERO
            match = re.search(r"wa\.me/(\+?[\d]{7,15})", href)
            if match:
                return re.sub(r"\D", "", match.group(1))

            # Extrair número de api.whatsapp.com/send?phone=NUMERO
            match = re.search(r"phone=(\+?[\d]{7,15})", href)
            if match:
                return re.sub(r"\D", "", match.group(1))

            # Número no texto do botão (ex: "+55 11 99999-9999")
            if text and re.search(r"\d{7,}", text):
                nums = re.sub(r"\D", "", text)
                if len(nums) >= 7:
                    return nums

        except Exception:
            continue

    return None
