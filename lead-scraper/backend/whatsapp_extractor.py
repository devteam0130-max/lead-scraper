import asyncio
import re
import httpx

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Padrões para encontrar WhatsApp — funcionam para qualquer país
PATTERNS = [
    # wa.me com número (já tem DDI completo — mais confiável)
    (re.compile(r"wa\.me/(\+?[\d]{7,15})"), "wame"),
    # api.whatsapp.com com phone= (já tem DDI completo)
    (re.compile(r"api\.whatsapp\.com/send[/\?].*?phone=(\+?[\d]{7,15})"), "api"),
    # Atributo href com wa.me
    (re.compile(r'href=["\']https?://wa\.me/(\+?[\d]{7,15})["\']'), "wame_href"),
    # wa.link (link curto do WhatsApp)
    (re.compile(r"(https?://wa\.link/[A-Za-z0-9]+)"), "wa_link"),
    # Número PRÓXIMO à palavra whatsapp/zap/wpp no HTML
    # Captura o número que aparece em até 60 chars depois da palavra-chave
    (re.compile(r"(?i)(?:whatsapp|whats\s*app|whasapp|wpp|zap)[^0-9+]{0,60}(\+[\d\s\-().]{7,20})"), "contexto_intl"),
    # Número brasileiro próximo a whatsapp (fallback regional)
    (re.compile(r"(?i)(?:whatsapp|wpp|zap)[^0-9]{0,30}\(?\+?(\d{2})\)?[\s.-]?(\d{4,5})[\s.-]?(\d{4})"), "contexto_br"),
]


async def extract_whatsapp(url: str) -> str | None:
    """
    Faz GET na URL do site e procura por links/números de WhatsApp no HTML.
    Funciona para qualquer país — não assume DDI do Brasil.
    Retorna o número (com DDI se disponível) ou None.
    """
    if not url or not url.startswith("http"):
        return None

    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=True,
            verify=False,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            resp = await client.get(url, timeout=10.0)
            html = resp.text
    except Exception:
        return None

    return _parse_whatsapp_from_html(html)


def _parse_whatsapp_from_html(html: str) -> str | None:
    """Aplica os padrões regex no HTML e retorna o primeiro número encontrado."""

    for pattern, kind in PATTERNS:
        match = pattern.search(html)
        if not match:
            continue

        if kind == "wa_link":
            # Link curto — retornar URL completa (não tem o número disponível)
            return match.group(1)

        if kind == "contexto_br":
            # Padrão regional brasileiro: extrair DDI + número
            ddd, parte1, parte2 = match.group(1), match.group(2), match.group(3)
            numero = f"55{ddd}{parte1}{parte2}"
            return _limpar_numero(numero)

        if kind == "contexto_intl":
            # Número internacional próximo a "whatsapp" — já tem + DDI
            numero_raw = match.group(1)
            return _limpar_numero(numero_raw)

        # wame, api, wame_href — número já vem com DDI completo
        numero_raw = match.group(1)
        return _limpar_numero(numero_raw)

    return None


def _limpar_numero(numero: str) -> str | None:
    """
    Remove formatação e retorna apenas dígitos.
    NÃO assume DDI — preserva o número como veio da fonte.
    Números de wa.me já chegam com DDI completo.
    """
    if not numero:
        return None

    # Se for uma URL (wa.link), retornar como está
    if numero.startswith("http"):
        return numero

    # Remover tudo que não é dígito (mantém o número limpo)
    apenas_digitos = re.sub(r"\D", "", numero)

    # Muito curto para ser válido
    if len(apenas_digitos) < 7:
        return None

    # Número longo com DDI (>= 10 dígitos) — usar como está
    if len(apenas_digitos) >= 10:
        return apenas_digitos

    # Número curto (7-9 dígitos) — sem DDI identificável, retornar como está
    return apenas_digitos


async def extract_whatsapp_batch(resultados: list[dict], session: dict) -> None:
    """
    Enriquece os resultados com WhatsApp em paralelo.
    Limita a 5 requisições simultâneas com semáforo.
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
