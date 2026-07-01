export default function ResultsTable({ resultados, sessionId, concluido }) {
  // Contar quantos têm WhatsApp
  const qtdWpp = resultados.filter((r) => r.whatsapp).length;

  // Formatar domínio curto para exibição na tabela
  function displayUrl(url) {
    if (!url) return "";
    try {
      const u = new URL(url.startsWith("http") ? url : `https://${url}`);
      return u.hostname.replace(/^www\./, "");
    } catch {
      return url.slice(0, 30);
    }
  }

  // Baixar o arquivo XLSX via GET /api/export/{session_id}
  function handleExport() {
    const link = document.createElement("a");
    link.href = `/api/export/${sessionId}`;
    link.download = `leads_${sessionId.slice(0, 8)}.xlsx`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  return (
    <div className="card">
      <div className="card-header">
        <span>📊</span>
        <span className="card-header-title">Resultados</span>
      </div>

      <div className="card-body">
        {/* Cabeçalho com contadores e botão de export */}
        <div className="results-header">
          <div className="results-counter">
            <span className="counter-badge">
              <strong>{resultados.length}</strong> contatos encontrados
            </span>
            {qtdWpp > 0 && (
              <span className="counter-badge green">
                💬 <strong>{qtdWpp}</strong> com WhatsApp
              </span>
            )}
          </div>

          {/* Mostrar botão de export apenas quando houver dados */}
          {resultados.length > 0 && (
            <button className="btn-export" onClick={handleExport}>
              ⬇️ Exportar planilha .xlsx
            </button>
          )}
        </div>

        {/* Tabela ou empty state */}
        {resultados.length === 0 ? (
          <div className="empty-state">
            <span className="empty-icon">🔍</span>
            <span>Os resultados aparecerão aqui conforme forem coletados...</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table className="results-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Nome</th>
                  <th>Telefone</th>
                  <th>WhatsApp</th>
                  <th>Endereço</th>
                  <th>Site</th>
                  <th>⭐</th>
                </tr>
              </thead>
              <tbody>
                {resultados.map((r, idx) => (
                  <tr key={idx}>
                    {/* Índice */}
                    <td>{idx + 1}</td>

                    {/* Nome */}
                    <td className="td-nome" title={r.nome}>
                      {r.nome || "—"}
                    </td>

                    {/* Telefone */}
                    <td className="td-phone">
                      {r.telefone || <span style={{ color: "#cbd5e1" }}>—</span>}
                    </td>

                    {/* Badge WhatsApp */}
                    <td>
                      {r.whatsapp ? (
                        <a
                          href={
                            r.whatsapp.startsWith("http")
                              ? r.whatsapp
                              : `https://wa.me/${r.whatsapp}`
                          }
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ textDecoration: "none" }}
                        >
                          <span className="badge badge-green">✅ Tem WhatsApp</span>
                        </a>
                      ) : (
                        <span className="badge badge-gray">❌ Sem WhatsApp</span>
                      )}
                    </td>

                    {/* Endereço */}
                    <td title={r.endereco}>
                      {r.endereco
                        ? r.endereco.length > 35
                          ? r.endereco.slice(0, 33) + "…"
                          : r.endereco
                        : <span style={{ color: "#cbd5e1" }}>—</span>}
                    </td>

                    {/* Site */}
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
                        <span style={{ color: "#cbd5e1" }}>—</span>
                      )}
                    </td>

                    {/* Avaliação */}
                    <td className="td-rating">
                      {r.avaliacao ? `${r.avaliacao} ⭐` : <span style={{ color: "#cbd5e1" }}>—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Botão de export no rodapé (duplicado para conveniência quando a tabela é longa) */}
        {resultados.length > 10 && (
          <div style={{ marginTop: "16px", textAlign: "right" }}>
            <button className="btn-export" onClick={handleExport}>
              ⬇️ Exportar planilha .xlsx
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
