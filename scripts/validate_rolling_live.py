import asyncio,json,time
from pathlib import Path
import httpx
async def main():
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8765',timeout=15) as c:
        r=await c.post('/api/sessions',json={'dream':'A fox and a rabbit walk home through a quiet forest'})
        r.raise_for_status();sid=r.json()['session_id'];url='/api/sessions/'+sid
        started=time.monotonic();rows=[]
        try:
            for n in range(1,6):
                deadline=time.monotonic()+420
                while time.monotonic()<deadline:
                    state=(await c.get(url)).json()
                    if state['phase'] in ('error','blocked','stopped'):
                        print(json.dumps({'failed_scene':n,'state':state['phase'],'prepared':state['prepared_scenes']}),flush=True)
                        raise RuntimeError(f'Generation stopped before scene {n}')
                    if state['phase'] in ('ready','ending') and state['scene']['scene_id']==n:break
                    await asyncio.sleep(1)
                else: raise RuntimeError('Scene timeout')
                if n==1:assert state['prepared_scenes']==[1,2]
                scene=state['scene'];assert bool(scene['ending'])==(n==5)
                image=await c.get(scene['image']['url']);image.raise_for_status()
                if scene['audio']['url']:(await c.get(scene['audio']['url'])).raise_for_status()
                (await c.post(url+'/playing',json={'scene_id':n})).raise_for_status()
                rows.append({'scene':n,'elapsed_s':round(time.monotonic()-started,1),'prepared':state['prepared_scenes']})
                print(json.dumps(rows[-1]),flush=True)
                if n<5:(await c.post(url+'/continue',json={'scene_id':n})).raise_for_status()
            metrics=(await c.get(url+'/metrics')).json()
            Path('runtime/rolling-validation.json').write_text(json.dumps({'result':'passed','scenes':rows,'metrics':metrics},indent=2))
        finally:await c.delete(url)
asyncio.run(main())
