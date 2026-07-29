import asyncio
import uuid
import json
import os
import time
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from scraper import scrape_google_maps
from whatsapp_extractor import extract_whatsapp_batch
from exporter import generate_xlsx

app = FastAPI(title="Lead Scraper API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Armazenamento em memória por session_id
# Inclui _criado_em para permitir limpeza automática
sessions: dict = {}

# Tempo máximo de vida de uma sessão (segundos)
SESSION_TTL = 1800  # 30 minutos


class SearchRequest(BaseModel):
    nicho: str
    localizacao: str
    max_resultados: int = 100
    apenas_sem_site: bool = False  # filtro frontend, ignorado no backend


async def _limpar_sessions_antigas():
    """
    Task em background que remove sessões expiradas a cada 5 minutos.
    Evita vazamento de memória em uso contínuo.
    """
    while True:
        await asyncio.sleep(300)  # verificar a cada 5 minutos
        agora = time.time()
        expiradas = [
            sid for sid, s in list(sessions.items())
            if agora - s.get("_criado_em", 0) > SESSION_TTL
        ]
        for sid in expiradas:
            sessions.pop(sid, None)
        if expiradas:
            print(f"[Cleanup] {len(expiradas)} sessões expiradas removidas.")


@app.on_event("startup")
async def startup():
    """Inicia a task de limpeza de sessões ao subir o servidor."""
    asyncio.create_task(_limpar_sessions_antigas())


@app.post("/api/search")
async def search(req: SearchRequest, background_tasks: BackgroundTasks):
    """Inicia uma busca no Google Maps e retorna o session_id."""
    session_id = str(uuid.uuid4())

    sessions[session_id] = {
        "status": "Iniciando...",
        "total": req.max_resultados,
        "processados": 0,
        "resultados": [],
        "concluido": False,
        "erro": None,
        "_criado_em": time.time(),  # para limpeza automática
    }

    background_tasks.add_task(
        run_scraping,
        session_id,
        req.nicho,
        req.localizacao,
        req.max_resultados,
    )

    return {"session_id": session_id}


async def run_scraping(session_id: str, nicho: str, localizacao: str, max_resultados: int):
    """Executa o scraping e enriquece resultados com WhatsApp."""
    if session_id not in sessions:
        return

    session = sessions[session_id]

    try:
        # Fase 1: coletar dados do Google Maps
        session["status"] = "Abrindo Google Maps..."
        resultados = await scrape_google_maps(nicho, localizacao, max_resultados, session)
        session["resultados"] = resultados

        # Fase 2: extrair WhatsApp dos sites (pula quem já tem do GMaps)
        if resultados:
            session["status"] = "Extraindo WhatsApp dos sites..."
            await extract_whatsapp_batch(resultados, session)

        session["status"] = "concluido"
        session["processados"] = len(resultados)
        session["total"] = len(resultados)
        session["concluido"] = True

    except Exception as exc:
        session["erro"] = str(exc)
        session["status"] = f"Erro: {str(exc)[:120]}"
        session["concluido"] = True


@app.get("/api/status/{session_id}")
async def get_status(session_id: str):
    """
    Server-Sent Events (SSE) — envia atualizações de progresso a cada 500ms.
    """
    async def event_generator():
        if session_id not in sessions:
            payload = json.dumps({"erro": "Sessão não encontrada"}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
            return

        while True:
            session = sessions[session_id]
            data = {
                "total": session["total"],
                "processados": session["processados"],
                "status": session["status"],
                "resultados": session["resultados"],
                "concluido": session["concluido"],
                "erro": session["erro"],
            }
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

            if session["concluido"]:
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/export/{session_id}")
async def export(session_id: str, sem_site: bool = False):
    """
    Gera e retorna o arquivo .xlsx.
    Se sem_site=true, exporta apenas resultados sem site.
    """
    if session_id not in sessions:
        return Response(status_code=404, content="Sessão não encontrada")

    resultados = sessions[session_id]["resultados"]

    if not resultados:
        return Response(status_code=404, content="Nenhum resultado para exportar")

    # Aplicar filtro de sem site se solicitado
    if sem_site:
        resultados = [r for r in resultados if not r.get("site")]

    if not resultados:
        return Response(status_code=404, content="Nenhum resultado sem site para exportar")

    xlsx_bytes = generate_xlsx(resultados)
    sufixo = "_sem_site" if sem_site else ""
    filename = f"leads{sufixo}_{session_id[:8]}.xlsx"

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "sessoes_ativas": len(sessions),
        "versao": "2.0.0",
    }


# -------------------------------------------------------
# Frontend React — deve ficar DEPOIS dos endpoints /api
# -------------------------------------------------------
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

if os.path.exists(FRONTEND_DIR):
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
