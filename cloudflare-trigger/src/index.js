const OWNER = "antonina-katlinskaya";
const REPO = "kufar-radar";
const WORKFLOW = "radar.yml";

async function triggerRadar(env) {
  if (!env.GITHUB_ACTIONS_TOKEN) {
    throw new Error("GITHUB_ACTIONS_TOKEN is not configured");
  }

  const url = `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}/dispatches`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Accept": "application/vnd.github+json",
      "Authorization": `Bearer ${env.GITHUB_ACTIONS_TOKEN}`,
      "X-GitHub-Api-Version": "2026-03-10",
      "User-Agent": "kufar-radar-cloudflare-trigger"
    },
    body: JSON.stringify({ ref: "main" })
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`GitHub dispatch failed: ${response.status} ${body}`);
  }

  return response.status;
}

export default {
  async scheduled(controller, env, ctx) {
    ctx.waitUntil(triggerRadar(env));
  },

  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/health") {
      return new Response("ok", { status: 200 });
    }

    if (url.pathname === "/trigger") {
      const auth = request.headers.get("authorization");
      if (!env.MANUAL_TRIGGER_KEY || auth !== `Bearer ${env.MANUAL_TRIGGER_KEY}`) {
        return new Response("unauthorized", { status: 401 });
      }
      const status = await triggerRadar(env);
      return Response.json({ ok: true, github_status: status });
    }

    return new Response("kufar-radar trigger", { status: 200 });
  }
};
