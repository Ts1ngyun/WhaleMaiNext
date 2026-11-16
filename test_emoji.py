import base64, io, time, unittest
from PIL import Image
import test_relay

class EmojiTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_relay.RelayTests.asyncSetUp
    asyncTearDown=test_relay.RelayTests.asyncTearDown
    def message(self,chat='__test__emoji'):
        buffer=io.BytesIO();Image.new('RGB',(2,2)).save(buffer,format='PNG')
        return {'platform':'whale_wechat','account_id':'whale-local','message_id':'emoji-test',
            'message_info':{'group_info':{'group_id':chat}},
            'raw_message':[{'type':'emoji','binary_data_base64':base64.b64encode(buffer.getvalue()).decode()}]}

    async def test_emoji_preview_and_invalid_data(self):
        message=self.message()
        r=await self.client.post('/adapter/outbox',headers=self.headers,json=message)
        self.assertTrue((await r.json())['success'])
        path=self.h.db.execute('SELECT path FROM emoji_jobs').fetchone()[0]
        with Image.open(path) as img:self.assertEqual(img.format,'PNG')
        self.assertEqual(self.h.db.execute('SELECT state FROM outbox').fetchone()[0],'preview')
        message['raw_message'][0]={'type':'emoji','data':'C:/private.txt'}
        r=await self.client.post('/adapter/outbox',headers=self.headers,json=message)
        self.assertGreaterEqual(r.status,400)

    async def test_emoji_claim_requires_capability_and_takeover_blocks(self):
        self.h.native_chats.add('room');self.h.settings.update(native_whale=True,mode='mai')
        self.h.db.execute('INSERT INTO chats VALUES(?,?,?)',('room','room','group'))
        for mid in ['old','new']:
            self.h.db.execute('INSERT INTO emoji_jobs VALUES(?,?)',(mid,'image.png'))
            self.h.db.execute('INSERT INTO outbox VALUES(?,?,?,?,?)',(mid,'room','[emoji]','queued',time.time()))
        self.h.db.commit()
        self.assertIsNone(await (await self.client.get('/bridge/claim',headers=self.headers)).json())
        self.assertEqual(self.h.db.execute("SELECT state FROM outbox WHERE id='old'").fetchone()[0],'failed')
        job=await (await self.client.get('/bridge/claim?emoji=1',headers=self.headers)).json()
        self.assertEqual(job['transport'],'emoji')
        self.h.db.execute('INSERT INTO takeover VALUES(?,1)',('room',));self.h.db.commit()
        self.assertFalse((await (await self.client.get('/bridge/permit?id=new',headers=self.headers)).json())['ok'])
        r=await self.client.post('/adapter/outbox',headers=self.headers,json=self.message('room'))
        self.assertFalse((await r.json())['success'])
