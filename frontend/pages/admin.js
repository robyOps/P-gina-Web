import { useState } from 'react';
import { fetchJSON } from '../lib/api';

function useForm(initial) {
  const [values, setValues] = useState(initial);
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleChange = (event) => {
    const { name, value } = event.target;
    setValues((prev) => ({ ...prev, [name]: value }));
  };

  const submit = async (path, transform) => {
    setLoading(true);
    setStatus(null);
    setError(null);
    try {
      const payload = transform ? transform(values) : values;
      const response = await fetchJSON(path, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      setStatus('Operación realizada correctamente.');
      setValues(initial);
      return response;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  };

  return { values, handleChange, submit, status, error, loading };
}

export default function AdminPage() {
  const informeForm = useForm({ token: '', titulo: '', fecha: '', url: '' });
  const arancelForm = useForm({ token: '', codigo: '', nombre: '', monto: '', moneda: 'CLP', vigenteDesde: '' });
  const indiceForm = useForm({ token: '', numero: '', fecha: '', tipo: '', comparecientes: '' });

  const handleInforme = async (event) => {
    event.preventDefault();
    await informeForm.submit('/admin/informe');
  };

  const handleArancel = async (event) => {
    event.preventDefault();
    await arancelForm.submit('/admin/arancel', (values) => ({
      ...values,
      monto: Number(values.monto),
    }));
  };

  const handleIndice = async (event) => {
    event.preventDefault();
    await indiceForm.submit('/admin/indice', (values) => ({
      token: values.token,
      registros: [
        {
          numero: values.numero,
          fecha: values.fecha,
          tipo: values.tipo,
          comparecientes: values.comparecientes
            .split('\n')
            .map((name) => name.trim())
            .filter(Boolean)
            .map((nombre) => ({ nombre })),
        },
      ],
    }));
  };

  return (
    <>
      <section>
        <h2>Agregar informe</h2>
        <form onSubmit={handleInforme}>
          <label htmlFor="token-informe">Token</label>
          <input
            id="token-informe"
            name="token"
            value={informeForm.values.token}
            onChange={informeForm.handleChange}
            required
          />

          <label htmlFor="titulo">Título</label>
          <input
            id="titulo"
            name="titulo"
            value={informeForm.values.titulo}
            onChange={informeForm.handleChange}
            required
          />

          <label htmlFor="fecha">Fecha</label>
          <input
            id="fecha"
            name="fecha"
            type="date"
            value={informeForm.values.fecha}
            onChange={informeForm.handleChange}
            required
          />

          <label htmlFor="url">URL del informe (PDF)</label>
          <input
            id="url"
            name="url"
            type="url"
            value={informeForm.values.url}
            onChange={informeForm.handleChange}
            required
          />

          <button type="submit" disabled={informeForm.loading}>
            {informeForm.loading ? 'Guardando...' : 'Guardar informe'}
          </button>
          {informeForm.status && <p>{informeForm.status}</p>}
          {informeForm.error && <p>Error: {informeForm.error}</p>}
        </form>
      </section>

      <section>
        <h2>Registrar arancel</h2>
        <form onSubmit={handleArancel}>
          <label htmlFor="token-arancel">Token</label>
          <input
            id="token-arancel"
            name="token"
            value={arancelForm.values.token}
            onChange={arancelForm.handleChange}
            required
          />

          <label htmlFor="codigo">Código</label>
          <input
            id="codigo"
            name="codigo"
            value={arancelForm.values.codigo}
            onChange={arancelForm.handleChange}
            required
          />

          <label htmlFor="nombre">Nombre</label>
          <input
            id="nombre"
            name="nombre"
            value={arancelForm.values.nombre}
            onChange={arancelForm.handleChange}
            required
          />

          <label htmlFor="monto">Monto</label>
          <input
            id="monto"
            name="monto"
            type="number"
            min="0"
            step="0.01"
            value={arancelForm.values.monto}
            onChange={arancelForm.handleChange}
            required
          />

          <label htmlFor="moneda">Moneda</label>
          <input
            id="moneda"
            name="moneda"
            value={arancelForm.values.moneda}
            onChange={arancelForm.handleChange}
            required
          />

          <label htmlFor="vigenteDesde">Vigente desde</label>
          <input
            id="vigenteDesde"
            name="vigenteDesde"
            type="date"
            value={arancelForm.values.vigenteDesde}
            onChange={arancelForm.handleChange}
            required
          />

          <button type="submit" disabled={arancelForm.loading}>
            {arancelForm.loading ? 'Guardando...' : 'Guardar arancel'}
          </button>
          {arancelForm.status && <p>{arancelForm.status}</p>}
          {arancelForm.error && <p>Error: {arancelForm.error}</p>}
        </form>
      </section>

      <section>
        <h2>Agregar índice</h2>
        <form onSubmit={handleIndice}>
          <label htmlFor="token-indice">Token</label>
          <input
            id="token-indice"
            name="token"
            value={indiceForm.values.token}
            onChange={indiceForm.handleChange}
            required
          />

          <label htmlFor="numero">Número</label>
          <input
            id="numero"
            name="numero"
            value={indiceForm.values.numero}
            onChange={indiceForm.handleChange}
            required
          />

          <label htmlFor="fechaIndice">Fecha</label>
          <input
            id="fechaIndice"
            name="fecha"
            type="date"
            value={indiceForm.values.fecha}
            onChange={indiceForm.handleChange}
            required
          />

          <label htmlFor="tipo">Tipo</label>
          <input
            id="tipo"
            name="tipo"
            value={indiceForm.values.tipo}
            onChange={indiceForm.handleChange}
            required
          />

          <label htmlFor="comparecientes">Comparecientes (uno por línea)</label>
          <textarea
            id="comparecientes"
            name="comparecientes"
            rows="4"
            value={indiceForm.values.comparecientes}
            onChange={indiceForm.handleChange}
            placeholder={'Ejemplo:\nMaría López\nJuan Pérez'}
            required
          />

          <button type="submit" disabled={indiceForm.loading}>
            {indiceForm.loading ? 'Guardando...' : 'Guardar índice'}
          </button>
          {indiceForm.status && <p>{indiceForm.status}</p>}
          {indiceForm.error && <p>Error: {indiceForm.error}</p>}
        </form>
      </section>
    </>
  );
}
