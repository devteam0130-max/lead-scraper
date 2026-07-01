import { useEffect, useState } from "react";

export default function StatusBar({ status, processados, total, concluido, qtdWpp }) {
  const [elapsed, setElapsed] = useState(0);

  // Cronômetro: incrementa a cada segundo enquanto não concluído
  useEffect(() => {
    if (concluido) return;
    const interval = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(interval);
  }, [concluido]);

  // Calcular porcentagem de progresso
  const pct = total > 0 ? Math.min(100, Math.round((processados / total) * 100)) : 0;

  // Formatar tempo decorrido como mm:ss
  function formatTime(secs) {
    const m = Math.floor(secs / 60).toString().padStart(2, "0");
    const s = (secs % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  }

  // Texto amigável do status
  function statusLabel() {
    if (status === "concluido") return "Concluído com sucesso";
    if (!status) return "Iniciando...";
    return status;
  }

  return (
    <div className="card">
      <div className="card-header">
        <span>📡</span>
        <span className="card-header-title">Progresso</span>
      </div>

      <div className="status-bar-container">
        {/* Linha superior: texto de status + cronômetro */}
        <div className="status-top-row">
          <div className="status-text">
            {!concluido && <span className="status-spinner" />}
            {concluido && <span>✅</span>}
            <span>{statusLabel()}</span>
          </div>
          <span className="status-timer">⏱ {formatTime(elapsed)}</span>
        </div>

        {/* Barra de progresso */}
        <div className="progress-track">
          <div
            className="progress-bar"
            style={{ width: concluido ? "100%" : `${Math.max(pct, 3)}%` }}
          />
        </div>

        {/* Contadores */}
        <div className="status-counts">
          <div className="count-item">
            📋 <strong>{processados}</strong>&nbsp;coletados
          </div>
          {total > 0 && (
            <div className="count-item">
              🎯 Meta: <strong>{total}</strong>
            </div>
          )}
          {qtdWpp > 0 && (
            <div className="count-item">
              💬 <strong>{qtdWpp}</strong>&nbsp;com WhatsApp
            </div>
          )}
          {pct > 0 && (
            <div className="count-item">
              <strong>{pct}%</strong>&nbsp;concluído
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
