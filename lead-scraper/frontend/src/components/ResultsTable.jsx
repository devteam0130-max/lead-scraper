export default function ResultsTable({ resultados, sessionId, concluido, apenasSemSite }) {
  const resultadosFiltrados = apenasSemSite
    ? resultados.filter((r) => !r.site)
    : resultados;

  const qtdSemSite = resultados.filter((r) => !r.site).length;

  // Formatar domínio curto para exibição
  function displayUrl(url) {
    if (!url) return "";
    try {
      const u = new URL(url.startsWith("http") ? url : `https://${url}`);
      return u.hostname.replace(/^www\./, "");
    } catch {
      return url.slice(0, 30);
    }
  }

  // Gerar link wa.me a partir do número de telefone
  // Remove tudo que não é dígito e monta a URL
  function waLink(telefone) {
    if (!telefone) return null;
    const digits = telefone.replace(/\D/g, "");
    if (digits.length < 7) return null;
    return `https://wa.me/${digits}`;
  }

  function handleExport() {
    if (apenasSemSite) {
      const link = document.createElement("a");
      link.href = `/api/export/${sessionId}?sem_site=true`;
      link.download = `leads_sem_site_${sessionId.slice(0, 8)}.xlsx`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } else {
      const link = document.createElement("a");
      link.href = `/api/export/${sessionId}`;
      link.download = `leads_${sessionId.slice(0, 8)}.xlsx`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <span>📊</span>
        <span className="card-header-title">Resultados</span>
      </div>

      <div className="card-body">
        <div className="results-header">
          <div className="results-counter">
            <span className="counter-badge">
              <strong>{resultados.length}</strong> coletados
            </span>
            {qtdSemSite > 0 && (
              <span className="counter-badge" style={{ background: "#fef3c7", color: "#92400e" }}>
                🌐 <strong>{qtdSemSite}</strong> sem site
              </span>
            )}
            {apenasSemSite && (
              <span className="counter-badge" style={{ background: "#ede9fe", color: "#5b21b6" }}>
                🎯 Filtro ativo: <strong>{resultadosFiltrados.length}</strong> sem site
              </span>
            )}
          </div>

          {resultadosFiltrados.length > 0 && (
            <button className="btn-export" onClick={handleExport}>
              ⬇️ Exportar {apenasSemSite ? "sem site " : ""}(.xlsx)
            </button>
          )}
        </div>

        {apenasSemSite && resultados.length > 0 && (
          <div style={{
            marginTop: "12px",
            padding: "10px 14px",
            background: "#ede9fe",
            border: "1px solid #c4b5fd",
            borderRadius: "6px",
            fontSize: "0.8rem",
            color: "#5b21b6",
          }}>
            🎯 Filtro ativo — mostrando <strong>{resultadosFiltrados.length}</strong> de{" "}
            <strong>{resultados.length}</strong> contatos sem site.
          </div>
        )}

        {resultadosFiltrados.length === 0 ? (
          <div className="empty-state">
            <span className="empty-icon">
              {apenasSemSite && resultados.length > 0 ? "🌐" : "🔍"}
            </span>
            <span>
              {apenasSemSite && resultados.length > 0
                ? "Nenhum contato sem site encontrado."
                : "Os resultados aparecerão aqui conforme forem coletados..."}
            </span>
          </div>
        ) : (
          <div className="table-scroll">
            <table className="results-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Nome</th>
                  <th>Telefone</th>
                  <th>Endereço</th>
                  <th>Site</th>
                  <th>⭐</th>
                </tr>
              </thead>
              <tbody>
                {resultadosFiltrados.map((r, idx) => (
                  <tr key={idx}>
                    <td>{idx + 1}</td>

                    <td className="td-nome" title={r.nome}>
                      {r.nome || "—"}
                    </td>

                    {/* Telefone clicável — abre WhatsApp com o número */}
                    <td className="td-phone">
                      {r.telefone ? (
                        <a
                          href={waLink(r.telefone)}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{
                            color: "#16a34a",
                            textDecoration: "none",
                            fontFamily: "monospace",
                            fontSize: "0.8rem",
                            fontWeight: 600,
                          }}
                          title="Abrir no WhatsApp"
                        >
                          {r.telefone}
                        </a>
                      ) : (
                        <span style={{ color: "#cbd5e1" }}>—</span>
                      )}
                    </td>

                    <td title={r.endereco}>
                      {r.endereco
                        ? r.endereco.length > 35
                          ? r.endereco.slice(0, 33) + "…"
                          : r.endereco
                        : <span style={{ color: "#cbd5e1" }}>—</span>}
                    </td>

                    <td className="td-site">
                      {r.site ? (
                        <a
                          href={r.site.startsWith("http") ? r.site : `https://${r.site}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          title={r.site}
                        >
                          {displayUrl(r.site)}
                        </a>
                      ) : (
                        <span className="badge" style={{
                          background: "#fef3c7",
                          color: "#92400e",
                          fontSize: "0.7rem",
                        }}>
                          Sem site
                        </span>
                      )}
                    </td>

                    <td className="td-rating">
                      {r.avaliacao
                        ? `${r.avaliacao} ⭐`
                        : <span style={{ color: "#cbd5e1" }}>—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {resultadosFiltrados.length > 10 && (
          <div style={{ marginTop: "16px", textAlign: "right" }}>
            <button className="btn-export" onClick={handleExport}>
              ⬇️ Exportar {apenasSemSite ? "sem site " : ""}(.xlsx)
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
