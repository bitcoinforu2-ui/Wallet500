from __future__ import annotations
import json, math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA=Path('data'); OUT='signal-intelligence.json'; LEDGER='signal-dna-ledger.json'
EVM={'ethereum','eth','bsc','bnb','base','arbitrum','optimism','polygon','avalanche','fantom','linea','zksync','mantle','scroll','blast'}
FEATURES=('holder_acceleration','unique_buyer_acceleration','wallet_accumulation','social_acceleration','volume_acceleration','liquidity_expansion','cex_acceleration','price_structure')
FRESH={'candidate-evidence-envelope.json':5400,'run-summary.json':5400,'holder-cluster-production-report.json':7200}


def load(p:Path,d:Any)->Any:
    try:return json.loads(p.read_text()) if p.exists() and p.stat().st_size else d
    except Exception:return d
def write(p:Path,x:Any): p.write_text(json.dumps(x,indent=2,ensure_ascii=False),encoding='utf-8')
def num(v,d=0.0):
    try:return float(v if v is not None else d)
    except (TypeError,ValueError):return float(d)
def ts(v):
    s=str(v or '').strip()
    if not s:return None
    try:
        if s.endswith('Z'):s=s[:-1]+'+00:00'
        x=datetime.fromisoformat(s); return (x.replace(tzinfo=timezone.utc) if x.tzinfo is None else x.astimezone(timezone.utc))
    except Exception:return None
def payload_ts(x):
    if not isinstance(x,dict):return None
    for k in ('generated_at','updated_at','created_at','timestamp','observed_at'):
        if x.get(k):return x[k]
    return None
def health(root:Path,now:datetime,enforce=True):
    checks={}; blockers=[]
    for name,max_age in FRESH.items():
        raw=payload_ts(load(root/name,None)); t=ts(raw); age=(now-t).total_seconds() if t else None
        ok=age is not None and -120<=age<=max_age
        checks[name]={'timestamp':raw,'age_seconds':round(age,1) if age is not None else None,'max_age_seconds':max_age,'ok':ok}
        if enforce and not ok:blockers.append('STALE_OR_MISSING:'+name)
    return {'production_safe':not blockers,'status':'HEALTHY' if not blockers else 'DATA_DEGRADED_FAIL_CLOSED','blockers':blockers,'checks':checks,'policy':'STALE_REQUIRED_DECISION_INPUT_BLOCKS_REAL_ALERT_PROMOTION'}
def ident(r):
    c=str(r.get('chain') or r.get('network') or '').strip().lower(); t=str(r.get('token_address') or r.get('token') or r.get('mint') or '').strip(); p=str(r.get('pair_address') or r.get('entry_pair_address') or r.get('dex_pair_address') or '').strip()
    if c in EVM:t,p=t.lower(),p.lower()
    return c,t,p
def key(r):
    c,t,p=ident(r); return f'{c}:{t}:{p}' if c and t and p else (f'{c}:{t}' if c and t else '')
def rows(x,*preferred):
    if isinstance(x,list):return [r for r in x if isinstance(r,dict)]
    if not isinstance(x,dict):return []
    for k in (*preferred,'candidates','targets','alerts','coins','tokens','rows','positions','items'):
        if isinstance(x.get(k),list):return [r for r in x[k] if isinstance(r,dict)]
    return []
def index(rs):
    exact={}; token={}
    for r in rs:
        k=key(r); c,t,_=ident(r)
        if k:exact[k]=r
        if c and t:token[f'{c}:{t}']=r
    exact.update({k:v for k,v in token.items() if k not in exact}); return exact
def lookup(ix,k): return ix.get(k) or ix.get(':'.join(k.split(':')[:2])) or {}
def vals(r,names,depth=0):
    if depth>4 or not isinstance(r,dict):return []
    out=[]
    for k,v in r.items():
        if k in names:
            try:out.append(float(v))
            except (TypeError,ValueError):pass
        elif isinstance(v,dict):out+=vals(v,names,depth+1)
    return out
def best(rs,names,d=0.0):
    z=[]; names=set(names)
    for r in rs:z+=vals(r,names)
    return max(z) if z else d
def clamp(v):return max(0.0,min(1.0,v))
def pct(v,span):return round(clamp(v/span),6)
def score(v,ceil=100):return round(clamp(v if v<=1 else v/ceil),6)
def count(v,ceil=5):return round(clamp(v/ceil),6)


def signal_dna(*rs):
    rs=tuple(r for r in rs if isinstance(r,dict) and r)
    h=best(rs,('holder_growth_pct','holders_growth_pct','holder_change_pct','holder_acceleration_pct','new_holders_pct','holder_count_change_pct'))
    b=best(rs,('unique_buyers_change_pct','buyers_change_pct','buyer_acceleration_pct','buy_count_change_pct','unique_buyer_growth_pct'))
    ws=best(rs,('wallet_accumulation_score','smart_money_score','wallet_score','accumulation_score')); wc=best(rs,('smart_wallet_buy_count','unique_smart_wallets','accumulation_wallets','wallets_buying'))
    s=best(rs,('organic_acceleration_score','social_acceleration_score','social_acceleration','social_velocity_score','social_momentum','mention_growth_pct'))
    v=best(rs,('pair_volume_change_pct','volume_change_pct','volume_acceleration_pct','h1_volume_change_pct','volume_growth_pct'))
    l=best(rs,('liquidity_change_pct','liquidity_growth_pct','execution_liquidity_change_pct','liquidity_delta_pct'))
    cs=best(rs,('cex_revival_score','cex_score')); cc=best(rs,('coherent_confirmations','cex_confirmations'))
    pr=best(rs,('price_change_pct','price_change_h1_pct','h1_price_change_pct','price_change_1h_pct')); br=best(rs,('buy_sell_ratio','buyers_sellers_ratio','buy_to_sell_ratio'))
    f={'holder_acceleration':pct(h,50),'unique_buyer_acceleration':pct(b,50),'wallet_accumulation':max(score(ws),count(wc)),'social_acceleration':score(s) if s<=100 else pct(s,200),'volume_acceleration':pct(v,150),'liquidity_expansion':pct(l,35),'cex_acceleration':max(score(cs),count(cc)),'price_structure':max(pct(pr,40),score(max(0,br-1),2))}
    o={'holder_growth_pct':h or None,'unique_buyers_change_pct':b or None,'wallet_accumulation_score':ws or None,'smart_wallet_buy_count':int(wc) if wc else None,'social_acceleration_raw':s or None,'volume_change_pct':v or None,'liquidity_change_pct':l or None,'cex_revival_score':cs or None,'cex_confirmations':int(cc) if cc else None,'price_change_pct':pr or None,'buy_sell_ratio':br or None}
    covered=sum(x is not None for x in o.values())
    return {'features':f,'observed':o,'feature_coverage_count':covered,'feature_coverage_ratio':round(covered/len(o),6),'truth_rule':'MISSING_FEATURES_REMAIN_UNOBSERVED'}
def wallet_intent(*rs):
    rs=tuple(r for r in rs if isinstance(r,dict) and r); explicit=''
    for r in rs:
        explicit=str(r.get('wallet_intent') or r.get('smart_money_intent') or '').upper()
        if explicit:break
    buys=best(rs,('smart_wallet_buy_count','wallets_buying','unique_smart_wallets','buying_wallets')); sells=best(rs,('smart_wallet_sell_count','wallets_selling','selling_wallets')); rep=best(rs,('repeat_buyers','repeat_buy_wallets','accumulation_wallets')); acc=best(rs,('wallet_accumulation_score','accumulation_score','smart_money_score'))
    if explicit in {'DISTRIBUTION','SELLING','EXIT'} or (sells>=2 and sells>max(1,buys*1.25)):lab,conf='DISTRIBUTION',.9
    elif buys>=3 or rep>=3 or score(acc)>=.65:lab,conf='CLUSTER_ACCUMULATION',.85
    elif rep>=2 or buys>=2:lab,conf='CONVICTION_BUY',.7
    elif buys>=1:lab,conf='PROBE_BUY',.55
    else:lab,conf='UNKNOWN',0.0
    return {'label':lab,'confidence':conf,'smart_wallet_buys':int(buys),'smart_wallet_sells':int(sells),'repeat_buyers':int(rep)}
def phase(dna,intent):
    f=dna['features']; avg=sum(float(f.get(k) or 0) for k in FEATURES)/len(FEATURES); o=dna['observed']; pr=num(o.get('price_change_pct')); liq=num(o.get('liquidity_change_pct'))
    if intent['label']=='DISTRIBUTION' or liq<=-25:p='DISTRIBUTION'
    elif pr>=60 or avg>=.72:p='BREAKOUT'
    elif avg>=.50:p='ACCELERATING'
    elif avg>=.28:p='WAKING'
    elif avg>=.10:p='STIRRING'
    else:p='DEAD'
    return {'phase':p,'phase_score':round(avg*100,2),'early_window':p in {'STIRRING','WAKING'},'breakout_already_visible':p=='BREAKOUT','distribution_risk':p=='DISTRIBUTION'}


def outcome(pos):
    cp=pos.get('checkpoints') if isinstance(pos.get('checkpoints'),dict) else {}; r24=num(cp.get('24h',{}).get('return_pct')) if isinstance(cp.get('24h'),dict) else None; peak=num(pos.get('peak_return_pct')) if pos.get('peak_return_pct') is not None else None
    return r24,peak
def examples(records,positions):
    by={str(p.get('key') or ''):p for p in positions if isinstance(p,dict)}; out=[]
    for rec in records:
        f=((rec.get('t0_signal_dna') or {}).get('features') or {}) if isinstance(rec,dict) else {}; pos=by.get(str(rec.get('key') or ''))
        if not pos or not all(k in f for k in FEATURES):continue
        r24,pk=outcome(pos); x=pk if pk is not None else r24
        if x is None:continue
        out.append({'key':rec.get('key'),'t0_at':rec.get('t0_at'),'features':{k:num(f.get(k)) for k in FEATURES},'winner_100':x>=100,'winner_300':x>=300,'loss_50':(r24 if r24 is not None else x)<=-50})
    return sorted(out,key=lambda x:str(x.get('t0_at') or ''))
def dna_stats(ex):
    w=[x for x in ex if x['winner_100']]; l=[x for x in ex if not x['winner_100']]
    def means(z):return {k:(round(sum(x['features'][k] for x in z)/len(z),6) if z else None) for k in FEATURES}
    wm,lm=means(w),means(l); sep=[{'feature':k,'winner_minus_loser':round(wm[k]-lm[k],6)} for k in FEATURES if wm[k] is not None and lm[k] is not None]; sep.sort(key=lambda x:abs(x['winner_minus_loser']),reverse=True)
    return {'status':'READY' if len(ex)>=20 and w and l else 'INSUFFICIENT_SAMPLE','sample_size':len(ex),'winner_count':len(w),'loser_count':len(l),'winner_feature_means':wm,'loser_feature_means':lm,'largest_separators':sep}
def fit(ex):
    w=[x for x in ex if x['winner_100']]; l=[x for x in ex if not x['winner_100']]
    if not w or not l:return {k:1/len(FEATURES) for k in FEATURES},{k:1 for k in FEATURES}
    d={k:sum(x['features'][k] for x in w)/len(w)-sum(x['features'][k] for x in l)/len(l) for k in FEATURES}; total=sum(abs(x) for x in d.values()) or 1
    return {k:abs(v)/total for k,v in d.items()},{k:(1 if v>=0 else -1) for k,v in d.items()}
def sigmoid(x):return 1/(1+math.exp(-max(-35,min(35,x))))
def predict(f,m):
    base=max(.001,min(.999,num(m.get('base_rate'),.1))); z=math.log(base/(1-base))+3*sum(num(m['weights'].get(k))*int(m['directions'].get(k) or 1)*(num(f.get(k))-.5) for k in FEATURES); return sigmoid(z)
def train(ex):
    n=len(ex); base=sum(x['winner_100'] for x in ex)/n if n else .1; weights,directions=fit(ex)
    if n<30:return {'status':'COLLECTING_SAMPLE','sample_size':n,'minimum_validation_sample':30,'base_rate':round(base,6),'weights':weights,'directions':directions,'validated':False,'production_gate_effect':False,'ranking_effect':False}
    cut=max(20,int(n*.7)); tr,ho=ex[:cut],ex[cut:]; base=sum(x['winner_100'] for x in tr)/len(tr); weights,directions=fit(tr); m={'base_rate':base,'weights':weights,'directions':directions}
    mb=sum((predict(x['features'],m)-int(x['winner_100']))**2 for x in ho)/len(ho); bb=sum((base-int(x['winner_100']))**2 for x in ho)/len(ho); imp=bb-mb; valid=len(ho)>=8 and imp>=.01
    return {'status':'VALIDATED_FOR_RANKING_ONLY' if valid else 'VALIDATION_FAILED_SHADOW_ONLY','sample_size':n,'training_size':len(tr),'holdout_size':len(ho),'base_rate':round(base,6),'weights':weights,'directions':directions,'validation':{'metric':'BRIER_SCORE','model_brier':round(mb,6),'baseline_brier':round(bb,6),'improvement':round(imp,6),'minimum_improvement':.01},'validated':valid,'production_gate_effect':False,'ranking_effect':valid}
def ev(dna,m,ex):
    f=dna['features']; avg=sum(num(f.get(k)) for k in FEATURES)/len(FEATURES); p100=predict(f,m) if m.get('validated') else min(.55,max(.03,.04+.42*avg)); w=[x for x in ex if x['winner_100']]; r300=sum(x['winner_300'] for x in w)/len(w) if len(w)>=5 else .25; loss=sum(x['loss_50'] for x in ex)/len(ex) if len(ex)>=10 else max(.08,.28-.18*avg); p300=min(p100,p100*r300); loss=min(.7,max(.03,loss)); residual=max(0,1-p100-loss); exp=p300*300+max(0,p100-p300)*100+residual*10-loss*50; ls=100*sum(num(m.get('weights',{}).get(k),1/len(FEATURES))*num(f.get(k)) for k in FEATURES)
    return {'probability_gain_100pct':round(p100,4),'probability_gain_300pct':round(p300,4),'probability_loss_50pct':round(loss,4),'expected_return_scenario_pct':round(exp,2),'learning_score':round(ls,2),'method':'VALIDATED_SHADOW_MODEL' if m.get('validated') else 'CONSERVATIVE_HEURISTIC_UNTIL_VALIDATION','confidence':'HIGH' if m.get('validated') and len(ex)>=60 else ('MEDIUM' if m.get('validated') else 'LOW'),'research_only':True}
def missed(report):
    rs=list(report.get('false_negatives') or []) if isinstance(report,dict) else []; reasons=Counter(); sources=Counter(); major=[]
    for r in rs:
        gain=num(r.get('tradable_peak_gain_since_reject_pct')); reasons.update(map(str,r.get('first_reject_reasons') or [])); sources.update([str(r.get('first_reject_source') or 'UNKNOWN')])
        if gain>=400:major.append({'identity':r.get('identity'),'peak_gain_pct':round(gain,4),'first_reject_source':r.get('first_reject_source'),'first_reject_reasons':list(r.get('first_reject_reasons') or [])})
    major.sort(key=lambda x:x['peak_gain_pct'],reverse=True)
    return {'status':'READY' if rs else 'NO_FALSE_NEGATIVE_SAMPLE','records':int(report.get('records') or 0) if isinstance(report,dict) else 0,'false_negative_winners':len(rs),'major_false_negatives':len(major),'top_blocking_rules':[{'rule':k,'count':v} for k,v in reasons.most_common(12)],'top_reject_sources':[{'source':k,'count':v} for k,v in sources.most_common(8)],'major_cases':major[:20],'learning_rule':'ANALYZE_FALSE_NEGATIVES_WITHOUT_AUTO_WEAKENING_HARD_GATES'}


def source_rows(root):
    specs={'envelope':('candidate-evidence-envelope.json',('candidates',)),'active':('active-qualified-candidates.json',()),'precursor':('revival-precursor-latest.json',('targets',)),'waking':('waking-confirmation-latest.json',('targets',)),'revival':('revival-1000-latest.json',('coins',)),'cex':('cex-revival-radar.json',('alerts',)),'holder':('holder-cluster-gate.json',('rows',)),'social':('social-intelligence-v2.json',('tokens',)),'fusion':('cross-signal-fusion-v2.json',('tokens',))}
    return {lane:rows(load(root/name,{}),*pref) for lane,(name,pref) in specs.items()}
def build(root:Path=DATA,now:datetime|None=None,enforce_freshness=True):
    now=(now or datetime.now(timezone.utc)).astimezone(timezone.utc); now_iso=now.isoformat(); h=health(root,now,enforce_freshness); src=source_rows(root); ix={k:index(v) for k,v in src.items()}; keys=set()
    for lane in ('envelope','active','precursor','waking','revival','cex'):
        keys.update(k for r in src[lane] if (k:=key(r)))
    tracker=load(root/'real-alert-10usd-summary.json',{}); positions=list(tracker.get('positions') or []) if isinstance(tracker,dict) else []; old=load(root/LEDGER,{'records':[]}); records=[x for x in old.get('records',[]) if isinstance(x,dict)] if isinstance(old,dict) else []; recmap={str(x.get('key') or ''):x for x in records if x.get('key')}; ex=examples(records,positions); model=train(ex); items=[]
    for k in sorted(keys):
        lane={name:lookup(i,k) for name,i in ix.items()}; rs=tuple(r for r in lane.values() if r)
        if not rs:continue
        ir=next((r for r in rs if ident(r)[0] and ident(r)[1]),rs[0]); c,t,p=ident(ir); p=p or next((ident(r)[2] for r in rs if ident(r)[2]),''); ck=f'{c}:{t}:{p}' if c and t and p else k; d=signal_dna(*rs); wi=wallet_intent(*rs); ph=phase(d,wi); e=ev(d,model,ex); sym=str(next((r.get('symbol') or r.get('name') for r in rs if r.get('symbol') or r.get('name')),'UNKNOWN')); price=best(rs,('price_usd','dex_price_usd','current_price_usd','reference_price')); liq=best(rs,('execution_pool_liquidity_usd','dex_pair_liquidity_usd','liquidity_usd','current_liquidity_usd'))
        items.append({'key':ck,'symbol':sym,'chain':c,'token_address':t,'pair_address':p or None,'observed_at':now_iso,'signal_dna':d,'wallet_intent':wi,'revival_phase':ph,'expected_value':e,'data_health_status':h['status'],'production_safe_data':h['production_safe'],'source_lanes_present':sorted(n for n,r in lane.items() if r)})
        rec=recmap.get(ck)
        if rec is None:
            rec={'key':ck,'symbol':sym,'chain':c,'token_address':t,'pair_address':p or None,'t0_at':now_iso,'t0_price_usd':price or None,'t0_liquidity_usd':liq or None,'t0_signal_dna':d,'t0_wallet_intent':wi,'t0_revival_phase':ph,'t0_expected_value':e,'immutable_t0':True,'observations':[]}; records.append(rec); recmap[ck]=rec
        obs=list(rec.get('observations') or []); obs.append({'at':now_iso,'price_usd':price or None,'liquidity_usd':liq or None,'revival_phase':ph['phase'],'wallet_intent':wi['label'],'learning_score':e['learning_score']}); rec['observations']=obs[-96:]; rec['last_observed_at']=now_iso
    ex=examples(records,positions); model=train(ex); items.sort(key=lambda x:(bool(x['production_safe_data']),num(x['expected_value']['expected_return_scenario_pct']),num(x['revival_phase']['phase_score'])),reverse=True)
    payload={'version':1,'generated_at':now_iso,'mode':'PROSPECTIVE_SIGNAL_DNA_SELF_LEARNING_SHADOW_V1','production_change':True,'automatic_buy':False,'data_health':h,'truth_contract':{'veteran_revival_focus':True,'signal_dna_captured_at_first_seen':True,'immutable_t0_never_rewritten':True,'stale_required_inputs_fail_closed':True,'self_learning_requires_holdout_validation':True,'self_learning_never_weakens_hard_gates':True,'validated_model_ranks_only_never_auto_promotes':True,'expected_value_is_research_estimate':True},'counts':{'candidates':len(items),'stirring':sum(x['revival_phase']['phase']=='STIRRING' for x in items),'waking':sum(x['revival_phase']['phase']=='WAKING' for x in items),'accelerating':sum(x['revival_phase']['phase']=='ACCELERATING' for x in items),'breakout':sum(x['revival_phase']['phase']=='BREAKOUT' for x in items),'distribution':sum(x['revival_phase']['phase']=='DISTRIBUTION' for x in items),'training_examples':len(ex)},'winner_loser_dna':dna_stats(ex),'self_learning_model':model,'missed_winner_lab':missed(load(root/'rejected-outcome-report.json',{})),'candidates':items}
    return payload,{'version':1,'updated_at':now_iso,'policy':'IMMUTABLE_FIRST_SEEN_T0_APPEND_ONLY_BOUNDED_OBSERVATIONS_EXACT_PAIR','records':records[-5000:]}
def run(root:Path=DATA):
    p,l=build(root,enforce_freshness=True); write(root/OUT,p); write(root/LEDGER,l); return {'data_health':p['data_health']['status'],'candidates':p['counts']['candidates'],'training_examples':p['counts']['training_examples'],'model_status':p['self_learning_model']['status'],'false_negative_winners':p['missed_winner_lab']['false_negative_winners']}
if __name__=='__main__':print(json.dumps(run(),indent=2,ensure_ascii=False))
