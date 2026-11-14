# Low-Complexity RAG Test Documents: Answer Key

All page numbers are 1-based PDF page indexes (matching `page_number` in retrieved chunks and citations). Each entry is verified against the actual extracted text of the PDFs in `backend/data/sample_pdfs/Low/`.

Target Files:
- `hr_policy.pdf` (Company HR Policy Handbook, 3 pages)
- `product_specs_a.pdf` (Product Specification Model A-100, 2 pages)
- `product_specs_b.pdf` (Product Specification Model B-200 Revision 2, 2 pages)

---

## 1. Answerable Questions

| # | Question | Correct Grounded Answer | File | Page |
|---|---|---|---|:---:|
| 1 | How many days of paid annual leave are full-time employees entitled to? | All full-time employees are entitled to 25 working days of paid annual leave per calendar year. | `hr_policy.pdf` | 1 |
| 2 | What is the annual leave entitlement for full-time employees? | 25 working days per calendar year. | `hr_policy.pdf` | 1 |
| 3 | How many days of paid sick leave do employees receive annually? | Employees receive 10 days of paid sick leave annually. | `hr_policy.pdf` | 2 |
| 4 | When are medical certificates required according to the HR policy? | Medical certificates are required for absences extending beyond standard sick leave. | `hr_policy.pdf` | 2 |
| 5 | How many days per week are employees allowed to work remotely? | Employees may work remotely up to two days per week. | `hr_policy.pdf` | 3 |
| 6 | Whose approval is required to work remotely? | Direct manager approval is required. | `hr_policy.pdf` | 3 |
| 7 | What is the maximum battery flight time of the Model A-100 in eco standby mode? | 48 hours in eco standby mode. | `product_specs_a.pdf` | 1 |
| 8 | What type of aircraft is the Model A-100? | A high-performance quadcopter. | `product_specs_a.pdf` | 1 |
| 9 | What is the maximum operating altitude of the Model A-100 quadcopter? | 5,000 meters above sea level. | `product_specs_a.pdf` | 2 |
| 10 | What is the weather resistance rating of the Model A-100? | Rated IP67. | `product_specs_a.pdf` | 2 |
| 11 | What is the revision number of the Model B-200 product specification document? | Revision 2. | `product_specs_b.pdf` | 1 |
| 12 | What is the battery flight time of the Model B-200 quadcopter in eco standby mode? | 24 hours under eco standby mode. | `product_specs_b.pdf` | 1 |
| 13 | How many hours of active flight does the Model B-200 battery provide? | 8 hours of active flight. | `product_specs_b.pdf` | 1 |
| 14 | What is the maximum operating altitude of the Model B-200? | 4,200 meters above sea level. | `product_specs_b.pdf` | 2 |
| 15 | What is the weather resistance rating of the Model B-200? | Rated IP54. | `product_specs_b.pdf` | 2 |

---

## 2. Similar-Wording & Disambiguation Pairs

These question pairs test whether semantic retrieval can distinguish between the two quadcopter models (`Model A-100` vs `Model B-200`) without confusing their specifications.

| # | Question | Target Entity | Correct Answer | File | Page |
|---|---|---|---|---|:---:|
| 16a | What is the maximum operating altitude of Model A-100? | Model A-100 | 5,000 meters above sea level. | `product_specs_a.pdf` | 2 |
| 16b | What is the maximum operating altitude of Model B-200? | Model B-200 | 4,200 meters above sea level. | `product_specs_b.pdf` | 2 |
| 17a | What is the weather resistance rating of Model A-100? | Model A-100 | Rated IP67. | `product_specs_a.pdf` | 2 |
| 17b | What is the weather resistance rating of Model B-200? | Model B-200 | Rated IP54. | `product_specs_b.pdf` | 2 |
| 18a | What is the battery standby flight time of Model A-100? | Model A-100 | 48 hours in eco standby. | `product_specs_a.pdf` | 1 |
| 18b | What is the battery standby flight time of Model B-200? | Model B-200 | 24 hours under eco standby mode. | `product_specs_b.pdf` | 1 |

---

## 3. Unanswerable & Out-of-Scope Questions (Refusal Testing)

These questions test the system's grounding refusal logic (`is_refusal_answer`, returning `found=False` and zero hallucinated citations).

| # | Question | Expected System Behavior | Grounding Rationale |
|---|---|---|---|
| 19 | How many weeks of maternity leave do employees receive? | Refusal: "The provided documents do not contain sufficient information..." | Not mentioned in `hr_policy.pdf`. |
| 20 | What is the retail price of the Model A-100 quadcopter? | Refusal | Pricing is not stated in `product_specs_a.pdf`. |
| 21 | What camera resolution or sensor does the Model B-200 carry? | Refusal | Camera payload is omitted in `product_specs_b.pdf`. |
| 22 | What is the reimbursement rate for business travel meals? | Refusal | Travel expense policy is not included in `hr_policy.pdf`. |
| 23 | In which city is the company headquarters located? | Refusal | Office location is not mentioned in any Low dataset file. |
| 24 | What is the recharging time for the Model A-100 battery? | Refusal | Recharge duration is not specified in the text. |

---

## 4. Comparison & Conflict Questions

These questions test whether the assistant can perform cross-document comparisons across `product_specs_a.pdf` and `product_specs_b.pdf`.

| # | Question | Correct Multi-Document Answer | Sources |
|---|---|---|---|
| 25 | Which quadcopter has a higher maximum operating altitude, Model A-100 or Model B-200? | Model A-100 has a higher operating altitude (5,000 meters above sea level) compared to Model B-200 (4,200 meters above sea level). | `product_specs_a.pdf` (p. 2), `product_specs_b.pdf` (p. 2) |
| 26 | How do the weather resistance ratings compare between Model A-100 and Model B-200? | Model A-100 is rated IP67, offering higher ingress protection than Model B-200, which is rated IP54. | `product_specs_a.pdf` (p. 2), `product_specs_b.pdf` (p. 2) |
| 27 | Which model provides longer eco standby flight time? | Model A-100 provides longer eco standby flight time (48 hours) compared to Model B-200 (24 hours). | `product_specs_a.pdf` (p. 1), `product_specs_b.pdf` (p. 1) |

---

## 5. Scope-Constrained Questions (Filter Testing)

These questions test the frontend `file_names` scoping filter (`AnswerRequest.file_names`):

| # | Question | Document Scope | Expected Behavior |
|---|---|---|---|
| 28 | What is the weather resistance rating? | Scoped to `product_specs_a.pdf` | Returns IP67 citing `product_specs_a.pdf` (p. 2). |
| 29 | What is the weather resistance rating? | Scoped to `product_specs_b.pdf` | Returns IP54 citing `product_specs_b.pdf` (p. 2). |
| 30 | What is the remote work policy? | Scoped to `product_specs_a.pdf` | Returns refusal (`found=False`) because `hr_policy.pdf` was not in scope. |

