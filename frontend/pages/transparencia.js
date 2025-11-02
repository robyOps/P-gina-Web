import { useEffect, useState } from 'react';
import { fetchJSON } from '../lib/api';

export default function TransparenciaPage() {
  const [personal, setPersonal] = useState([]);
  const [informes, setInformes] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([
      fetchJSON('/public/personal'),
      fetchJSON('/public/informes'),
    ])
      .then(([personalData, informesData]) => {
        setPersonal(personalData);
        setInformes(informesData);
      })
      .catch((err) => setError(err.message));
  }, []);

  return (
    <>
      <section>
        <h2>Nómina de personal</h2>
        {error && <p>Error: {error}</p>}
        {personal.length === 0 && !error && <p>No hay personal registrado.</p>}
        {personal.map((persona) => (
          <article key={`${persona.nombre}-${persona.cargo}`}>
            <h3>{persona.nombre}</h3>
            <p><strong>Cargo:</strong> {persona.cargo}</p>
            <p><strong>Remuneración:</strong> ${new Intl.NumberFormat('es-CL').format(persona.remuneracion)}</p>
          </article>
        ))}
      </section>

      <section>
        <h2>Informes de fiscalización</h2>
        {informes.length === 0 && !error && <p>No hay informes disponibles.</p>}
        <ul>
          {informes.map((informe) => (
            <li key={informe.url}>
              <span className="badge">{new Date(informe.fecha).toLocaleDateString()}</span>
              <a href={informe.url} target="_blank" rel="noreferrer">
                {informe.titulo}
              </a>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
