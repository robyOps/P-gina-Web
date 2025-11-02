import { useEffect, useState } from 'react';
import { fetchJSON } from '../lib/api';

function formatComparecientes(comparecientes) {
  return comparecientes.map((c) => c.nombre).join(', ');
}

export default function IndicesPage() {
  const [indices, setIndices] = useState([]);
  const [nombre, setNombre] = useState('');
  const [mes, setMes] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const consultar = async (params = '') => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchJSON(`/public/indices${params}`);
      setIndices(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    consultar('');
  }, []);

  const handleSubmit = (event) => {
    event.preventDefault();
    const queryParams = new URLSearchParams();
    if (nombre.trim()) {
      queryParams.set('q', nombre.trim());
    }
    if (mes) {
      queryParams.set('fecha', mes);
    }
    const suffix = queryParams.toString();
    consultar(suffix ? `?${suffix}` : '');
  };

  return (
    <>
      <section>
        <h2>Consulta de índices</h2>
        <form onSubmit={handleSubmit}>
          <label htmlFor="nombre">Compareciente</label>
          <input
            id="nombre"
            type="text"
            placeholder="Nombre del compareciente"
            value={nombre}
            onChange={(event) => setNombre(event.target.value)}
          />

          <label htmlFor="mes">Mes (YYYY-MM)</label>
          <input
            id="mes"
            type="month"
            value={mes}
            onChange={(event) => setMes(event.target.value)}
          />

          <button type="submit">Buscar</button>
        </form>
      </section>

      <section>
        <h2>Resultados</h2>
        {loading && <p>Buscando...</p>}
        {error && <p>Error: {error}</p>}
        {!loading && !error && indices.length === 0 && <p>No se encontraron resultados.</p>}
        {indices.map((indice) => (
          <article key={indice.numero}>
            <h3>{indice.numero}</h3>
            <p><strong>Fecha:</strong> {new Date(indice.fecha).toLocaleDateString()}</p>
            <p><strong>Tipo:</strong> {indice.tipo}</p>
            <p><strong>Comparecientes:</strong> {formatComparecientes(indice.comparecientes)}</p>
          </article>
        ))}
      </section>
    </>
  );
}
