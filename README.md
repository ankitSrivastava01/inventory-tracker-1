# PPRL SLDS USA Demo

This Streamlit app demonstrates privacy-preserving record linkage (PPRL) for
synthetic State Longitudinal Data System (SLDS)-style education-to-workforce
records.

The demo links two client datasets without directly comparing raw personal
identifiers. It normalizes selected fields, converts values into q-grams, hashes
those q-grams with a local salt, blocks records by birth year, ZIP3, and gender,
then scores candidate links with Dice similarity.

## Files

- `streamlit_app.py` - main Streamlit app.
- `pprl_streamlit_app.py` - synced copy of the app.
- `workforce_client_a.csv` - synthetic Client A SLDS/workforce records.
- `workforce_client_b.csv` - synthetic Client B SLDS/workforce records.
- `PPRL.md` - short document explaining PPRL concepts and this demo workflow.
- `pprl_sample/PPRL .pdf` - supplied reference document.

## Run Locally

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Learn More

See [PPRL.md](PPRL.md) for the privacy-preserving linkage workflow, data fields,
benefits, and limitations.
