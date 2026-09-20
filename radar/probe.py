import asyncio
from radar.collectors.kufar import KufarCollector
from radar.collectors.bir import BirCollector

async def main():
    print('=== KUFAR PROBE ===')
    k = KufarCollector()
    items = await k.collect()
    print('count:', len(items))
    for x in items[:10]:
        print(x)
    print('diagnostics:', len(k.diagnostics))
    for row in k.diagnostics[-20:]:
        print(row)

    print('\n=== BIR PROBE ===')
    b = BirCollector()
    items2 = await b.collect()
    print('count:', len(items2))
    for x in items2[:10]:
        print(x)
    print('diagnostics:', len(b.diagnostics))
    for row in b.diagnostics[-20:]:
        print(row)

if __name__ == '__main__':
    asyncio.run(main())
