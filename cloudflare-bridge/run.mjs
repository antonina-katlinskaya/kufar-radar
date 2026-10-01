import {scan} from './worker.mjs';

const {
  CF_ACCOUNT_ID,
  BIR_D1_DATABASE_ID,
  CF_D1_API_TOKEN,
  KUFAR_PRIORITY_PROFILES = '',
  KUFAR_GROUP = ''
} = process.env;

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

function prepared(sql, params = []) {
  const statement = {sql, params};
  return {
    statement,
    async all() { return (await query([statement]))[0]; },
    async run() { return (await query([statement]))[0]; },
    async first() {
      const result = (await query([statement]))[0];
      return result?.results?.[0] ?? null;
    }
  };
}

const db = {
  prepare(sql) {
    return {
      bind(...params) { return prepared(sql, params); },
      async all() { return prepared(sql).all(); },
      async run() { return prepared(sql).run(); },
      async first() { return prepared(sql).first(); }
    };
  },
  async batch(items) {
    return query(items.map(item => item.statement));
  }
};

const priorityProfiles = KUFAR_PRIORITY_PROFILES
  .split(',')
  .map(x => x.trim())
  .filter(Boolean);

const group = KUFAR_GROUP === '0' || KUFAR_GROUP === '1'
  ? Number(KUFAR_GROUP)
  : null;

const result = await scan({BIR_DB: db}, group, priorityProfiles);
console.log(JSON.stringify(result));
