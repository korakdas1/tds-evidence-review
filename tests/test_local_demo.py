"""Disposable full workflow verifies legal separation and checkpoint state without network."""
import unittest
from unittest.mock import patch
from local_demo import walkthrough, render


class CompleteDemoTests(unittest.TestCase):
    def test_complete_workflow_is_offline_separates_suggestions_and_never_approves(self):
        with patch('src.extraction.OpenRouterClient.complete',side_effect=AssertionError('No live inference')) as provider, \
             patch('urllib.request.build_opener',side_effect=AssertionError('No internet')) as network:
            result=walkthrough()
            self.assertEqual(result['model_network_calls'],0)
            self.assertEqual(result['simulated_client_invocations'],1)
            self.assertEqual(result['reviewer']['statutory_proposal'],'WITHHELD')
            self.assertTrue(result['reviewer']['findings_unchanged'])
            self.assertIn('ai_suggestion',result['suggestion']['states'])
            self.assertEqual(result['scanned']['evidence_count'],0)
            self.assertEqual(result['checkpoint']['status'],'MATCHES_EXTERNAL_CHECKPOINT')
            self.assertEqual(result['checkpoint']['later_events'],1)
            self.assertEqual(result['export_integrity'],'VERIFIED')
            provider.assert_not_called(); network.assert_not_called()
            text=render(result)
            self.assertIn('REPLAYED HISTORICAL LLM EVIDENCE',text)
            self.assertIn('NOT a model',text)
            self.assertIn('No API calls',text)
