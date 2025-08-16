// app/graph/page.tsx
'use client';

import React, { useEffect, useRef, useState } from 'react';
import cytoscape, { ElementsDefinition } from 'cytoscape';

type Summary = { files: number; functions: number; callEdges: number; importEdges: number; totalEdges: number } | null;

export default function GraphPage() {
  const fileRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);

  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState('');
  const [elements, setElements] = useState<ElementsDefinition | null>(null);
  const [summary, setSummary] = useState<Summary>(null);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    if (!containerRef.current || !elements) return;
    if (cyRef.current) { cyRef.current.destroy(); cyRef.current = null; }

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      layout: { name: 'cose', animate: false },
      style: [
        { selector: 'node[kind = "file"]', style: { 'background-opacity': 0.2, 'border-width': 1, 'border-color': '#999', label: 'data(label)', 'font-size': 9 } },
        { selector: 'node[kind = "fn"]', style: { label: 'data(label)', 'font-size': 10 } },
        { selector: 'edge[kind = "decl"]', style: { width: 1, 'line-style': 'dotted', 'curve-style': 'bezier' } },
        { selector: 'edge[kind = "calls"]', style: { width: 2, 'target-arrow-shape': 'triangle', 'curve-style': 'bezier' } },
        { selector: 'edge[kind = "imports"]', style: { width: 1.5, 'line-color': '#888', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier' } },
      ],
    });

    cy.on('render', () => cy.resize());
    cy.ready(() => cy.fit(undefined, 30));

    cyRef.current = cy;
    return () => { cy.destroy(); cyRef.current = null; };
  }, [elements]);

  const onChoose = () => fileRef.current?.click();
  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] || null;
    setFile(f); setStatus(f ? `Selected: ${f.name}` : '');
  };

  const onUpload = async () => {
    if (!file) return;
    setUploading(true); setStatus('Uploading & parsing...');
    try {
      const form = new FormData(); form.append('file', file);
      const res = await fetch('/api/upload', { method: 'POST', body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || `Upload failed (${res.status})`);
      setElements(data.elements);
      setSummary(data.summary || null);
      setStatus(`✅ Parsed${data?.summary ? ` — files:${data.summary.files} fns:${data.summary.functions} edges:${data.summary.totalEdges}` : ''}`);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Upload failed';
      setStatus(`❌ ${msg}`);
    } finally { setUploading(false); }
  };

  const onFit = () => { cyRef.current?.fit(undefined, 30); };

  return (
    <main style={{ minHeight: '100svh', display: 'grid', gridTemplateRows: 'auto auto 1fr', gap: 12, padding: 16 }}>
      <section style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <input ref={fileRef} type="file" accept=".zip" onChange={onFile} style={{ display: 'none' }} />
        <button onClick={onChoose} style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid #e5e7eb' }}>Choose .zip</button>
        <button onClick={onUpload} disabled={!file || uploading} style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid transparent', background: (!file || uploading) ? '#9ca3af' : '#111827', color: 'white' }}>{uploading ? 'Working…' : 'Upload & Graph'}</button>
        <button onClick={onFit} disabled={!elements} style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid #e5e7eb' }}>Fit</button>
        <div role="status" aria-live="polite" style={{ marginLeft: 8 }}>{status}</div>
      </section>

      {summary && (
        <section style={{ fontSize: 12, color: '#374151' }}>
          <strong>Summary:</strong> files {summary.files} · functions {summary.functions} · call edges {summary.callEdges} · import edges {summary.importEdges} · total edges {summary.totalEdges}
        </section>
      )}

      <section style={{ border: '1px solid #e5e7eb', borderRadius: 12, minHeight: 520 }}>
        <div ref={containerRef} style={{ width: '100%', height: '100%', minHeight: 520 }} />
      </section>
    </main>
  );
}