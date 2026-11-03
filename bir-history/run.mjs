import {writeFileSync} from 'node:fs';
import {scan,refreshAllDetails} from './worker.mjs';

const {CF_ACCOUNT_ID, BIR_D1_DATABASE_ID, CF_D1_API_TOKEN} = process.env;
if (!CF_ACCOUNT_ID || !BIR_D1_DATABASE_ID || !CF_D1_API_TOKEN) {
  throw Error('Missing CF_ACCOUNT_ID, BIR_D1_DATABASE_ID or CF_D1_API_TOKEN');
}

const endpoint = `https://api.cloudflare.com/client/v4/accounts/${encodeURIComponent(CF_ACCOUNT_ID)}/d1/database/${encodeURIComponent(BIR_D1_DATABASE_ID)}/query`;

let successfulCheckedAt = null;
let rowsWritten=0,rowsRead=0;
function exportMeta(checked_at) {
  if (process.env.BIR_EXPORT_META_PATH) writeFileSync(process.env.BIR_EXPORT_META_PATH, JSON.stringify({ok:true,checked_at}));
}
async function query(statements) {
  if (process.env.BIR_REFRESH_ALL_DETAILS === '1' && rowsWritten >= 25000 && statements.some(s=>!/^SELECT|^INSERT OR REPLACE INTO service_state/i.test(s.sql)))
    throw Error('Nightly D1 write budget reached (25000 rows); waiting for next run');
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
  for (const statement of statements) {
    if (statement.sql.startsWith('INSERT INTO bir_scans(') && statement.params?.[5] === 'ok')
      successfulCheckedAt = statement.params[2];
  }
  for(const r of body.result) {rowsWritten+=r.meta?.rows_written??0;rowsRead+=r.meta?.rows_read??0;}
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
const fullDetails = process.env.BIR_REFRESH_ALL_DETAILS === '1';
if (!fullDetails && Number.isFinite(freshMinutes) && freshMinutes > 0) {
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
    exportMeta(latest.checked_at);
    process.exit(0);
  }
}

const result = await scan({BIR_DB: db});
console.log(JSON.stringify(result));
if (result.ok && successfulCheckedAt) exportMeta(successfulCheckedAt);
if (fullDetails) {
  const details=await refreshAllDetails({BIR_DB:db});
  console.log(JSON.stringify(details));
  console.log(JSON.stringify({nightlyUsage:{rowsWritten,rowsRead}}));
  if(!details.ok) process.exitCode=1;
}
