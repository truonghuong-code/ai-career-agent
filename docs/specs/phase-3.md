# Phase 3 — Grounded LLM / Question Answering

## 1. Purpose

Phase 3 introduces grounded question answering on top of the retrieval capabilities completed in Phase 2.

The system shall allow a user to ask a question about their ingested documents and receive an answer generated from relevant retrieved document content.

Phase 3 extends the existing flow:

```text
User Question
      ↓
Retrieval
      ↓
Relevant Document Chunks
```

into:

```text
User Question
      ↓
Retrieval
      ↓
Relevant Document Chunks
      ↓
Grounded Answer Generation
      ↓
Answer + Sources
```

The primary goal is to establish a reliable RAG question-answering foundation before introducing career-domain logic or agent orchestration.

---

## 2. Scope

Phase 3 covers:

- accepting a user question
- retrieving relevant document chunks using the existing retrieval capability
- preparing retrieved content for answer generation
- generating an answer using an LLM
- grounding the answer in retrieved document content
- returning source information associated with the answer
- handling cases where relevant context is unavailable
- isolating LLM-provider-specific behavior from core application logic
- preserving document ownership boundaries throughout the Q&A flow
- providing testable behavior without requiring external LLM calls in all tests

Phase 3 does not introduce autonomous agents or career-specific reasoning.

---

# 3. Functional Requirements

## P3-REQ-01 — Question Input

The system shall accept a user question as input to the grounded question-answering flow.

A question shall:

- be textual
- contain non-empty meaningful content
- belong to the requesting user context

Invalid or empty questions shall not proceed to answer generation.

---

## P3-REQ-02 — Relevant Context Retrieval

The system shall use the existing retrieval capability to retrieve document chunks relevant to the user's question.

Retrieval shall continue to respect:

- document ownership
- document processing status
- retrieval result limits
- supported retrieval filters

Phase 3 shall not bypass the retrieval and ownership rules established in Phase 2.

---

## P3-REQ-03 — Grounded Context Preparation

The system shall transform retrieved document chunks into context suitable for answer generation.

Context preparation shall:

- use retrieved content
- preserve retrieval ordering unless a later requirement explicitly introduces re-ranking
- maintain traceability between prepared context and original document chunks
- support a configurable limit on the amount of retrieved content included

Context preparation shall not independently perform document retrieval.

---

## P3-REQ-04 — Prompt Construction

The system shall construct an LLM request using:

- instructions for grounded answering
- the user's question
- the prepared document context

The prompt shall clearly distinguish user questions from retrieved document context.

The prompt shall instruct the model to base its answer on the provided context rather than unsupported information.

---

## P3-REQ-05 — LLM Provider Abstraction

Answer generation shall not depend directly on one specific external LLM provider throughout the application.

The system shall provide an abstraction through which answer generation can be requested.

The abstraction shall allow:

- external LLM implementations
- test or fake implementations
- future replacement of the selected LLM provider without redesigning the entire Q&A flow

Provider-specific credentials and configuration shall remain outside core business logic.

---

## P3-REQ-06 — Grounded Answer Generation

The system shall generate an answer using the user's question and retrieved document context.

The generated answer shall be instructed to rely on the supplied context.

The system shall not intentionally present unsupported information as if it came from the user's documents.

Where the available context does not support an answer, the system shall indicate insufficient information rather than intentionally fabricate document-derived facts.

---

## P3-REQ-07 — Source Traceability

The Q&A result shall preserve information allowing returned source references to be traced back to the retrieved content.

For each returned source, sufficient information shall be available to identify the relevant source chunk and its document.

At minimum, source traceability shall support:

- document identification
- chunk identification
- chunk position/index where applicable
- source numbering or equivalent stable reference within the generated context

The API shall not require consumers to understand internal ORM objects.

---

## P3-REQ-08 — No Relevant Context

The system shall handle cases where retrieval returns no relevant document context.

An empty retrieval result shall not cause an unhandled application failure.

The system shall return behavior that clearly indicates that sufficient document context is unavailable.

The system shall not fabricate document-grounded answers when no document context is available.

---

## P3-REQ-09 — Structured Q&A Response

The question-answering operation shall return a structured response rather than an unstructured raw LLM response.

The response shall contain, at minimum:

- the generated answer
- associated source information

Internal persistence objects shall not be exposed directly through the public API.

---

# 4. Grounding Requirements

## P3-GR-01 — Context-Based Answering

The LLM shall receive retrieved document context as part of the answer-generation request.

The generated answer shall be instructed to use this context as the evidence base for document-related claims.

---

## P3-GR-02 — Insufficient Evidence

If retrieved context does not contain sufficient information to answer the question, the system shall support an explicit insufficient-information response.

The system shall prefer acknowledging missing evidence over inventing unsupported document content.

---

## P3-GR-03 — Source Association

Source references returned with an answer shall originate from the retrieval results used to construct the answer-generation context.

The system shall not create source references for documents or chunks that were not part of that context.

---

## P3-GR-04 — Retrieval Order Preservation

Unless an explicit re-ranking capability is introduced, Phase 3 shall preserve the ordering provided by the retrieval layer when preparing context.

Phase 3 shall not silently introduce an independent ranking strategy.

---

# 5. Ownership and Security Requirements

## P3-SEC-01 — Ownership Isolation

A user shall only be able to use their own accessible documents as grounding context.

The Q&A flow shall preserve the ownership isolation established by the retrieval layer.

Content belonging exclusively to another user shall not appear in:

- retrieved context
- generated answer sources
- Q&A API responses

---

## P3-SEC-02 — Internal User Header

The existing internal user identification mechanism may continue to be used during this phase.

`X-Internal-User-ID` shall not be treated as production authentication.

Production authentication and authorization remain outside Phase 3 scope.

---

## P3-SEC-03 — Provider Credentials

LLM provider credentials shall not be:

- hard-coded in source code
- committed to version control
- returned through API responses
- included in application logs

---

# 6. Error and Edge-Case Requirements

## P3-ERR-01 — Empty Question

An empty or invalid question shall be rejected before LLM answer generation.

---

## P3-ERR-02 — Empty Retrieval Result

No retrieved chunks shall be treated as a valid no-context condition.

It shall not result in an unhandled exception.

---

## P3-ERR-03 — LLM Provider Failure

Failures from an LLM provider shall be handled explicitly.

Provider errors shall not be silently converted into successful grounded answers.

The system shall preserve enough error information for application-level handling without exposing sensitive provider information to API clients.

---

## P3-ERR-04 — Retrieval Failure

A retrieval infrastructure failure shall be distinguishable from a successful retrieval that returns no relevant results.

For example:

```text
Retrieval succeeded
results = []
```

is not equivalent to:

```text
Retrieval failed
database/provider error
```

---

# 7. Non-Functional Requirements

## P3-NFR-01 — Deterministic Pre-LLM Processing

Operations performed before the LLM call, including context preparation and prompt construction, should be deterministic for identical inputs and configuration.

---

## P3-NFR-02 — Testability

Core Phase 3 behavior shall be testable without requiring live external LLM calls.

Tests shall be able to substitute controlled LLM behavior where appropriate.

---

## P3-NFR-03 — Separation of Concerns

Phase 3 shall preserve the project's existing architectural separation.

Responsibilities for:

- retrieval
- context preparation
- prompt construction
- LLM interaction
- API representation

shall remain separable and independently testable where practical.

---

## P3-NFR-04 — Provider Replaceability

Changing the configured LLM provider shall not require rewriting retrieval or context-preparation logic.

---

## P3-NFR-05 — Regression Safety

Phase 3 changes shall not break existing Phase 1 and Phase 2 document ingestion, lifecycle, chunking, embedding, or retrieval behavior.

Existing tests shall continue to pass.

---

# 8. Out of Scope

The following capabilities are explicitly outside Phase 3:

- autonomous agents
- multi-step agent planning
- tool calling
- CV-specific structured analysis
- JD-specific structured analysis
- skill-gap calculation
- personalized learning-plan generation
- interview simulation
- Japanese IT coaching
- conversation memory
- long-term user memory
- production authentication
- advanced authorization
- hybrid retrieval
- re-ranking
- query rewriting
- advanced token-budget optimization
- streaming responses
- production observability
- autonomous web search

These capabilities may be introduced in later phases.

---

# 9. Acceptance Criteria

Phase 3 is considered functionally complete when:

1. A valid user question can enter the Q&A flow.
2. Relevant chunks can be obtained through the existing retrieval capability.
3. Retrieved chunks can be transformed into grounded LLM context.
4. The user's question and retrieved context can be used to construct an LLM request.
5. The system can generate an answer through an LLM-provider abstraction.
6. The answer is returned