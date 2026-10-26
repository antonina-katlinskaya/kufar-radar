"""Realt-only state in a dedicated Git branch. No Cloudflare access or credentials stored."""
import base64
import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError

REPO = 'antonina-katlinskaya/kufar-radar'

class GitHubFile:
    def __init__(self, branch, path, request=None):
        self.branch, self.path = branch, path
        self.request = request or self._request
        self.sha = None

    def _request(self, method, path, body=None):
        token = os.environ.get('GITHUB_TOKEN')
        if not token:
            raise RuntimeError('GITHUB_TOKEN is required; refusing nonpersistent operation')
        req = Request('https://api.github.com/repos/' + REPO + path,
                      data=json.dumps(body).encode() if body is not None else None,
                      method=method, headers={'Authorization':'Bearer '+token,
                      'Accept':'application/vnd.github+json','User-Agent':'realt-github-state',
                      'Content-Type':'application/json'})
        try:
            with urlopen(req, timeout=60) as response:
                return json.load(response)
        except HTTPError as e:
            raise RuntimeError(f'GitHub state request failed ({e.code}); no blind retry') from None

    def read(self):
        result = self.request('GET', '/contents/'+self.path+'?ref='+self.branch)
        if result.get('encoding') != 'base64' or not result.get('content'):
            raise RuntimeError('GitHub state file is absent or too large; refusing to reset history')
        self.sha = result['sha']
        return json.loads(base64.b64decode(result['content']))

    def write(self, value):
        if not self.sha:
            raise RuntimeError('State must be read before update')
        encoded = json.dumps(value, ensure_ascii=False, separators=(',',':')).encode()
        if len(encoded) > 900_000:
            raise RuntimeError('GitHub state approaches Contents API budget; requires partitioning')
        result = self.request('PUT', '/contents/'+self.path, {
            'branch':self.branch, 'sha':self.sha, 'message':'realt: persist isolated state [skip ci]',
            'content':base64.b64encode(encoded).decode()})
        self.sha = result['content']['sha']

class GitHubState:
    def __init__(self, file=None):
        self.file = file or GitHubFile('realt-state','realt_state/state.json')
        self.data = self.file.read()
        if self.data.get('schema') != 1 or not self.data.get('migration_complete'):
            raise RuntimeError('Realt history migration is incomplete')
        if not isinstance(self.data.get('values'),dict):
            raise RuntimeError('Invalid Realt state map')

    def get_state(self, key, default=None):
        return self.data['values'].get(key, default)

    def set_state(self, key, value):
        if not key.startswith('realt_'):
            raise RuntimeError('Refusing to modify a shared/Kufar key')
        if self.get_state(key) == value:
            return
        before = dict(self.data['values'])
        self.data['values'][key] = value
        try:
            self.file.write(self.data)
        except BaseException:
            self.data['values'] = before
            raise
