export default function ResultsTable({ resultados, sessionId, concluido, apenasSemSite }) {
  // Aplicar filtro se checkbox estiver marcado
  const resultadosFiltrados = apenasSemSite
    ? resultados.filter((r) => !r.site)
    : resultados;

  // Contadores baseados nos dados filtrados
  const qtdWpp = resultadosFiltrados.filter((r) => r.whatsapp).length;
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

  // Exportar apenas os resultados filtrados
  function handleExport() {
    // Passar o filtro como query param para o backend saber quais exportar
    // Como o filtro é no frontend, enviamos os IDs via workaround:
    // O mais simples é exportar tudo e filtrar no download via blob
    if (apenasSemSite) {
      exportarFiltrado(resultadosFiltrados);
    } else {
      const link = document.createElement("a");
      link.href = `/api/export/${sessionId}`;
      link.download = `leads_${sessionId.slice(0, 8)}.xlsx`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
  }

  // Para o filtro sem site, chamar o endpoint com query param
  function exportarFiltrado(dados) {
    // Usamos o endpoint padrão mas passando flag de filtro
    const url = `/api/export/${sessionId}?sem_site=true`;
    const link = document.createElement("a");
    link.href = url;
    link.download = `leads_sem_site_${sessionId.slice(0, 8)}.xlsx`;
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
        {/* Cabeçalho com contadores */}
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
            {qtdWpp > 0 && (
              <span className="counter-badge green">
                💬 <strong>{qtdWpp}</strong> com WhatsApp
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

        {/* Aviso quando filtro está ativo */}
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
            <strong>{resultados.length}</strong> contatos (sem site). Desmarque o filtro no
            formulário para ver todos.
          </div>
        )}

        {/* Tabela ou empty state */}
        {resultadosFiltrados.length === 0 ? (
          <div className="empty-state">
            <span className="empty-icon">
              {apenasSemSite && resultados.length > 0 ? "🌐" : "🔍"}
            </span>
            <span>
              {apenasSemSite && resultados.length > 0
                ? "Nenhum contato sem site encontrado. Todos os resultados têm site."
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
                  <th>WhatsApp</th>
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

                    <td className="td-phone">
                      {r.telefone || <span style={{ color: "#cbd5e1" }}>—</span>}
                    </td>

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
