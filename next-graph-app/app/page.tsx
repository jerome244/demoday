import Link from 'next/link';

export default function Home() {
  return (
    <main
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        background: '#0f172a',
        color: '#e5e7eb',
        textAlign: 'center',
        padding: '2rem',
      }}
    >
      <h1 style={{ fontSize: '2rem', marginBottom: '1rem' }}>Welcome to Project Graph</h1>
      <p style={{ marginBottom: '2rem', maxWidth: '500px', lineHeight: '1.5' }}>
        Upload your project as a zip file and explore its file-level call graph interactively.
      </p>
      <Link
        href="/graph"
        style={{
          background: '#1e293b',
          color: '#e2e8f0',
          padding: '0.75rem 1.5rem',
          borderRadius: '0.5rem',
          border: '1px solid #334155',
          textDecoration: 'none',
          fontWeight: 500,
        }}
      >
        Go to Graph View →
      </Link>
    </main>
  );
}
