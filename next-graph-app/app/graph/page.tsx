'use client';

import { useEffect, useRef } from 'react';
import cytoscape, { Core, NodeSingular, EdgeSingular } from 'cytoscape';

export default function GraphPage(){
  const cyRef = useRef<HTMLDivElement>(null);
  const overlaysRef = useRef<HTMLDivElement>(null);
  const wiresRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const API_BASE = ''; // Next.js rewrite proxies /api/* to Django

    let cyGraph: Core | null = null;    let graphSources: Record<string, string> = {};
    const popOwner = new Map<HTMLElement, string>();

    let fnColors = new Map<string, string>();
    let namesByFile = new Map<string, Set<string>>();
    let defsByFile = new Map<string, Set<string>>();

    const HUES = [0,30,55,85,120,165,200,230,260,290,320];
    const MATCH_COLORS = HUES.map(h => `hsl(${h} 80% 55%)`);
    const colorFor = (()=>{ const m=new Map<string,string>(); let i=0; return (k:string) => m.has(k)?m.get(k)!:(m.set(k,MATCH_COLORS[i++%MATCH_COLORS.length]), m.get(k)!); })();

    function normalizeToGraph(payload:any){
      if (!payload) return {global:{}, files:{}, sources:{}};
      if (payload.global && payload.files) return { global:payload.global, files:payload.files, sources:payload.sources || {} };
      if (payload.result) return { global:payload.result.global||{}, files:payload.result.files||{}, sources:payload.result.sources||{} };
      return { global:payload.global||{}, files:payload.files||{}, sources:payload.sources||{} };
    }

    function extractDefinitions(globalResults:any){
      const defs: Array<{name:string,file:string}> = [];
      const list = Array.isArray(globalResults?.defined) ? globalResults.defined : [];
      for (const d of list){
        const name = d?.name || d?.function || d?.id || 'anon';
        const file = d?.file || d?.path || d?.module || 'unknown';
        defs.push({ name, file });
      }
      return defs;
    }
    function extractCalls(globalResults:any, fileResults:any){
      const calls: Array<{name:string,file:string}> = [];
      const gCalled = globalResults?.called;
      if (gCalled && typeof gCalled === 'object'){
        Object.entries(gCalled).forEach(([callee, sites]: any)=>{
          (sites||[]).forEach((s:any) => calls.push({ name: callee as string, file: s?.file || s?.path || 'unknown' }));
        });
      }
      const candidateKeys = ["python","python_relations","js","js_relations","c","c_relations"];
      Object.entries(fileResults || {}).forEach(([fname, rel]: any)=>{
        if (!rel || typeof rel !== 'object') return;
        const buckets = candidateKeys.map((k:string)=>rel[k]).filter(Boolean).concat([rel]);
        for (const b of buckets){
          if (Array.isArray(b?.calls)){
            b.calls.forEach((c:any) => calls.push({ name: c?.name || c?.function || c?.callee || 'unknown', file: fname as string }));
          } else if (b?.called && typeof b.called === 'object'){
            Object.entries(b.called).forEach(([callee])=>{
              calls.push({ name: callee as string, file: fname as string });
            });
          }
        }
      });
      return calls;
    }

    function buildFunctionColorMap(globalResults:any, fileResults:any){
      const names = new Set<string>();
      (Array.isArray(globalResults?.defined) ? globalResults.defined : []).forEach((d:any)=>{ const n = d?.name || d?.function || d?.id; if(n) names.add(n); });
      const gCalled = globalResults?.called;
      if (gCalled && typeof gCalled === 'object'){ Object.keys(gCalled).forEach(n => names.add(n)); }
      const candidateKeys = ["python","python_relations","js","js_relations","c","c_relations"];
      Object.values(fileResults || {}).forEach((rel:any)=>{
        if (!rel || typeof rel !== 'object') return;
        const buckets = candidateKeys.map((k:string)=>rel[k]).filter(Boolean).concat([rel]);
        for (const b of buckets){
          if (Array.isArray(b?.calls)){
            b.calls.forEach((c:any) => { const n = c?.name || c?.function || c?.callee; if(n) names.add(n); });
          } else if (b?.called && typeof b.called === 'object'){
            Object.keys(b.called).forEach(n => names.add(n));
          }
        }
      });
      const out = new Map<string,string>(); let i=0;
      [...names].sort((a,b)=>b.length-a.length).forEach(n=>{ out.set(n, MATCH_COLORS[i++ % MATCH_COLORS.length]); });
      return out;
    }
    function buildNamesByFile(globalResults:any, fileResults:any){
      const map = new Map<string, Set<string>>();
      (Array.isArray(globalResults?.defined) ? globalResults.defined : []).forEach((d:any)=>{ const file = d?.file || d?.path || d?.module; const n = d?.name || d?.function || d?.id; if(file && n){ if(!map.has(file)) map.set(file, new Set()); map.get(file)!.add(n); } });
      const candidateKeys = ["python","python_relations","js","js_relations","c","c_relations"];
      Object.entries(fileResults || {}).forEach(([fname, rel]: any)=>{
        if(!map.has(fname as string)) map.set(fname as string, new Set());
        if (!rel || typeof rel !== 'object') return;
        const bucketList = candidateKeys.map((k:string)=>rel[k]).filter(Boolean).concat([rel]);
        for (const b of bucketList){
          if (Array.isArray(b?.calls)){ b.calls.forEach((c:any)=>{ const n = c?.name || c?.function || c?.callee; if(n) map.get(fname as string)!.add(n); }); }
          else if (b?.called && typeof b.called === 'object'){
            Object.keys(b.called).forEach(n => map.get(fname as string)!.add(n));
          }
        }
      });
      return map;
    }
    function buildDefsByFile(globalResults:any){
      const map = new Map<string, Set<string>>();
      (Array.isArray(globalResults?.defined) ? globalResults.defined : []).forEach((d:any)=>{ const file = d?.file || d?.path || d?.module; const n = d?.name || d?.function || d?.id; if(file && n){ if(!map.has(file)) map.set(file, new Set()); map.get(file)!.add(n); } });
      return map;
    }

    function buildFileGraphElements(globalResults:any, fileResults:any, sources:any){
      const defs = extractDefinitions(globalResults);
      const calls = extractCalls(globalResults, fileResults);
      const defFilesByName = new Map<string, Set<string>>();
      defs.forEach(d => { const set = defFilesByName.get(d.name) || new Set<string>(); set.add(d.file); defFilesByName.set(d.name, set); });

      const fileSet = new Set<string>([
        ...Object.keys(fileResults || {}),
        ...defs.map(d => d.file),
        ...calls.map(c => c.file),
        ...Object.keys(sources || {})
      ]);

      const nodes = [...fileSet].map(file => ({
        group: 'nodes',
        data: { id:`file|${file}`, label:(file||'unknown').split('/').slice(-1)[0], file }
      }));

      const edgeMap = new Map<string, {count:number,callees:Set<string>}>();
      for (const c of calls){
        const src = c.file;
        const targets = defFilesByName.get(c.name);
        if (!targets) continue;
        targets.forEach(dst => {
          if (src === dst) return;
          const key = `${src}||${dst}`;
          let entry = edgeMap.get(key);
          if (!entry) { entry = { count:0, callees:new Set() }; edgeMap.set(key, entry); }
          entry.count += 1; entry.callees.add(c.name);
        });
      }

      const edges:any[] = [];
      for (const [key, entry] of edgeMap.entries()){
        const [src, dst] = key.split('||');
        const color = colorFor(key);
        edges.push({
          group:'edges',
          data:{
            id:`e|${src}|${dst}`,
            source:`file|${src}`,
            target:`file|${dst}`,
            weight:entry.count,
            label:`${entry.count}`,
            tip:[...entry.callees].slice(0,6).join(', ')+(entry.callees.size>6?'…':''),
            color
          }
        });
      }
      return { elements:[...nodes, ...edges] };
    }

    function normPath(p: string) {
      // normalize windows backslashes -> '/', strip leading './', collapse '//' runs
      return (p || '')
        .replace(/\\/g, '/')   // backslashes -> '/'
        .replace(/^\.\//, '')  // leading "./"
        .replace(/\/+/g, '/'); // collapse multiple '/'
    }
    function commonSuffixLen(a:string,b:string){ let i=0; for(let ai=a.length-1,bi=b.length-1; ai>=0&&bi>=0; ai--,bi--){ if(a[ai]!==b[bi]) break; i++; } return i; }
    function bestSourceFor(file:string, sourcesMap:Record<string,string>){
      if (!file || !sourcesMap) return '';
      const req = normPath(file);
      if (req in sourcesMap) return sourcesMap[req];
      const reqBase = req.split('/').pop() as string;
      let bestKey: string | null = null, bestScore=-1;
      for (const k of Object.keys(sourcesMap)){
        const nk = normPath(k);
        if (nk === req) return sourcesMap[k];
        if (nk.split('/').pop() === reqBase){
          const s = commonSuffixLen(nk, req);
          if (s > bestScore){ bestScore = s; bestKey = k; }
        }
      }
      if (!bestKey){
        for (const k of Object.keys(sourcesMap)){
          const s = commonSuffixLen(normPath(k), req);
          if (s > bestScore){ bestScore = s; bestKey = k; }
        }
      }
      return bestKey ? sourcesMap[bestKey] : '';
    }
    function escapeHtml(s:string){ return (s||'').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'} as any)[c]); }

    function highlightCode(rawText:string, namesSet:Set<string>, fnColorMap:Map<string,string>){
      if (!rawText) return '';
      let html = escapeHtml(rawText);
      const names = Array.from(namesSet || []);
      if (!names.length) return html;
      const esc = (s:string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const group = names.sort((a,b)=>b.length-a.length).map(esc).join('|');
      const re = new RegExp(`\\b(${group})\\s*\\(`, 'g');
      html = html.replace(re, (_m, name) => {
        const col = fnColorMap.get(name) || '#eab308';
        const bg  = /^hsl\(/i.test(col) ? col.replace(/\)$/, ' / 0.18)') : 'rgba(234,179,8,0.18)';
        return `<span class="fn-hit" data-fn="${name}" style="color:${col}; background:${bg};">${name}</span>(`;
      });
      return html;
    }

    function linkPopover(pop:HTMLElement, nodeId:string){ popOwner.set(pop, nodeId); }
    function unlinkPopover(pop:HTMLElement){ popOwner.delete(pop); }
    function clearAllPopovers(){ overlaysRef.current?.querySelectorAll('.popover').forEach(el => el.remove()); popOwner.clear(); }
    function positionPopover(pop:HTMLElement, node:any, offset={dx:12, dy:-12}){
      if (!pop || !node) return;
      const pos = node.renderedPosition();
      (pop.style as any).left = `${pos.x + offset.dx}px`;
      (pop.style as any).top  = `${pos.y + offset.dy}px`;
    }
    function bringWiresToFront(){
      const overlays = overlaysRef.current;
      const wires = wiresRef.current;
      if (overlays && wires && wires.parentNode === overlays) overlays.appendChild(wires);
    }
    function clearWires(){
      const svg = wiresRef.current;
      if (!svg) return;
      while (svg.firstChild) svg.removeChild(svg.firstChild);
    }
    function redrawWires(){
      const svg = wiresRef.current;
      const overlays = overlaysRef.current;
      if (!svg || !overlays) return;
      clearWires();
      const overlayRect = overlays.getBoundingClientRect();
      const allPops = Array.from(overlays.querySelectorAll('.popover')) as HTMLElement[];
      const declMap = new Map<string, HTMLElement[]>();
      const callMap = new Map<string, HTMLElement[]>();
      allPops.forEach(pop=>{
        pop.querySelectorAll('.fn-hit').forEach((tok:any)=>{
          const el = tok as HTMLElement;
          const fn = el.dataset.fn as string;
          const role = el.dataset.role || 'call';
          const map = (role === 'decl') ? declMap : callMap;
          if (!map.has(fn)) map.set(fn, []);
          map.get(fn)!.push(el);
        });
      });
      callMap.forEach((callEls, fn) => {
        const declEls = declMap.get(fn) || [];
        if (!declEls.length) return;
        const decl = declEls[0];
        const dRect = decl.getBoundingClientRect();
        const dPt = { x: (dRect.left + dRect.right)/2 - overlayRect.left, y: (dRect.top + dRect.bottom)/2 - overlayRect.top };
        callEls.forEach(cEl => {
          const cRect = cEl.getBoundingClientRect();
          const cPt = { x: (cRect.left + cRect.right)/2 - overlayRect.left, y: (cRect.top + cRect.bottom)/2 - overlayRect.top };
          const col = fnColors.get(fn) || '#60a5fa';
          const dx = (dPt.x - cPt.x);
          const mx = cPt.x + dx * 0.5;
          const d = `M ${cPt.x.toFixed(1)} ${cPt.y.toFixed(1)} C ${mx.toFixed(1)} ${cPt.y.toFixed(1)}, ${mx.toFixed(1)} ${dPt.y.toFixed(1)}, ${dPt.x.toFixed(1)} ${dPt.y.toFixed(1)}`;
          const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
          path.setAttribute('class', 'wire');
          path.setAttribute('data-fn', fn);
          path.setAttribute('d', d);
          path.setAttribute('stroke', col);
          path.setAttribute('fill', 'none');
          path.setAttribute('stroke-width', '2');
          path.setAttribute('stroke-opacity', '.9');
          svg.appendChild(path);
        });
      });
      bringWiresToFront();
    }

    function openCodePopover(node: NodeSingular){
      const overlays = overlaysRef.current!;
      const file = node.data('file');
      const content = bestSourceFor(file, graphSources) || '';
      const names = namesByFile.get(file) || new Set<string>();

      const pop = document.createElement('div');
      pop.className = 'popover';
      pop.innerHTML = `
        <div class="ph">
          <div class="title" title="${file || ''}">${file || '(unknown file)'}</div>
          <div class="actions">
            <button class="btn" data-act="copy">Copy</button>
            <button class="btn" data-act="dl">Download</button>
            <button class="btn" data-act="x">Close</button>
          </div>
        </div>
        <pre></pre>
      ` as any;

      // 🔧 make popover absolute + clickable so it sits near nodes and buttons work
      Object.assign(pop.style, {
        position: 'absolute',
        zIndex: '4',
        pointerEvents: 'auto',
        minWidth: '260px',
        maxWidth: '460px',
        maxHeight: '260px',
        background: '#0b1220',
        border: '1px solid #334155',
        borderRadius: '10px',
        boxShadow: '0 10px 24px rgba(0,0,0,.45)',
        overflow: 'hidden',
      } as CSSStyleDeclaration);

      const head = pop.querySelector('.ph') as HTMLElement | null;
      if (head) Object.assign(head.style, {
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px',
        background: '#0f172a', borderBottom: '1px solid #1f2937', padding: '6px 8px'
      } as CSSStyleDeclaration);

      const pre = pop.querySelector('pre') as HTMLElement;
      Object.assign(pre.style, {
        margin: '0', padding: '10px', overflow: 'auto',
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace',
        fontSize: '12px', whiteSpace: 'pre-wrap', wordWrap: 'break-word', color: '#e5e7eb'
      } as CSSStyleDeclaration);

      (pre as any).innerHTML = highlightCode(content, names, fnColors) || '(no source available)';

      const defSet = defsByFile.get(file) || new Set<string>();
      pre.querySelectorAll('.fn-hit').forEach((el:any)=>{
        const n = el.dataset.fn as string;
        const role = defSet.has(n) ? 'decl' : 'call';
        el.dataset.role = role;
        if (role === 'decl') (el.style as any).boxShadow = 'inset 0 -1px 0 rgba(255,255,255,.25)';
      });

      (pop.querySelector('[data-act="x"]') as HTMLButtonElement).onclick = () => { unlinkPopover(pop); pop.remove(); redrawWires(); };
      (pop.querySelector('[data-act="copy"]') as HTMLButtonElement).onclick = async () => { try { await navigator.clipboard.writeText(content); } catch {} };
      (pop.querySelector('[data-act="dl"]') as HTMLButtonElement).onclick = () => {
        const blob = new Blob([content], { type:'text/plain;charset=utf-8' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = (file || 'source.txt').split('/').pop() || 'source.txt';
        document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(a.href);
      };

      pre.addEventListener('mouseover', (e:any)=>{
        const t = e.target.closest('.fn-hit');
        if (!t) return;
        const fn = t.dataset.fn;
        document.querySelectorAll(`.fn-hit[data-fn="${CSS.escape(fn)}"]`).forEach((x:any)=>x.classList.add('hover'));
        document.querySelectorAll(`.wire[data-fn="${CSS.escape(fn)}"]`).forEach((w:any)=>{ (w as SVGPathElement).style.strokeWidth = '3.5'; (w as SVGPathElement).style.strokeOpacity = '1'; });
      });
      pre.addEventListener('mouseout', (e:any)=>{
        const t = e.target.closest('.fn-hit');
        if (!t) return;
        const fn = t.dataset.fn;
        document.querySelectorAll(`.fn-hit[data-fn="${CSS.escape(fn)}"]`).forEach((x:any)=>x.classList.remove('hover'));
        document.querySelectorAll(`.wire[data-fn="${CSS.escape(fn)}"]`).forEach((w:any)=>{ (w as SVGPathElement).style.strokeWidth = '2'; (w as SVGPathElement).style.strokeOpacity = '.9'; });
      });
      pre.addEventListener('scroll', () => { redrawWires(); }, { passive:true } as any);

      overlays.appendChild(pop);
      linkPopover(pop, node.id());
      positionPopover(pop, node, { dx: 14, dy: -14 });
      bringWiresToFront();
      redrawWires();
    }

    function applyFilters(){
      if (!cyGraph) return;
      const fileSub = (document.getElementById('fileFilter') as HTMLInputElement)?.value?.toLowerCase().trim() || '';
      const nodeQ   = (document.getElementById('nodeQuery') as HTMLInputElement)?.value?.toLowerCase().trim() || '';
      cyGraph.batch(()=>{
        cyGraph!.elements().style('display','element');
        if (fileSub){
          cyGraph!.nodes().forEach((n: NodeSingular) => {
            const f = (n.data('file')||'').toLowerCase();
            if (!f.includes(fileSub)) n.style('display','none');
        });
        }
        if (nodeQ){
          cyGraph!.nodes().forEach((n: NodeSingular) => {
              const lbl = (n.data('label')||'').toLowerCase();
              if (!lbl.includes(nodeQ)) n.style('display','none');
          });
        }
          cyGraph!.edges().forEach((e: EdgeSingular) => {
              const s = e.source().style('display') !== 'none';
              const t = e.target().style('display') !== 'none';
              if (!(s && t)) e.style('display','none');
          });
      });
    }
    function clearFilters(){
      (document.getElementById('fileFilter') as HTMLInputElement).value = '';
      (document.getElementById('nodeQuery') as HTMLInputElement).value = '';
      cyGraph?.elements().style('display','element');
    }

    function renderFileGraph(globalResults:any, fileResults:any, sources:any){
      const { elements } = buildFileGraphElements(globalResults, fileResults, sources);
      const container = cyRef.current!;
      if (cyGraph && typeof (cyGraph as any).destroy === 'function'){ try { (cyGraph as any).destroy(); } catch {} }
      clearAllPopovers();
      clearWires();
      const style:any[] = [
        { selector:'node',
          style:{
            'background-color':'#0ea5e9',
            'label':'data(label)',
            'color':'#e5e7eb',
            'font-size':12,
            'text-wrap':'wrap',
            'text-max-width':240,
            'border-width':1,
            'border-color':'#334155',
            'padding':'6px',
            'shape':'round-rectangle'
          }
        },
        { selector:'edge',
          style:{
            'curve-style':'bezier',
            'width': (ele:any) => Math.min(8, 1 + (parseInt(ele.data('weight')||1, 10) * 0.8)),
            'line-color':'data(color)',
            'target-arrow-shape':'triangle',
            'target-arrow-color':'data(color)',
            'label':'data(label)',
            'font-size':9,
            'color':'#cbd5e1',
            'text-background-opacity':0.15,
            'text-background-color':'#0b1220',
            'text-background-shape':'round-rectangle',
            'text-background-padding':2
          }
        },
        { selector:':selected', style:{ 'border-width':3, 'border-color':'#f59e0b' } }
      ];
      cyGraph = cytoscape({ container, elements, style, layout:{ name:'cose', animate:false, padding:24 } });
      cyGraph.resize();

      cyGraph.off('tap', 'node');
      cyGraph.on('tap', 'node', (evt:any) => openCodePopover(evt.target));

      const repositionAll = () => {
        popOwner.forEach((nodeId, el) => {
            const n = cyGraph!.getElementById(nodeId) as unknown as NodeSingular;
            if (n && (n as any).length) positionPopover(el, n);
        });
        redrawWires();
      };
      cyGraph.on('pan zoom render', repositionAll);
      cyGraph.on('drag position', 'node', (evt:any) => {
        popOwner.forEach((nid, el) => { if (nid === evt.target.id()) positionPopover(el, evt.target); });
        redrawWires();
      });
      cyGraph.on('layoutstop', repositionAll);
      bringWiresToFront();
    }

    // bind sidebar UI after DOM is ready
    const elStatus = document.getElementById('status')!;
    const elZip = document.getElementById('zipFile') as HTMLInputElement;
    const elForm = document.getElementById('zipForm') as HTMLFormElement;
    function setStatus(msg: string) { elStatus.textContent = msg || ''; }

    elForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!elZip.files?.length) return;
      setStatus('Uploading & parsing…');

      const url = `${API_BASE}/api/code/parse-zip/`;

      try {
        const fd = new FormData();
        fd.append('file', elZip.files[0]);

        const res = await fetch(url, { method: 'POST', body: fd });
        const raw = await res.text();

        if (!res.ok) {
          let msg = `Error: ${res.status}`;
          try {
            const j = JSON.parse(raw);
            if (j.detail || j.error || j.message) {
              msg += ` – ${j.detail || j.error || j.message}`;
            }
          } catch {
            msg += ' – ' + raw.replace(/<[^>]+>/g, '').slice(0, 200);
          }
          console.error('API error body:', raw);
          setStatus(msg);
          return;
        }

        let payload: any;
        try {
          payload = JSON.parse(raw);
        } catch (e) {
          console.error('JSON parse error:', e, raw);
          setStatus('Bad JSON from API');
          return;
        }

        const { global, files, sources } = normalizeToGraph(payload);
        graphSources = sources || {};
        fnColors = buildFunctionColorMap(global, files);
        namesByFile = buildNamesByFile(global, files);
        defsByFile = buildDefsByFile(global);

        const filesCount = Object.keys(files || {}).length || Object.keys(graphSources || {}).length;
        const defsCount = Array.isArray(global?.defined) ? global.defined.length : 0;
        const callsCount = Object.values((global?.metrics || {}) as any)
          .reduce((a: number, m: any) => a + ((m || {}).num_calls || 0), 0);

        document.getElementById('metrics')!.textContent =
          `files: ${filesCount} • definitions: ${defsCount} • calls: ${callsCount}`;

        renderFileGraph(global, files, graphSources);
        setStatus('Done.');
      } catch (err) {
        console.error(err);
        setStatus('Request failed.');
      }
    });

    document.getElementById('resetBtn')!.addEventListener('click', ()=>{
      cyGraph?.destroy(); cyGraph = null;
      clearAllPopovers();
      clearWires();
      (document.getElementById('metrics')!).textContent = '—';
      (document.getElementById('status')!).textContent = '';
    });
    document.getElementById('applyFilter')!.addEventListener('click', applyFilters);
    document.getElementById('clearFilter')!.addEventListener('click', clearFilters);
    window.addEventListener('resize', () => redrawWires());

    return () => { cyGraph?.destroy(); };
  }, []);

  return (
    <div className="wrap" style={{display:'grid', gridTemplateColumns:'340px 1fr', height:'100vh'}}>
      <aside className="side" style={{padding:16, borderRight:'1px solid #1f2937', background:'#111827', overflow:'auto'}}>
        <h2 className="h" style={{fontWeight:600, margin:'0 0 8px'}}>Project Graph</h2>
        <p className="muted">
          Upload a <code>.zip</code>. We build a <b>file-level</b> call graph.<br/>
          Click a node to open a popover with its code. Declarations & calls share a unique color.<br/>
          Foreground lines connect call sites ↔ their declarations between popovers.
        </p>

        <div className="box" style={{background:'#0b1220', border:'1px solid #1f2937', borderRadius:12, padding:12, margin:'12px 0'}}>
          <form id="zipForm">
            <div className="row" style={{display:'flex', gap:8, alignItems:'center', margin:'8px 0'}}>
              <input id="zipFile" type="file" name="file" accept=".zip" required style={{width:'100%'}} />
            </div>
            <div className="row" style={{display:'flex', gap:8, alignItems:'center', margin:'8px 0'}}>
              <button className="btn" type="submit" style={{cursor:'pointer', background:'#1e293b', border:'1px solid #334155', color:'#e2e8f0', padding:'8px 12px', borderRadius:10}}>Build graph</button>
              <button className="btn" type="button" id="resetBtn" style={{cursor:'pointer', background:'#1e293b', border:'1px solid #334155', color:'#e2e8f0', padding:'8px 12px', borderRadius:10}}>Reset</button>
            </div>
          </form>
          <div id="status" className="muted" style={{color:'#9ca3af'}}></div>
        </div>

        <div className="box" style={{background:'#0b1220', border:'1px solid #1f2937', borderRadius:12, padding:12, margin:'12px 0'}}>
          <h3 className="h" style={{fontWeight:600, margin:'0 0 8px'}}>Metrics</h3>
          <div id="metrics" className="muted" style={{color:'#9ca3af'}}>—</div>
        </div>

        <div className="box" style={{background:'#0b1220', border:'1px solid #1f2937', borderRadius:12, padding:12, margin:'12px 0'}}>
          <h3 className="h" style={{fontWeight:600, margin:'0 0 8px'}}>Filters</h3>
          <div className="row" style={{display:'flex', gap:8, alignItems:'center', margin:'8px 0'}}><input id="fileFilter" type="text" placeholder="Filter by filename substring…" style={{width:'100%', padding:'8px 10px', borderRadius:10, border:'1px solid #334155', background:'#0b1220', color:'#e5e7eb'}}/></div>
          <div className="row" style={{display:'flex', gap:8, alignItems:'center', margin:'8px 0'}}><input id="nodeQuery" type="text" placeholder="Find node (label)…" style={{width:'100%', padding:'8px 10px', borderRadius:10, border:'1px solid #334155', background:'#0b1220', color:'#e5e7eb'}}/></div>
          <div className="row" style={{display:'flex', gap:8, alignItems:'center', margin:'8px 0'}}>
            <button className="btn" id="applyFilter" type="button"
              style={{ cursor:'pointer', background:'#1e293b', border:'1px solid #334155', color:'#e2e8f0', padding:'8px 12px', borderRadius:10 }}>
              Apply
            </button>
            <button className="btn" id="clearFilter" type="button" style={{cursor:'pointer', background:'#1e293b', border:'1px solid #334155', color:'#e2e8f0', padding:'8px 12px', borderRadius:10}}>Clear</button>
          </div>
        </div>
      </aside>

      <main className="main" style={{position:'relative'}}>
        <div id="cy" ref={cyRef} style={{position:'absolute', inset:0 as any, zIndex:1}} />
        <div id="overlays" ref={overlaysRef} style={{position:'absolute', inset:0 as any, zIndex:3, pointerEvents:'none'}}>
          <svg id="wires" ref={wiresRef} style={{position:'absolute', inset:0 as any, width:'100%', height:'100%', overflow:'visible', zIndex:5, pointerEvents:'none'}}/>
        </div>
      </main>
    </div>
  );
}
