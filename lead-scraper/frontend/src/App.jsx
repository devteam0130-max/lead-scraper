import { useState, useEffect, useRef } from "react";
import SearchForm from "./components/SearchForm.jsx";
import StatusBar from "./components/StatusBar.jsx";
import ResultsTable from "./components/ResultsTable.jsx";

export default function App() {
  const [sessionId, setSessionId] = useState(null);
  const [isSearching, setIsSearching] = useState(false);
  const [status, setStatus] = useState("");
  const [processados, setProcessados] = useState(0);
  const [total, setTotal] = useState(0);
  const [resultados, setResultados] = useState([]);
  const [concluido, setConcluido] = useState(false);
  const [erro, setErro] = useState(null);
  const [apenasSemSite, setApenasSemSite] = useState(false);

  const esRef = useRef(null);

  async function handleSearch(params) {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }

    setResultados([]);
    setProcessados(0);
    setTotal(params.max_resultados);
    setConcluido(false);
    setErro(null);
    setStatus("Iniciando...");
    setIsSearching(true);
    setApenasSemSite(params.apenas_sem_site || false);

    try {
      const resp = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });

      if (!resp.ok) throw new Error(`Erro ao iniciar busca: ${resp.status}`);

      const { session_id } = await resp.json();
      setSessionId(session_id);

      const es = new EventSource(`/api/status/${session_id}`);
      esRef.current = es;

      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setStatus(data.status || "");
          setProcessados(data.processados ?? 0);
          setTotal(data.total ?? 0);
          setResultados(data.resultados ?? []);
          if (data.erro) setErro(data.erro);
          if (data.concluido) {
            setConcluido(true);
            setIsSearching(false);
            es.close();
            esRef.current = null;
          }
        } catch {
          // ignorar mensagens malformadas
        }
      };

      es.onerror = () => {
        setConcluido(true);
        setIsSearching(false);
        es.close();
        esRef.current = null;
      };

    } catch (err) {
      setErro(err.message);
      setIsSearching(false);
    }
  }

  useEffect(() => {
    return () => { if (esRef.current) esRef.current.close(); };
  }, []);

  const qtdWpp = resultados.filter((r) => r.whatsapp).length;

  return (
    <div className="app-wrapper">
      <header className="app-header">
        <h1 className="app-title">🔍 Buscador de Leads</h1>
        <p className="app-subtitle">
          Encontre empresas e extraia contatos do Google Maps
        </p>
      </header>

      <main className="app-main">
        <SearchForm onSearch={handleSearch} isSearching={isSearching} />

        {sessionId && (
          <StatusBar
            status={status}
            processados={processados}
            total={total}
            concluido={concluido}
            qtdWpp={qtdWpp}
          />
        )}

        {erro && (
          <div style={{
            background: "#fef2f2",
            border: "1px solid #fecaca",
            borderRadius: "8px",
            padding: "14px 18px",
            color: "#b91c1c",
            fontSize: "0.875rem",
            fontWeight: 500,
          }}>
            ⚠️ {erro}
          </div>
        )}

        {sessionId && (
          <ResultsTable
            resultados={resultados}
            sessionId={sessionId}
            concluido={concluido}
            apenasSemSite={apenasSemSite}
          />
        )}
      </main>
    </div>
  );
}
