"""Run local bedtime stories and record timings without storing their content."""
import argparse,asyncio,json,platform,statistics,tempfile
from datetime import datetime,timezone
from pathlib import Path
from .core import create_core
from .media import DreamVision,DreamTunes
from .schema import StoryConfig
from .sync import DreamSync,Session

async def benchmark(count,length):
    rows=[];completed=0
    dreams=['A fox in a rainy forest','A small robot watching stars','A turtle near gentle ocean waves','A dragon tending a moonlit garden']
    with tempfile.TemporaryDirectory(prefix='dreamtales-benchmark-') as directory:
        sync=DreamSync(create_core(),DreamVision(),DreamTunes(Path(directory)))
        for i in range(count):
            s=Session(str(i),StoryConfig(dream=dreams[i%4],length=length));await sync.run(s)
            while len(s.scenes)<length and s.phase not in ('error','blocked'):
                s.requested_scene_id=len(s.scenes)+1
                s.fill_to=min(length,s.requested_scene_id+2)
                await sync.run(s)
            if len(s.scenes)==length:s.phase='ending'
            completed+=s.phase=='ending'
            rows.extend({'story':i+1,**metric} for metric in s.metrics)
        await sync.tunes.close()
    times=[row['total_s'] for row in rows]
    return {'version':2,'created_utc':datetime.now(timezone.utc).isoformat(),'platform':platform.platform(),
        'stories_requested':count,'stories_completed':completed,'scenes':rows,
        'summary':{'mean_scene_s':round(statistics.mean(times),3) if times else None,
            'max_scene_s':max(times) if times else None,'rejections':sum(r['rejections'] for r in rows)},
        'limitations':['No peak-memory measurement.','Curated images, not diffusion.','Quality and safety require separate evaluation.']}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stories',type=int,default=1);parser.add_argument('--length',type=int,choices=[5],default=5)
    parser.add_argument('--output',type=Path,default=Path('runtime/benchmark.json'));args=parser.parse_args()
    if not 1<=args.stories<=100:parser.error('--stories must be between 1 and 100')
    result=asyncio.run(benchmark(args.stories,args.length));args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(f"Completed {result['stories_completed']}/{args.stories} stories. Report: {args.output}")
    if result['stories_completed']!=args.stories:raise SystemExit(1)
if __name__=='__main__':main()
