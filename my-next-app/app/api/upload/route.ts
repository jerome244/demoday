// app/api/upload/route.ts
import { NextResponse } from 'next/server';
import AdmZip, { IZipEntry } from 'adm-zip';
import * as babelParser from '@babel/parser';
import traverse, { NodePath } from '@babel/traverse';
import * as t from '@babel/types';
import path from 'path';

export const runtime = 'nodejs';

// --- Config ---------------------------------------------------------------
const CODE_EXTS = ['.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.vue', '.py'] as const;
const MAX_BYTES = 40 * 1024 * 1024; // 40 MB

// --- Utils ----------------------------------------------------------------
function isCodeFile(name: string): boolean {
  const lower = name.toLowerCase();
  if (lower.includes('node_modules/')) return false;
  if (lower.includes('__pycache__/')) return false;
  return CODE_EXTS.some((ext) => lower.endsWith(ext));
}

function sanitizeEntryName(entryName: string): string {
  const raw = entryName.replace(/\\/g, '/').replace(/^\/+/, '');
  const safeParts: string[] = [];
  for (const part of raw.split('/')) {
    if (!part || part === '.' || part === '..') continue;
    safeParts.push(part);
  }
  return safeParts.join('/');
}

function extractVueScript(src: string): string {
  const m = src.match(/<script[^>]*>([\s\S]*?)<\/script>/i);
  return m ? m[1] : '';
}

function parseJsTs(filename: string, source: string): t.File {
  return babelParser.parse(source, {
    sourceFilename: filename,
    sourceType: 'unambiguous',
    plugins: [
      'jsx',
      'typescript',
      'classProperties',
      'classPrivateProperties',
      'classPrivateMethods',
      'decorators-legacy',
      'objectRestSpread',
      'topLevelAwait',
      'importAssertions',
      'dynamicImport',
    ],
  }) as unknown as t.File;
}

function toPosix(p: string): string { return p.replace(/\\/g, '/'); }

// Resolve JS/TS import path to a file entry
function resolveJsImport(fromFile: string, src: string, allFiles: Set<string>): string | null {
  if (!src) return null; if (src.startsWith('http')) return null;
  let candidate = src;
  if (src.startsWith('.')) {
    const dir = toPosix(path.posix.dirname(fromFile));
    candidate = toPosix(path.posix.normalize(path.posix.join(dir, src)));
  }
  if (allFiles.has(candidate)) return candidate;
  const tryExts = ['', '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '/index.js', '/index.ts', '/index.tsx'];
  for (const ext of tryExts) { const c = candidate + ext; if (allFiles.has(c)) return c; }
  return null;
}

// Resolve Python module import to a file entry
function resolvePyModule(fromFile: string, module: string, allFiles: Set<string>): string | null {
  let mod = module.trim(); if (!mod) return null;
  const fromDir = path.posix.dirname(fromFile);
  const toCandidates = (base: string) => [`${base}.py`, `${base}/__init__.py`];

  // Relative module: from .foo import bar  or  from .. import x
  if (mod.startsWith('.')) {
    const dotsMatch = mod.match(/^\.+/);
    const dots = dotsMatch ? dotsMatch[0].length : 0;
    let base = fromDir;
    for (let i = 0; i < dots; i++) base = path.posix.dirname(base);
    const rest = mod.slice(dots).replace(/^\./, '').replace(/\./g, '/');
    const basePath = rest ? toPosix(path.posix.join(base, rest)) : base;
    for (const c of toCandidates(basePath)) if (allFiles.has(c)) return c;
    for (const c of toCandidates(basePath)) { const hit = [...allFiles].find(f => f.endsWith(c)); if (hit) return hit; }
    return null;
  }
  // Absolute dotted module
  const exact = mod.replace(/\./g, '/');
  for (const c of toCandidates(exact)) if (allFiles.has(c)) return c;
  const suffixHit = [...allFiles].find(f => f.endsWith(`/${exact}.py`) || f.endsWith(`/${exact}/__init__.py`) || f === `${exact}.py` || f === `${exact}/__init__.py`);
  return suffixHit || null;
}

// Very lightweight Python analyzer: decls + calls (+ imports)
function analyzePython(_file: string, source: string): { decls: Set<string>; calls: Array<{ caller?: string; callee: string }>; imports: string[] } {
  const decls = new Set<string>();
  const calls: Array<{ caller?: string; callee: string }> = [];
  const imports: string[] = [];

  const lines = source.replace(/\r\n?/g, '\n').split('\n');
  const stack: Array<{ name: string; indent: number }> = [];

  const defRe = /^\s*def\s+([A-Za-z_]\w*)\s*\(/;
  const importRe1 = /^\s*import\s+([A-Za-z_][\w\.]*)(?:\s+as\s+[A-Za-z_][\w]*)?/;
  const importRe2 = /^\s*from\s+([\.A-Za-z_][\w\.]*)\s+import\s+([A-Za-z_\*][\w\*,\s]*)/;
  const callRe = /\b([A-Za-z_]\w*)\s*\(/g;

  for (const rawLine of lines) {
    const line = rawLine;
    const indent = (line.match(/^\s*/)?.[0] || '').length;

    // def blocks
    const mdef = defRe.exec(line);
    if (mdef) {
      const fname = mdef[1];
      while (stack.length && indent <= stack[stack.length - 1].indent) stack.pop();
      stack.push({ name: fname, indent });
      decls.add(fname);
      continue; // skip scanning calls on the def line
    }

    // imports
    let m: RegExpExecArray | null;
    if ((m = importRe1.exec(line))) imports.push(m[1]);
    else if ((m = importRe2.exec(line))) imports.push(m[1]);

    // calls (skip member calls like obj.method by checking preceding char)
    callRe.lastIndex = 0;
    let cm: RegExpExecArray | null;
    while ((cm = callRe.exec(line))) {
      const start = cm.index;
      if (start > 0 && line[start - 1] === '.') continue; // skip obj.method(
      const callee = cm[1];
      const caller = stack.length ? stack[stack.length - 1].name : undefined;
      calls.push({ caller, callee });
    }
  }

  return { decls, calls, imports };
}

export async function POST(req: Request) {
  try {
    const form = await req.formData();
    const file = form.get('file') as File | null;
    if (!file) return NextResponse.json({ error: 'No file provided' }, { status: 400 });
    if (file.size > MAX_BYTES) return NextResponse.json({ error: `Zip too large (> ${MAX_BYTES / (1024 * 1024)}MB)` }, { status: 413 });

    const buf = Buffer.from(await file.arrayBuffer());
    const zip = new AdmZip(buf);

    // Gather entries & cache data
    const entries: string[] = zip
      .getEntries()
      .filter((e: IZipEntry) => !e.isDirectory)
      .map((e: IZipEntry) => sanitizeEntryName(e.entryName))
      .filter((n: string) => n && isCodeFile(n));

    const allFiles = new Set(entries);

    // State
    const declaredBy = new Map<string, Set<string>>(); // name -> set(files)
    const fileDecls = new Map<string, Set<string>>();   // file -> set(names)
    const rawCalls: Array<{ file: string; caller?: string; callee: string }> = [];
    const rawImportsJs: Array<{ file: string; source: string }> = [];
    const rawImportsPy: Array<{ file: string; module: string }> = [];

    for (const entryName of entries) {
      const ext = path.posix.extname(entryName).toLowerCase();
      let code = zip.getEntry(entryName)!.getData().toString('utf8');

      if (ext === '.vue') {
        code = extractVueScript(code);
        if (!code.trim()) continue;
      }

      if (ext === '.py') {
        const { decls, calls, imports } = analyzePython(entryName, code);
        fileDecls.set(entryName, new Set(decls));
        for (const d of decls) {
          if (!declaredBy.has(d)) declaredBy.set(d, new Set());
          declaredBy.get(d)!.add(entryName);
        }
        for (const c of calls) rawCalls.push({ file: entryName, caller: c.caller, callee: c.callee });
        for (const mod of imports) rawImportsPy.push({ file: entryName, module: mod });
        continue;
      }

      // JS/TS path via Babel
      let ast: t.File | null = null;
      try { ast = parseJsTs(entryName, code); } catch (_err: unknown) { continue; }

      const thisFileDecls = new Set<string>();
      fileDecls.set(entryName, thisFileDecls);

      const fnStack: string[] = [];
      const pushCtx = (n?: string) => fnStack.push(n || '');
      const popCtx = () => { fnStack.pop(); };
      const current = () => fnStack[fnStack.length - 1] || undefined;

      traverse(ast, {
        Function(path: NodePath<t.Function>) {
          let fname: string | undefined;
          const node = path.node;
          if (t.isFunctionDeclaration(node) && node.id?.name) {
            fname = node.id.name;
          } else if (t.isFunctionExpression(node) || t.isArrowFunctionExpression(node)) {
            const parent = path.parentPath?.node as t.Node | undefined;
            if (parent && t.isVariableDeclarator(parent) && t.isIdentifier(parent.id)) {
              fname = parent.id.name;
            } else if (parent && t.isClassMethod(parent) && t.isIdentifier(parent.key)) {
              fname = parent.key.name;
            }
          }
          if (fname) {
            thisFileDecls.add(fname);
            if (!declaredBy.has(fname)) declaredBy.set(fname, new Set());
            declaredBy.get(fname)!.add(entryName);
          }
          pushCtx(fname);
        },
        FunctionExit(_p: NodePath<t.Function>) { popCtx(); },
        VariableDeclarator(path: NodePath<t.VariableDeclarator>) {
          const id = path.node.id; const init = path.node.init;
          if (t.isIdentifier(id) && (t.isFunctionExpression(init) || t.isArrowFunctionExpression(init))) {
            const name = id.name;
            thisFileDecls.add(name);
            if (!declaredBy.has(name)) declaredBy.set(name, new Set());
            declaredBy.get(name)!.add(entryName);
          }
        },
        FunctionDeclaration(path: NodePath<t.FunctionDeclaration>) {
          const id = path.node.id; if (id?.name) {
            const name = id.name;
            thisFileDecls.add(name);
            if (!declaredBy.has(name)) declaredBy.set(name, new Set());
            declaredBy.get(name)!.add(entryName);
          }
        },
        CallExpression(path: NodePath<t.CallExpression>) {
          const callee = path.node.callee;
          if (t.isIdentifier(callee)) rawCalls.push({ file: entryName, caller: current(), callee: callee.name });
          if (t.isIdentifier(callee) && callee.name === 'require') {
            const arg = path.node.arguments?.[0] as t.StringLiteral | undefined;
            if (arg && typeof arg.value === 'string') rawImportsJs.push({ file: entryName, source: arg.value });
          }
        },
        ImportDeclaration(path: NodePath<t.ImportDeclaration>) {
          const src = path.node.source?.value;
          if (typeof src === 'string') rawImportsJs.push({ file: entryName, source: src });
        },
      });
    }

    // Build nodes/edges -----------------------------------------------------
    type Node = { data: { id: string; label: string; kind: 'file' | 'fn' } };
    type Edge = { data: { id: string; source: string; target: string; kind: 'decl' | 'calls' | 'imports' } };

    const nodes: Node[] = [];
    const edges: Edge[] = [];

    for (const file of fileDecls.keys()) nodes.push({ data: { id: `file:${file}`, label: file, kind: 'file' } });

    let fnCount = 0;
    for (const [file, fset] of fileDecls.entries()) {
      for (const fname of fset) {
        nodes.push({ data: { id: `fn:${file}#${fname}`, label: `${fname}()`, kind: 'fn' } });
        edges.push({ data: { id: `decl:${file}#${fname}`, source: `file:${file}`, target: `fn:${file}#${fname}`, kind: 'decl' } });
        fnCount++;
      }
    }

    let eidx = 0; let callEdges = 0; let importEdges = 0;
    for (const { file, caller, callee } of rawCalls) {
      const callerId = caller ? `fn:${file}#${caller}` : `file:${file}`;
      const targets = declaredBy.get(callee);
      if (!targets || targets.size === 0) continue;
      for (const tfile of targets) {
        const targetId = `fn:${tfile}#${callee}`;
        edges.push({ data: { id: `call:${eidx++}`, source: callerId, target: targetId, kind: 'calls' } });
        callEdges++;
      }
    }

    // JS imports → file→file
    for (const { file, source } of rawImportsJs) {
      const resolved = resolveJsImport(file, source, new Set(fileDecls.keys()));
      if (!resolved) continue;
      edges.push({ data: { id: `imp:${eidx++}`, source: `file:${file}`, target: `file:${resolved}`, kind: 'imports' } });
      importEdges++;
    }

    // Python imports → file→file
    for (const { file, module } of rawImportsPy) {
      const resolved = resolvePyModule(file, module, new Set(fileDecls.keys()));
      if (!resolved) continue;
      edges.push({ data: { id: `imp:${eidx++}`, source: `file:${file}`, target: `file:${resolved}`, kind: 'imports' } });
      importEdges++;
    }

    // Fallback: if still no nodes, at least show files present in entries
    if (nodes.length === 0) {
      for (const f of entries) nodes.push({ data: { id: `file:${f}`, label: f, kind: 'file' } });
    }

    const summary = {
      files: fileDecls.size,
      functions: fnCount,
      callEdges,
      importEdges,
      totalEdges: edges.length,
    };

    return NextResponse.json({ elements: { nodes, edges }, summary });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Server error';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}