# Privacy-Preserving Record Linkage (PPRL)

Privacy-preserving record linkage is a method for finding records that likely
refer to the same person, student, worker, or entity without sharing raw
identifiers across organizations.

In this project, PPRL is used for a synthetic USA SLDS education-to-workforce
scenario. Two clients hold similar records with names, dates of birth, ZIP
codes, education fields, credentials, employment information, wages, and
occupation transitions. The app links likely matching records while keeping the
matching process focused on encoded tokens instead of raw identity fields.

## Why PPRL Matters

Organizations often need to combine data to answer cross-system questions:

- Did learners complete a credential and later enter related employment?
- Which programs connect to higher wage outcomes?
- How do workers move between occupations?
- Which industries hire graduates from specific programs?

Those questions are useful, but the underlying data can include sensitive
personally identifying information. PPRL reduces exposure by transforming
linkage fields before comparison.

## Demo Workflow

1. **Load two client datasets**

   The demo uses `workforce_client_a.csv` and `workforce_client_b.csv`.
   Each file contains synthetic SLDS-style records.

2. **Select linkage fields**

   By default, the app uses:

   - `first_name`
   - `last_name`
   - `date_of_birth`
   - `gender`
   - `zip`

   Optional fields such as phone, email, address, institution, program, and
   occupation codes can also be included.

3. **Normalize values**

   Values are standardized before encoding. For example, names are lowercased,
   dates are converted to `YYYYMMDD`, ZIP codes keep five digits, and phone
   numbers keep the last ten digits.

4. **Create q-grams**

   Each normalized value is split into overlapping character chunks. This helps
   tolerate small differences like spelling variation, abbreviations, and typos.

5. **Hash q-grams with a salt**

   The app hashes each q-gram using SHA-256 and a local salt. Matching compares
   hashed tokens rather than raw q-grams.

6. **Block candidate pairs**

   Records are only compared when they share a block key:

   ```text
   birth year | ZIP3 | gender
   ```

   Blocking keeps comparisons smaller and reduces unnecessary exposure.

7. **Score candidate matches**

   The app uses Dice similarity:

   ```text
   2 * shared_hashes / (left_hashes + right_hashes)
   ```

   Candidate pairs above the selected threshold appear in the linked output.

## What This Demo Shows

- Multi-state synthetic USA SLDS-style records.
- Fuzzy matching over encoded linkage fields.
- A tunable q-gram length, match threshold, and hashing salt.
- Candidate match scores and shared token counts for review.
- Linked output that can support education-to-workforce analysis.

## Important Limitations

This app is a proof of concept, not a production privacy system.

- Hashing alone does not guarantee strong privacy against all attacks.
- Real deployments should use a formal privacy and security design.
- Salts and secrets need managed rotation, storage, and access controls.
- Linkage quality should be evaluated against labeled test data.
- Governance, consent, data minimization, and auditing are essential.

## Production Considerations

A production PPRL workflow should define:

- Which fields are legally and ethically allowed for linkage.
- How salts or cryptographic keys are generated and shared.
- How false positives and false negatives are reviewed.
- What raw data is never exposed to the linkage service.
- How linked IDs are separated from downstream analytics datasets.
- How access, logs, exports, and retention are governed.
