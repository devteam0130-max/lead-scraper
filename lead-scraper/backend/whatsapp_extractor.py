import asyncio
import re
import httpx

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Padrões para encontrar WhatsApp no HTML de sites
PATTERNS = [
    # Link direto wa.me com número
    (re.compile(r"wa\.me/(\+?[\d]{10,15})"), "wame"),
    # API WhatsApp com phone=
    (re.compile(r"api\.whatsapp\.com/send\?phone=(\+?[\d]{10,15})"), "api"),
    # Atributo data-* ou href com número em formato wa.me
    (re.compile(r'["\']https?://wa\.me/(\+?[\d]{10,15})["\']'), "wame_href"),
    # wa.link (registrar o link completo)
    (re.compile(r"(https?://wa\.link/[A-Za-z0-9]+)"), "wa_link"),
    # Número brasileiro formatado próximo a "whatsapp" (case insensitive)
    (re.compile(r"(?i)whatsapp[^0-9]{0,30}\(?\+?(\d{2})\)?[\s.-]?(\d{4,5})[\s.-]?(\d{4})"), "contexto"),
    # Número brasileiro puro: (11) 99999-9999 ou 11999999999
    (re.compile(r"\+?55[\s-]?\(?\d{2}\)?\s?9\d{4}[-\s]?\d{4}"), "br_raw"),
]

# Prefixo DDI Brasil para normalizar
DDI_BR = "55"


async def extract_whatsapp(url: str) -> str | None:
    """
    Faz GET na URL do site e procura por links/números de WhatsApp no HTML.
    Retorna o número limpo (só dígitos, com DDI 55) ou None.
    """
    if not url or not url.startswith("http"):
        return None

    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=True,
            verify=False,  # Ignorar erros de SSL
            headers={"User-Agent": USER_AGENT},
        ) as client:
            resp = await client.get(url, timeout=10.0)
            html = resp.text

    except Exception:
        return None

    return _parse_whatsapp_from_html(html)


def _parse_whatsapp_from_html(html: str) -> str | None:
    """Aplica os padrões regex no HTML e retorna o primeiro número encontrado."""

    # Padrão 1: wa.me/NUMERO
    for pattern, kind in PATTERNS:
        match = pattern.search(html)
        if not match:
            continue

        if kind == "wa_link":
            # Retornar o link wa.link direto como número (será exibido como link)
            return match.group(1)

        if kind == "contexto":
            # Reconstruir número do grupo de captura de contexto
            ddd, parte1, parte2 = match.group(1), match.group(2), match.group(3)
            numero = f"55{ddd}{parte1}{parte2}"
            return _limpar_numero(numero)

        if kind == "br_raw":
            return _limpar_numero(match.group(0))

        # wame, api, wame_href
        numero_raw = match.group(1)
        return _limpar_numero(numero_raw)

    return None


def _limpar_numero(numero: str) -> str | None:
    """Remove tudo que não é dígito e normaliza para formato 55DDNUMERO."""
    apenas_digitos = re.sub(r"\D", "", numero)

    if not apenas_digitos:
        return None

    # Remover + inicial se vier como +55...
    if apenas_digitos.startswith("55") and len(apenas_digitos) >= 12:
        return apenas_digitos

    # Número brasileiro sem DDI (10 ou 11 dígitos com DDD)
    if len(apenas_digitos) in (10, 11):
        return f"{DDI_BR}{apenas_digitos}"

    # Tem DDI mas não é 55 — retornar assim mesmo
    if len(apenas_digitos) >= 12:
        return apenas_digitos

    return None


async def extract_whatsapp_batch(resultados: list[dict], session: dict) -> None:
    """
    Enriquece os resultados com WhatsApp em paralelo.
    Limita a 5 requisições simultâneas com semáforo.
    Atualiza a sessão com o progresso.
    """
    semaphore = asyncio.Semaphore(5)
    total = len(resultados)
    processados_wpp = 0

    async def process_one(resultado: dict):
        nonlocal processados_wpp

        async with semaphore:
            site = resultado.get("site")
            if site:
                wpp = await extract_whatsapp(site)
                resultado["whatsapp"] = wpp
            else:
                resultado["whatsapp"] = None

            processados_wpp += 1
            session["status"] = f"Extraindo WhatsApp dos sites... ({processados_wpp}/{total})"
            session["resultados"] = list(resultados)

    tasks = [process_one(r) for r in resultados]
    await asyncio.gather(*tasks)
