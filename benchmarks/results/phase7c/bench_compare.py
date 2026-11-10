"""Bench-level comparison (WER, latency, partial freshness, finals) baseline (7B) vs Phase 7C. Writes phase7c_bench_compare.json"""
import json
H='./'; P='../phase7b/'
def summ(L):
    c=L['clips']; s=L['summary']; w=s['wer']
    return {'wer_pct':round(w['wer']*100,2),'wer_ci95_pct':[round(x*100,1) for x in w['ci95']],'ref_words':w['ref_words'],
      'finals_received':sum(x['finals_received'] for x in c),'partials_received':sum(x['partials_received'] for x in c),
      'ttfw_p50':s['ttfw_s']['p50'],'ttfw_p95':s['ttfw_s']['p95'],
      'first_partial_p50':s['first_partial_s']['p50'],'first_partial_p95':s['first_partial_s']['p95'],
      'final_latency_p50':s['final_latency_s']['p50'],'final_latency_p95':s['final_latency_s']['p95'],
      'final_after_hang_p95':s['final_latency_after_hang_s']['p95'],'partial_revision_rate':round(s['partial_revision_rate'],3),
      'errors':len(L['errors']),'clips_with_final_count_mismatch':sum(1 for x in c if x['finals_received']!=x['utterances_expected']),
      'hyp_words':{x['id']:x['hypothesis'] for x in c}}
def lv(f,i): return json.load(open(f))['levels'][i]
base={'subset12_n1':lv(P+'phase7b_bench_subset12.json',0),'subset12_n2':lv(P+'phase7b_bench_subset12.json',1),
      'subset12_n3':lv(P+'phase7b_bench_n34.json',0),'subset12_n4':lv(P+'phase7b_bench_n34.json',1),
      'full60_n2':lv(P+'phase7b_bench_full_n2.json',0)}
out={}
for t,b in base.items():
    n=lv(f'phase7c_bench_{t}.json',0); sb,sn=summ(b),summ(n)
    # per-clip identical hypothesis? (ids repeat across sessions at N>1: compare multiset by id order)
    hb,hn=sb.pop('hyp_words'),sn.pop('hyp_words')
    same=sum(1 for k in hb if k in hn and hb[k]==hn[k]); out[t]={'baseline':sb,'new':sn,'clips_identical_hypothesis':same,'clips_compared':len(hb)}
    print(t,'B',{k:sb[k] for k in ('wer_pct','finals_received','partials_received','first_partial_p50','final_latency_p95','partial_revision_rate','clips_with_final_count_mismatch')})
    print(t,'N',{k:sn[k] for k in ('wer_pct','finals_received','partials_received','first_partial_p50','final_latency_p95','partial_revision_rate','clips_with_final_count_mismatch')},'identical',same,'/',len(hb))
json.dump(out,open('phase7c_bench_compare.json','w'),indent=1)
