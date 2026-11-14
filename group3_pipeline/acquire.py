"""Official NASA CMR discovery and authenticated downloads. No stored credentials."""
import argparse,csv,datetime,hashlib,json,os,pathlib,re,sys,urllib.parse,urllib.request,urllib.error
PRODUCTS={'imerg_monthly':('GPM_3IMERGM','07'),'imerg_daily':('GPM_3IMERGDF','07'),
          'aqua_monthly':('MYD08_M3','6.1'),'aqua_daily':('MYD08_D3','6.1'),
          'terra_monthly':('MOD08_M3','6.1'),'merra2_monthly':('M2TMNXAER','5.12.4')}
def cmr(endpoint,params):
    url='https://cmr.earthdata.nasa.gov/search/'+endpoint+'.json?'+urllib.parse.urlencode(params)
    with urllib.request.urlopen(url,timeout=60) as r:return json.load(r)
def discover(product,start,end,limit=None):
    short,version=PRODUCTS[product]
    cols=cmr('collections',{'short_name':short,'version':version})['feed']['entry']
    if not cols:raise ValueError('NASA collection not found for product/version')
    collection=cols[0];items=[];page=1
    while True:
        data=cmr('granules',{'collection_concept_id':collection['id'],'temporal':start+'T00:00:00Z,'+end+'T23:59:59Z',
            'sort_key':'start_date','page_size':min(limit or 2000,2000),'page_num':page})['feed']['entry']
        if not data:break
        for g in data:
            # CMR intervals can overlap a boundary. Do not mistake a preceding monthly interval for the requested month.
            begin=g.get('time_start','')[:10]
            if begin and begin<start:continue
            links=[l['href'] for l in g.get('links',[]) if '/data#' in l.get('rel','') and re.search(r'\.(hdf5|hdf|nc4|nc)(?:\?|$)',l.get('href',''),re.I)]
            if links:items.append({'granule_id':g['id'],'title':g['title'],'time_start':g.get('time_start'),'time_end':g.get('time_end'),'download_url':links[0]})
            if limit and len(items)>=limit:return collection,items
        if len(data)<min(limit or 2000,2000):break
        page+=1
    return collection,items
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--product',choices=PRODUCTS,required=True)
    ap.add_argument('--start',default='2003-01-01');ap.add_argument('--end',default='2024-12-31')
    ap.add_argument('--destination',default='data/raw');ap.add_argument('--limit',type=int)
    ap.add_argument('--download',action='store_true',help='Without this flag, only public metadata is saved')
    args=ap.parse_args();dest=pathlib.Path(args.destination);dest.mkdir(parents=True,exist_ok=True)
    collection,items=discover(args.product,args.start,args.end,args.limit)
    catalogue={'product':args.product,'collection':collection,'granules':items,'discovered_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'note':'Metadata inventory only. Presence in catalogue does not mean values were downloaded.'}
    (dest/(args.product+'_inventory.json')).write_text(json.dumps(catalogue,indent=2))
    print(f'NASA inventory: {len(items)} granules. Global files may be large; Giovanni subsets are preferred.')
    if not args.download:return
    token=os.environ.get('EARTHDATA_TOKEN')
    if not token:raise SystemExit('Download requires your Earthdata token in EARTHDATA_TOKEN. Do not put it in code, chat, or a public repository.')
    for g in items:
        url=g['download_url'];host=urllib.parse.urlsplit(url).hostname
        if not host or not(host.endswith('.nasa.gov') and url.startswith('https://')):raise ValueError('Unexpected download host')
        target=dest/pathlib.Path(urllib.parse.urlsplit(url).path).name
        if target.exists():print('Existing file retained:',target.name);continue
        partial=target.with_suffix(target.suffix+'.partial')
        req=urllib.request.Request(url,headers={'Authorization':'Bearer '+token,'User-Agent':'TrendTrace student research'})
        digest=hashlib.sha256()
        try:
            with urllib.request.urlopen(req,timeout=120) as response,open(partial,'wb') as output:
                kind=response.headers.get('Content-Type','')
                if 'html' in kind:raise ValueError('Server returned login HTML rather than a science file')
                for chunk in iter(lambda:response.read(1024*1024),b''):output.write(chunk);digest.update(chunk)
            partial.rename(target)
            log=dest/'download_provenance.jsonl'
            with log.open('a',encoding='utf8') as f:f.write(json.dumps(g|{'file':str(target),'sha256':digest.hexdigest(),'downloaded_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})+'\n')
            print('Downloaded',target.name)
        except urllib.error.HTTPError as e:raise SystemExit(f'NASA returned HTTP {e.code}; complete Earthdata authorisation or use Giovanni CSV exports.')
if __name__=='__main__':main()
