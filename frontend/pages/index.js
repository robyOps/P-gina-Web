import { useEffect, useState } from 'react';
import { API_URL, fetchJSON } from '../lib/api';

export default function HomePage() {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchJSON('/public/info')
      .then(setInfo)
      .catch((err) => setError(err.message));
  }, []);

  return (
    <>
      <section>
        <h2>Información General</h2>
        {!info && !error && <p>Cargando información de la notaría...</p>}
        {error && <p>Error: {error}</p>}
        {info && (
          <div>
            <p><strong>Nombre:</strong> {info.nombreNotaria}</p>
            <p><strong>Dirección:</strong> {info.direccion}</p>
            <p><strong>Correo:</strong> <a href={`mailto:${info.correo}`}>{info.correo}</a></p>
            <p><strong>Teléfonos:</strong> {info.telefonos.join(', ')}</p>
            <div>
              <strong>Horarios:</strong>
              <ul>
                {info.horario.map((slot) => (
                  <li key={slot}>{slot}</li>
                ))}
              </ul>
            </div>
            {info.mapa && (
              <p>
                <a href={info.mapa} target="_blank" rel="noreferrer">
                  Ver mapa
                </a>
              </p>
            )}
          </div>
        )}
      </section>

      <section>
        <h2>Accesos rápidos</h2>
        <p>Utiliza el menú superior para acceder a los trámites, aranceles, transparencia, índices y contacto.</p>
        <p>
          Base de la API actual: <strong>{API_URL}</strong>
        </p>
      </section>
    </>
  );
}
