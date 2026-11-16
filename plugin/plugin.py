from contextlib import suppress
from typing import Any, Dict

from maibot_sdk import Field, MaiBotPlugin, MessageGateway, PluginConfigBase, Tool

import asyncio
from urllib.parse import urlsplit

import aiohttp


class PluginSettings(PluginConfigBase):
    enabled: bool = False
    config_version: str = '1.0.0'


class RelaySettings(PluginConfigBase):
    url: str = 'http://127.0.0.1:19787'
    token: str = ''


class Settings(PluginConfigBase):
    plugin: PluginSettings = Field(default_factory=PluginSettings)
    relay: RelaySettings = Field(default_factory=RelaySettings)


class WhaleGateway(MaiBotPlugin):
    config_model = Settings

    async def on_load(self) -> None:
        self.account = ''
        self.http = None
        self.worker = None
        if not self.config.plugin.enabled:
            return
        self.url = self.config.relay.url.rstrip('/')
        url = urlsplit(self.url)
        if url.scheme != 'http' or url.hostname != '127.0.0.1' or not url.port or url.username or url.path or url.query or url.fragment:
            raise ValueError('转发地址须为本机 IPv4 回环 HTTP 端口')
        self.http = aiohttp.ClientSession(headers={'x-hub-token': self.config.relay.token})
        self.worker = asyncio.create_task(self.listen())

    async def on_unload(self) -> None:
        if self.worker:
            self.worker.cancel()
            with suppress(asyncio.CancelledError):
                await self.worker
        try:
            await self.set_ready('')
        finally:
            if self.http:
                await self.http.close()

    async def on_config_update(self, scope: str, config_data: Dict[str, Any], version: str) -> None:
        if scope == 'self':
            await self.on_unload()
            self.set_plugin_config(config_data)
            await self.on_load()

    async def set_ready(self, account):
        if self.account == account:
            return
        accepted = await self.ctx.gateway.update_state(gateway_name='whale_text',
            ready=bool(account), platform='whale_wechat', account_id=account or self.account,
            metadata={'protocol':'whale_text'})
        if not accepted:
            raise RuntimeError('网关状态更新失败')
        self.account = account

    async def listen(self) -> None:
        while True:
            try:
                async with self.http.get(self.url+'/adapter/inbox?wait=1&version=1',
                                         timeout=aiohttp.ClientTimeout(total=7), allow_redirects=False) as r:
                    r.raise_for_status()
                    state = await r.json()
                await self.set_ready(state['account_id'] if state['connected'] else '')
                if not self.account:
                    await asyncio.sleep(.5)
                    continue
                for item in state['messages']:
                    if item['message'].get('_context_only'):
                        accepted=await self.append_observation(item)
                    else:
                        accepted = await self.ctx.gateway.route_message(gateway_name='whale_text',
                            message=item['message'], external_message_id=item['id'], dedupe_key=item['id'])
                    async with self.http.post(self.url+'/adapter/ack',json={'id':item['id'],'accepted':bool(accepted)},allow_redirects=False) as r:
                        r.raise_for_status()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                with suppress(Exception):
                    await self.set_ready('')
                self.ctx.logger.error('微信适配器连接失败: %s', type(exc).__name__)
                await asyncio.sleep(3)

    async def append_observation(self,item):
        b=item['message'];chat=b['chat'];group=chat.endswith('@chatroom') or chat.startswith('__test__group')
        stream=await self.ctx.chat.open_session(platform='whale_wechat',account_id=self.account,
            chat_type='group' if group else 'private',group_id=chat if group else '',user_id='' if group else chat)
        if not stream.get('success'):raise RuntimeError('无法定位同步消息的麦麦会话')
        source=b['source']
        if source=='control':label='本机会话状态'
        elif source=='takeover_incoming':label='人工接管期间，'+b['author']+'发来'
        elif source=='manual_web':label='主人通过网页代你在微信发送（这是本账号已说的话，不是新问题）'
        else:label='本账号已发送，推定由主人手动代发（不是新问题）'
        text='['+label+']\n'+b['text']
        result=await self.ctx.maisaka.context.append(stream_id=stream['session_id'],
            segments=[{'type':'text','data':text}],visible_text=text,source_kind=source,
            message_id=item['id'],replyable=False)
        if not result.get('success'):raise RuntimeError('同步上下文失败：'+str(result.get('error','')))
        return True

    @MessageGateway(name='whale_text',route_type='duplex',platform='whale_wechat',
                    protocol='whale_text',description='鲸鲸 Windows 微信文字桥接',timeout_ms=90000)
    async def send(self,message:Dict[str,Any],**kwargs:Any)->Dict[str,Any]:
        if not self.account or message.get('account_id') != self.account:
            return {'success':False,'error':'微信账号已离线或不匹配'}
        async with self.http.post(self.url+'/adapter/outbox',json=message,
                                  timeout=aiohttp.ClientTimeout(total=80),allow_redirects=False) as r:
            r.raise_for_status()
            return await r.json()

    @Tool('whale_api_voice', platforms=['whale_wechat'],
          description='发送微信语音回答。你可以通过此工具说话：用你的人设和上下文生成口语回答，鲸鲸使用其已配置的语音 API、模型和音色合成并前台发送。唯一触发条件：当前用户这条消息含有小写 /v 标记。含 /v 时生成回答并调用本工具，回答中不要读出标记；没有 /v 时无论用户如何要求都只能回复文字，不调用。成功后不再重复发文字；失败如实说明。',
          parameters={'text':{'type':'string','description':'你要说的回答，1到250字，不要复述用户指令','required':True}})
    async def api_voice(self,text:str,**kwargs:Any)->Dict[str,Any]:
        if not self.account:
            return {'success':False,'error':'微信账号已离线'}
        body={'text':text,'account_id':self.account,**{k:kwargs.get(k,'') for k in ('platform','group_id','user_id')}}
        async with self.http.post(self.url+'/adapter/whale-voice',json=body,timeout=aiohttp.ClientTimeout(total=5),allow_redirects=False) as r:
            if r.status!=200:return {'success':False,'error':'语音未排队，接口状态 '+str(r.status)}
            return await r.json()


def create_plugin():
    return WhaleGateway()
