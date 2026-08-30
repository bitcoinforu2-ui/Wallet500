from __future__ import annotations
import json, os, time, urllib.error
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEX="https://api.dexscreener.com"
GECKO="https://api.geckoterminal.com/api/v2"
MOONSHOT="https://api.moonshot.cc"
BIRDEYE="https://public-api.birdeye.so"
BIRDEYE_KEY=os.getenv("BIRDEYE_API_KEY","").strip()
CHAINS=("solana","ethereum","bsc")
GECKO_NETWORK={"solana":"solana","ethereum":"eth","bsc":"bsc"}
BIRDEYE_CHAIN={"solana":"solana","ethereum":"ethereum","bsc":"bsc"}
BSC_MIN_DISCOVERY_CAP=300
FRESH_PAGE_COUNT=5
DEEP_MAX_PAGE=15
GECKO_MIN_INTERVAL_SECONDS=2.15
BLOCKED_BASE_TOKENS={
 "solana":{"So11111111111111111111111111111111111111112","EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v","Es9vMFrzaCERmJfrF4H2FYD9iG6vGvL5JZtJm6Gq5tQ"},
 "ethereum":{"0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2","0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48","0xdac17f958d2ee523a2206206994597c13d831ec7","0x6b175474e89094c44da98b954eedeac495271d0f","0x2260fac5e5542a773aa44fbcfedf7c193bc2c599"},
 "bsc":{"0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c","0x55d398326f99059ff775485246999027b3197955","0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d","0xc5f0f7b66764f6ec8c8dff7ba683102295e16409"},
}
_LAST_DIAGNOSTICS={}; _LAST_GECKO_CALL=0.0

def _get(url,timeout=20,retries=3,headers=None):
 last=None
 for attempt in range(max(1,retries)):
  try:
   h={"Accept":"application/json","User-Agent":"Wallet500/1.5"}; h.update(headers or {})
   with urlopen(Request(url,headers=h),timeout=timeout) as r:return json.loads(r.read().decode())
  except urllib.error.HTTPError as e:
   last=e
   if e.code==429 and attempt+1<retries:
    try: delay=max(2.5,float(e.headers.get("Retry-After") or 0))
    except Exception: delay=3.5*(attempt+1)
    if delay<=2.5: delay=3.5*(attempt+1)
    time.sleep(delay); continue
   if attempt+1<retries: time.sleep(1.5*(attempt+1))
  except Exception as e:
   last=e
   if attempt+1<retries: time.sleep(1.5*(attempt+1))
 raise last

def _gecko_get(url):
 global _LAST_GECKO_CALL
 wait=GECKO_MIN_INTERVAL_SECONDS-(time.monotonic()-_LAST_GECKO_CALL)
 if wait>0: time.sleep(wait)
 try:return _get(url,retries=4)
 finally:_LAST_GECKO_CALL=time.monotonic()

def _key(chain,token):return (chain,token.lower() if chain in {"ethereum","bsc"} else token)
def _blocked(chain,token):
 if not token:return True
 norm=token.lower() if chain in {"ethereum","bsc"} else token
 return norm in BLOCKED_BASE_TOKENS.get(chain,set())
def _chain_limit(chain,limit):return max(int(limit),BSC_MIN_DISCOVERY_CAP) if chain=="bsc" else int(limit)

def _add(rows,seen,counts,filtered,chain,token,source,limit,**extra):
 if chain not in counts or not token:return
 if _blocked(chain,token):filtered[chain]=filtered.get(chain,0)+1;return
 key=_key(chain,token)
 if key in seen:
  for row in rows:
   if _key(row["chain"],row["token"])==key:
    srcs=row.setdefault("sources",[row.get("source")])
    if source not in srcs:srcs.append(source)
    row["source_confirmations"]=len(srcs); row.update({k:v for k,v in extra.items() if v is not None}); break
  return
 if counts[chain]>=_chain_limit(chain,limit):return
 seen.add(key); counts[chain]+=1
 rows.append({"chain":chain,"token":token,"source":source,"sources":[source],"source_confirmations":1,**extra})

def _moonshot(wanted,limit,rows,seen,counts,filtered,errors):
 if "solana" not in wanted:return
 for view in ("rising","trending","top","finalized","new"):
  try:data=_get(f"{MOONSHOT}/tokens/v1/{view}/solana")
  except Exception as e:errors.append({"source":"moonshot","view":view,"error":repr(e)});continue
  if isinstance(data,dict):data=data.get("data") or data.get("tokens") or [data]
  for x in data or []:
   token=x.get("tokenId") or x.get("tokenAddress") or x.get("mint") or x.get("address")
   _add(rows,seen,counts,filtered,"solana",token,"moonshot:"+view,limit,moonshot_view=view,moonshot_pair=x.get("pairId") or x.get("pairAddress"),moonshot_price=x.get("priceUsd") or x.get("price"),moonshot_volume=x.get("volumeUsd") or x.get("volume"),moonshot_marketcap=x.get("marketCap") or x.get("marketCapUsd"))

def _dex_latest(wanted,limit,rows,seen,counts,filtered,errors):
 for ep in ("/token-profiles/latest/v1","/token-boosts/latest/v1","/token-boosts/top/v1","/community-takeovers/latest/v1"):
  try:data=_get(DEX+ep)
  except Exception as e:errors.append({"source":"dexscreener","endpoint":ep,"error":repr(e)});continue
  if isinstance(data,dict):data=[data]
  for rank,x in enumerate(data or [],1):
   chain=str(x.get("chainId","")).lower(); token=x.get("tokenAddress")
   if chain not in wanted:continue
   extra={"url":x.get("url")}
   if ep=="/token-boosts/latest/v1":extra.update({"dex_boost_active":True,"dex_boost_latest_rank":rank,"boost_amount":x.get("amount"),"boost_total":x.get("totalAmount")})
   elif ep=="/token-boosts/top/v1":extra.update({"dex_boost_active":True,"dex_boost_top_rank":rank,"boost_amount":x.get("amount"),"boost_total":x.get("totalAmount")})
   _add(rows,seen,counts,filtered,chain,token,"dexscreener:"+ep,limit,**extra)

def _birdeye_new_listings(wanted,limit,rows,seen,counts,filtered,errors):
 if not BIRDEYE_KEY:
  errors.append({"source":"birdeye:new_listing","status":"UNCONFIGURED","error":"BIRDEYE_API_KEY_MISSING"});return
 for chain in sorted(wanted):
  bchain=BIRDEYE_CHAIN.get(chain)
  if not bchain:continue
  params={"limit":20}
  if chain=="solana":params["meme_platform_enabled"]="true"
  try:data=_get(f"{BIRDEYE}/defi/v2/tokens/new_listing?{urlencode(params)}",headers={"X-API-KEY":BIRDEYE_KEY,"x-chain":bchain})
  except Exception as e:errors.append({"source":"birdeye:new_listing","chain":chain,"error":repr(e)});continue
  body=data.get("data") if isinstance(data,dict) else data
  items=(body.get("items") or body.get("tokens") or body.get("list") or []) if isinstance(body,dict) else (body or [])
  for x in items:
   if not isinstance(x,dict):continue
   token=x.get("address") or x.get("tokenAddress") or x.get("token_address")
   _add(rows,seen,counts,filtered,chain,token,"birdeye:new_listing",limit,birdeye_liquidity=x.get("liquidity"),birdeye_symbol=x.get("symbol"),birdeye_name=x.get("name"),birdeye_listing_time=x.get("liquidityAddedAt") or x.get("listedAt") or x.get("createdAt"))

def _extract_address(token_id,token_obj):
 attrs=(token_obj or {}).get("attributes") or {}; address=attrs.get("address")
 return address or (token_id.split("_",1)[1] if token_id and "_" in token_id else None)

def _gecko_pool_page(chain,network,endpoint,page,limit,rows,seen,counts,filtered,source):
 payload=_gecko_get(f"{GECKO}/networks/{network}/{endpoint}?{urlencode({'page':page,'include':'base_token'})}")
 included={x.get("id"):x for x in payload.get("included",[]) if isinstance(x,dict)}; before=counts[chain]
 for pool in payload.get("data",[]) or []:
  rel=(pool.get("relationships") or {}).get("base_token",{}).get("data") or {}; tid=rel.get("id"); a=pool.get("attributes") or {}; token_obj=included.get(tid,{}) or {}; ta=token_obj.get("attributes") or {}
  _add(rows,seen,counts,filtered,chain,_extract_address(tid,token_obj),source,limit,pool_address=a.get("address"),pool_created_at=a.get("pool_created_at"),name=a.get("name"),symbol=ta.get("symbol"),token_name=ta.get("name"),discovery_page=page,reserve_usd=a.get("reserve_in_usd"),volume_usd=a.get("volume_usd"),transactions=a.get("transactions"),price_change_percentage=a.get("price_change_percentage"))
 return counts[chain]-before

def _gecko_fresh_lane(wanted,limit,rows,seen,counts,filtered,errors,fresh_pages=FRESH_PAGE_COUNT):
 pages_used={}
 for chain in sorted(wanted):
  network=GECKO_NETWORK.get(chain)
  if not network:continue
  pages=list(range(1,max(1,fresh_pages)+1)); pages_used[chain]=pages
  for page in pages:
   try:_gecko_pool_page(chain,network,"new_pools",page,limit,rows,seen,counts,filtered,"geckoterminal:new_pools:fresh")
   except Exception as e:errors.append({"source":"geckoterminal:new_pools:fresh","chain":chain,"page":page,"error":repr(e)})
 return pages_used

def _gecko_deep_lane(wanted,limit,rows,seen,counts,filtered,start_pages,pages_per_run,max_page,errors,fresh_pages=FRESH_PAGE_COUNT):
 start_pages=start_pages or {}; next_pages={}; pages_used={}; deep_first=max(2,fresh_pages+1); max_page=max(deep_first,max_page)
 for chain in sorted(wanted):
  network=GECKO_NETWORK.get(chain)
  if not network:continue
  raw=int(start_pages.get(chain,deep_first)); start=raw if deep_first<=raw<=max_page else deep_first; pages=[]; p=start
  for _ in range(max(1,pages_per_run)):pages.append(p);p=deep_first if p>=max_page else p+1
  next_pages[chain]=p; pages_used[chain]=pages
  for page in pages:
   try:_gecko_pool_page(chain,network,"new_pools",page,limit,rows,seen,counts,filtered,"geckoterminal:new_pools:deep")
   except Exception as e:errors.append({"source":"geckoterminal:new_pools:deep","chain":chain,"page":page,"error":repr(e)})
  for endpoint,source in (("trending_pools","geckoterminal:trending_pools"),("pools","geckoterminal:top_pools")):
   try:_gecko_pool_page(chain,network,endpoint,1,limit,rows,seen,counts,filtered,source)
   except Exception as e:errors.append({"source":source,"chain":chain,"error":repr(e)})
 return next_pages,pages_used

def _source_stats(rows):
 counts={}; confirmations={}
 for row in rows:
  srcs=row.get("sources") or [row.get("source")]
  for s in srcs:
   if s:counts[s]=counts.get(s,0)+1
  c=int(row.get("source_confirmations") or len(srcs) or 1); confirmations[c]=confirmations.get(c,0)+1
 return {"unique_tokens_by_source":counts,"cross_source_confirmation_histogram":confirmations,"multi_source_tokens":sum(1 for r in rows if int(r.get("source_confirmations") or 1)>=2)}

def discovery_diagnostics():return dict(_LAST_DIAGNOSTICS)

def discover_tokens(chains=CHAINS,limit_per_chain=120,start_pages=None,pages_per_run=3,max_page=DEEP_MAX_PAGE):
 global _LAST_DIAGNOSTICS
 wanted=set(chains); rows=[]; seen=set(); errors=[]; counts={c:0 for c in wanted}; filtered={c:0 for c in wanted}
 effective_limits={c:_chain_limit(c,limit_per_chain) for c in wanted}
 _birdeye_new_listings(wanted,limit_per_chain,rows,seen,counts,filtered,errors)
 fresh_pages_used=_gecko_fresh_lane(wanted,limit_per_chain,rows,seen,counts,filtered,errors,FRESH_PAGE_COUNT)
 _moonshot(wanted,limit_per_chain,rows,seen,counts,filtered,errors)
 _dex_latest(wanted,limit_per_chain,rows,seen,counts,filtered,errors)
 next_pages,deep_pages_used=_gecko_deep_lane(wanted,limit_per_chain,rows,seen,counts,filtered,start_pages,pages_per_run,max_page,errors,FRESH_PAGE_COUNT)
 dead=[c for c in sorted(wanted) if counts.get(c,0)==0]; health={c:("FAILED" if counts.get(c,0)==0 else "DEGRADED" if counts.get(c,0)<10 else "HEALTHY") for c in sorted(wanted)}
 boosted=[x for x in rows if x.get("dex_boost_active")]; saturated={c:counts.get(c,0)>=effective_limits.get(c,0) for c in sorted(wanted)}; stats=_source_stats(rows)
 _LAST_DIAGNOSTICS={"version":2,"mode":"DISCOVERY_V2_MULTI_SOURCE","counts":dict(counts),"total_unique_tokens":len(rows),"effective_limits":effective_limits,"cap_saturated":saturated,"health":health,"filtered_base_assets":dict(filtered),"cursor_in":dict(start_pages or {}),"cursor_out":dict(next_pages),"fresh_overlap_pages":fresh_pages_used,"deep_pages_scanned":deep_pages_used,"fresh_overlap_enabled":True,"fresh_overlap_page_count":FRESH_PAGE_COUNT,"gecko_min_interval_seconds":GECKO_MIN_INTERVAL_SECONDS,"birdeye_configured":bool(BIRDEYE_KEY),"dex_boosted_seen":len(boosted),"dex_boost_top_seen":sum(1 for x in boosted if x.get("dex_boost_top_rank") is not None),**stats,"errors_count":len(errors),"recent_errors":errors[-30:]}
 if dead:raise RuntimeError(f"Discovery health failure: zero tokens on {dead}; recent_errors={errors[-12:]}")
 return rows,next_pages

def discover_solana_tokens(limit=120):
 rows,_=discover_tokens(("solana",),limit);return [{"mint":x["token"],**x} for x in rows]
