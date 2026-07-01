import asyncio
import uuid
import json
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from scraper import scrape_google_maps
from whatsapp_extractor import extract_whatsapp_batch
from exporter import generate_xlsx

app = FastAPI(title="Lead Scraper API", version="1.0.0")

# CORS liberado para qualquer origem (frontend pode estar em outro domínio)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Armazenamento em memória por session_id
# Formato: { session_id: { status, total, processados, resultados, concluido, erro } }
sessions: dict = {}


class SearchRequest(BaseModel):
    nicho: str
    localizacao: str
    max_resultados: int = 100


@app.post("/api/search")
async def search(req: SearchRequest, background_tasks: BackgroundTasks):
    """Inicia uma busca no Google Maps e retorna o session_id para acompanhar o progresso."""
    session_id = str(uuid.uuid4())

    sessions[session_id] = {
        "status": "Iniciando...",
        "total": req.max_resultados,
        "processados": 0,
        "resultados": [],
        "concluido": False,
        "erro": None,
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
    """Tarefa em background que executa o scraping e enriquece os dados com WhatsApp."""
    session = sessions[session_id]

    try:
        # Fase 1: coletar dados do Google Maps
        session["status"] = "Abrindo Google Maps..."
        resultados = await scrape_google_maps(nicho, localizacao, max_resultados, session)
        session["resultados"] = resultados

        # Fase 2: extrair WhatsApp dos sites coletados
        if resultados:
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
    Formato: { total, processados, status, resultados, concluido }
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
            "X-Accel-Buffering": "no",  # Desativa buffering do Nginx para SSE
            "Connection": "keep-alive",
        },
    )


@app.get("/api/export/{session_id}")
async def export(session_id: str):
    """Gera e retorna o arquivo .xlsx com os resultados da sessão."""
    if session_id not in sessions:
        return Response(status_code=404, content="Sessão não encontrada")

    resultados = sessions[session_id]["resultados"]

    if not resultados:
        return Response(status_code=404, content="Nenhum resultado para exportar")

    xlsx_bytes = generate_xlsx(resultados)
    filename = f"leads_{session_id[:8]}.xlsx"

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/health")
async def health():
    return {"status": "ok", "sessoes_ativas": len(sessions)}
