import {scan} from './worker.mjs';

const {CF_ACCOUNT_ID, BIR_D1_DATABASE_ID, CF_D1_API_TOKEN} = process.env;
if (!CF_ACCOUNT_ID || !BIR_D1_DATABASE_ID || !CF_D1_API_TOKEN) {
  throw Error('Missing CF_ACCOUNT_ID, BIR_D1_DATABASE_ID or CF_D1_API_TOKEN');
}

const endpoint = `https://api.cloudflare.com/client/v4/accounts/${encodeURIComponent(CF_ACCOUNT_ID)}/d1/database/${encodeURIComponent(BIR_D1_DATABASE_ID)}/query`;

async function query(statements) {
  const payload = statements.length === 1
    ? {sql: statements[0].sql, params: statements[0].params}
    : {batch: statements.map(({sql, params}) => ({sql, params}))};
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${CF_D1_API_TOKEN}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  });
  if (!response.ok) throw Error(`D1 HTTP ${response.status}`);
  const body = await response.json();
  if (!body.success || !Array.isArray(body.result) || body.result.length !== statements.length ||
      body.result.some(result => result.success === false)) {
    throw Error(`D1 query failed: ${JSON.stringify(body.errors ?? body.result?.map(r => r.error ?? null))}`);
  }
  return body.result;
}

const db = {
  prepare(sql) {
    return {
      bind(...params) {
        const statement = {sql, params};
        return {
          async all() { return (await query([statement]))[0]; },
          async run() { return (await query([statement]))[0]; },
          statement
        };
      },
      async all() { return (await query([{sql, params: []}]))[0]; },
      async run() { return (await query([{sql, params: []}]))[0]; }
    };
  },
  async batch(prepared) { return query(prepared.map(({statement}) => statement)); }
};

const freshMinutes = Number(process.env.BIR_SKIP_IF_FRESH_MINUTES || 0);
if (Number.isFinite(freshMinutes) && freshMinutes > 0) {
  const latest = (await db.prepare(
    "SELECT checked_at FROM bir_scans WHERE status='ok' ORDER BY checked_at DESC LIMIT 1"
  ).all()).results?.[0];
  const checkedAt = latest?.checked_at ? Date.parse(latest.checked_at) : NaN;
  const ageMs = Date.now() - checkedAt;
  if (Number.isFinite(ageMs) && ageMs >= 0 && ageMs <= freshMinutes * 60_000) {
    console.log(JSON.stringify({
      ok:true,
      skipped:true,
      reason:'fresh_snapshot',
      checked_at:latest.checked_at,
      age_seconds:Math.round(ageMs / 1000)
    }));
    process.exit(0);
  }
}

const result = await scan({BIR_DB: db});
console.log(JSON.stringify(result));
