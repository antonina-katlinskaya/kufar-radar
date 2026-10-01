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
  if (statements.length > 1) {
    if (!globalThis.batchExplained) {
      globalThis.batchExplained = true;
      console.log('D1 first batch', JSON.stringify({sql: statements[0]?.sql,
        params: statements[0]?.params?.map(v => typeof v), response: body.result[0]}));
    }
    console.log('D1 batch', JSON.stringify({statements: statements.length,
      rowsWritten: body.result.reduce((sum, result) => sum + Number(result.meta?.rows_written ?? 0), 0)}));
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
      async all() {
        const result = (await query([{sql, params: []}]))[0];
        if (sql === 'SELECT * FROM bir_objects') {
          const sample = result.results?.find(row => row.present);
          console.log('D1 types', JSON.stringify({present: sample?.present, missing_checks: sample?.missing_checks,
            presentType: typeof sample?.present, missingType: typeof sample?.missing_checks}));
          console.log('D1 state', JSON.stringify({total: result.results.length,
            active: result.results.filter(row => row.present).length,
            activeMissing: result.results.filter(row => row.present && row.missing_checks).length}));
        }
        return result;
      },
      async run() { return (await query([{sql, params: []}]))[0]; }
    };
  },
  async batch(prepared) { return query(prepared.map(({statement}) => statement)); }
};

const result = await scan({BIR_DB: db});
console.log(JSON.stringify(result));
