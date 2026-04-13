import streamlit as st
import json
import os

# ─────────────────────────────────────────────────────────────
# CONFIG & PATHS
# ─────────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "conversations")
OUTPUT_FILE = os.path.join(DATA_DIR, "custom_eval_data.jsonl")
os.makedirs(DATA_DIR, exist_ok=True)

PRESET_APPS = ["manuel_parc_auto", "hr_portal", "billing_system"]

# ─────────────────────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────────────────────
if "turns" not in st.session_state:
    st.session_state.turns = []
if "app_id" not in st.session_state:
    st.session_state.app_id = PRESET_APPS[0]
if "conv_id" not in st.session_state:
    st.session_state.conv_id = "conv_1"

# ─────────────────────────────────────────────────────────────
# UI LAYOUT
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="RAG Data Builder", layout="wide")
st.title("📝 Multi-Turn RAG Evaluation Data Builder")
st.caption("Fill turns sequentially. Export appends to JSONL safely.")

with st.sidebar:
    st.header("⚙️ Conversation Settings")

    app_choice = st.selectbox("App ID", PRESET_APPS + ["✏️ Enter custom..."], index=0)
    if app_choice == "✏️ Enter custom...":
        st.session_state.app_id = st.text_input(
            "Custom App ID",
            value=st.session_state.app_id if st.session_state.app_id not in PRESET_APPS else "",
            placeholder="e.g., legacy_hr_v2"
        )
    else:
        st.session_state.app_id = app_choice

    st.text_input("Conversation ID", key="conv_id", value=st.session_state.conv_id)

    st.divider()
    st.subheader(f"📊 Turns: {len(st.session_state.turns)}")
    if st.session_state.turns:
        for i, turn in enumerate(st.session_state.turns, 1):
            quality_icon = {
                "well_written": "✅",
                "poorly_written": "⚠️",
                "ambiguous": "🔀"
            }.get(turn.get("query_quality", ""), "❓")
            st.text(f"Turn {i} {quality_icon}: {turn['user_query'][:28]}...")

    st.divider()
    if st.button("🗑️ Clear All Turns", type="secondary"):
        st.session_state.turns = []
        st.rerun()

# ─────────────────────────────────────────────────────────────
# TURN INPUT FORM
# ─────────────────────────────────────────────────────────────

# ⚠️ KEY DU TURN — force Streamlit à recréer tous les widgets à chaque nouveau turn
turn_index = len(st.session_state.turns)

st.subheader(f"✏️ Turn {turn_index + 1}")
with st.form(f"turn_form_{turn_index}", clear_on_submit=False):
    col1, col2 = st.columns(2)
    user_query = col1.text_area(
        "User Query",
        placeholder="e.g., Comment créer un compte?",
        height=100,
        key=f"user_query_{turn_index}"
    )
    rewritten_query = col2.text_area(
        "Rewritten Query (Optional)",
        placeholder="e.g., Procédure création compte entreprise",
        height=100,
        key=f"rewritten_query_{turn_index}"
    )

    # ── CHAMP QUALITÉ OBLIGATOIRE ──────────────────────────────
    QUALITY_OPTIONS = {
        "well_written ": "well_written",
        "poorly_written": "poorly_written",
        "ambiguous": "ambiguous",
    }
    query_quality_label = st.selectbox(
        "🔍 Query Quality *",
        options=list(QUALITY_OPTIONS.keys()),
        index=0,
        key=f"quality_{turn_index}",
        help="Indiquez si la requête utilisateur est bien formulée ou non. Ce champ est obligatoire.",
    )
    query_quality = QUALITY_OPTIONS[query_quality_label]
    # ───────────────────────────────────────────────────────────

    # ⚠️ FIX : key dynamique → le radio repart à "faq" à chaque nouveau turn
    routing_label = st.radio(
        "Routing Label",
        ["faq", "rag", "ood"],
        horizontal=True,
        key=f"routing_{turn_index}"   # ← LE FIX
    )

    show_context = routing_label != "ood"
    with st.expander(
        "📖 Context & Answer" if show_context else "ℹ️ OOD: No context needed",
        expanded=show_context
    ):
        if show_context:
            rel_sections = st.text_input(
                "Relevant Section IDs (comma-separated)",
                placeholder="sec_auth_01, sec_fact_02",
                key=f"rel_sections_{turn_index}"   # ← key dynamique aussi
            )
            answer = st.text_area(
                "Ground Truth Answer",
                placeholder="Paste concise answer from manual...",
                height=100,
                key=f"answer_{turn_index}"   # ← idem
            )
        else:
            rel_sections = ""
            answer = ""

    submitted = st.form_submit_button("✅ Add Turn", use_container_width=True)

# ─────────────────────────────────────────────────────────────
# VALIDATION & STATE UPDATE
# ─────────────────────────────────────────────────────────────
if submitted:
    if not user_query.strip():
        st.error("User Query is required.")
    elif query_quality is None:
        st.error("⚠️ Veuillez évaluer la qualité de la requête avant de continuer.")
    elif routing_label != "ood" and not rel_sections.strip():
        st.error("Relevant Section IDs are required for FAQ/RAG.")
    else:
        turn_data = {
            "turn_id": turn_index + 1,
            "user_query": user_query.strip(),
            "rewritten_query": rewritten_query.strip() if rewritten_query.strip() else None,
            "query_quality": query_quality,
            "routing_label": routing_label,
            "relevant_sections": [s.strip() for s in rel_sections.split(",") if s.strip()] if rel_sections else [],
            "answer": answer.strip() if answer.strip() else None,
            "assistant_response": answer.strip() if answer.strip() else "N/A"
        }
        st.session_state.turns.append(turn_data)
        st.success(f"✅ Turn {turn_data['turn_id']} added!")
        st.rerun()

# ─────────────────────────────────────────────────────────────
# EXPORT TO JSONL
# ─────────────────────────────────────────────────────────────
st.divider()
if st.session_state.turns:
    st.subheader("📤 Export Conversation")
    col_left, col_right = st.columns([3, 1])

    preview_data = {
        "conversation_id": st.session_state.conv_id,
        "app_id": st.session_state.app_id,
        "turns": st.session_state.turns
    }
    with col_left:
        with st.expander("👀 Preview JSON"):
            st.json(preview_data)

    if col_right.button("💾 Export to JSONL", type="primary", use_container_width=True):
        try:
            with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(preview_data, ensure_ascii=False) + "\n")
            st.success(f"✅ Appended to `{os.path.basename(OUTPUT_FILE)}`")
            st.session_state.turns = []
            st.rerun()
        except Exception as e:
            st.error(f"❌ Export failed: {e}")
else:
    st.info("💡 Add at least one turn to enable export.")