import { useEffect, useState } from 'react';
import { fetchJSON } from '../lib/api';

export default function ArancelesPage() {
  const [aranceles, setAranceles] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchJSON('/public/aranceles')
      .then((data) => {
        setAranceles(data);
      })
      .catch((err) => setError(err.message));
  }, []);

  return (
    <section>
      <h2>Aranceles vigentes</h2>
      {error && <p>Error: {error}</p>}
      {!error && aranceles.length === 0 && <p>No hay aranceles registrados.</p>}
      {aranceles.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="table">
            <thead>
              <tr>
                <th>Código</th>
                <th>Nombre</th>
                <th>Monto</th>
                <th>Moneda</th>
                <th>Vigente desde</th>
              </tr>
            </thead>
            <tbody>
              {aranceles.map((arancel) => (
                <tr key={arancel.codigo}>
                  <td>{arancel.codigo}</td>
                  <td>{arancel.nombre}</td>
                  <td>{new Intl.NumberFormat('es-CL').format(arancel.monto)}</td>
                  <td>{arancel.moneda}</td>
                  <td>{new Date(arancel.vigenteDesde).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
