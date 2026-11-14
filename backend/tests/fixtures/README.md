# Test Fixtures & QA Benchmark Answer Keys

This directory contains ground-truth question-answer benchmarks used to evaluate the GroundTruth Assistant's retrieval, citation, and answering accuracy.

## Benchmark Keys

1. **`TEST_ANSWER_KEY_LOW.md`**
   - **Target Dataset:** `backend/data/sample_pdfs/Low/` (`hr_policy.pdf`, `product_specs_a.pdf`, `product_specs_b.pdf`)
   - **Coverage:** 30 benchmark cases covering answerable questions, model disambiguation, unanswerable refusals, cross-model comparisons, and document scoping filters.

2. **`TEST_ANSWER_KEY_MEDIUM.md`**
   - **Target Dataset:** `backend/data/sample_pdfs/Medium/` (`01_NovaTech_Employee_Handbook_2024.pdf`, `02_PulseHub_X2_Product_Specifications_and_User_Guide.pdf`, `03_NovaTech_Policy_Updates_and_IT_Security_Standard_2025.pdf`)
   - **Coverage:** 158 verified test cases covering answerable multi-page questions, regional multi-office conditions, temporal policy conflict overrides, and out-of-scope refusals.
