from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parent
SAMPLE_A = ROOT / "pprl_sample" / "workforce_client_a.csv"
SAMPLE_B = ROOT / "pprl_sample" / "workforce_client_b.csv"

DEFAULT_FIELDS = ["first_name", "last_name", "date_of_birth", "gender", "zip"]
PREVIEW_COLUMNS = [
    "client_id",
    "first_name",
    "last_name",
    "date_of_birth",
    "city",
    "state",
    "zip",
    "state_slds_id",
    "learner_id",
    "k12_district",
    "institution",
    "credential_level",
    "program_area",
    "graduation_year",
    "employment_quarter",
    "employer_industry",
    "annual_wages",
    "year",
    "from_occupation",
    "to_occupation",
    "wage_change",
    "transition_rate",
]


@dataclass(frozen=True)
class EncodedRecord:
    record_id: str
    block_key: str
    token_count: int
    tokens: frozenset[str]


def normalize_text(value: object) -> str:
    if pd.isna(value):
        return ""
    value = str(value).lower().strip()
    value = re.sub(r"[^a-z0-9]+", "", value)
    return value


def normalize_dob(value: object) -> str:
    if pd.isna(value):
        return ""
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return normalize_text(value)
    return parsed.strftime("%Y%m%d")


def normalize_zip(value: object) -> str:
    digits = re.sub(r"\D+", "", "" if pd.isna(value) else str(value))
    return digits[:5]


def normalize_phone(value: object) -> str:
    digits = re.sub(r"\D+", "", "" if pd.isna(value) else str(value))
    return digits[-10:]


def normalize_field(field: str, value: object) -> str:
    if field == "date_of_birth":
        return normalize_dob(value)
    if field == "zip":
        return normalize_zip(value)
    if field == "phone":
        return normalize_phone(value)
    return normalize_text(value)


def qgrams(value: str, q: int) -> list[str]:
    if not value:
        return []
    padded = f"^{value}$"
    if len(padded) <= q:
        return [padded]
    return [padded[i : i + q] for i in range(len(padded) - q + 1)]


def hash_token(token: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}|{token}".encode("utf-8")).hexdigest()[:24]


def encode_row(row: pd.Series, fields: list[str], q: int, salt: str) -> frozenset[str]:
    tokens = []
    for field in fields:
        normalized = normalize_field(field, row.get(field, ""))
        tokens.extend(f"{field}:{gram}" for gram in qgrams(normalized, q))
    return frozenset(hash_token(token, salt) for token in tokens)


def build_block_key(row: pd.Series) -> str:
    dob = normalize_dob(row.get("date_of_birth", ""))
    birth_year = dob[:4] if len(dob) >= 4 else "unknown"
    zip3 = normalize_zip(row.get("zip", ""))[:3] or "unknown"
    gender = normalize_text(row.get("gender", ""))[:1] or "u"
    return f"{birth_year}|{zip3}|{gender}"


def encode_dataframe(
    df: pd.DataFrame,
    id_column: str,
    fields: list[str],
    q: int,
    salt: str,
) -> list[EncodedRecord]:
    encoded = []
    for _, row in df.iterrows():
        tokens = encode_row(row, fields, q, salt)
        encoded.append(
            EncodedRecord(
                record_id=str(row[id_column]),
                block_key=build_block_key(row),
                token_count=len(tokens),
                tokens=tokens,
            )
        )
    return encoded


def dice_similarity(left: frozenset[str], right: frozenset[str]) -> float:
    denominator = len(left) + len(right)
    if denominator == 0:
        return 0.0
    return 2 * len(left & right) / denominator


def link_records(
    left: pd.DataFrame,
    right: pd.DataFrame,
    id_column: str,
    fields: list[str],
    q: int,
    salt: str,
    threshold: float,
) -> pd.DataFrame:
    left_encoded = encode_dataframe(left, id_column, fields, q, salt)
    right_encoded = encode_dataframe(right, id_column, fields, q, salt)

    right_by_block: dict[str, list[EncodedRecord]] = {}
    for record in right_encoded:
        right_by_block.setdefault(record.block_key, []).append(record)

    rows = []
    for left_record in left_encoded:
        for right_record in right_by_block.get(left_record.block_key, []):
            score = dice_similarity(left_record.tokens, right_record.tokens)
            if score >= threshold:
                rows.append(
                    {
                        "left_id": left_record.record_id,
                        "right_id": right_record.record_id,
                        "block_key": left_record.block_key,
                        "similarity_score": score,
                        "left_token_count": left_record.token_count,
                        "right_token_count": right_record.token_count,
                        "shared_token_count": len(left_record.tokens & right_record.tokens),
                    }
                )
    if not rows:
        return pd.DataFrame(
            columns=[
                "left_id",
                "right_id",
                "block_key",
                "similarity_score",
                "left_token_count",
                "right_token_count",
                "shared_token_count",
            ]
        )
    return pd.DataFrame(rows).sort_values("similarity_score", ascending=False)


def enrich_matches(
    matches: pd.DataFrame,
    left: pd.DataFrame,
    right: pd.DataFrame,
    id_column: str,
) -> pd.DataFrame:
    if matches.empty:
        return matches
    preview_cols = [col for col in PREVIEW_COLUMNS if col in left.columns and col in right.columns]
    left_preview = left[preview_cols].rename(
        columns={col: f"left_{col}" for col in preview_cols}
    ).rename(columns={f"left_{id_column}": "left_id"})
    right_preview = right[preview_cols].rename(
        columns={col: f"right_{col}" for col in preview_cols}
    ).rename(columns={f"right_{id_column}": "right_id"})
    return matches.merge(left_preview, on="left_id", how="left").merge(
        right_preview, on="right_id", how="left"
    )


@st.cache_data(show_spinner=False)
def load_sample(path: str) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str)


def read_uploaded_or_sample(uploaded_file, sample_path: Path) -> pd.DataFrame:
    if uploaded_file is None:
        return load_sample(str(sample_path))
    return pd.read_csv(uploaded_file, dtype=str)


def main() -> None:
    st.set_page_config(page_title="PPRL SLDS USA POC", layout="wide")
    st.markdown(
        """
        <style>
        :root {
            --pprl-gray-900: #374151;
            --pprl-gray-700: #4b5563;
            --pprl-gray-600: #6b7280;
            --pprl-purple: #7c3aed;
            --pprl-purple-soft: rgba(124, 58, 237, 0.12);
        }
        .stApp, .stMarkdown, .stText, p, li, label, span, div {
            color: var(--pprl-gray-700);
        }
        h1, h2, h3, h4, h5, h6 {
            color: var(--pprl-gray-900) !important;
        }
        [data-testid="stCaptionContainer"] {
            color: var(--pprl-gray-600) !important;
        }
        [data-testid="stMetricLabel"],
        [data-testid="stMetricValue"],
        [data-testid="stMetricDelta"] {
            color: var(--pprl-gray-700) !important;
        }
        button, [role="tab"] {
            color: var(--pprl-gray-700) !important;
        }
        [role="tab"][aria-selected="true"] {
            color: var(--pprl-purple) !important;
        }
        .stSlider [data-baseweb="slider"] div {
            color: var(--pprl-purple) !important;
        }
        .logic-gray {
            color: var(--pprl-gray-600);
            font-size: 1rem;
            line-height: 1.55;
        }
        .logic-gray strong {
            color: var(--pprl-purple);
        }
        .logic-gray code {
            color: var(--pprl-gray-900);
            background: var(--pprl-purple-soft);
            padding: 0.1rem 0.25rem;
            border-radius: 0.25rem;
        }
        .gray-heading {
            color: var(--pprl-gray-900);
            font-weight: 650;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("PPRL SLDS USA Matching POC")
    st.caption(
        "Proof of concept: link synthetic State Longitudinal Data System records across "
        "education and workforce partners using salted hashed q-grams and blocking. "
        "The USA sample spans multiple states; raw identifiers are shown only for demo review."
    )

    with st.sidebar:
        st.header("Inputs")
        left_file = st.file_uploader("Client A SLDS workforce CSV", type=["csv"])
        right_file = st.file_uploader("Client B SLDS workforce CSV", type=["csv"])
        st.divider()
        q = st.slider("Q-gram length", 2, 4, 2)
        threshold = st.slider("Match threshold", 0.1, 1.0, 0.72, 0.01)
        salt = st.text_input("Local hashing salt", value="pprl-demo-salt", type="password")

    left = read_uploaded_or_sample(left_file, SAMPLE_A)
    right = read_uploaded_or_sample(right_file, SAMPLE_B)

    if "client_id" not in left.columns or "client_id" not in right.columns:
        st.error("Both files need a client_id column.")
        return

    common_fields = [
        col for col in DEFAULT_FIELDS + [
            "phone",
            "email",
            "address",
            "city",
            "state",
            "state_slds_id",
            "learner_id",
            "k12_district",
            "institution",
            "credential_level",
            "program_area",
            "graduation_year",
            "year",
            "employment_quarter",
            "employer_industry",
            "from_occupation_code",
            "to_occupation_code",
        ]
        if col in left.columns and col in right.columns
    ]

    selected_fields = st.multiselect(
        "Fields encoded into hashed linkage keys",
        options=common_fields,
        default=[field for field in DEFAULT_FIELDS if field in common_fields],
    )

    if not selected_fields:
        st.warning("Choose at least one linkage field.")
        return

    matches = link_records(
        left=left,
        right=right,
        id_column="client_id",
        fields=selected_fields,
        q=q,
        salt=salt,
        threshold=threshold,
    )
    enriched = enrich_matches(matches, left, right, "client_id")

    metric_cols = st.columns(4)
    metric_cols[0].metric("Client A records", f"{len(left):,}")
    metric_cols[1].metric("Client B records", f"{len(right):,}")
    metric_cols[2].metric("Candidate matches", f"{len(matches):,}")
    metric_cols[3].metric(
        "Avg score",
        "0.00" if matches.empty else f"{matches['similarity_score'].mean():.2f}",
    )

    tab_data, tab_matches, tab_logic = st.tabs(
        [
            "SLDS Data",
            "Linked SLDS Data",
            "Logic",
        ]
    )

    with tab_data:
        left_col, right_col = st.columns(2)
        with left_col:
            st.subheader("Client A")
            st.dataframe(left, width="stretch", hide_index=True)
        with right_col:
            st.subheader("Client B")
            st.dataframe(right, width="stretch", hide_index=True)

    with tab_matches:
        st.subheader("Linked SLDS Data")
        st.dataframe(enriched, width="stretch", hide_index=True)
        st.download_button(
            "Download linked SLDS data",
            enriched.to_csv(index=False).encode("utf-8"),
            "pprl_slds_candidate_matches.csv",
            "text/csv",
        )

    with tab_logic:
        st.markdown(
            f"""
            <h3 class="gray-heading">PPRL Logic</h3>
            <div class="logic-gray">
            <p><strong>1. Start with SLDS education-to-workforce records.</strong><br>
            The demo uses synthetic USA client records in a State Longitudinal Data System style.
            Each row includes demographic fields plus education and workforce fields such as
            <code>state_slds_id</code>, <code>institution</code>, <code>program_area</code>,
            <code>graduation_year</code>, <code>employer_industry</code>,
            <code>annual_wages</code>, <code>from_occupation</code>, and
            <code>to_occupation</code>.</p>

            <p><strong>2. Normalize linkage fields locally.</strong><br>
            Selected fields are standardized before encoding. Names are lowercased and stripped
            of punctuation, dates become <code>YYYYMMDD</code>, ZIPs use five digits, and phone
            numbers use the last ten digits.</p>

            <p><strong>3. Convert values into q-grams.</strong><br>
            Each selected field is split into overlapping q-grams. Current q-gram length:
            <code>{q}</code>. This allows fuzzy matching for small spelling differences like
            <code>Aisha</code> vs <code>Ayesha</code> or <code>Street</code> vs <code>St</code>.</p>

            <p><strong>4. Hash q-grams with a local salt.</strong><br>
            Raw q-grams are transformed with salted SHA-256 hashes. The match step compares hashed
            token overlap, not raw names or addresses. The salt should be shared only by approved
            linkage parties.</p>

            <p><strong>5. Block candidate pairs.</strong><br>
            Records are only compared inside the same block:
            <code>birth year | ZIP3 | gender</code>. Blocking keeps the candidate set small and
            reduces unnecessary comparisons.</p>

            <p><strong>6. Score matches with Dice similarity.</strong><br>
            For each candidate pair, the app computes
            <code>2 * shared_hashes / (left_hashes + right_hashes)</code>. Current threshold:
            <code>{threshold:.2f}</code>. Pairs above the threshold appear in Candidate Matches.</p>

            <p><strong>7. Review linkage output.</strong><br>
            The POC shows raw fields only for demo validation. In a production PPRL workflow, the
            linkage service would return record IDs and scores while keeping personally identifying
            fields separated from downstream workforce mobility analytics.</p>
            </div>
            
            <h3 class="gray-heading">Data Flow</h3>
            <div class="logic-gray">
            <p><strong>Raw SLDS partner data</strong><br>
            Education and workforce partners contribute state, district, institution, credential,
            program, occupation movement, wage, and employment-quarter signals.</p>

            <p><strong>Synthetic client SLDS records</strong><br>
            The sample generator creates two client-side files that represent the same
            multi-state USA population with realistic data-entry variation and a small set of
            unmatched records.</p>

            <p><strong>Local preprocessing</strong><br>
            Each party normalizes selected demographic and workforce fields locally.
            Raw identifiers do not need to be sent to the matching layer.</p>

            <p><strong>Privacy-preserving encoding</strong><br>
            Normalized values become q-grams, then salted hashes. The linkage layer compares
            hashed tokens and blocking keys instead of raw names, addresses, or dates.</p>

            <p><strong>Candidate matching</strong><br>
            Records in the same block are scored with Dice similarity. The output is a list of
            likely linked IDs with scores, not a joined table of raw personal identifiers.</p>

            <p><strong>SLDS analytics after linkage</strong><br>
            Matched IDs can be used to analyze education-to-career questions such as credential
            completion, program alignment, occupation movement, wage outcomes, and employment
            industry while minimizing direct exposure of identifying fields.</p>
            </div>

            <h3 class="gray-heading">Advantages of PPRL</h3>
            <div class="logic-gray">
            <p><strong>Privacy by design.</strong> Linkage uses encoded tokens rather than plain
            personally identifying information.</p>

            <p><strong>Works across organizations.</strong> Different clients can participate in
            linkage without sharing full raw demographic files with each other.</p>

            <p><strong>Tolerates messy data.</strong> Q-grams help match common variations such as
            nicknames, abbreviations, typos, and address formatting differences.</p>

            <p><strong>Operationally scalable.</strong> Blocking reduces pairwise comparisons, which
            keeps matching practical as record counts grow.</p>

            <p><strong>Auditable matching.</strong> Scores, shared hash counts, block keys, thresholds,
            and selected fields make match decisions reviewable.</p>

            <p><strong>Useful for SLDS reporting.</strong> Once records are linked, analysts can
            estimate education-to-workforce outcomes across states, schools, programs, employers,
            wages, occupations, and transition rates without centralizing sensitive identifiers.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.subheader("Encoded Linkage Features")
        st.write(
            "This view exposes record IDs, blocking keys, token counts, and hash overlap. "
            "It does not expose the raw q-grams used for matching."
        )
        encoded_preview = matches[
            [
                "left_id",
                "right_id",
                "block_key",
                "left_token_count",
                "right_token_count",
                "shared_token_count",
                "similarity_score",
            ]
        ]
        st.dataframe(encoded_preview, width="stretch", hide_index=True)


if __name__ == "__main__":
    main()
