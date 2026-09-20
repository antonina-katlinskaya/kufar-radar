# Cloudflare Cron trigger

This Worker does only one job: every five minutes it calls GitHub's workflow_dispatch endpoint for `radar.yml`.

Required Worker secret:

- `GITHUB_ACTIONS_TOKEN` — fine-grained GitHub personal access token limited to repository `kufar-radar`, with **Actions: Read and write** only.

Optional secret:

- `MANUAL_TRIGGER_KEY` — protects the /trigger test endpoint.

The radar itself continues to run in GitHub Actions. The Worker is only a reliable clock.
