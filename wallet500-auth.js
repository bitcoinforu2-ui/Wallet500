(() => {
  'use strict';

  const CLIENT_ID = '639379001638-uc8gc79gokfoe2ltmt29880g56durdmi.apps.googleusercontent.com';
  const ALLOWED_EMAILS = new Set(['bitcoinforu2@gmail.com']);
  const STORAGE_KEY = 'wallet500_google_auth_v1';
  const GSI_SRC = 'https://accounts.google.com/gsi/client';

  function decodeJwtPayload(token) {
    try {
      const part = token.split('.')[1];
      if (!part) return null;
      const normalized = part.replace(/-/g, '+').replace(/_/g, '/');
      const padded = normalized + '='.repeat((4 - (normalized.length % 4 || 4)) % 4);
      const json = decodeURIComponent(Array.prototype.map.call(atob(padded), c =>
        '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)
      ).join(''));
      return JSON.parse(json);
    } catch (_) {
      return null;
    }
  }

  function getStoredSession() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      const session = JSON.parse(raw);
      if (!session || !session.email || !session.exp) return null;
      if (Date.now() >= Number(session.exp) * 1000) return null;
      if (!ALLOWED_EMAILS.has(String(session.email).toLowerCase())) return null;
      return session;
    } catch (_) {
      return null;
    }
  }

  function storeSession(payload) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      email: String(payload.email || '').toLowerCase(),
      name: String(payload.name || payload.email || ''),
      picture: String(payload.picture || ''),
      exp: Number(payload.exp || 0)
    }));
  }

  function addStyles() {
    if (document.getElementById('w500-auth-style')) return;
    const style = document.createElement('style');
    style.id = 'w500-auth-style';
    style.textContent = `
      #w500-auth-gate{position:fixed;inset:0;z-index:2147483647;background:#05090df2;backdrop-filter:blur(14px);display:flex;align-items:center;justify-content:center;padding:18px;font-family:Arial,sans-serif}
      #w500-auth-card{width:min(420px,100%);background:#0a141b;border:1px solid #1f5568;border-radius:18px;padding:22px;color:#eafcff;box-shadow:0 24px 70px #000a;text-align:center;direction:rtl}
      #w500-auth-card h2{margin:0 0 8px;font-size:24px}#w500-auth-card p{margin:0 0 18px;color:#9fc4d1;line-height:1.5}
      #w500-auth-btn{display:flex;justify-content:center;min-height:44px}#w500-auth-err{min-height:20px;margin-top:12px;color:#ff7d91;font-size:12px}
      #w500-auth-chip{position:fixed;top:8px;left:8px;z-index:2147483001;background:#08141be8;border:1px solid #215a6d;border-radius:999px;color:#d9f7ff;padding:6px 9px;font:700 10px Arial,sans-serif;display:flex;gap:7px;align-items:center;box-shadow:0 3px 12px #0008}
      #w500-auth-chip button{border:0;background:transparent;color:#7fdcf3;font:700 10px Arial,sans-serif;padding:0;cursor:pointer}
    `;
    document.head.appendChild(style);
  }

  function removeGate() {
    const gate = document.getElementById('w500-auth-gate');
    if (gate) gate.remove();
  }

  function showChip(session) {
    if (document.getElementById('w500-auth-chip')) return;
    const chip = document.createElement('div');
    chip.id = 'w500-auth-chip';
    const email = document.createElement('span');
    email.textContent = session.email;
    const logout = document.createElement('button');
    logout.type = 'button';
    logout.textContent = 'יציאה';
    logout.addEventListener('click', () => {
      localStorage.removeItem(STORAGE_KEY);
      try { if (window.google?.accounts?.id) google.accounts.id.disableAutoSelect(); } catch (_) {}
      location.reload();
    });
    chip.append(email, logout);
    document.body.appendChild(chip);
  }

  function showGate() {
    if (document.getElementById('w500-auth-gate')) return;
    const gate = document.createElement('div');
    gate.id = 'w500-auth-gate';
    gate.innerHTML = `
      <div id="w500-auth-card" role="dialog" aria-modal="true" aria-label="Wallet500 Google Sign-In">
        <h2>Wallet500</h2>
        <p>גישה למערכת מחייבת כניסה עם חשבון Google המאושר לפרויקט.</p>
        <div id="w500-auth-btn"></div>
        <div id="w500-auth-err"></div>
      </div>`;
    document.body.appendChild(gate);
  }

  function setError(text) {
    const el = document.getElementById('w500-auth-err');
    if (el) el.textContent = text || '';
  }

  function handleCredential(response) {
    const payload = decodeJwtPayload(response && response.credential);
    const email = String(payload?.email || '').toLowerCase();
    const aud = payload?.aud;
    const exp = Number(payload?.exp || 0);
    const verified = payload?.email_verified === true || payload?.email_verified === 'true';

    if (!payload || aud !== CLIENT_ID || !verified || !exp || Date.now() >= exp * 1000) {
      setError('אימות Google נכשל. נסה שוב.');
      return;
    }
    if (!ALLOWED_EMAILS.has(email)) {
      setError(`החשבון ${email || 'שנבחר'} אינו מורשה ל-Wallet500.`);
      return;
    }

    storeSession(payload);
    removeGate();
    showChip({ email });
  }

  function loadGsi() {
    return new Promise((resolve, reject) => {
      if (window.google?.accounts?.id) return resolve();
      const existing = document.querySelector(`script[src="${GSI_SRC}"]`);
      if (existing) {
        existing.addEventListener('load', resolve, { once: true });
        existing.addEventListener('error', reject, { once: true });
        return;
      }
      const script = document.createElement('script');
      script.src = GSI_SRC;
      script.async = true;
      script.defer = true;
      script.onload = resolve;
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }

  async function init() {
    addStyles();
    const session = getStoredSession();
    if (session) {
      showChip(session);
      return;
    }

    showGate();
    try {
      await loadGsi();
      google.accounts.id.initialize({
        client_id: CLIENT_ID,
        callback: handleCredential,
        auto_select: false,
        cancel_on_tap_outside: false,
        itp_support: true
      });
      google.accounts.id.renderButton(document.getElementById('w500-auth-btn'), {
        theme: 'outline',
        size: 'large',
        text: 'signin_with',
        shape: 'pill',
        width: 280
      });
    } catch (_) {
      setError('לא ניתן לטעון את Google Sign-In. בדוק חיבור אינטרנט ורענן את הדף.');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
