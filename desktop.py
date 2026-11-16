"""Single desktop entry point for the isolated relay, MaiBot host and WeChat bridge."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import msvcrt
import os
from pathlib import Path
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener
import webbrowser

from aiohttp import web

from setup_local import initialize, install_adapter

ROOT = Path(__file__).resolve().parent
ORIGIN = 'http://127.0.0.1:19787'
HTTP = build_opener(ProxyHandler({}))


def request(path, payload=None):
    headers = {'x-hub-token': hub.TOKEN, 'Content-Type': 'application/json'}
    data = None if payload is None else json.dumps(payload).encode()
    try:
        with HTTP.open(Request(ORIGIN + path, data=data, headers=headers), timeout=50) as response:
            return json.load(response)
    except HTTPError as exc:
        try:
            reason = json.load(exc)['error']
        except (ValueError, KeyError):
            reason = f'本机接口返回 HTTP {exc.code}'
        raise ValueError(reason) from None


def save_voice(fields):
    import win32crypt

    provider = fields['Provider']
    keys = {'breezeblue': 'breeze', 'minimax': 'minimax', 'siliconflow': 'siliconflow'}
    if provider not in keys:
        raise ValueError('请选择支持的语音厂商')
    if fields['Enabled'] and not all(fields[k] for k in ('Model', 'Voice', 'Device')):
        raise ValueError('启用语音前请填写模型、音色和虚拟声卡播放端点 ID')
    if fields['Enabled'] and not (hub.WHALE_ROOT / 'WhaleMaiVoiceWorker.exe').is_file():
        raise ValueError('请先运行 Build-VoiceWorker.ps1 编译语音工作进程')
    secret = fields.pop('key')
    path = hub.WHALE_ROOT / 'data'
    keyfile = path / f'voice-send-{keys[provider]}.key'
    if secret:
        encrypted = win32crypt.CryptProtectData(secret.encode(), 'WhaleMai Next', None, None, None, 0)
        temporary = keyfile.with_suffix('.tmp')
        temporary.write_bytes(encrypted)
        temporary.replace(keyfile)
    if fields['Enabled'] and not keyfile.is_file():
        raise ValueError('请填写当前语音厂商的 Key')
    hub.save_json(path / 'voice-send.json', fields)


class Desktop:
    def __init__(self, root, loop, stopping):
        self.root, self.loop, self.stopping = root, loop, stopping
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.busy = False
        self.loaded = False
        self.remote = False
        root.title('WhaleMai Next')
        root.minsize(680, 525)
        panel = ttk.Frame(root, padding=20)
        panel.pack(fill='both', expand=True)
        panel.columnconfigure(1, weight=1)
        self.state = tk.StringVar(value='正在启动本机服务')
        ttk.Label(panel, textvariable=self.state).grid(row=0, columnspan=3, sticky='w', pady=(0, 10))
        self.account = self.field(panel, 1, '微信账号目录名')
        self.allowed = self.field(panel, 2, '允许的会话 ID，以逗号分隔')
        self.image = tk.StringVar(value='request')
        ttk.Label(panel, text='图片接收').grid(row=3, column=0, sticky='w')
        ttk.Combobox(panel, textvariable=self.image, values=('request', 'auto', 'off'),
                     state='readonly').grid(row=3, column=1, sticky='ew')
        ttk.Button(panel, text='保存微信设置', command=self.save_settings).grid(row=3, column=2)
        self.bot_id = self.field(panel, 4, '麦麦 Bot 目录名')
        ttk.Button(panel, text='安装适配器', command=self.install).grid(row=4, column=2)
        commands = ttk.Frame(panel)
        commands.grid(row=5, columnspan=3, sticky='w', pady=12)
        for title, callback in (
            ('启动麦麦', lambda: self.control('start')),
            ('麦麦 WebUI', self.management),
            ('连接微信', lambda: self.control('bridge')),
            ('断开微信', lambda: self.control('disconnect')),
            ('取消队列', lambda: self.control('cancel')),
            ('全部停止', lambda: self.control('stop')),
        ):
            ttk.Button(commands, text=title, command=callback).pack(side='left', padx=2)
        tools = ttk.Frame(panel)
        tools.grid(row=6, columnspan=3, sticky='w')
        ttk.Button(tools, text='远程接管开关', command=lambda: self.control('remote', enabled=not self.remote)).pack(side='left')
        ttk.Button(tools, text='打开远程页面', command=lambda: webbrowser.open('http://127.0.0.1:19788')).pack(side='left')
        ttk.Button(tools, text='复制远程 Key', command=self.copy_remote_key).pack(side='left')
        ttk.Button(tools, text='语音设置', command=self.voice_window).pack(side='left')
        self.result = tk.StringVar()
        ttk.Label(panel, textvariable=self.result, wraplength=630).grid(row=7, columnspan=3, sticky='w', pady=10)
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh()

    def field(self, panel, row, label, secret=False):
        variable = tk.StringVar()
        ttk.Label(panel, text=label).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=5)
        ttk.Entry(panel, textvariable=variable, show='•' if secret else '').grid(row=row, column=1, sticky='ew', padx=(0, 8))
        return variable

    def run(self, work, on_success=None, quiet=False):
        if self.busy:
            return
        self.busy = True
        future = self.executor.submit(work)

        def finish():
            if not future.done():
                self.root.after(100, finish)
                return
            self.busy = False
            try:
                value = future.result()
                if on_success:
                    on_success(value)
                if not quiet:
                    self.result.set('操作完成')
            except Exception as exc:
                self.result.set(str(exc) if isinstance(exc, ValueError) else type(exc).__name__)

        finish()

    def control(self, action, **values):
        self.run(lambda: request('/control', {'action':action, **values}))

    def save_settings(self):
        self.control('settings', account=self.account.get(),
                     allowed=self.allowed.get().replace('，', ',').split(','), image_mode=self.image.get())

    def refresh(self):
        def update(state):
            self.remote = state['remoteEnabled']
            mai = '运行' if state['mai'] else '停止'
            adapter = '已配对' if state['adapter'] else '等待'
            bridge = '在线' if state['bridgeOnline'] else ('启动中' if state['bridge'] else '断开')
            remote = '开启' if self.remote else '关闭'
            self.state.set(f'麦麦 {mai}   ·   适配器 {adapter}   ·   微信 {bridge}   ·   远程 {remote}')
            if state['exits']:
                codes = ', '.join(f'{name} ({code})' for name, code in state['exits'].items())
                self.result.set('子进程异常退出 ' + codes)
            if not self.loaded:
                self.account.set(state['account'])
                self.allowed.set(', '.join(state['allowed']))
                self.image.set(state['imageMode'])
                self.loaded = True

        self.run(lambda: request('/status'), update, quiet=True)
        self.root.after(1500, self.refresh)

    def install(self):
        bot = self.bot_id.get().strip()
        if not bot:
            candidates = [path.name for path in (hub.INSTANCE_ROOT / 'bots').glob('*')
                          if (path / 'config/bot_config.toml').is_file()]
            if len(candidates) == 1:
                bot = candidates[0]
                self.bot_id.set(bot)

        def configure():
            if request('/status')['mai']:
                raise ValueError('请先全部停止，再安装适配器')
            install_adapter(bot, hub.TOKEN)

        self.run(configure)

    def management(self):
        def open_local(data):
            url = urlsplit(data['url'])
            if url.scheme != 'http' or url.hostname != '127.0.0.1' or url.port != 19790:
                raise ValueError('麦麦 WebUI 地址不属于此安装')
            webbrowser.open(data['url'])

        self.run(lambda: request('/management', {}), open_local)

    def copy_remote_key(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(hub.remote.keyfile.read_text(encoding='utf-8').strip())
        self.result.set('远程 Key 已复制到剪贴板')

    def voice_window(self):
        child = tk.Toplevel(self.root)
        child.title('API 语音')
        panel = ttk.Frame(child, padding=16)
        panel.pack(fill='both', expand=True)
        panel.columnconfigure(1, weight=1)
        path = hub.WHALE_ROOT / 'data/voice-send.json'
        saved = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
        enabled = tk.BooleanVar(value=saved.get('Enabled', False))
        ttk.Checkbutton(panel, text='允许小写 /v 授权的语音回复', variable=enabled).grid(row=0, columnspan=2)
        fields = {}
        for row, (name, label) in enumerate((
            ('Provider', '厂商（breezeblue / minimax / siliconflow）'),
            ('Address', 'HTTPS API 基址（留空使用厂商默认）'),
            ('key', 'Key（留空保留）'), ('Model', '模型'), ('Voice', '音色'),
            ('Device', '虚拟声卡播放端点 ID'), ('RecordingHotkey', '微信录音按键'),
        ), 1):
            fields[name] = self.field(panel, row, label, name == 'key')
            fields[name].set(saved.get(name, {'Provider':'breezeblue','RecordingHotkey':'Ctrl+Alt'}.get(name, '')))

        def save():
            values = {name: var.get().strip() for name, var in fields.items()}
            values.update(Enabled=enabled.get(), Groups=True, Private=True, Probability=0)
            self.run(lambda: save_voice(values), lambda _: child.destroy())

        def microphone(switch):
            script = ROOT / 'audio/Ensure-Microphone.ps1'
            command = ['powershell.exe', '-NoProfile', '-NonInteractive',
                       '-ExecutionPolicy', 'Bypass', '-File', str(script)]
            if not switch:
                command.append('-CheckOnly')
            result = subprocess.run(command, capture_output=True, timeout=20,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode:
                raise ValueError('未验证 CABLE Output 为默认录音及通信设备')

        ttk.Button(panel, text='检查麦克风', command=lambda: self.run(lambda: microphone(False))).grid(row=8, column=0)
        ttk.Button(panel, text='切换麦克风', command=lambda: self.run(lambda: microphone(True))).grid(row=8, column=1)
        ttk.Button(panel, text='保存语音设置', command=save).grid(row=9, column=1)

    def close(self):
        if self.busy:
            self.root.after(200, self.close)
            return
        self.run(lambda: request('/control', {'action':'stop'}), self.exit, quiet=True)

    def exit(self, _):
        self.loop.call_soon_threadsafe(self.stopping.set)
        self.executor.shutdown(wait=False)
        self.root.destroy()


def main():
    root = tk.Tk()
    root.withdraw()
    initialize()
    lock = (ROOT / 'data/desktop.lock').open('a+b')
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        messagebox.showerror('WhaleMai Next', '此安装的桌面应用已打开')
        lock.close()
        return
    os.environ.pop('WHALE_MAI_DATA', None)
    loop = asyncio.new_event_loop()
    started = threading.Event()
    stopping = asyncio.Event()
    errors = []

    async def serve():
        global hub
        runner = None
        try:
            import hub
            runner = web.AppRunner(hub.app, access_log=None)
            await runner.setup()
            await web.TCPSite(runner, '127.0.0.1', hub.PORT).start()
        except Exception as exc:
            errors.append(type(exc).__name__)
        finally:
            started.set()
        if not errors:
            await stopping.wait()
        if runner is not None:
            await runner.cleanup()

    worker = threading.Thread(target=lambda: loop.run_until_complete(serve()))
    worker.start()
    if not started.wait(8) or errors:
        messagebox.showerror('WhaleMai Next', '无法启动本机服务，请检查端口 19787 和 19788')
        loop.call_soon_threadsafe(stopping.set)
        return
    try:
        Desktop(root, loop, stopping)
        root.deiconify()
        root.mainloop()
    finally:
        if worker.is_alive():
            loop.call_soon_threadsafe(stopping.set)
        worker.join(timeout=35)
        lock.close()


if __name__ == '__main__':
    main()
