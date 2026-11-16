import asyncio,json,time,uuid,unittest
from aiohttp.test_utils import TestClient,TestServer
import test_relay

class RemoteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await test_relay.RelayTests.asyncSetUp(self)
        self.h.remote.enabled=True;self.h.remote.ready_at=time.time()
        self.remote=TestClient(TestServer(self.h.remote.app));await self.remote.start_server()
        self.auth={'Authorization':'Bearer '+self.h.remote.keyfile.read_text()}
        self.h.native_chats.add('room');self.h.settings['native_whale']=True
        self.h.db.execute('INSERT INTO chats VALUES(?,?,?)',('room','测试群','group'));self.h.db.commit()
    async def asyncTearDown(self):
        await self.remote.close();await test_relay.RelayTests.asyncTearDown(self)

    async def test_remote_auth_and_isolation(self):
        self.assertEqual((await self.remote.get('/api/state')).status,401)
        self.assertEqual((await self.remote.get('/control',headers=self.auth)).status,404)
        self.assertEqual((await self.remote.get('/api/state',headers=self.auth)).status,200)
        headers={**self.auth,'Origin':'https://evil.example'}
        self.assertEqual((await self.remote.post('/api/takeover',headers=headers,json={'chat':'room','enabled':True})).status,403)
        self.h.remote.enabled=False
        self.assertEqual((await self.remote.get('/api/state',headers=self.auth)).status,503)

    async def test_manual_requires_takeover_and_idempotency(self):
        b={'id':str(uuid.uuid4()),'chat':'room','text':'人工代发测试'}
        self.assertEqual((await self.remote.post('/api/send',headers=self.auth,json=b)).status,409)
        r=await self.remote.post('/api/takeover',headers=self.auth,json={'chat':'room','enabled':True})
        self.assertEqual(r.status,200)
        for _ in range(2):self.assertEqual((await self.remote.post('/api/send',headers=self.auth,json=b)).status,200)
        self.assertEqual(self.h.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],1)
        self.assertIsNone(await (await self.client.get('/bridge/claim',headers=self.headers)).json())
        job=await (await self.client.get('/bridge/claim?remote=1',headers=self.headers)).json()
        self.assertEqual(job['text'],b['text'])
        self.assertTrue((await (await self.client.get('/bridge/permit?id='+job['id'],headers=self.headers)).json())['ok'])
        b['text']='different'
        self.assertEqual((await self.remote.post('/api/send',headers=self.auth,json=b)).status,409)

    async def test_takeover_suppresses_automatic_and_appends_context(self):
        self.h.db.execute('INSERT INTO outbox VALUES(?,?,?,?,?)',('auto','room','自动回答','claimed',time.time()));self.h.db.commit()
        await self.remote.post('/api/takeover',headers=self.auth,json={'chat':'room','enabled':True})
        self.assertFalse((await (await self.client.get('/bridge/permit?id=auto',headers=self.headers)).json())['ok'])
        self.h.adapter_at=time.time()
        await self.client.post('/native/reply',headers=self.headers,json={'chat_id':'room','msg_id':'incoming-manual','text':'你好'})
        p=json.loads(self.h.db.execute("SELECT payload FROM inbox WHERE id='incoming-manual'").fetchone()[0])
        self.assertTrue(p['_context_only'])
        m={'platform':'whale_wechat','account_id':'whale-local','message_id':'auto-new','message_info':{'group_info':{'group_id':'room'}},'raw_message':[{'type':'text','data':'不应该发'}]}
        self.assertFalse((await (await self.client.post('/adapter/outbox',headers=self.headers,json=m)).json())['success'])

    async def test_self_sync_dedup_and_bot_echo(self):
        b={'chat':'room','name':'群','id':'self1','text':'我手动说的话','allowed':True}
        for _ in range(2):self.assertEqual((await self.client.post('/bridge/self-message',headers=self.headers,json=b)).status,200)
        self.assertEqual(self.h.db.execute('SELECT COUNT(*) FROM timeline').fetchone()[0],1)
        p=json.loads(self.h.db.execute('SELECT payload FROM inbox').fetchone()[0])
        self.assertTrue(p['_context_only']);self.assertEqual(p['source'],'manual_local')
        self.h.db.execute('INSERT INTO outbox VALUES(?,?,?,?,?)',('bot1','room','机器人回复','sent',time.time()));self.h.db.commit()
        b.update(id='self2',text='机器人回复')
        self.assertEqual((await (await self.client.post('/bridge/self-message',headers=self.headers,json=b)).json())['source'],'bot')
        self.assertEqual(self.h.db.execute('SELECT COUNT(*) FROM inbox').fetchone()[0],1)

if __name__=='__main__':unittest.main()
