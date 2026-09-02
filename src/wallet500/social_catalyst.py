from __future__ import annotations
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

EVM_RE=re.compile(r'0x[a-fA-F0-9]{40}')
SOL_RE=re.compile(r'(?<![1-9A-HJ-NP-Za-km-z])[1-9A-HJ-NP-Za-km-z]{32,44}(?![1-9A-HJ-NP-Za-km-z])')
SOCIAL_SOURCES=('x','twitter','tiktok','telegram','youtube','reddit','discord','instagram','farcaster','other')


def _load(path:Path,default):
    if not path.exists():return default
    try:return json.loads(path.read_text(encoding='utf-8'))
    except Exception:return default


def _write(path:Path,payload):path.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')

def _now():return datetime.now(timezone.utc).isoformat()

def _get_json(url:str):
    req=Request(url,headers={'Accept':'application/json','User-Agent':'Wallet500/1.0'})
    with urlopen(req,timeout=20) as r:return json.loads(r.read().decode())


def _source(x:dict)->str:
    s=str(x.get('source') or x.get('platform') or 'other').lower().strip()
    return s if s in SOCIAL_SOURCES else 'other'


def _truthy(v)->bool:
    if isinstance(v,bool):return v
    return str(v or '').strip().lower() in {'1','true','yes','y','paid','sponsored'}


def _contracts(x:dict)->list[tuple[str|None,str]]:
    out=[];explicit=x.get('contract') or x.get('token') or x.get('token_address') or x.get('mint')
    chain=(str(x.get('chain') or '').lower() or None)
    if explicit:
        t=str(explicit).strip();out.append((chain,t))
    text=' '.join(str(x.get(k) or '') for k in ('text','body','title','caption','description'))
    for t in EVM_RE.findall(text):out.append((chain if chain in {'ethereum','bsc'} else None,t))
    for t in SOL_RE.findall(text):
        if not t.startswith('0x'):out.append((chain if chain=='solana' else None,t))
    seen=set();clean=[]
    for c,t in out:
        norm=t.lower() if t.startswith('0x') else t
        k=(c,norm)
        if k in seen:continue
        seen.add(k);clean.append((c,t))
    return clean


def _fingerprint(row:dict)->str:
    raw='|'.join(str(row.get(k) or '') for k in ('source','author','contract','url','published_at','text'))
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _normalize(raw:dict,seen_at:str)->list[dict]:
    if not isinstance(raw,dict):return []
    source=_source(raw);author=str(raw.get('author') or raw.get('handle') or raw.get('username') or '').strip() or None
    url=raw.get('url') or raw.get('post_url');published=raw.get('published_at') or raw.get('created_at') or raw.get('timestamp')
    text=str(raw.get('text') or raw.get('body') or raw.get('caption') or raw.get('title') or '')[:2000]
    followers=raw.get('followers');engagement=raw.get('engagement') or raw.get('views') or raw.get('likes')
    # Preserve provenance/quality metadata from providers instead of collapsing every
    # post into an equal "mention". Downstream organic-acceleration analysis is
    # fail-closed: missing metadata is unknown, never silently assumed organic.
    quality_meta={
        'project_owned':any(_truthy(raw.get(k)) for k in ('project_owned','official','is_project_account','project_account','team_account')),
        'author_role':raw.get('author_role') or raw.get('account_role'),
        'paid':any(_truthy(raw.get(k)) for k in ('paid','is_paid','paid_promotion')),
        'sponsored':any(_truthy(raw.get(k)) for k in ('sponsored','is_sponsored')),
        'incentivized':_truthy(raw.get('incentivized')),
        'promotion_type':raw.get('promotion_type') or raw.get('campaign_type'),
        'provider_event_id':raw.get('event_id') or raw.get('post_id') or raw.get('id'),
    }
    rows=[]
    for chain,contract in _contracts(raw):
        row={'source':source,'author':author,'contract':contract,'chain':chain,'url':url,'published_at':published,'first_seen_by_wallet500':seen_at,'text':text,'followers':followers,'engagement':engagement,**quality_meta}
        row['fingerprint']=_fingerprint(row);rows.append(row)
    return rows


def _seed_events(out:Path)->list[dict]:
    d=_load(out/'social-seed-events.json',[])
    return d if isinstance(d,list) else []


def _external_events(errors:list)->list[dict]:
    rows=[]
    urls=[u.strip() for u in os.getenv('WALLET500_SOCIAL_FEED_URLS','').split(',') if u.strip()]
    for url in urls:
        try:
            d=_get_json(url)
            if isinstance(d,dict):d=d.get('events') or d.get('data') or [d]
            if isinstance(d,list):rows.extend(x for x in d if isinstance(x,dict))
        except Exception as e:errors.append({'url':url,'error':f'{type(e).__name__}: {e}'[:300]})
    return rows


def _market_map(out:Path)->dict:
    d=_load(out/'market-snapshots.json',[]);rows=d if isinstance(d,list) else d.get('snapshots',[]) if isinstance(d,dict) else []
    m={}
    for x in rows or []:
        if not isinstance(x,dict):continue
        token=x.get('token') or x.get('mint');chain=x.get('chain')
        if not token:continue
        m[(chain,str(token).lower() if str(token).startswith('0x') else str(token))]=x
        m[(None,str(token).lower() if str(token).startswith('0x') else str(token))]=x
    return m


def run_social_catalyst(out:Path|str='data',now:str|None=None)->dict:
    out=Path(out);out.mkdir(parents=True,exist_ok=True);now=now or _now();errors=[]
    raw=_seed_events(out)+_external_events(errors);incoming=[]
    for x in raw:incoming.extend(_normalize(x,now))

    ledger_path=out/'social-catalyst-ledger.json';old=_load(ledger_path,{})
    events=old.get('events',[]) if isinstance(old,dict) and isinstance(old.get('events'),list) else []
    known={x.get('fingerprint') for x in events if isinstance(x,dict)};market=_market_map(out);new_count=0
    for row in incoming:
        if row['fingerprint'] in known:continue
        token=str(row['contract']);key=(row.get('chain'),token.lower() if token.startswith('0x') else token);snap=market.get(key) or market.get((None,key[1]))
        if snap:
            row['market_at_first_observation']={k:snap.get(k) for k in ('pair_address','price_usd','liquidity_usd','market_cap','fdv','volume_m5','volume_h1','buys_h1','sells_h1','price_change_m5','price_change_h1','observed_at')}
        events.append(row);known.add(row['fingerprint']);new_count+=1
    events=events[-10000:]

    groups={};authors={}
    for e in events:
        token=str(e.get('contract') or '');norm=token.lower() if token.startswith('0x') else token;key=f"{e.get('chain') or 'unknown'}:{norm}"
        g=groups.setdefault(key,{'chain':e.get('chain'),'contract':token,'mentions':0,'sources':set(),'authors':set(),'first_seen':e.get('first_seen_by_wallet500'),'latest_seen':e.get('first_seen_by_wallet500')})
        g['mentions']+=1;g['sources'].add(e.get('source'))
        if e.get('author'):g['authors'].add(e.get('author'))
        g['first_seen']=min(filter(None,[g.get('first_seen'),e.get('first_seen_by_wallet500')]),default=None);g['latest_seen']=max(filter(None,[g.get('latest_seen'),e.get('first_seen_by_wallet500')]),default=None)
        akey=f"{e.get('source')}:{e.get('author')}" if e.get('author') else None
        if akey:
            a=authors.setdefault(akey,{'source':e.get('source'),'author':e.get('author'),'mentions':0,'contracts':set(),'followers_latest':None,'engagement_observations':[]})
            a['mentions']+=1;a['contracts'].add(norm)
            if e.get('followers') is not None:a['followers_latest']=e.get('followers')
            if e.get('engagement') is not None:a['engagement_observations'].append(e.get('engagement'))

    candidates=[]
    for g in groups.values():
        g['sources']=sorted(x for x in g['sources'] if x);g['authors']=sorted(g['authors']);g['source_count']=len(g['sources']);g['author_count']=len(g['authors']);candidates.append(g)
    candidates.sort(key=lambda x:(x['source_count'],x['mentions']),reverse=True)
    influence=[]
    for a in authors.values():
        a['unique_contracts']=len(a.pop('contracts'));a['engagement_observations']=a['engagement_observations'][-50:];influence.append(a)
    influence.sort(key=lambda x:(x['unique_contracts'],x['mentions']),reverse=True)

    ledger={'version':2,'updated_at':now,'method':'IMMUTABLE_SOCIAL_EVENT_LEDGER_NO_CAUSALITY_ASSUMED','events_count':len(events),'new_events_this_run':new_count,'quality_metadata_preserved':True,'events':events};_write(ledger_path,ledger)
    report={'version':2,'updated_at':now,'status':'ACTIVE_INPUT_BRIDGE' if raw else 'WAITING_FOR_SOCIAL_FEEDS','configured_feed_count':len([u for u in os.getenv('WALLET500_SOCIAL_FEED_URLS','').split(',') if u.strip()]),'seed_events_count':len(_seed_events(out)),'new_events':new_count,'candidate_count':len(candidates),'candidates':candidates[:500],'errors':errors,'rule':'Raw social mentions are evidence only. Organic acceleration must be computed separately and never overrides liquidity, security, holder-cluster or manipulation gates.'};_write(out/'social-discovery-candidates.json',report)
    _write(out/'social-influencer-ledger.json',{'version':2,'updated_at':now,'method':'OBSERVED_MENTIONS_ONLY_NO_INFLUENCE_CLAIM_WITHOUT_FORWARD_OUTCOMES','influencers':influence[:1000]})
    return {'status':report['status'],'events':len(events),'new_events':new_count,'candidates':len(candidates),'influencers':len(influence),'errors':len(errors)}


if __name__=='__main__':print(json.dumps(run_social_catalyst(),indent=2))
