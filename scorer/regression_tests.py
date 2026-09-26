#!/usr/bin/env python3
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
    return pred, variants

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
    perfect, variants=build_perfect(root)
    decoys={v['id'] for v in variants if 'deliberate_error' in v}

    r=score(scorer,root,perfect)
    assert r['false_merge_safety']['decoy_false_merge_rate']==0
    assert r['false_merge_safety']['pair_false_merge_rate']==0
    assert r['false_merge_safety']['wrong_target_equal_rate']==0
    assert r['contradiction_safety']['manufactured_contradiction_rate']==0
    assert r['canonicalization']['correct_merge_rate']==1
    assert r['directional_entailment']['accuracy']==1
    print('PASS 1: perfect predictions')

    bad=copy.deepcopy(perfect)
    row=next(x for x in bad['variant_predictions'] if x['variant_id']=='V004ca')
    row['proposition_id']='K004m'; row['logical_relation']='EQUAL'
    r=score(scorer,root,bad)
    assert r['false_merge_safety']['wrong_target_equal_rate']>0
    assert any(x['variant_id']=='V004ca' for x in r['canonicalization']['wrong_target_equals'])
    assert r['canonicalization']['correct_merge_rate']<1
    print('PASS 2: wrong-target EQUAL is a false merge')

    bad=copy.deepcopy(perfect)
    for row in bad['pair_predictions']:
        if row['pair_id'] in {'P01','P05'}: row['logical_relation']='CONTRADICTS'
    r=score(scorer,root,bad)
    assert r['contradiction_safety']['manufactured_contradiction_rate']>0
    assert set(r['contradiction_safety']['manufactured_contradiction_ids'])=={'P01','P05'}
    assert r['lexicographic_key'][3]<1
    print('PASS 3: manufactured contradictions hit headline score')

    bad=copy.deepcopy(perfect)
    for row in bad['variant_predictions']:
        if row['variant_id'] in decoys: row['logical_relation']='EQUAL'
    r=score(scorer,root,bad)
    assert r['false_merge_safety']['decoy_false_merge_rate']==1
    assert r['lexicographic_key'][0]==0
    print('PASS 4: all-decoy collapse = 100% decoy false-merge rate')

    # 5. Default-to-UNRELATED must not hide total COMPATIBLE-class failure.
    bad=copy.deepcopy(perfect)
    compatible_ids=set()
    pairs=load(root/'pairs.json')['pairs']
    for p in pairs:
        if p['logical_relation']=='COMPATIBLE':
            compatible_ids.add(p['id'])
    for row in bad['pair_predictions']:
        if row['pair_id'] in compatible_ids:
            row['logical_relation']='UNRELATED'
    r=score(scorer,root,bad)
    assert r['compatible_recognition']['recall']==0
    assert set(r['compatible_recognition']['missed_ids'])==compatible_ids
    assert set(r['compatible_recognition']['predicted_as_unrelated_ids'])==compatible_ids
    assert r['lexicographic_key'][4]==0
    print('PASS 5: all-COMPATIBLE -> UNRELATED gives 0% compatible recall and hits headline score')

    print('\nAll scorer adversarial regression tests passed.')

if __name__=='__main__': main()
