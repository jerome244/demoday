'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

type FieldErrors = Record<string, string[]>;

export default function RegisterPage() {
  const router = useRouter();

  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [status, setStatus] = useState<string>('');
  const [debug, setDebug] = useState<any>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [submitting, setSubmitting] = useState(false);

  // If you add basePath in next.config, expose it as NEXT_PUBLIC_BASE_PATH
  const base = process.env.NEXT_PUBLIC_BASE_PATH || '';

  function isValidEmail(v: string) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
  }

  function softStrengthIssues(pw: string): string[] {
    const issues: string[] = [];
    if (pw.length < 8) issues.push('Password must be at least 8 characters.');
    const hasLetter = /[A-Za-z]/.test(pw);
    const hasNumber = /\d/.test(pw);
    const hasSymbol = /[^A-Za-z0-9]/.test(pw);
    if (!(hasLetter && hasNumber && hasSymbol)) {
      issues.push('Use letters, numbers, and a symbol.');
    }
    return issues;
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (submitting) return;

    setSubmitting(true);
    setFieldErrors({});
    setDebug(null);
    setStatus('');

    if (password !== confirm) {
      setFieldErrors({
        password: ['Passwords do not match.'],
        confirm: ['Passwords do not match.'],
      });
      setSubmitting(false);
      return;
    }

    // Optional client-side strength checks (keeps UX friendly with Django validators)
    const issues = softStrengthIssues(password);
    if (issues.length) {
      setFieldErrors({ password: issues });
      setSubmitting(false);
      return;
    }

    const emailTrim = email.trim();
    const emailLooksValid = emailTrim ? isValidEmail(emailTrim) : false;

    const uname = (username || (emailLooksValid ? emailTrim.split('@')[0] : '')).trim();
    if (!uname) {
      setFieldErrors({
        username: ['Username required (or enter a valid email so we can derive one).'],
      });
      setSubmitting(false);
      return;
    }

    // Djoser payload: username + password required; email optional (must be valid if present)
    const payload: Record<string, string> = { username: uname, password };
    if (emailLooksValid) payload.email = emailTrim;

    setStatus('Creating account…');

    try {
      const res = await fetch(`${base}/api/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        // Try to surface DRF/Djoser style field errors first
        const backendJson: any =
          data?.backend?.json ?? // our proxy shape
          (typeof data === 'object' ? data : null); // direct pass-through fallback

        if (backendJson && typeof backendJson === 'object') {
          const fe: FieldErrors = { ...(backendJson as FieldErrors) };
          if (backendJson.detail) fe.non_field_errors = [String(backendJson.detail)];
          setFieldErrors(fe);
        }
        setDebug(data);
        throw new Error(data?.error || `Registration failed (${res.status})`);
      }

      setStatus('✅ Account created');
      setFieldErrors({});
      setDebug(null);
      // Optional: clear fields
      setEmail('');
      setUsername('');
      setPassword('');
      setConfirm('');

      // Go to login; replace to avoid leaving /register in history
      router.replace('/login');
    } catch (err: any) {
      setStatus(`❌ ${err?.message || 'Registration failed'}`);
      // (optional) clear password fields after failure
      setPassword('');
      setConfirm('');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main style={{ minHeight: '100svh', display: 'grid', placeItems: 'center', padding: 24 }}>
      <form
        onSubmit={onSubmit}
        noValidate
        style={{ width: 420, border: '1px solid #e5e7eb', borderRadius: 12, padding: 20 }}
      >
        <h1 style={{ margin: 0, fontSize: 24 }}>Register</h1>

        {fieldErrors.non_field_errors?.length ? (
          <ul style={{ color: '#b91c1c', marginTop: 12 }}>
            {fieldErrors.non_field_errors.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        ) : null}

        <label style={{ display: 'block', marginTop: 14 }}>
          Email (optional)
          <input
            type="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            placeholder="you@example.com"
            // NOTE: email is optional, so no 'required'
            style={{ width: '100%', marginTop: 6, padding: 8, border: '1px solid #e5e7eb', borderRadius: 8 }}
          />
          <small style={{ color: '#6b7280' }}>Leave blank or enter a valid email format.</small>
        </label>
        {fieldErrors.email?.length ? (
          <ul style={{ color: '#b91c1c', marginTop: 6 }}>
            {fieldErrors.email.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        ) : null}

        <label style={{ display: 'block', marginTop: 12 }}>
          Username (auto if email is valid)
          <input
            value={username}
            onChange={e => setUsername(e.target.value)}
            placeholder="auto from email if blank"
            style={{ width: '100%', marginTop: 6, padding: 8, border: '1px solid #e5e7eb', borderRadius: 8 }}
          />
        </label>
        {fieldErrors.username?.length ? (
          <ul style={{ color: '#b91c1c', marginTop: 6 }}>
            {fieldErrors.username.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        ) : null}

        <label style={{ display: 'block', marginTop: 12 }}>
          Password
          <input
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            required
            style={{ width: '100%', marginTop: 6, padding: 8, border: '1px solid #e5e7eb', borderRadius: 8 }}
          />
        </label>
        {fieldErrors.password?.length ? (
          <ul style={{ color: '#b91c1c', marginTop: 6 }}>
            {fieldErrors.password.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        ) : null}

        <label style={{ display: 'block', marginTop: 12 }}>
          Confirm Password
          <input
            type="password"
            value={confirm}
            onChange={e => setConfirm(e.target.value)}
            required
            style={{ width: '100%', marginTop: 6, padding: 8, border: '1px solid #e5e7eb', borderRadius: 8 }}
          />
        </label>
        {fieldErrors.confirm?.length ? (
          <ul style={{ color: '#b91c1c', marginTop: 6 }}>
            {fieldErrors.confirm.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        ) : null}

        <button
          type="submit"
          disabled={submitting}
          style={{
            marginTop: 16,
            padding: '10px 14px',
            borderRadius: 8,
            background: submitting ? '#6b7280' : '#111827',
            color: 'white',
            border: '1px solid transparent',
            cursor: submitting ? 'not-allowed' : 'pointer',
          }}
        >
          {submitting ? 'Creating…' : 'Create account'}
        </button>

        <div role="status" aria-live="polite" style={{ marginTop: 10, minHeight: 20 }}>{status}</div>

        {debug && (
          <pre
            style={{
              marginTop: 10,
              background: '#f9fafb',
              border: '1px solid #e5e7eb',
              padding: 10,
              borderRadius: 8,
              maxHeight: 220,
              overflow: 'auto',
            }}
          >
            {JSON.stringify(debug, null, 2)}
          </pre>
        )}
      </form>
    </main>
  );
}
