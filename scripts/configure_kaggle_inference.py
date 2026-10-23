"""One-time private setup: read token without echo, fetch authenticated config.

Never takes the token on the command line or prints the token/response body.
Only writes local configuration after the authenticated health check succeeds.
"""
import argparse
import getpass
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

ROOT = Path(__file__).resolve().parents[1]


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def update_env(path, changes):
    text = path.read_text(encoding='utf-8-sig') if path.exists() else ''
    lines = text.splitlines()
    pending = dict(changes)
    result = []
    for line in lines:
        key = line.split('=', 1)[0].strip() if '=' in line and not line.lstrip().startswith('#') else None
        if key in changes:
            if key in pending:
                result.append(key + '=' + pending.pop(key))
        else:
            result.append(line)
    result.extend(key + '=' + value for key, value in pending.items())
    path.write_text('\n'.join(result) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description='Cau hinh API Kaggle bang token nhap kin tren may.')
    parser.add_argument('--url', required=True)
    parser.add_argument('--local', action='store_true', help='Duong dan config cho Django local thay vi Docker')
    parser.add_argument('--use-env-token', action='store_true', help='Dung token da luu trong .env, khong in token')
    parser.add_argument('--dual-gpu', action='store_true', help='Chi chap nhan gateway hai replica va profile 1024 token/90 giay')
    args = parser.parse_args()
    url = args.url.rstrip('/')
    parts = urlsplit(url)
    if (parts.scheme != 'https' or not parts.hostname or parts.username or parts.password
            or parts.path or parts.query or parts.fragment):
        parser.error('URL phai la HTTPS base URL, khong co /generate hoac token.')
    if args.use_env_token:
        from dotenv import dotenv_values
        token = dotenv_values(ROOT / '.env').get('AI_INFERENCE_TOKEN') or ''
    else:
        token = getpass.getpass('Nhap OHAYO_INFERENCE_TOKEN (khong hien ky tu): ')
    if len(token) < 32 or not token.isascii() or any(c.isspace() for c in token):
        parser.error('Token phai la ASCII >=32 ky tu, khong co khoang trang.')
    try:
        request = Request(url + '/health', headers={'Authorization': 'Bearer ' + token,
            'ngrok-skip-browser-warning': '1'})
        with build_opener(NoRedirect()).open(request, timeout=20) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError('Response too large')
        health = json.loads(raw)
        config = health['config']
        required = {'model', 'revision', 'prompt_version', 'max_input_tokens', 'max_output_tokens',
                    'timeout_seconds', 'temperature'}
        if (health.get('ready') is not True or set(config) != required
                or config['model'] != 'Qwen/Qwen2.5-7B-Instruct'):
            raise ValueError('Invalid server config')
        if args.dual_gpu and (health.get('replicas') != 2 or config['max_output_tokens'] != 1024
                or config['max_input_tokens'] != 3584 or config['timeout_seconds'] != 90):
            raise ValueError('The two-GPU startup cell is not ready')
    except Exception as exc:
        status = getattr(exc, 'code', None)
        label = str(status) if type(status) is int else type(exc).__name__
        print('Chua ghi cau hinh: health check that bai (' + label + '). Kiem tra URL, token va session Kaggle.')
        return 1
    target = ROOT / ('backend/config/ai/kaggle-dual-gpu.json' if args.dual_gpu
                     else 'backend/config/ai/w4-generation-kaggle.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    update_env(ROOT / '.env', {
        'AI_GENERATOR': 'apps.ai.remote.generate_answer',
        'AI_GENERATION_CONFIG': str(target) if args.local else '/app/' + target.relative_to(ROOT).as_posix(),
        'AI_INFERENCE_URL': url,
        'AI_INFERENCE_TOKEN': token,
    })
    print('Ket noi Kaggle thanh cong. Da luu config va token vao .env rieng tu; khong in token.')
    print('Can recreate backend de nhan env moi. Retrieval index/catalog van can preflight rieng.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
