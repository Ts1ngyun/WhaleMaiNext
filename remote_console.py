"""Isolated mobile console. Only this app (19788), never the hub, is tunneled."""
import asyncio, collections, hashlib, json, re, secrets, time, uuid
from aiohttp import web

class Console:
    def __init__(self,h):
        self.h=h; self.enabled=False; self.ready_at=0; self.failures={}
        self.keyfile=h.DATA/'remote-key.txt'
        if not self.keyfile.exists():self.keyfile.write_text(secrets.token_urlsafe(32),encoding='utf-8')
        h.db.executescript('''CREATE TABLE IF NOT EXISTS takeover(chat TEXT PRIMARY KEY, enabled INTEGER);
        CREATE TABLE IF NOT EXISTS manual_jobs(id TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS timeline(id TEXT PRIMARY KEY, chat TEXT, author TEXT, text TEXT, source TEXT, at REAL);
        CREATE TABLE IF NOT EXISTS self_seen(id TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS echo_matches(outbox_id TEXT PRIMARY KEY);
        ''');h.db.commit()
        self.app=web.Application(middlewares=[self.guard],client_max_size=16000)
        self.app.add_routes([web.get('/',self.page),web.get('/app.js',self.script),web.get('/api/state',self.state),
            web.post('/api/takeover',self.takeover),web.post('/api/send',self.send)])

    def paused(self,chat):
        r=self.h.db.execute('SELECT enabled FROM takeover WHERE chat=?',(chat,)).fetchone()
        return bool(r and r[0])

    def manual(self,mid):return bool(self.h.db.execute('SELECT 1 FROM manual_jobs WHERE id=?',(mid,)).fetchone())

    def event(self,mid,chat,author,text,source):
        self.h.db.execute('INSERT OR IGNORE INTO timeline VALUES(?,?,?,?,?,?)',(mid,chat,author,text[:12000],source,time.time()))
        self.h.db.commit()

    def context(self,mid,chat,text,source,author='本账号'):
        payload={'_context_only':True,'chat':chat,'text':text,'source':source,'author':author}
        self.h.db.execute('INSERT OR IGNORE INTO inbox VALUES(?,?,?,?)',(mid,json.dumps(payload,ensure_ascii=False),'queued',time.time()))
        self.h.db.commit();self.h.inbox_ready.set()

    @web.middleware
    async def guard(self,req,handler):
        try:
            if req.path.startswith('/api/'):
                if not self.enabled:raise web.HTTPServiceUnavailable(text='远程控制已关闭，请在本机启动双端。')
                peer=req.headers.get('CF-Connecting-IP',req.remote or 'unknown')
                now=time.monotonic();bucket=self.failures.setdefault(peer,collections.deque())
                while bucket and now-bucket[0]>60:bucket.popleft()
                if len(bucket)>=12:raise web.HTTPTooManyRequests(text='认证尝试过多，请一分钟后重试。')
                supplied=req.headers.get('Authorization','').removeprefix('Bearer ')
                expected=self.keyfile.read_text(encoding='utf-8').strip()
                if not secrets.compare_digest(hashlib.sha256(supplied.encode()).digest(),hashlib.sha256(expected.encode()).digest()):
                    bucket.append(now);raise web.HTTPUnauthorized(text='认证 Key 不正确。')
                origin=req.headers.get('Origin')
                if origin and origin not in ('https://'+req.host,'http://'+req.host):raise web.HTTPForbidden(text='不允许跨站请求。')
                if len(self.failures)>2000:self.failures.clear()
            response=await handler(req)
        except web.HTTPException as exc:response=web.Response(status=exc.status,text=exc.text,headers=exc.headers)
        response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
            'Referrer-Policy':'no-referrer','X-Frame-Options':'DENY',
            'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
        return response

    async def page(self,req):return web.FileResponse(self.h.ROOT/'remote/index.html')
    async def script(self,req):return web.FileResponse(self.h.ROOT/'remote/app.js')

    async def state(self,req):
        h=self.h;chat=req.query.get('chat','')
        chats=[dict(zip(('id','name','kind'),r)) for r in h.db.execute("SELECT * FROM chats WHERE id NOT LIKE '__test__%' ORDER BY name") if r[0] in h.native_chats]
        events=[];jobs=[]
        if chat:
            if chat not in {c['id'] for c in chats}:raise web.HTTPForbidden(text='会话尚未由鲸鲸验证。')
            events=[dict(zip(('id','author','text','source','at'),r)) for r in h.db.execute('SELECT id,author,text,source,at FROM timeline WHERE chat=? ORDER BY at DESC LIMIT 80',(chat,))][::-1]
            jobs=[dict(zip(('id','text','state','at'),r)) for r in h.db.execute('SELECT o.id,o.text,o.state,o.at FROM outbox o JOIN manual_jobs m ON m.id=o.id WHERE chat=? ORDER BY at DESC LIMIT 12',(chat,))]
        return web.json_response({'chats':chats,'events':events,'jobs':jobs,'takeover':self.paused(chat),
            'mai':h.alive('mai'),'bridge':time.time()-self.ready_at<10,'note':'已执行发送不等于微信服务端送达；不自动重试。'})

    def allowed(self,chat):
        if chat not in self.h.settings['allowed'] or chat not in self.h.native_chats:
            raise web.HTTPForbidden(text='只能操作已授权并同步的会话。')

    async def takeover(self,req):
        b=await req.json();chat=str(b.get('chat',''));self.allowed(chat)
        value=b.get('enabled')
        if not isinstance(value,bool):raise web.HTTPBadRequest(text='开关值无效。')
        h=self.h;h.db.execute('INSERT OR REPLACE INTO takeover VALUES(?,?)',(chat,int(value)))
        if value:
            h.db.execute("UPDATE outbox SET state='cancelled' WHERE chat=? AND state IN ('queued','claimed') AND id NOT IN (SELECT id FROM manual_jobs)",(chat,))
            h.db.execute('UPDATE voice_grants SET used=1 WHERE chat=?',(chat,))
        h.db.commit()
        self.context('mode-'+uuid.uuid4().hex,chat,'主人已接管会话，暂停自动回复。' if value else '主人已结束接管；后续新消息可以正常回应。','control')
        return web.json_response({'ok':True,'takeover':value})

    async def send(self,req):
        b=await req.json();chat=str(b.get('chat',''));self.allowed(chat)
        if not self.paused(chat):raise web.HTTPConflict(text='请先打开本会话的人工接管开关。')
        if time.time()-self.ready_at>=10:raise web.HTTPConflict(text='桥接离线或尚未更新，请在鲸鲸断开再重连。')
        text=str(b.get('text','')).strip()
        if not 1<=len(text)<=2000:raise web.HTTPBadRequest(text='请输入 1～2000 字。')
        try:mid='manual-'+str(uuid.UUID(str(b.get('id',''))))
        except ValueError:raise web.HTTPBadRequest(text='请求编号无效。')
        h=self.h;r=h.db.execute('SELECT chat,text,state FROM outbox WHERE id=?',(mid,)).fetchone()
        if r:
            if r[:2]!=(chat,text):raise web.HTTPConflict(text='重复编号对应不同消息。')
            return web.json_response({'id':mid,'state':r[2]})
        h.db.execute('INSERT INTO manual_jobs VALUES(?)',(mid,))
        h.db.execute('INSERT INTO outbox VALUES(?,?,?,?,?)',(mid,chat,text,'queued',time.time()));h.db.commit()
        return web.json_response({'id':mid,'state':'queued'})

    async def observed(self,req):
        h=self.h;b=await req.json();chat=str(b.get('chat',''));mid=str(b.get('id',''));text=str(b.get('text',''))
        if not b.get('allowed') or not chat or not mid or not text or len(text)>12000:raise web.HTTPBadRequest()
        if chat not in h.settings['allowed']:raise web.HTTPForbidden()
        if h.db.execute('SELECT 1 FROM self_seen WHERE id=?',(mid,)).fetchone():return web.json_response({'ok':True})
        h.native_chats.add(chat)
        h.db.execute('INSERT OR REPLACE INTO chats VALUES(?,?,?)',(chat,str(b.get('name') or chat),'group' if chat.endswith('@chatroom') else 'private'))
        h.db.execute('INSERT INTO self_seen VALUES(?)',(mid,))
        # Match bounded exact-content send records. Identical human text can be ambiguous.
        sent=h.db.execute("SELECT id FROM outbox WHERE chat=? AND text=? AND at>? AND state IN ('claimed','sent','uncertain') AND id NOT IN (SELECT outbox_id FROM echo_matches) ORDER BY at DESC LIMIT 1",(chat,text,time.time()-120)).fetchone()
        if sent:
            h.db.execute('INSERT INTO echo_matches VALUES(?)',sent)
        source='manual_web' if sent and self.manual(sent[0]) else 'bot' if sent else 'manual_local'
        self.event('self-'+mid,chat,'本账号',text,source)
        if source!='bot':self.context('observed-'+mid,chat,text,source)
        h.db.commit();return web.json_response({'ok':True,'source':source})

    async def inventory(self,req):
        items=await req.json()
        if not isinstance(items,list) or len(items)>200:raise web.HTTPBadRequest()
        for item in items:
            chat=str(item.get('id',''))
            if chat in self.h.settings['allowed'] and not chat.startswith('__test__'):
                self.h.native_chats.add(chat)
                self.h.db.execute('INSERT OR REPLACE INTO chats VALUES(?,?,?)',(chat,str(item.get('name') or chat),'group' if chat.endswith('@chatroom') else 'private'))
        self.h.db.commit();return web.json_response({'ok':True})

    async def start_tunnel(self):
        h=self.h
        if h.alive('remote_tunnel'):return
        exe=h.ROOT/'tools/cloudflared.exe'
        if not exe.exists():return
        log=h.DATA/'remote_tunnel.log';log.write_text('',encoding='utf-8')
        (h.DATA/'remote-url.txt').write_text('正在建立 HTTPS 连接，请稍后查看。',encoding='utf-8')
        h.launch('remote_tunnel',[str(exe),'tunnel','--no-autoupdate','--url','http://127.0.0.1:19788','--protocol','http2'],str(h.ROOT))
        for _ in range(60):
            if not self.enabled or not h.alive('remote_tunnel'):break
            raw=await asyncio.to_thread(log.read_text,encoding='utf-8',errors='replace')
            match=re.search(r'https://[a-z0-9-]+\.trycloudflare\.com',raw)
            if match:
                (h.DATA/'remote-url.txt').write_text(match[0],encoding='utf-8');return
            await asyncio.sleep(1)
        (h.DATA/'remote-url.txt').write_text('隧道未就绪，请检查 remote_tunnel.log；本机页面为 http://127.0.0.1:19788',encoding='utf-8')

    async def permit(self,req):
        h=self.h;r=h.db.execute('SELECT chat,state FROM outbox WHERE id=?',(req.query.get('id',''),)).fetchone()
        ok=bool(r and r[1]=='claimed' and (self.manual(req.query['id']) and self.enabled or not self.manual(req.query['id']) and not self.paused(r[0])))
        return web.json_response({'ok':ok})

    async def start(self,app):
        self.runner=web.AppRunner(self.app,access_log=None);await self.runner.setup()
        await web.TCPSite(self.runner,'127.0.0.1',19788).start()

    async def stop(self,app):
        self.enabled=False
        if self.h.alive('remote_tunnel'):self.h.children['remote_tunnel'].terminate()
        if hasattr(self,'runner'):await self.runner.cleanup()
