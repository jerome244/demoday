import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Project Graph',
  description: 'Explore project graphs with Cytoscape',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body
        style={{
          background: '#0f172a',
          color: '#e5e7eb',
          minHeight: '100vh',
          margin: 0,
        }}
      >
        {children}
      </body>
    </html>
  );
}
