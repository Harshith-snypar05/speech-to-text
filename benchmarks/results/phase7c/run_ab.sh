#!/bin/bash
# Paired A/B rerun, same session conditions as the drift baseline: (A) unmodified baseline N=4, then (B) Phase 7C relay N=2,3,4 (12 clips).
cd /c/Users/sriha/snypar/stt/speech-to-text
R=benchmarks/results/phase7c
waitport() { for i in $(seq 1 90); do netstat -ano | grep -q ":$1.*LISTENING" && return; sleep 2; done; }
pidof_port() { netstat -ano | grep ":$1.*LISTENING" | head -1 | awk '{print $5}'; }
# ---- A: baseline N=4
: > $R/phase7c_driftA_calls.jsonl
STT_PHASE7B_LOG=$R/phase7c_driftA_calls.jsonl python benchmarks/results/phase7b/instrumented_relay.py > $R/phase7c_driftA_relay.out 2>&1 &
waitport 8770; sleep 3; APID=$(pidof_port 8770); echo "baseline pid $APID"
python benchmarks/ws_bench.py --manifest $R/manifest_subset12.json --url "ws://localhost:8770/?role=speaker" --out $R/phase7c_driftA_bench_n4.json --concurrency 4 --warmup 1 --relay-pid $APID --note "drift-control baseline N=4" > $R/phase7c_driftA_bench_stdout.log 2>&1
taskkill //PID $APID //F > /dev/null 2>&1; sleep 3
echo "done baseline-n4 $(date +%T)"
# ---- B: new relay N=2,3,4
: > $R/phase7c_ab_sched.jsonl; : > $R/phase7c_ab_flush.jsonl
( cd relays_phase7c && STT_SCHED_LOG_FILE=../$R/phase7c_ab_sched.jsonl STT_FLUSH_DIAG_FILE=../$R/phase7c_ab_flush.jsonl python ../$R/start_phase7c_relay.py > ../$R/phase7c_ab_relay.out 2>&1 & )
waitport 8771; sleep 3; BPID=$(pidof_port 8771); echo "new pid $BPID"
rm -f $R/STOP_SAMPLER_AB
python $R/sampler.py $R/phase7c_ab_sys.jsonl $BPID $R/STOP_SAMPLER_AB &
SP=$!
for n in 2 3 4; do
  : > $R/phase7c_ab_sched.jsonl; : > $R/phase7c_ab_flush.jsonl
  python benchmarks/ws_bench.py --manifest $R/manifest_subset12.json --url "ws://localhost:8771/?role=speaker" --out $R/phase7c_ab_bench_n$n.json --concurrency $n --warmup 1 --relay-pid $BPID --note "Phase 7C rerun N=$n" > $R/phase7c_ab_bench_n${n}_stdout.log 2>&1
  sleep 3; cp $R/phase7c_ab_sched.jsonl $R/phase7c_ab_sched_n$n.jsonl; cp $R/phase7c_ab_flush.jsonl $R/phase7c_ab_flush_n$n.jsonl
  echo "done new-n$n $(date +%T)"
done
touch $R/STOP_SAMPLER_AB; wait $SP
taskkill //PID $BPID //F > /dev/null 2>&1
echo ABDONE
