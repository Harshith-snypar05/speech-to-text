#!/bin/bash
# Phase 7C benchmark matrix against the isolated relay on :8771 (same ws_bench conditions as Phase 7B).
cd /c/Users/sriha/snypar/stt/speech-to-text
R=benchmarks/results/phase7c
RPID=$1
rm -f $R/STOP_SAMPLER
python $R/sampler.py $R/phase7c_sys.jsonl $RPID $R/STOP_SAMPLER &
SP=$!
run() { # tag manifest concurrency
  tag=$1; man=$2; conc=$3
  : > $R/phase7c_sched.jsonl; : > $R/phase7c_flush_diag.jsonl
  python benchmarks/ws_bench.py --manifest $R/$man --url "ws://localhost:8771/?role=speaker" \
     --out $R/phase7c_bench_$tag.json --concurrency $conc --warmup 1 --relay-pid $RPID \
     --note "Phase 7C scheduler relay :8771 $tag" > $R/phase7c_bench_${tag}_stdout.log 2>&1
  sleep 3
  cp $R/phase7c_sched.jsonl $R/phase7c_sched_$tag.jsonl; cp $R/phase7c_flush_diag.jsonl $R/phase7c_flush_diag_$tag.jsonl
  echo "done $tag $(date +%T)"
}
run subset12_n1 manifest_subset12.json 1
run subset12_n2 manifest_subset12.json 2
run subset12_n3 manifest_subset12.json 3
run subset12_n4 manifest_subset12.json 4
run full60_n2 manifest_full60_abs.json 2
touch $R/STOP_SAMPLER; wait $SP
echo ALLDONE
