import asyncio
import re
import httpx

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Padrões regex para encontrar WhatsApp no HTML estático
# Em ordem de confiabilidade
PATTERNS = [
    # wa.me com número completo (mais confiável — já tem DDI)
    (re.compile(r"wa\.me/(\+?[\d]{7,15})"), "wame"),
    # api.whatsapp.com/send?phone=NUMERO
    (re.compile(r"api\.whatsapp\.com/send[/\?].*?phone=(\+?[\d]{7,15})"), "api"),
    # href com wa.me
    (re.compile(r'href=["\']https?://wa\.me/(\+?[\d]{7,15})["\']'), "wame_href"),
    # wa.link (link curto — retorna a URL diretamente)
    (re.compile(r"(https?://wa\.link/[A-Za-z0-9]+)"), "wa_link"),
    # Número com + DDI explícito próximo à palavra "whatsapp/zap/wpp"
    (re.compile(
        r"(?i)(?:whatsapp|whats\s*app|whasapp|wpp|zap)[^0-9+]{0,60}"
        r"(\+[\d\s\-().]{7,20})"
    ), "contexto_intl"),
    # Formato brasileiro próximo a "whatsapp/zap"
    (re.compile(
        r"(?i)(?:whatsapp|wpp|zap)[^0-9]{0,30}"
        r"\(?(?\d{2})\)?[\s.-]?(\d{4,5})[\s.-]?(\d{4})"
    ), "contexto_br"),
    # Número brasileiro no href (detecta +55 explícito)
    (re.compile(r"href=[\"'][^\"']*\+55(\d{10,11})[\"']"), "br_href"),
]


async def extract_whatsapp(url: str) -> str | None:
    """
    Faz GET na URL do site e procura por links/números de WhatsApp no HTML.
    Também tenta a página /contato ou /contact se não achar no index.
    Retorna o número limpo ou None.
    """
    if not url or not url.startswith("http"):
        return None

    # Tentar na página principal
    html = await _fetch_html(url)
    if html:
        resultado = _parse_whatsapp_from_html(html)
        if resultado:
            return resultado

    # Tentar em páginas de contato se não achou
    base = url.rstrip("/")
    for path in ["/contato", "/contact", "/fale-conosco", "/whatsapp"]:
        html_extra = await _fetch_html(f"{base}{path}")
        if html_extra:
            resultado = _parse_whatsapp_from_html(html_extra)
            if resultado:
                return resultado

    return None


async def _fetch_html(url: str) -> str | None:
    """Busca o HTML de uma URL com timeout e SSL ignorado."""
    try:
        async with httpx.AsyncClient(
            timeout=8.0,
            follow_redirects=True,
            verify=False,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,*/*",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            },
        ) as client:
            resp = await client.get(url, timeout=8.0)
            if resp.status_code < 400:
                return resp.text
    except Exception:
        pass
    return None


def _parse_whatsapp_from_html(html: str) -> str | None:
    """Aplica os padrões regex no HTML e retorna o primeiro número encontrado."""
    for pattern, kind in PATTERNS:
        match = pattern.search(html)
        if not match:
            continue

        if kind == "wa_link":
            return match.group(1)

        if kind == "contexto_br":
            ddd, parte1, parte2 = match.group(1), match.group(2), match.group(3)
            return _limpar_numero(f"55{ddd}{parte1}{parte2}")

        if kind == "contexto_intl":
            return _limpar_numero(match.group(1))

        if kind == "br_href":
            return f"55{match.group(1)}"

        # wame, api, wame_href
        return _limpar_numero(match.group(1))

    return None


def _limpar_numero(numero: str) -> str | None:
    """Remove formatação e retorna apenas dígitos. Não assume DDI."""
    if not numero:
        return None

    if numero.startswith("http"):
        return numero

    apenas_digitos = re.sub(r"\D", "", numero)

    if len(apenas_digitos) < 7:
        return None

    return apenas_digitos


async def extract_whatsapp_batch(resultados: list[dict], session: dict) -> None:
    """
    Enriquece os resultados com WhatsApp em paralelo.
    Melhorias v2:
    - Pula resultados que já têm WhatsApp (extraído do Google Maps)
    - Semáforo aumentado de 5 para 8 requisições simultâneas
    - Timeout reduzido de 10s para 8s por site
    """
    # Filtrar só os que precisam de busca no site
    # (os que já têm whatsapp do GMaps são pulados)
    pendentes = [r for r in resultados if not r.get("whatsapp") and r.get("site")]
    ja_tem = len(resultados) - len(pendentes) - len([r for r in resultados if not r.get("site")])

    total = len(pendentes)
    processados_wpp = 0

    # Semáforo aumentado: 8 requisições simultâneas (era 5)
    semaphore = asyncio.Semaphore(8)

    async def process_one(resultado: dict):
        nonlocal processados_wpp

        async with semaphore:
            wpp = await extract_whatsapp(resultado["site"])
            resultado["whatsapp"] = wpp

            processados_wpp += 1
            session["status"] = (
                f"Extraindo WhatsApp dos sites... ({processados_wpp}/{total})"
                + (f" | {ja_tem} já obtidos do Google Maps" if ja_tem > 0 else "")
            )
            session["resultados"] = list(resultados)

    if pendentes:
        tasks = [process_one(r) for r in pendentes]
        await asyncio.gather(*tasks)

    # Garantir que resultados sem site tenham whatsapp=None
    for r in resultados:
        if "whatsapp" not in r:
            r["whatsapp"] = None
