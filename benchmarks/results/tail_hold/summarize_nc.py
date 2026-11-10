import json,sys
r=json.load(open(sys.argv[1]))['reps']
for x in r:
    print(x['kind'][:4],x['rep'],x['account'],'f',x['finals'],'w',x['words'],'ok' if x['valid'] else 'INVALID','fw',round(x['first_word'][0],2) if x['first_word'] else None,'fin_max',round(max(x['final_lat']),2) if x['final_lat'] else None,'lastEv',round(x['last_event_t'],1) if x['last_event_t'] else None,'close',x['close'],'exc',x['exc'],'gpu',x['gpu_mem_mib_max'],x['gpu_util_pct_max'],x['worker_log_problems'][:1])
