"""Phase 2A regressions use new wording; no expected labels reach extraction."""
import unittest

from src.evidence import lexical_extract, validate_evidence
from src.rules import factual_status
from src.schema import CUSTOMER, VENDOR, INSUFFICIENT, CONFLICT
from tests.test_core import process, transaction


class ReliabilityTests(unittest.TestCase):
    def test_passive_workers_and_separated_availability(self):
        result = process(transaction("Provider makes two technicians available to Purchaser. Each technician is directly supervised by the Purchaser coordinator."))
        self.assertEqual(result["factual_evidence_status"], CUSTOMER)
        self.assertTrue(all(q["verbatim"] for q in result["supporting_quotes"]))

    def test_passive_compound_supervision(self):
        result = process(transaction("Agency supplies cleaners. The cleaners are instructed and supervised by Client."))
        self.assertEqual(result["factual_evidence_status"], CUSTOMER)

    def test_passive_vendor_supervision(self):
        result = process(transaction("Agency provides technicians. The technicians are supervised by Supplier."))
        self.assertEqual(result["factual_evidence_status"], VENDOR)

    def test_passive_negation_is_not_positive(self):
        result = process(transaction("Agency supplies technicians. Each technician is not supervised by Customer."))
        self.assertEqual(result["factual_evidence_status"], INSUFFICIENT)

    def test_passive_service_output_is_not_worker_control(self):
        result = process(transaction("Agency supplies technicians. The output prepared by technicians is supervised by Customer."))
        self.assertEqual(result["factual_evidence_status"], INSUFFICIENT)

    def test_passive_subject_must_be_workers_not_an_attribute(self):
        for clause in ("Safety of workers is supervised by Customer.",
                       "Workers' attendance is supervised by Customer."):
            with self.subTest(clause=clause):
                result = process(transaction("Agency supplies workers. " + clause))
                self.assertEqual(result["factual_evidence_status"], INSUFFICIENT)

    def test_worker_records_available_does_not_prove_supply(self):
        result = process(transaction("Vendor makes worker records available to Customer. Customer supervises workers."))
        self.assertEqual(result["validated_facts"]["personnel_supplied"], "unknown")
        self.assertEqual(result["factual_evidence_status"], INSUFFICIENT)

    def test_company_bound_to_explicit_recipient(self):
        result = process(transaction("Agency supplies staff to the Company. Company directs each worker."))
        self.assertEqual(result["factual_evidence_status"], CUSTOMER)

    def test_company_without_recipient_binding_abstains(self):
        result = process(transaction("Agency supplies staff. Company directs each worker."))
        self.assertEqual(result["factual_evidence_status"], INSUFFICIENT)

    def test_supplier_company_is_not_recipient(self):
        result = process(transaction("Supplier company provides staff. Supplier company supervises workers."))
        self.assertEqual(result["factual_evidence_status"], VENDOR)

    def test_multiple_actor_grammar_does_not_guess(self):
        result = process(transaction("Agency supplies staff to Company. Company requires Supplier to supervise workers."))
        self.assertEqual(result["factual_evidence_status"], INSUFFICIENT)

    def test_agent_worker_noun(self):
        result = process(transaction("Supplier provides agents. Supplier allocates tasks to each agent. Customer inspects completed output."))
        self.assertEqual(result["factual_evidence_status"], VENDOR)

    def test_explicitly_obsolete_clause_does_not_create_conflict(self):
        result = process(transaction("Vendor supplies workers. Superseded clause: Customer supervises workers. Current clause: Vendor supervises workers."))
        self.assertEqual(result["factual_evidence_status"], VENDOR)

    def test_clipped_quote_cannot_revive_deleted_clause(self):
        contract = "Vendor supplies workers. Deleted provision: Customer supervises workers."
        extraction = lexical_extract("Vendor supplies workers. Customer supervises workers.")
        result = validate_evidence(contract, extraction)
        self.assertEqual(factual_status(result["facts"]), INSUFFICIENT)
        self.assertTrue(result["validation_failures"])

    def test_unknown_amendment_precedence_remains_conflicting(self):
        result = process(transaction("Vendor supplies workers. Main agreement: Customer supervises workers. Schedule with unknown effective date: Vendor supervises workers."))
        self.assertEqual(result["factual_evidence_status"], CONFLICT)

    def test_future_condition_does_not_establish_current_control(self):
        result = process(transaction("Provider supplies workers. Only after a future agreement is signed may Customer supervise workers."))
        self.assertEqual(result["factual_evidence_status"], INSUFFICIENT)

    def test_separate_unrelated_negation_keeps_control_evidence(self):
        result = process(transaction("Vendor supplies workers. Customer does not administer wages. Customer directly supervises each worker."))
        self.assertEqual(result["factual_evidence_status"], CUSTOMER)

    def test_ambiguous_same_sentence_negation_still_abstains(self):
        result = process(transaction("Vendor supplies workers. Customer does not handle wages but supervises workers."))
        self.assertEqual(result["factual_evidence_status"], INSUFFICIENT)


if __name__ == "__main__":
    unittest.main()
