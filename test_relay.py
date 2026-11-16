from pathlib import Path
import asyncio, importlib.util, json, os, tempfile, time, unittest
from aiohttp.test_utils import TestClient, TestServer

class RelayTests(unittest.IsolatedAsyncioTestCase):
    async def test_group_tool_context_requires_the_authorizing_user(self):
        chat='__test__group_voice'
        args={'platform':'whale_wechat','account_id':self.h.account_id(),'group_id':chat,'text':'你好呀'}
        r=await self.client.post('/adapter/whale-voice',headers=self.headers,json=args)
        self.assertEqual(r.status,200);self.assertFalse((await r.json())['success'])
        self.h.db.execute('INSERT INTO voice_grants VALUES(?,?,?,?,0)',('group-a',chat,'alice',time.time()+30))
        self.h.db.execute('INSERT INTO voice_grants VALUES(?,?,?,?,0)',('group-b',chat,'bob',time.time()+30))
        r=await self.client.post('/adapter/whale-voice',headers=self.headers,json=args)
        self.assertFalse((await r.json())['success'])
        self.h.db.execute("UPDATE voice_grants SET used=1 WHERE id='group-b'")
        r=await self.client.post('/adapter/whale-voice',headers=self.headers,json=args)
        self.assertFalse((await r.json())['success'])
        args['user_id']='alice'
        r=await self.client.post('/adapter/whale-voice',headers=self.headers,json=args)
        self.assertEqual((await r.json())['status'],'preview')
        r=await self.client.post('/adapter/whale-voice',headers=self.headers,json=args)
        self.assertFalse((await r.json())['success'])
    async def test_only_v_marker_authorizes_voice(self):
        for text in ['/v','/v 晚安','今天怎么样 /v','你好/v']:
            self.assertTrue(self.h.explicit_voice_request(text),text)
        for text in ['用语音回复','给我发语音','/语音 晚安','/V 晚安','你能发语音吗']:
            self.assertFalse(self.h.explicit_voice_request(text),text)
    async def test_voice_prompts_are_not_injected(self):
        self.h.adapter_at=time.time()
        for i,text in enumerate(['你能发语音吗','用语音跟我打个招呼呗','/语音 晚安']):
            r=await self.client.post('/native/reply',headers=self.headers,json={'chat_id':'room','text':text,'msg_id':str(i)})
            self.assertEqual(r.status,200)
            message=json.loads(self.h.db.execute('SELECT payload FROM inbox WHERE id=?',(str(i),)).fetchone()[0])
            self.assertEqual(message['raw_message'],[{'type':'text','data':text}])
        self.assertEqual(self.h.db.execute('SELECT COUNT(*) FROM voice_grants WHERE used=0').fetchone()[0],0)

    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        os.environ['WHALE_MAI_DATA']=self.tmp.name
        spec=importlib.util.spec_from_file_location('relay_test',Path(__file__).with_name('hub.py'))
        self.h=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.h)
        self.h.settings['allowed']=['room']
        self.client=TestClient(TestServer(self.h.app));await self.client.start_server()
        self.headers={'x-hub-token':self.h.TOKEN}
    async def test_whale_api_voice_reuses_config_without_model_copy_or_prompts(self):
        self.h.adapter_at=time.time();self.h.settings['native_whale']=True
        self.h.whale_voice_enabled=lambda chat:True
        await self.client.get('/bridge/claim?api_voice=1',headers=self.headers)
        message={'chat_id':'room','user_id':'alice','text':'/v 跟我打个招呼呗','msg_id':'ask'}
        await self.client.post('/native/reply',headers=self.headers,json=message)
        payload={'platform':'whale_wechat','account_id':self.h.account_id(),'group_id':'room','user_id':'bob','text':'你好呀'}
        r=await self.client.post('/adapter/whale-voice',headers=self.headers,json=payload)
        self.assertFalse((await r.json())['success'])
        payload['user_id']='alice'
        r=await self.client.post('/adapter/whale-voice',headers=self.headers,json=payload)
        self.assertTrue((await r.json())['success'])
        self.assertNotIn('/v1/audio/speech', {r.resource.canonical for r in self.h.app.router.routes()})
        self.assertIsNone(await (await self.client.get('/bridge/claim?voice=1',headers=self.headers)).json())
        job=await (await self.client.get('/bridge/claim?api_voice=1',headers=self.headers)).json()
        self.assertEqual(job['transport'],'whale_api_voice')
        self.assertEqual(job['text'],'你好呀')
        r=await self.client.post('/adapter/whale-voice',headers=self.headers,json=payload)
        self.assertFalse((await r.json())['success'])
        message.update(msg_id='ask2');await self.client.post('/native/reply',headers=self.headers,json=message)
        message.update(msg_id='cancel',text='不要发语音了');await self.client.post('/native/reply',headers=self.headers,json=message)
        r=await self.client.post('/adapter/whale-voice',headers=self.headers,json=payload)
        self.assertFalse((await r.json())['success'])
    async def test_plugin_api_voice_preview(self):
        import aiohttp
        spec=importlib.util.spec_from_file_location('voice_plugin_test',Path(__file__).parent/'plugin/plugin.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        plugin=module.create_plugin();plugin.url=str(self.client.make_url('')).rstrip('/')
        plugin.account=self.h.account_id()
        chat='__test__cloud_voice'
        self.h.db.execute('INSERT INTO voice_grants VALUES(?,?,?,?,0)',('plugin-preview',chat,chat,time.time()+30))
        async with aiohttp.ClientSession(headers=self.headers) as session:
            plugin.http=session
            result=await plugin.api_voice('你好呀，今天过得怎么样？',platform='whale_wechat',user_id=chat)
        self.assertTrue(result['success']);self.assertEqual(result['status'],'preview')
        self.assertIsNone(await (await self.client.get('/bridge/claim?api_voice=1',headers=self.headers)).json())

    async def asyncTearDown(self):
        await self.client.close();self.tmp.cleanup();os.environ.pop('WHALE_MAI_DATA',None)
    async def test_native_ingest_does_not_wait_for_reply(self):
        self.h.adapter_at=time.time();self.h.settings['native_whale']=True
        for n in range(12):
            response=await asyncio.wait_for(self.client.post('/native/reply',headers=self.headers,json={'chat_id':'room','text':'hello','msg_id':str(n)}),.5)
            self.assertEqual((await response.json())['reason'],'queued_to_mai')
        self.assertEqual(self.h.db.execute('SELECT COUNT(*) FROM inbox').fetchone()[0],12)
        await self.client.get('/bridge/claim',headers=self.headers)
        m={'platform':'whale_wechat','account_id':'whale-local','message_id':'reply','message_info':{'additional_config':{'platform_io_target_user_id':'room'}},'raw_message':[{'type':'text','data':'response'}]}
        pending=asyncio.create_task(self.client.post('/adapter/outbox',headers=self.headers,json=m))
        job=None
        for _ in range(50):
            job=await (await self.client.get('/bridge/claim',headers=self.headers)).json()
            if job:break
            await asyncio.sleep(.01)
        self.assertEqual(job['text'],'response')
        await self.client.post('/bridge/receipt',headers=self.headers,json={'id':job['id'],'ok':True})
        self.assertTrue((await (await pending).json())['success'])
        self.assertIsNone(await (await self.client.get('/bridge/claim',headers=self.headers)).json())

    async def test_long_poll_wakes_on_message(self):
        task=asyncio.create_task(self.client.get('/adapter/inbox?wait=1',headers=self.headers))
        await asyncio.sleep(.05)
        self.assertFalse(task.done())
        start=time.monotonic()
        self.h.enqueue({'chat_id':'wake','text':'hello','msg_id':'wake1'})
        response=await asyncio.wait_for(task,1)
        self.assertEqual((await response.json())[0]['id'],'wake1')
        self.assertLess(time.monotonic()-start,.3)

    async def test_native_image_preserves_binary(self):
        import base64
        encoded=base64.b64encode(b'\x89PNG\r\n\x1a\n'+b'a'*150000).decode()
        self.h.adapter_at=time.time()
        r=await self.client.post('/native/reply',headers=self.headers,json={'chat_id':'room','text':'图片','msg_id':'img','image_base64':encoded})
        self.assertEqual(r.status,200)
        item=(await (await self.client.get('/adapter/inbox',headers=self.headers)).json())[0]['message']
        self.assertTrue(item['is_picture']);self.assertEqual(item['raw_message'][0]['binary_data_base64'],encoded)
        self.assertEqual(item['raw_message'][0]['type'],'image')


    async def test_auth(self):
        self.assertEqual((await self.client.get('/status')).status,403)
        self.assertEqual((await self.client.get('/status',headers=self.headers)).status,200)
    async def test_headless_child_has_pipe_stdin(self):
        import sys
        self.h.launch('probe',[sys.executable,'-c','import sys; assert not sys.stdin.isatty(); assert not sys.stdin.read()'],str(Path(__file__).parent))
        code=await asyncio.wait_for(asyncio.to_thread(self.h.children['probe'].wait),10)
        self.assertEqual(code,0)
    async def test_identity_dedupe_ack(self):
        m={'chat_id':'room@chatroom','chat_type':'group','user_id':'alice','nickname':'甲','chat_title':'测试群','text':'你好','msg_id':'stable'}
        self.h.enqueue(m);self.h.enqueue(m)
        r=await self.client.get('/adapter/inbox',headers=self.headers);rows=await r.json()
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['message']['message_info']['group_info']['group_id'],'room@chatroom')
        self.assertEqual(rows[0]['message']['message_info']['user_info']['user_id'],'alice')
        await self.client.post('/adapter/ack',headers=self.headers,json={'id':'stable','accepted':True})
        self.assertEqual(await (await self.client.get('/adapter/inbox',headers=self.headers)).json(),[])
    async def test_preview_never_enters_live_queue(self):
        m={'platform':'whale_wechat','account_id':'whale-local','message_id':'preview',
           'message_info':{'additional_config':{'platform_io_target_user_id':'__test__local'}},'raw_message':[{'type':'text','data':'test'}]}
        result=await (await self.client.post('/adapter/outbox',headers=self.headers,json=m)).json()
        self.assertTrue(result['success'])
        self.assertIsNone(await (await self.client.get('/bridge/claim',headers=self.headers)).json())
        m['message_id']='not-allowed';m['message_info']['additional_config']['platform_io_target_user_id']='real-user'
        result=await (await self.client.post('/adapter/outbox',headers=self.headers,json=m)).json()
        self.assertFalse(result['success'])
    async def test_claim_receipt_and_no_resend(self):
        self.h.settings['allowed']=['room'];self.h.db.execute('INSERT INTO chats VALUES(?,?,?)',('room','Room','group'))
        self.h.native_chats.add('room')
        self.h.db.execute('INSERT INTO outbox VALUES(?,?,?,?,?)',('send1','room','body','queued',time.time()));self.h.db.commit()
        job=await (await self.client.get('/bridge/claim',headers=self.headers)).json();self.assertEqual(job['id'],'send1')
        self.assertIsNone(await (await self.client.get('/bridge/claim',headers=self.headers)).json())
        await self.client.post('/bridge/receipt',headers=self.headers,json={'id':'send1','ok':False})
        self.assertEqual(self.h.db.execute('SELECT state FROM outbox').fetchone()[0],'failed')
        self.assertIsNone(await (await self.client.get('/bridge/claim',headers=self.headers)).json())
    async def test_cancel_queue(self):
        self.h.enqueue({'chat_id':'x','user_id':'u','text':'hi','msg_id':'x'})
        self.h.cancel_queue()
        self.assertEqual(await (await self.client.get('/adapter/inbox',headers=self.headers)).json(),[])

if __name__=='__main__':unittest.main()
