"""Exercise actual local child startup and shutdown without loading WeChat."""
import asyncio

from aiohttp import ClientSession

import hub


async def smoke():
    try:
        await hub.ensure_whale()
        async with ClientSession() as client:
            async with client.post(f'http://127.0.0.1:{hub.WHALE_PORT}/webhook/wechat',
                                   json={'text':'synthetic smoke test'}) as response:
                assert response.status == 403, response.status
        await hub.apply_control({'action':'start'})
        for _ in range(40):
            try:
                from aiohttp.test_utils import make_mocked_request
                result = await hub.management(make_mocked_request('POST', '/management'))
                assert result.status == 200
                break
            except ValueError:
                raise
            except RuntimeError:
                await asyncio.sleep(.5)
        else:
            raise RuntimeError('MaiBot host did not return its management link')
        assert not hub.alive('bridge')
        print('Node auth, MaiBot management, isolated processes: OK')
    finally:
        await hub.apply_control({'action':'stop'})
        assert not any(hub.alive(name) for name in ('mai','whale','bridge'))


if __name__ == '__main__':
    asyncio.run(smoke())
