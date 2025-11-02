import Link from 'next/link';

const routes = [
  { href: '/', label: 'Inicio' },
  { href: '/tramites', label: 'Trámites' },
  { href: '/aranceles', label: 'Aranceles' },
  { href: '/transparencia', label: 'Transparencia' },
  { href: '/indices', label: 'Índices' },
  { href: '/contacto', label: 'Contacto' },
  { href: '/admin', label: 'Admin' }
];

export default function Layout({ children }) {
  return (
    <>
      <header>
        <h1>Notaría Ejemplo</h1>
        <p>Portal público conforme a Ley 21.772</p>
        <nav>
          {routes.map((route) => (
            <Link key={route.href} href={route.href}>{route.label}</Link>
          ))}
        </nav>
      </header>
      <main>{children}</main>
    </>
  );
}
