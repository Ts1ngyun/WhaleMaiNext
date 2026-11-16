"""Initialize only this checkout. Run after installing its Python environments."""
from pathlib import Path
import json
import secrets
import shutil
import sys

from deployment import INSTANCE_ROOT, WHALE_ROOT

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'


def write_new(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('x', encoding='utf-8') as stream:
            stream.write(text)
    except FileExistsError:
        pass


def initialize():
    if not str(ROOT).isascii():
        raise ValueError('请先将整个目录放在英文路径下')
    write_new(DATA / 'token', secrets.token_urlsafe(32))
    token = (DATA / 'token').read_text(encoding='utf-8').strip()
    config = json.loads((WHALE_ROOT / 'config/config.example.json').read_text(encoding='utf-8'))
    config['server'].update(host='127.0.0.1', port=19789)
    config['gateway']['wechat']['inboundToken'] = secrets.token_urlsafe(32)
    config['wechat'].update(account='', accountGuard=True, whitelistOnly=True,
                            backgroundSend=False)
    config['wechat']['bgSend']['enabled'] = False
    config['care'].update(enabled=False, whitelist=[])
    config['voice']['enabled'] = False
    config['features']['stickers'] = True
    write_new(WHALE_ROOT / 'config.json', json.dumps(config, ensure_ascii=False, indent=2))
    association = WHALE_ROOT / 'data/maibot-link.json'
    association.parent.mkdir(parents=True, exist_ok=True)
    association.write_text(json.dumps({'tokenFile': str(DATA / 'token'), 'bridgeRoot': str(ROOT)}),
                           encoding='utf-8')
    write_new(INSTANCE_ROOT / 'host/config.toml',
              '[webui]\nenabled = true\nhosts = ["127.0.0.1"]\nport = 19790\n')
    if len(sys.argv) == 2:
        install_adapter(sys.argv[1], token)


def install_adapter(bot_id, token):
    bots = INSTANCE_ROOT / 'bots'
    bot = (bots / bot_id).resolve()
    if bot.parent != bots or not (bot / 'config/bot_config.toml').is_file():
        raise ValueError('请先在此应用的麦麦 WebUI 创建 Bot，再输入对应目录名')
    destination = bot / 'plugins/whalemai_next'
    destination.mkdir(parents=True, exist_ok=True)
    for name in ('plugin.py', '_manifest.json', 'LICENSE'):
        shutil.copyfile(ROOT / 'plugin' / name, destination / name)
    write_new(destination / 'config.toml',
              '[plugin]\nenabled = true\nconfig_version = "1.0.0"\n'
              '[relay]\nurl = "http://127.0.0.1:19787"\ntoken = ' + json.dumps(token) + '\n')


if __name__ == '__main__':
    initialize()
