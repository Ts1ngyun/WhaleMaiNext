"""Async MaiBot delivery using the original WhaleGirl foreground sender."""
import json
import os
import time
from pathlib import Path
import requests
import threading
import sqlite3

_requests = {}

def sync_self(runtime,msg):
    """Persist before forwarding; this path never calls the reply engine."""
    chat=str(msg.get('username') or '')
    if not chat or not runtime.send_policy_allows(chat,runtime.display_name(chat)):return
    if msg.get('type')!='文本':return
    text=str(msg.get('content') or '').strip()
    if not text:return
    payload={'chat':chat,'name':runtime.display_name(chat),'text':text,
        'id':'%s:%s:%s'%(chat,msg.get('shard') or '',msg.get('local_id')),'allowed':True}
    cfg=json.loads((Path(__file__).resolve().parent.parent/'data/maibot-link.json').read_text(encoding='utf-8-sig'))
    with sqlite3.connect(Path(cfg['tokenFile']).parent/'self-sync.sqlite3',timeout=5) as db:
        db.execute('CREATE TABLE IF NOT EXISTS pending(id TEXT PRIMARY KEY,payload TEXT)')
        db.execute('INSERT OR IGNORE INTO pending VALUES(?,?)',(payload['id'],json.dumps(payload,ensure_ascii=False)))

def flush_self(session,folder):
    with sqlite3.connect(folder/'self-sync.sqlite3',timeout=2) as db:
        db.execute('CREATE TABLE IF NOT EXISTS pending(id TEXT PRIMARY KEY,payload TEXT)')
        rows=db.execute('SELECT id,payload FROM pending LIMIT 5').fetchall()
        for mid,payload in rows:
            r=session.post('http://127.0.0.1:19787/bridge/self-message',json=json.loads(payload),timeout=3);r.raise_for_status()
            db.execute('DELETE FROM pending WHERE id=?',(mid,))

def permitted(session,job):
    r=session.get('http://127.0.0.1:19787/bridge/permit',params={'id':job['id']},timeout=3)
    r.raise_for_status();return bool(r.json().get('ok'))

def enabled():
    return (Path(__file__).resolve().parent.parent/'data/maibot-link.json').exists()

def image_mode():
    cfg=json.loads((Path(__file__).resolve().parent.parent/'data/maibot-link.json').read_text(encoding='utf-8-sig'))
    policy=Path(cfg['tokenFile']).parent/'image-policy.json'
    if not policy.exists():return 'request'
    mode=json.loads(policy.read_text(encoding='utf-8-sig')).get('mode','request')
    if mode not in ('auto','request','off'):raise ValueError('Invalid image policy')
    return mode


def allow_media(msg):
    if not enabled():return True
    kind=msg.get('type')
    content=str(msg.get('content') or '')
    # Stickers occasionally arrive with the image type but contain emoji XML.
    if kind in ('表情','动画表情') or (kind=='图片' and '<emoji' in content.lower()):
        return False
    if kind not in ('文本','图片'):return True
    if kind=='文本' and not content.strip().startswith('/识图'):return True
    mode=image_mode()
    now=time.monotonic()
    for k in list(_requests):
        if now-_requests[k]>60:_requests.pop(k,None)
    key=(msg.get('username'),msg.get('sender_username'))
    if kind=='文本':
        if mode=='request':_requests[key]=now
        return False
    requested=_requests.pop(key,None) is not None
    return mode=='auto' or (mode=='request' and requested)


_voice_busy=threading.Lock()

def voice_worker(runtime,job,headers):
    import engine as G
    session=requests.Session();session.trust_env=False;session.headers.update(headers)
    ok=False
    try:
        if G.rate_guard(job['chat']):
            if job.get('transport')=='whale_api_voice':
                import uiautomation as auto
                cfg=json.loads((Path(__file__).resolve().parent.parent/'data/maibot-link.json').read_text(encoding='utf-8-sig'))
                policy=Path(cfg['tokenFile']).parent/'voice-policy.json'
                def cancelled():
                    try:return json.loads(policy.read_text(encoding='utf-8'))['generation']!=job.get('voice_generation') or not permitted(session,job)
                    except Exception:return True
                with auto.UIAutomationInitializerInThread():
                    ok=bool(runtime.send_voice_reply(job['text'],runtime.display_name(job['chat']),job['chat'],cancelled=cancelled))
    except Exception as exc:G.log_error('API 语音未完成，不自动重发：',repr(exc))
    finally:
        try:session.post('http://127.0.0.1:19787/bridge/receipt',json={'id':job['id'],'ok':ok},timeout=3).raise_for_status()
        except Exception as exc:G.log_error('API 语音回执失败，不自动重发：',repr(exc))
        _voice_busy.release()

def run(runtime):
    import engine as G
    session=requests.Session();session.trust_env=False
    try:
        cfg=json.loads((Path(__file__).resolve().parent.parent/'data/maibot-link.json').read_text(encoding='utf-8-sig'))
        session.headers['x-hub-token']=Path(cfg['tokenFile']).read_text(encoding='utf-8-sig').strip()
    except Exception as exc:
        G.log_error('麦麦异步发送未启动：',repr(exc));return
    while True:
        try:
            if time.time()-getattr(run,'inventory_at',0)>30:
                items=[]
                for entry in runtime.db.get_sessions(limit=100):
                    chat=str(entry.get('username') or '')
                    if chat and runtime.send_policy_allows(chat,runtime.display_name(chat)):
                        items.append({'id':chat,'name':runtime.display_name(chat)})
                session.post('http://127.0.0.1:19787/bridge/chats',json=items,timeout=3).raise_for_status()
                run.inventory_at=time.time()
            flush_self(session,Path(cfg['tokenFile']).parent)
            result=session.get('http://127.0.0.1:19787/bridge/claim?voice=1&api_voice=1&remote=1&emoji=1',timeout=3);result.raise_for_status();job=result.json()
            if not job:time.sleep(.15);continue
            if job.get('transport') in ('whale_api_voice',):
                if _voice_busy.acquire(blocking=False):
                    threading.Thread(target=voice_worker,args=(runtime,job,dict(session.headers)),daemon=True,name='whale-api-voice').start()
                else:
                    session.post('http://127.0.0.1:19787/bridge/receipt',json={'id':job['id'],'ok':False},timeout=3)
                    G.log('上一条语音尚未结束，本次请求跳过；不会积压发送')
                continue
            ok=False
            try:
                if permitted(session,job) and G.rate_guard(job['chat']):
                    if job.get('transport')=='emoji':
                        import uiautomation as auto
                        with auto.UIAutomationInitializerInThread():
                            outcome=runtime.send_sticker(job['path'],runtime.display_name(job['chat']),job['chat'],job_id=job['id'],
                                bridge_gate=lambda:permitted(session,job),bridge_directory=str(Path(cfg['tokenFile']).parent/'emoji-outbox'))
                        ok=isinstance(outcome,dict) and outcome.get('status')=='confirmed'
                        if not ok:G.log_error('麦麦表情包未确认发送，不重试：',repr(outcome))
                    else:
                        ok=bool(runtime.send_text(job['text'],runtime.display_name(job['chat']),job['chat'], bridge_gate=lambda: permitted(session,job)))
            except Exception as exc:G.log_error('麦麦前台发送失败：',repr(exc))
            # No retry of uncertain sends; original send_text checks live permissions.
            receipt=session.post('http://127.0.0.1:19787/bridge/receipt',json={'id':job['id'],'ok':ok},timeout=3)
            receipt.raise_for_status()
        except Exception as exc:
            G.log_throttled('maibot-async-send','麦麦发送队列不可用：',repr(exc),ttl=30)
            time.sleep(2)
