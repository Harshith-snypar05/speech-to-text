#!/bin/bash
# Drift control: unmodified relays/ (7B instrumented launcher, :8770) rerun now, same bench, N=2 and N=3 (12 clips).
cd /c/Users/sriha/snypar/stt/speech-to-text
R=benchmarks/results/phase7c
: > $R/phase7c_drift_calls.jsonl
STT_PHASE7B_LOG=$R/phase7c_drift_calls.jsonl python benchmarks/results/phase7b/instrumented_relay.py > $R/phase7c_drift_relay.out 2>&1 &
RP=$!
for i in $(seq 1 90); do netstat -ano | grep -q ":8770.*LISTENING" && break; sleep 2; done
WPID=$(netstat -ano | grep ":8770.*LISTENING" | head -1 | awk '{print $5}')
echo "relay pid $WPID"
rm -f $R/STOP_SAMPLER_DRIFT
python $R/sampler.py $R/phase7c_drift_sys.jsonl $WPID $R/STOP_SAMPLER_DRIFT &
SP=$!
python benchmarks/ws_bench.py --manifest $R/manifest_subset12.json --url "ws://localhost:8770/?role=speaker" --out $R/phase7c_drift_bench_n23.json --concurrency 2,3 --warmup 1 --relay-pid $WPID --note "Phase 7C drift-control: unmodified baseline" > $R/phase7c_drift_bench_stdout.log 2>&1
touch $R/STOP_SAMPLER_DRIFT; wait $SP
taskkill //PID $WPID //F > /dev/null 2>&1
echo DRIFTDONE
