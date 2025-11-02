import { useEffect, useMemo, useState } from 'react';
import { fetchJSON } from '../lib/api';

export default function TramitesPage() {
  const [tramites, setTramites] = useState([]);
  const [query, setQuery] = useState('');
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchJSON('/public/tramites')
      .then(setTramites)
      .catch((err) => setError(err.message));
  }, []);

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return tramites;
    return tramites.filter((tramite) =>
      tramite.nombre.toLowerCase().includes(term) ||
      tramite.descripcion.toLowerCase().includes(term)
    );
  }, [query, tramites]);

  return (
    <section>
      <h2>Trámites disponibles</h2>
      <input
        type="search"
        placeholder="Buscar por nombre o descripción"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      {error && <p>Error: {error}</p>}
      {filtered.map((tramite) => (
        <article key={tramite.id}>
          <h3>{tramite.nombre}</h3>
          <p>{tramite.descripcion}</p>
          <div>
            <strong>Requisitos:</strong>
            <ul>
              {tramite.requisitos.map((req) => (
                <li key={req}>{req}</li>
              ))}
            </ul>
          </div>
        </article>
      ))}
      {!error && filtered.length === 0 && <p>No se encontraron trámites para la búsqueda ingresada.</p>}
    </section>
  );
}
