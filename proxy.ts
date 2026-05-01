/**
 * Passthrough proxy that works around upstream new-api quirks:
 *  - Strips `structured-outputs-2025-12-15` beta (not recognized → panic).
 *  - Strips body `output_config` field (not recognized → panic).
 *  - Injects minimum `thinking` block when 1m/interleaved-thinking beta is
 *    requested but body has no thinking, so upstream does not nil-deref.
 *  - Drops betas whose paired body field is missing after the above edits.
 *
 * Env:
 *   MODEL_PROXY_UPSTREAM — real API base URL (e.g. https://api.anthropic.com)
 *   PROXY_PORT           — listen port (default 18089)
 */

import http from 'node:http';

const UPSTREAM = (process.env.MODEL_PROXY_UPSTREAM || '').replace(/\/+$/, '');
const PORT = parseInt(process.env.PROXY_PORT || '18089', 10);

if (!UPSTREAM) {
  console.error('[model-proxy] MODEL_PROXY_UPSTREAM not set, exiting');
  process.exit(0);
}

const HOP_BY_HOP = new Set([
  'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
  'te', 'trailers', 'transfer-encoding', 'upgrade', 'content-length',
]);

const BETA_REMOVE = new Set(['structured-outputs-2025-12-15']);
const BODY_STRIP_FIELDS: string[] = [];

// Betas that require a paired body field, otherwise upstream panics.
const BETA_REQUIRES_FIELD: Record<string, string> = {
  'interleaved-thinking-2025-05-14': 'thinking',
  'context-1m-2025-08-07': 'thinking',
  'redact-thinking-2026-02-12': 'thinking',
  'context-management-2025-06-27': 'context_management',
  'effort-2025-11-24': 'output_config',
};

// Betas that if present should cause us to inject a minimum thinking block
// so the request is legal on upstream (matches BETA_REQUIRES_FIELD=thinking).
const BETAS_NEED_THINKING = new Set(['context-1m-2025-08-07', 'interleaved-thinking-2025-05-14']);

const SENSITIVE = new Set(['authorization', 'x-api-key', 'cookie', 'proxy-authorization']);

function patchBetaHeader(value: string, bodyFields: Set<string>): { value: string; dropped: string[] } {
  const flags = value.split(',').map(s => s.trim()).filter(Boolean);
  const dropped: string[] = [];
  const kept = flags.filter(f => {
    if (BETA_REMOVE.has(f)) { dropped.push(f); return false; }
    const req = BETA_REQUIRES_FIELD[f];
    if (req && !bodyFields.has(req)) { dropped.push(f); return false; }
    return true;
  });
  return { value: kept.join(','), dropped };
}

function redactHeaders(h: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(h)) {
    if (SENSITIVE.has(k.toLowerCase())) {
      const tail = v.length > 8 ? v.slice(-6) : '';
      out[k] = `<${v.length} chars …${tail}>`;
    } else {
      out[k] = v;
    }
  }
  return out;
}

function buildHeaders(
  raw: Record<string, string | string[] | undefined>,
  bodyFields: Set<string>,
): { headers: Record<string, string>; dropped: string[] } {
  const out: Record<string, string> = {};
  let dropped: string[] = [];
  for (const [key, value] of Object.entries(raw)) {
    if (HOP_BY_HOP.has(key.toLowerCase()) || !value) continue;
    const joined = Array.isArray(value) ? value.join(', ') : value;
    if (key.toLowerCase() === 'anthropic-beta') {
      const patched = patchBetaHeader(joined, bodyFields);
      dropped = patched.dropped;
      if (patched.value) out[key] = patched.value;
    } else {
      out[key] = joined;
    }
  }
  out['host'] = new URL(UPSTREAM).host;
  return { headers: out, dropped };
}

type BodyInfo = {
  model?: string;
  summary: string;
  patched?: Buffer;
  stripped: string[];
  injected: string[];
  fields: Set<string>;
};

function describeBody(body: Buffer, betaFlags: Set<string>): BodyInfo {
  if (body.length === 0) {
    return { summary: '<empty>', stripped: [], injected: [], fields: new Set() };
  }
  try {
    const data = JSON.parse(body.toString());
    const model = typeof data.model === 'string' ? data.model : undefined;
    const stripped: string[] = [];
    const injected: string[] = [];

    for (const f of BODY_STRIP_FIELDS) {
      if (f in data) { delete data[f]; stripped.push(f); }
    }

    const needsThinking = Array.from(betaFlags).some(f => BETAS_NEED_THINKING.has(f));
    // Only inject when body has no thinking at all — never overwrite the
    // caller's existing thinking block. Pick the mode that matches the rest
    // of the body:
    //   - With `output_config.effort`: use {type:"adaptive"}. Effort derives
    //     the budget automatically; manually setting budget_tokens here
    //     conflicts with effort ("xhigh" vs 1024) and upstream returns 503.
    //   - Without effort: use {type:"enabled", budget_tokens:1024} (haiku
    //     sub-agent path, already verified working).
    const hasEffort = !!(data.output_config
      && typeof data.output_config === 'object'
      && (data.output_config as { effort?: unknown }).effort);
    if (needsThinking && !data.thinking && Array.isArray(data.messages)) {
      const maxTok = typeof data.max_tokens === 'number' ? data.max_tokens : 0;
      if (hasEffort) {
        data.thinking = { type: 'adaptive' };
        injected.push('thinking:adaptive');
      } else if (maxTok >= 1100) {
        data.thinking = { type: 'enabled', budget_tokens: 1024 };
        injected.push('thinking:enabled');
      }
    }

    const fields = new Set<string>(Object.keys(data));
    const keys = Object.keys(data).map(k => {
      const v = data[k];
      if (Array.isArray(v)) return `${k}[${v.length}]`;
      if (typeof v === 'string') return `${k}(${v.length})`;
      if (typeof v === 'object' && v !== null) return `${k}=${JSON.stringify(v)}`;
      return `${k}=${JSON.stringify(v)}`;
    });
    const patched = (stripped.length > 0 || injected.length > 0) ? Buffer.from(JSON.stringify(data)) : undefined;
    return { model, summary: keys.join(' '), patched, stripped, injected, fields };
  } catch {
    return { summary: `<non-json ${body.length}B>`, stripped: [], injected: [], fields: new Set() };
  }
}

function parseBetaFlags(raw: string | string[] | undefined): Set<string> {
  if (!raw) return new Set();
  const joined = Array.isArray(raw) ? raw.join(',') : raw;
  return new Set(joined.split(',').map(s => s.trim()).filter(Boolean));
}

function collectBody(req: http.IncomingMessage): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on('data', (c: Buffer) => chunks.push(c));
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}

let reqSeq = 0;

const server = http.createServer(async (req, res) => {
  const id = ++reqSeq;
  const url = `${UPSTREAM}${req.url}`;
  try {
    const body = await collectBody(req);
    const betaFlags = parseBetaFlags(req.headers['anthropic-beta']);
    const { model, summary, patched, stripped, injected, fields } = describeBody(body, betaFlags);
    const { headers, dropped } = buildHeaders(req.headers as Record<string, string | string[] | undefined>, fields);
    const outBody = patched ?? body;

    const tags = [
      dropped.length ? 'dropped-beta=' + dropped.join(',') : '',
      stripped.length ? 'stripped=' + stripped.join(',') : '',
      injected.length ? 'injected=' + injected.join(',') : '',
    ].filter(Boolean).join('  ');
    console.error(`[#${id}] --> ${req.method} ${req.url}${model ? '  model=' + model : ''}${tags ? '  ' + tags : ''}`);
    console.error(`[#${id}]     headers: ${JSON.stringify(redactHeaders(headers))}`);
    console.error(`[#${id}]     body(${outBody.length}B): ${summary}`);

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 120_000);

    const upstream = await fetch(url, {
      method: req.method,
      headers,
      body: outBody.length > 0 ? outBody : undefined,
      signal: controller.signal,
      redirect: 'manual',
      duplex: 'half',
    } as RequestInit);
    clearTimeout(timer);
    console.error(`[#${id}] <-- ${upstream.status}`);

    const resHeaders: Record<string, string> = {};
    for (const [k, v] of upstream.headers.entries()) {
      if (!HOP_BY_HOP.has(k.toLowerCase())) resHeaders[k] = v;
    }
    res.writeHead(upstream.status, resHeaders);

    const isError = upstream.status < 200 || upstream.status >= 300;
    if (upstream.body) {
      const reader = (upstream.body as ReadableStream<Uint8Array>).getReader();
      const errChunks: Buffer[] = [];
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          if (isError) errChunks.push(Buffer.from(value));
          res.write(value);
        }
      } catch { /* stream ended */ }
      if (isError && errChunks.length > 0) {
        const text = Buffer.concat(errChunks).toString('utf8');
        console.error(`[#${id}] !! body: ${text.slice(0, 2000)}`);
      }
    }
    res.end();
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error(`[#${id}] error: ${msg}`);
    if (!res.headersSent) res.writeHead(502, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ error: 'Bad Gateway', message: msg }));
  }
});

server.listen(PORT, '127.0.0.1', () => {
  console.error(`[model-proxy] http://127.0.0.1:${PORT} → ${UPSTREAM}`);
  console.error(`[model-proxy] strip beta=[${[...BETA_REMOVE].join(',')}]${BODY_STRIP_FIELDS.length ? '  strip body=[' + BODY_STRIP_FIELDS.join(',') + ']' : ''}`);
  console.error(`[model-proxy] inject thinking when beta has [${[...BETAS_NEED_THINKING].join(',')}], body lacks thinking, max_tokens>=1100`);
});
