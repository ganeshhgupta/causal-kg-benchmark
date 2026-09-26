#!/usr/bin/env python3
"""
Adversarial regression suite for scorer.py. Genuinely generic across any
gold-dir following the propositions/variants/pairs/hyperedges schema (v5
fix: v4's tests 2 and 3 silently hardcoded physics-specific IDs like
'V004ca'/'K004m'/'P01'/'P05', so they only ever ran correctly against the
physics gold set despite --gold-dir suggesting otherwise. All tests here
pick their targets dynamically from whatever gold-dir is passed.
"""
import argparse, copy, json, subprocess, tempfile
from pathlib import Path

def load(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def build_perfect(root):
    variants = load(root/'variants.json')['variants']
    pairs = load(root/'pairs.json')['pairs']
    hyperedges = load(root/'hyperedges.json')['hyperedges']
    pred={'variant_predictions':[],'pair_predictions':[],'hyperedge_predictions':[]}
    for v in variants:
        pred['variant_predictions'].append({
            'variant_id':v['id'],
            'proposition_id':v['proposition_id'],
            'logical_relation':'ENTAILED_BY' if 'deliberate_error' in v else 'EQUAL'
        })
    for p in pairs:
        pred['pair_predictions'].append({
            'pair_id':p['id'],
            'logical_relation':p['logical_relation'],
            'schema_relation':p['schema_relation'],
            'context_relation':p['context_relation'],
            'direction_relation':p['direction_relation'],
        })
    for h in hyperedges:
        gold=h.get('entailed')
        if gold is None: gold=h.get('relation')=='ENTAILS'
        pred['hyperedge_predictions'].append({'hyperedge_id':h['id'],'entailed':bool(gold)})
    return pred, variants, pairs

def score(scorer, root, pred):
    with tempfile.TemporaryDirectory() as td:
        td=Path(td); pf=td/'pred.json'; rf=td/'report.json'
        pf.write_text(json.dumps(pred,indent=2),encoding='utf-8')
        cp=subprocess.run(['python',str(scorer),'--gold-dir',str(root),'--predictions',str(pf),'--json-out',str(rf)],capture_output=True,text=True)
        if cp.returncode != 0:
            raise AssertionError(cp.stderr or cp.stdout)
        return load(rf)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--gold-dir',required=True); args=ap.parse_args()
    root=Path(args.gold_dir); scorer=Path(__file__).with_name('scorer.py')
    perfect, variants, pairs = build_perfect(root)
    decoys={v['id'] for v in variants if 'deliberate_error' in v}
    ordinary_ids=[v['id'] for v in variants if 'deliberate_error' not in v]
    prop_ids=sorted({v['proposition_id'] for v in variants} | {p['a'] for p in pairs} | {p['b'] for p in pairs})

    r=score(scorer,root,perfect)
    assert r['false_merge_safety']['decoy_false_merge_rate']==0
    assert r['false_merge_safety']['pair_false_merge_rate']==0
    assert r['false_merge_safety']['wrong_target_equal_rate']==0
    assert r['contradiction_safety']['manufactured_contradiction_rate']==0
    assert r['class_recalls']['min_supported_class_recall']==1
    assert r['canonicalization']['correct_merge_rate']==1
    assert r['directional_entailment']['accuracy']==1
    print('PASS 1: perfect predictions')

    # 2. Wrong-target EQUAL must be caught, regardless of which two
    # propositions are involved -- pick any ordinary variant and any OTHER
    # proposition id to misassign it to.
    bad=copy.deepcopy(perfect)
    target_variant = next(v for v in variants if v['id'] in ordinary_ids)
    wrong_target = next(pid for pid in prop_ids if pid != target_variant['proposition_id'])
    row=next(x for x in bad['variant_predictions'] if x['variant_id']==target_variant['id'])
    row['proposition_id']=wrong_target; row['logical_relation']='EQUAL'
    r=score(scorer,root,bad)
    assert r['false_merge_safety']['wrong_target_equal_rate']>0
    assert any(x['variant_id']==target_variant['id'] for x in r['canonicalization']['wrong_target_equals'])
    assert r['canonicalization']['correct_merge_rate']<1
    print('PASS 2: wrong-target EQUAL is a false merge')

    # 3. Manufacturing a contradiction on any non-CONTRADICTS gold pair(s)
    # must be caught, regardless of which pair IDs this gold set uses.
    bad=copy.deepcopy(perfect)
    manufacture_ids=[p['id'] for p in pairs if p['logical_relation']!='CONTRADICTS'][:2]
    assert manufacture_ids, "gold set has no non-CONTRADICTS pair to test against"
    for row in bad['pair_predictions']:
        if row['pair_id'] in manufacture_ids: row['logical_relation']='CONTRADICTS'
    r=score(scorer,root,bad)
    assert r['contradiction_safety']['manufactured_contradiction_rate']>0
    assert set(r['contradiction_safety']['manufactured_contradiction_ids'])==set(manufacture_ids)
    assert r['lexicographic_key'][3]<1
    print(f'PASS 3: manufactured contradictions ({manufacture_ids}) hit headline score')

    # 4. Total decoy collapse.
    bad=copy.deepcopy(perfect)
    for row in bad['variant_predictions']:
        if row['variant_id'] in decoys: row['logical_relation']='EQUAL'
    r=score(scorer,root,bad)
    assert r['false_merge_safety']['decoy_false_merge_rate']==1
    assert r['lexicographic_key'][0]==0
    print('PASS 4: all-decoy collapse = 100% decoy false-merge rate')

    # 5. Default-to-UNRELATED must not hide total COMPATIBLE-class failure.
    bad=copy.deepcopy(perfect)
    compatible_ids={p['id'] for p in pairs if p['logical_relation']=='COMPATIBLE'}
    if compatible_ids:
        for row in bad['pair_predictions']:
            if row['pair_id'] in compatible_ids:
                row['logical_relation']='UNRELATED'
        r=score(scorer,root,bad)
        assert r['compatible_recognition']['recall']==0
        assert set(r['compatible_recognition']['missed_ids'])==compatible_ids
        assert set(r['compatible_recognition']['predicted_as_unrelated_ids'])==compatible_ids
        assert r['class_recalls']['per_class']['COMPATIBLE']['recall']==0
        assert r['lexicographic_key'][4]==0
        print('PASS 5: all-COMPATIBLE -> UNRELATED gives 0% compatible recall and hits headline score')
    else:
        print('SKIP 5: gold set has no COMPATIBLE pair')

    # 6. NEW (v5): missing a real CONTRADICTS pair (predicting COMPATIBLE
    # instead) must hit the headline score via min_supported_class_recall.
    # This is the exact hole found in ml-ai-dataset/benchmark on 2026-09-26:
    # v4's headline had no CONTRADICTS-recall gate, so this passed silently
    # until a gold set finally had a real CONTRADICTS pair to test with.
    # Skips gracefully on gold sets (e.g. the physics one) with none yet.
    contradicts_ids=[p['id'] for p in pairs if p['logical_relation']=='CONTRADICTS']
    if contradicts_ids:
        bad=copy.deepcopy(perfect)
        for row in bad['pair_predictions']:
            if row['pair_id'] in contradicts_ids:
                row['logical_relation']='COMPATIBLE'
        r=score(scorer,root,bad)
        assert r['class_recalls']['per_class']['CONTRADICTS']['recall']==0
        assert 'CONTRADICTS' in r['class_recalls']['weakest_classes']
        assert r['class_recalls']['min_supported_class_recall']==0
        assert r['lexicographic_key'][4]==0
        print(f'PASS 6: missing gold CONTRADICTS ({contradicts_ids}) hits headline via min_supported_class_recall')
    else:
        print('SKIP 6: gold set has no CONTRADICTS pair (this is itself worth fixing in the gold data, not the scorer)')

    print('\nAll scorer adversarial regression tests passed.')

if __name__=='__main__': main()
