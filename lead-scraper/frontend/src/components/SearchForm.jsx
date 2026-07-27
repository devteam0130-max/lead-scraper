import { useState } from "react";

export default function SearchForm({ onSearch, isSearching }) {
  const [nicho, setNicho] = useState("");
  const [localizacao, setLocalizacao] = useState("");
  const [maxResultados, setMaxResultados] = useState(100);
  const [apenasSemssite, setApenasSemSite] = useState(false);

  function handleSubmit(e) {
    e.preventDefault();
    if (!nicho.trim() || !localizacao.trim()) return;
    onSearch({
      nicho: nicho.trim(),
      localizacao: localizacao.trim(),
      max_resultados: maxResultados,
      apenas_sem_site: apenasSemssite,
    });
  }

  return (
    <div className="card">
      <div className="card-header">
        <span>🎯</span>
        <span className="card-header-title">Parâmetros da busca</span>
      </div>

      <div className="card-body">
        <form onSubmit={handleSubmit}>
          <div className="form-grid">
            {/* Campo 1: Nicho */}
            <div className="form-group">
              <label className="form-label" htmlFor="nicho">
                Nicho ou segmento
              </label>
              <input
                id="nicho"
                type="text"
                className="form-input"
                placeholder="Ex: professor de inglês, clínica odontológica, academia"
                value={nicho}
                onChange={(e) => setNicho(e.target.value)}
                disabled={isSearching}
                required
              />
            </div>

            {/* Campo 2: Localização */}
            <div className="form-group">
              <label className="form-label" htmlFor="localizacao">
                Localização
              </label>
              <input
                id="localizacao"
                type="text"
                className="form-input"
                placeholder="Ex: Salvador BA, São Paulo, New York USA"
                value={localizacao}
                onChange={(e) => setLocalizacao(e.target.value)}
                disabled={isSearching}
                required
              />
            </div>

            {/* Campo 3: Máximo de resultados */}
            <div className="form-group full-width">
              <label className="form-label" htmlFor="max-resultados">
                Máximo de resultados
              </label>
              <div className="slider-wrapper">
                <input
                  id="max-resultados"
                  type="range"
                  className="slider"
                  min={20}
                  max={500}
                  step={10}
                  value={maxResultados}
                  onChange={(e) => setMaxResultados(Number(e.target.value))}
                  disabled={isSearching}
                />
                <span className="slider-value">{maxResultados}</span>
              </div>
            </div>

            {/* Campo 4: Filtro apenas sem site */}
            <div className="form-group full-width">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  className="checkbox-input"
                  checked={apenasSemssite}
                  onChange={(e) => setApenasSemSite(e.target.checked)}
                  disabled={isSearching}
                />
                <span className="checkbox-text">
                  🎯 Mostrar apenas contatos <strong>sem site</strong>
                  <span className="checkbox-hint">
                    Ideal para prospectar empresas que ainda não têm presença digital
                  </span>
                </span>
              </label>
            </div>

            {/* Botão */}
            <div className="form-group full-width">
              <button
                type="submit"
                className="btn-primary"
                disabled={isSearching || !nicho.trim() || !localizacao.trim()}
              >
                {isSearching ? "⏳ Buscando..." : "🚀 Buscar Contatos"}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
