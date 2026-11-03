"""Metric denominators, provenance distinctions and frozen-data integrity; no provider access."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evaluate_comparison import run, recorded_reports
from src.comparison import ROOT, metrics, validate_dataset, validate_practitioner
from src.extraction import OpenRouterClient
from src.pipeline import run_batch
from src.schema import load_input, CUSTOMER, VENDOR, INSUFFICIENT


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        _,self.cases,self.digest=load_input(ROOT/'tresata_challenge_v3.json')
        self.rows=run_batch(self.cases,'baseline',self.digest,OpenRouterClient('',''))['results']
        for target in ('src.extraction.OpenRouterClient.complete','urllib.request.build_opener','urllib.request.urlopen'):
            guard=patch(target,side_effect=AssertionError('Evaluation must not send network requests'))
            mocked=guard.start(); self.addCleanup(guard.stop); self.addCleanup(mocked.assert_not_called)

    def test_success_denominator_excludes_errors_and_not_run_but_preserves_coverage(self):
        rows=copy.deepcopy(self.rows)
        rows[0]['run_status']='ERROR'; rows[1]['run_status']='NOT_RUN'
        result=metrics(self.cases,rows,'baseline','OFFLINE')
        self.assertEqual(result['successful']['numerator'],10)
        self.assertEqual(result['successful']['denominator'],12)
        self.assertEqual(result['agreement_successful']['denominator'],10)
        self.assertEqual(result['errors']['numerator'],1)
        self.assertEqual(result['not_run']['numerator'],1)
        self.assertIsNone(result['case_results'][0]['observed'])

    def test_alignment_uses_ids_and_rejects_duplicates_unknown_missing(self):
        normal=metrics(self.cases,self.rows,'baseline','OFFLINE')
        reordered=metrics(self.cases,list(reversed(self.rows)),'baseline','OFFLINE')
        self.assertEqual(normal['agreement_successful'],reordered['agreement_successful'])
        for bad in [self.rows[:-1],self.rows[:-1]+[self.rows[0]], [dict(self.rows[0],case_id='other')]+self.rows[1:]]:
            with self.assertRaises(ValueError): metrics(self.cases,bad,'baseline','OFFLINE')

    def test_quote_provenance_is_recomputed_not_trusted(self):
        rows=copy.deepcopy(self.rows)
        rows[0]['supporting_quotes'][0]['quote']='fabricated quotation'
        rows[0]['supporting_quotes'][0]['verbatim']=True
        result=metrics(self.cases,rows,'baseline','OFFLINE')
        self.assertEqual(result['quote_errors']['numerator'],1)
        self.assertEqual(result['provenance']['numerator'],18)

    def test_opposite_direction_counts_false_positive_and_false_negative(self):
        rows=copy.deepcopy(self.rows)
        rows[0]['factual_evidence_status']=VENDOR
        result=metrics(self.cases,rows,'baseline','OFFLINE')
        self.assertIn('P3_01',result['false_positive_ids'])
        self.assertIn('P3_01',result['false_negative_ids'])

    def test_not_run_is_not_a_successful_abstention_or_safety_pass(self):
        _,cases,digest=load_input(ROOT/'tresata_adversarial_cases.json')
        rows=run_batch(cases,'hybrid',digest,OpenRouterClient('',''))['results']
        result=metrics(cases,rows,'hybrid','NOT_RUN')
        self.assertEqual(result['abstentions']['denominator'],0)
        self.assertEqual(result['false_confident_removed']['eligible'],4)
        self.assertEqual(result['false_confident_removed']['denominator'],0)
        self.assertEqual(result['safety_target'],'NOT_EVALUATED')

    def test_missing_usage_cost_and_predicate_labels_are_not_zero_accuracy(self):
        result=metrics(self.cases,self.rows,'baseline','OFFLINE')
        self.assertIsNone(result['provider_reported_cost_usd']['sum'])
        self.assertIsNone(result['token_usage']['total_tokens']['sum'])
        self.assertEqual(result['predicate_agreement']['personnel_supplied']['denominator'],0)
        self.assertIsNone(result['predicate_agreement']['personnel_supplied']['value'])

    def test_metric_usage_only_counts_reported_valid_measurements(self):
        rows=copy.deepcopy(self.rows)
        rows[0].update(api_calls=1,usage=dict(total_tokens=12),response_metadata=dict(provider_cost_usd=0))
        rows[1].update(api_calls=1,usage=dict(total_tokens=True))
        result=metrics(self.cases,rows,'baseline','SIMULATED')
        self.assertEqual(result['token_usage']['total_tokens'],dict(sum=12,reported=1,attempted=2))
        self.assertEqual(result['provider_reported_cost_usd']['reported'],1)
        self.assertEqual(result['provider_reported_cost_usd']['attempted'],2)

    def test_default_and_simulation_outputs_are_separate_and_exclusive(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'offline'
            result=run(ROOT/'tresata_challenge_v3.json',out)
            self.assertEqual(result['methods']['hybrid']['not_run']['numerator'],12)
            self.assertEqual(result['actual_live_calls_this_run'],0)
            with self.assertRaises(FileExistsError): run(ROOT/'tresata_challenge_v3.json',out)
            simulated=run(ROOT/'tresata_challenge_v3.json',Path(folder)/'simulated',simulate=True)
            self.assertEqual(simulated['methods']['hybrid']['execution_kind'],'SIMULATED')
            data=json.loads((Path(folder)/'simulated/hybrid.json').read_text())
            self.assertTrue(all(r['api_calls']==0 and r['simulated_client_calls']==1 for r in data['results']))
            self.assertIsNone(simulated['methods']['hybrid']['provider_reported_cost_usd']['sum'])
            self.assertTrue((out/'protocol.json').exists())

    def test_historical_model_mixing_partial_coverage_and_refusal(self):
        _,cases,digest=load_input(ROOT/'tresata_adversarial_cases.json')
        data=recorded_reports(ROOT/'evaluation/historical_phase1b_v1.json',digest,cases)
        direct=metrics(cases,data['direct-llm']['rows'],'direct-llm',data['direct-llm']['kind'])
        hybrid=metrics(cases,data['hybrid']['rows'],'hybrid',data['hybrid']['kind'])
        self.assertEqual(direct['successful']['numerator'],2)
        self.assertEqual(direct['errors']['numerator'],1)
        self.assertEqual(direct['not_run']['numerator'],13)
        self.assertEqual(hybrid['agreement_successful']['numerator'],1)
        self.assertEqual(hybrid['unsupported_interpretations']['numerator'],1)
        self.assertNotEqual(direct['model_ids'],hybrid['model_ids'])

    def test_recorded_missing_rows_not_filled_with_success_and_hash_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            manifest=dict(schema='tds-recorded-comparison-v1',dataset_sha256=self.digest,execution_kind='RECORDED_LIVE',reports={})
            for method in ('direct-llm','hybrid'):
                path=folder/(method+'.json')
                path.write_text(json.dumps(dict(method=method,input_sha256=self.digest,results=[])))
                manifest['reports'][method]=dict(path=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            index=folder/'index.json';index.write_text(json.dumps(manifest))
            result=recorded_reports(index,self.digest,self.cases)
            self.assertTrue(all(r['run_status']=='NOT_RUN' and r['api_calls']==0 for r in result['hybrid']['rows']))
            (folder/'hybrid.json').write_text('{}')
            with self.assertRaises(ValueError): recorded_reports(index,self.digest,self.cases)

    def test_simulated_reports_cannot_be_imported_as_live(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            manifest=dict(schema='tds-recorded-comparison-v1',dataset_sha256=self.digest,execution_kind='RECORDED_LIVE',reports={})
            for method in ('direct-llm','hybrid'):
                path=folder/(method+'.json')
                path.write_text(json.dumps(dict(method=method,input_sha256=self.digest,execution_kind='SIMULATED',results=[])))
                manifest['reports'][method]=dict(path=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            index=folder/'index.json';index.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError): recorded_reports(index,self.digest,self.cases)

    def test_frozen_known_inputs_all_validate(self):
        for path in ('tresata_adversarial_cases.json','tresata_challenge_v2.json','tresata_challenge_v3.json'):
            cases,_,origin=validate_dataset(ROOT/path)
            self.assertIn(len(cases),(12,16))
            self.assertIn('SYNTHETIC',origin)

    def test_changed_labels_hash_and_nonexact_anchors_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'changed.json'
            cases=copy.deepcopy(self.cases)
            cases[0]['evidence_anchors']=['not a real quote']
            path.write_text(json.dumps(dict(cases=cases)))
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaises(ValueError): validate_dataset(path,self.digest)
            with self.assertRaises(ValueError): validate_dataset(path,digest)

    def test_practitioner_format_never_authenticates_an_identity(self):
        case=copy.deepcopy(self.cases[0])
        quote='Customer supervises each worker.'
        case.update(expected_facts=dict(personnel_supplied='unknown',worker_supervisor='customer'),
                    evidence_annotations=[dict(fact='worker_supervisor',value='customer',quote=quote,start=case['contract_excerpt'].index(quote),end=len(case['contract_excerpt']))],
                    annotation_rationale='Synthetic schema test only; no real practitioner label')
        data=dict(schema='tds-practitioner-cases-v1',cases=[case],annotation_process=dict(
            reviewer_reference='synthetic-reference',qualification_assertion='synthetic schema test',labelled_at='2026-11-03',
            source_permission='synthetic',conflict_resolution='example rationale',model_outputs_hidden_during_labelling=True))
        validate_practitioner(data)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'schema-example.json';path.write_text(json.dumps(data))
            _,_,origin=validate_dataset(path,hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertIn('NOT_INDEPENDENTLY_AUTHENTICATED',origin)
        data['cases'][0]['evidence_annotations'][0]['start']=0
        with self.assertRaises(ValueError): validate_practitioner(data)
        data['annotation_process']['model_outputs_hidden_during_labelling']=False
        with self.assertRaises(ValueError): validate_practitioner(data)
