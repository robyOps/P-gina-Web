import { useState } from 'react';
import { fetchJSON } from '../lib/api';

export default function ContactoPage() {
  const [form, setForm] = useState({ nombre: '', correo: '', mensaje: '' });
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);
    setStatus(null);
    setError(null);
    try {
      await fetchJSON('/public/reclamo', {
        method: 'POST',
        body: JSON.stringify(form),
      });
      setStatus('Tu reclamo fue enviado correctamente.');
      setForm({ nombre: '', correo: '', mensaje: '' });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section>
      <h2>Canal de reclamos</h2>
      <p>Envía tu reclamo o sugerencia. Este mensaje será registrado con fecha y hora.</p>
      <form onSubmit={handleSubmit}>
        <label htmlFor="nombre">Nombre</label>
        <input
          id="nombre"
          name="nombre"
          value={form.nombre}
          onChange={handleChange}
          required
        />

        <label htmlFor="correo">Correo electrónico</label>
        <input
          id="correo"
          name="correo"
          type="email"
          value={form.correo}
          onChange={handleChange}
          required
        />

        <label htmlFor="mensaje">Mensaje</label>
        <textarea
          id="mensaje"
          name="mensaje"
          rows="5"
          value={form.mensaje}
          onChange={handleChange}
          required
        />

        <button type="submit" disabled={loading}>
          {loading ? 'Enviando...' : 'Enviar reclamo'}
        </button>
      </form>
      {status && <p>{status}</p>}
      {error && <p>Error: {error}</p>}
    </section>
  );
}
