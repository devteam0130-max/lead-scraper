import { useState, useEffect, useRef } from "react";
import SearchForm from "./components/SearchForm.jsx";
import StatusBar from "./components/StatusBar.jsx";
import ResultsTable from "./components/ResultsTable.jsx";

export default function App() {
  // Estado principal
  const [sessionId, setSessionId] = useState(null);
  const [isSearching, setIsSearching] = useState(false);
  const [status, setStatus] = useState("");
  const [processados, setProcessados] = useState(0);
  const [total, setTotal] = useState(0);
  const [resultados, setResultados] = useState([]);
  const [concluido, setConcluido] = useState(false);
  const [erro, setErro] = useState(null);

  // Ref para fechar o EventSource ao desmontar ou iniciar nova busca
  const esRef = useRef(null);

  /**
   * Inicia uma nova busca:
   * 1. Faz POST /api/search e recebe o session_id
   * 2. Abre conexão SSE para receber atualizações em tempo real
   */
  async function handleSearch(params) {
    // Fechar conexão SSE anterior se existir
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }

    // Resetar estado
    setResultados([]);
    setProcessados(0);
    setTotal(params.max_resultados);
    setConcluido(false);
    setErro(null);
    setStatus("Iniciando...");
    setIsSearching(true);

    try {
      // Iniciar sessão de busca no backend
      const resp = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });

      if (!resp.ok) {
        throw new Error(`Erro ao iniciar busca: ${resp.status}`);
      }

      const { session_id } = await resp.json();
      setSessionId(session_id);

      // Abrir conexão SSE para receber progresso em tempo real
      const es = new EventSource(`/api/status/${session_id}`);
      esRef.current = es;

      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          setStatus(data.status || "");
          setProcessados(data.processados ?? 0);
          setTotal(data.total ?? 0);
          setResultados(data.resultados ?? []);

          if (data.erro) {
            setErro(data.erro);
          }

          if (data.concluido) {
            setConcluido(true);
            setIsSearching(false);
            es.close();
            esRef.current = null;
          }
        } catch {
          // Ignorar mensagens SSE malformadas
        }
      };

      es.onerror = () => {
        // SSE fechou (normalmente após concluir ou por timeout)
        if (!concluido) {
          setConcluido(true);
          setIsSearching(false);
        }
        es.close();
        esRef.current = null;
      };

    } catch (err) {
      setErro(err.message);
      setIsSearching(false);
    }
  }

  // Fechar SSE ao desmontar o componente
  useEffect(() => {
    return () => {
      if (esRef.current) esRef.current.close();
    };
  }, []);

  // Contar quantos resultados têm WhatsApp (para passar ao StatusBar)
  const qtdWpp = resultados.filter((r) => r.whatsapp).length;

  return (
    <div className="app-wrapper">
      {/* Cabeçalho */}
      <header className="app-header">
        <h1 className="app-title">🔍 Buscador de Leads</h1>
        <p className="app-subtitle">
          Encontre empresas e extraia contatos do Google Maps
        </p>
      </header>

      <main className="app-main">
        {/* Formulário de busca */}
        <SearchForm onSearch={handleSearch} isSearching={isSearching} />

        {/* Mostrar progresso apenas após iniciar busca */}
        {sessionId && (
          <StatusBar
            status={status}
            processados={processados}
            total={total}
            concluido={concluido}
            qtdWpp={qtdWpp}
          />
        )}

        {/* Mensagem de erro */}
        {erro && (
          <div
            style={{
              background: "#fef2f2",
              border: "1px solid #fecaca",
              borderRadius: "8px",
              padding: "14px 18px",
              color: "#b91c1c",
              fontSize: "0.875rem",
              fontWeight: 500,
            }}
          >
            ⚠️ {erro}
          </div>
        )}

        {/* Tabela de resultados — aparece assim que a busca começa */}
        {sessionId && (
          <ResultsTable
            resultados={resultados}
            sessionId={sessionId}
            concluido={concluido}
          />
        )}
      </main>
    </div>
  );
}
