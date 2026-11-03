// Plain-English wording for backend codes. Codes stay visible as secondary text for audit.
export const FINDINGS = {
  EVIDENCE_SUPPORTS_CUSTOMER_DIRECTED_MANPOWER: {
    title: "Text indicates workers supplied and directed by the customer",
    body: "The rule checks found contract sentences saying the vendor supplies workers and the customer supervises them. This describes the contract wording only, not actual working practice or the tax treatment.",
  },
  EVIDENCE_INDICATES_VENDOR_DIRECTED_SERVICE: {
    title: "Text indicates the vendor directs its own workers",
    body: "The rule checks found wording that the vendor controls the workers. Vendor control alone does not establish professional or technical services.",
  },
  INSUFFICIENT_TO_ESTABLISH_CONTROL: {
    title: "Not enough reliable evidence about who controls the workers",
    body: "The automated checks could not establish who supervises the workers from reliable contract text. Review the missing information and any suggestions below.",
  },
  CONFLICTING_EVIDENCE: {
    title: "The contract contradicts itself about who controls the workers",
    body: "Different clauses point to different supervisors. A reviewer needs to establish which clause applies, for example from effective dates or amendments.",
  },
  OUT_OF_SCOPE: {
    title: "Outside this prototype's scope",
    body: "The vendor is recorded as non-resident. This prototype only covers resident-payment scenarios.",
  },
};

export const REPORT_STATUS = {
  TEXT_REVIEW_COMPLETE: { label: "Text read, no document problems detected", ink: "validated" },
  NEEDS_DOCUMENT_REVIEW: { label: "Document needs a visual check", ink: "missing" },
};

export const DOC_STATUS = {
  EXTRACTED: { label: "Text extracted", ink: "validated" },
  NEEDS_DOCUMENT_REVIEW: { label: "Needs a visual check", ink: "missing" },
  REJECTED: { label: "Could not be read", ink: "contradiction" },
};

export const ISSUES = {
  FILE_SIZE_LIMIT: "The file is larger than the 5 MiB limit.",
  UNSUPPORTED_FILE: "This is not a PDF file.",
  ENCRYPTED_PDF_NOT_SUPPORTED: "The PDF is password-protected. Remove the protection and upload it again.",
  PAGE_COUNT_LIMIT: "The PDF has more than 20 pages.",
  NO_PAGES: "The PDF has no pages.",
  MALFORMED_OR_UNSUPPORTED_PDF: "The PDF is damaged or uses an unsupported structure.",
  FILE_UNAVAILABLE: "The stored file could not be opened.",
  PDF_DEPENDENCY_MISSING_INSTALL_REQUIREMENTS_PDF: "The PDF reader is not installed. Run: pip install -r requirements-pdf.txt",
  INVALID_LIMIT: "An internal size limit is misconfigured.",
  ACTIVE_CONTENT_NOT_EXECUTED: "The PDF contains scripts or automatic actions. They were not run.",
  CONTENT_STREAM_LIMIT: "A page is too complex to read safely within limits.",
  TEXT_SIZE_LIMIT: "A page has more text than the safe reading limit. Nothing was cut silently.",
  NO_SELECTABLE_TEXT_OCR_OR_MANUAL_REVIEW: "This page has no selectable text (for example a scan). No OCR was attempted. Read the page yourself.",
  UNREADABLE_TEXT: "Some characters on this page could not be read reliably.",
  LAYOUT_EXTRACTION_UNAVAILABLE: "The second, layout-based reading could not be produced for comparison.",
  EXTRACTION_ORDER_DISAGREEMENT: "Two ways of reading this page disagree about word order. Check the original layout, for example columns.",
  IMAGE_CONTENT_REQUIRES_VISUAL_REVIEW: "This page contains images that may hold text the reader cannot see.",
  ROTATED_PAGE_REQUIRES_VISUAL_REVIEW: "This page is rotated. Check that the text reads in the right order.",
  PAGE_EXTRACTION_FAILED: "Text could not be extracted from this page.",
  CONTRACT_TEXT_INCOMPLETE_OR_UNRELIABLE: "The contract text is incomplete or unreliable, so no supported facts are relied on.",
  INVOICE_TEXT_INCOMPLETE_OR_UNRELIABLE: "The invoice text is incomplete or unreliable.",
  SOURCE_MAPPING_UNRESOLVED: "A quotation could not be traced back to an exact place in the page text.",
  CROSS_PAGE_EVIDENCE_REQUIRES_VISUAL_REVIEW: "A quotation runs across two pages. Check it in the original document.",
};

// Validation messages produced by the existing pipeline, in plain words.
const FAILURES = {
  "contract_excerpt must be a nonempty string": "No contract text could be read, so nothing was analysed.",
  "invoice_description must be a nonempty string": "The invoice description is missing.",
  "payer_type must be a nonempty string": "The payer type is missing.",
  "payee_residency must be a nonempty string": "The vendor residency is missing.",
  "payee_legal_form must be a nonempty string": "The vendor legal form is missing.",
  "id must be a nonempty string": "The case reference is missing.",
};

export function explainFailure(text) {
  return ISSUES[text] || FAILURES[text] || text;
}

export const REASONS = {
  QUOTE_NOT_FOUND: "This quotation does not appear word for word in the contract.",
  EMBEDDED_INSTRUCTION: "The contract contains text that looks like an instruction to an AI system.",
  ASSERTION_QUOTE_MISMATCH: "The claimed fact does not match what was asserted for this quotation.",
  NEGATED_CONTEXT: "The surrounding sentence contains a negation (for example “not” or “no”).",
  INOPERATIVE_CONTEXT: "The surrounding text suggests this clause is a draft, deleted or superseded.",
  CONDITIONAL_CONTEXT: "The surrounding sentence is conditional (for example “if” or “subject to”).",
  POSSIBLE_SERVICE_OUTCOME_NOT_WORKER_CONTROL: "This may describe control of service results, not of individual workers.",
  EXACT_SOURCE_BUT_INTERPRETATION_NOT_VERIFIED: "The words are exactly in the contract, but the rule checks do not recognise this wording, so the reading is unverified.",
};

export const FACTS = {
  personnel_supplied: { question: "Are workers supplied to the customer?", values: { yes: "Yes", no: "No", unknown: "Not established" } },
  worker_supervisor: { question: "Who supervises or directs the workers?", values: { customer: "The customer", vendor: "The vendor", unknown: "Not established", conflicting: "Conflicting" } },
  contradiction: { question: "Listed as contradictory evidence", values: { conflicting: "Conflicts with another clause" } },
};

// A plain statement of what an assertion claims, used in reviewer prompts.
const STATEMENTS = {
  personnel_supplied: { yes: "workers are supplied to the customer", no: "workers are not supplied to the customer" },
  worker_supervisor: {
    customer: "the customer supervises or directs the workers",
    vendor: "the vendor supervises or directs the workers",
    conflicting: "the clauses conflict about who supervises the workers",
  },
};

export function statement(fact, value) {
  return STATEMENTS[fact]?.[value] ?? `${FACTS[fact]?.question || fact} ${factAnswer(fact, value)}`;
}

export function factAnswer(fact, value) {
  return FACTS[fact]?.values?.[value] ?? value;
}

export const TEXT_STATUS = {
  SUPPORTED_FACTUAL_EVIDENCE: { label: "Validated by rule checks", ink: "validated" },
  AI_SUGGESTED_REQUIRING_REVIEW: { label: "Suggestion, not verified", ink: "ai_suggestion" },
  REJECTED_BY_SAFETY_GUARD: { label: "Rejected by a safety check", ink: "rejected" },
  UNVALIDATED_EXTRACTION: { label: "Not validated", ink: "unvalidated" },
  INSUFFICIENT_EVIDENCE: { label: "Insufficient", ink: "unvalidated" },
  CONTRADICTORY_EVIDENCE: { label: "Contradictory", ink: "contradiction" },
};

export const CATEGORIES = {
  contradiction: {
    title: "Contradictions",
    sub: "Clauses that point in different directions. Both are exact quotations; the conflict must be resolved by a person.",
    empty: "No contradictory clauses were recognised by the rule checks. Unfamiliar wording can still conflict, so read the full text.",
  },
  validated: {
    title: "Validated by rule checks",
    sub: "Exact quotations that passed the existing conservative rule checks. Validated means the wording matched known patterns. It does not prove what happens in practice.",
    empty: "No quotation passed the rule checks.",
  },
  ai_suggestion: {
    title: "AI suggestions (review only)",
    sub: "Exact quotations an extraction proposed, but the rule checks could not confirm. They are leads for you to judge and never feed the automated finding.",
    empty: "No suggestions in this run. The offline rule checks do not produce AI suggestions. They appear only when an extraction is supplied.",
  },
  rejected: {
    title: "Rejected by safety checks",
    sub: "Kept visible for audit. A safety check blocked them, which is not proof that they are wrong.",
  },
  unvalidated: {
    title: "Not validated",
    sub: "Quotations that were extracted but not validated.",
  },
};

export const DECISIONS = {
  QUOTE_CHECK: {
    MATCHES_DOCUMENT: "Matches the PDF",
    DOES_NOT_MATCH: "Doesn't match the PDF",
    UNCLEAR: "Unclear",
  },
  INTERPRETATION_REVIEW: {
    AGREE: "Agree with this reading",
    DISAGREE: "Disagree",
    NEEDS_MORE_INFORMATION: "Need more information",
  },
  DOCUMENT_CHECK: {
    READING_ORDER_AND_COMPLETENESS_CONFIRMED: "Reading order and completeness checked",
    ISSUES_FOUND: "Problems found",
  },
  CASE_STATUS: {
    IN_REVIEW: "In review",
    ESCALATED_TO_QUALIFIED_TAX_REVIEW: "Escalated to a tax specialist",
    REVIEW_RECORD_COMPLETE: "Review record complete",
    REOPENED: "Reopened",
  },
};

export const CASE_STATUS = {
  AWAITING_REVIEW: { label: "Awaiting review", cls: "status-awaiting" },
  IN_REVIEW: { label: "In review", cls: "status-in-review" },
  ESCALATED_TO_QUALIFIED_TAX_REVIEW: { label: "Escalated to tax specialist", cls: "status-escalated" },
  REVIEW_RECORD_COMPLETE: { label: "Review record complete", cls: "status-complete" },
};

export const EVENTS = {
  CASE_CREATED: "Case created",
  ANALYSIS_RUN: "Analysis run",
  QUOTE_CHECK: "Quotation checked",
  INTERPRETATION_REVIEW: "Reading reviewed",
  DOCUMENT_CHECK: "Document checked",
  NOTE: "Note added",
  CASE_STATUS: "Status changed",
};

export const FIELDS = {
  id: "Case reference",
  invoice_description: "Invoice description",
  payer_type: "Payer type",
  payee_residency: "Vendor residency",
  payee_legal_form: "Vendor legal form",
  credit_date: "Credit date",
  payment_date: "Payment date",
};

export const METHODS = {
  live_hybrid: "External AI extraction with deterministic validation (see execution record)",
  baseline: "Offline rule checks",
  supplied_extraction: "Supplied extraction replay (simulated, no model)",
};
