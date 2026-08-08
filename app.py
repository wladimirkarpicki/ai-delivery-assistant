import streamlit as st

from analyzer import analyze_document
from router import ModelRouter
from config import (
    GROQ_ALLOWED_MODELS,
    GEMINI_ALLOWED_MODELS
)
from document_parser import extract_text


router = ModelRouter()


st.set_page_config(
    page_title="AI Delivery Assistant",
    layout="wide"
)


st.title("AI Delivery Assistant")


# -------------------------
# Provider selection
# -------------------------

provider_options = {
    "Google Gemini": "google",
    "Groq": "groq"
}


provider_name = st.selectbox(
    "AI Provider",
    list(provider_options.keys()),
    width=400
)

provider = provider_options[provider_name]


# -------------------------
# Model selection
# -------------------------

@st.cache_data(ttl=3600)
def get_available_models(provider):
    return router.get_models(provider)


models = get_available_models(provider)


# Filter models according to provider
if provider == "groq":

    models = [
        model
        for model in models
        if model in GROQ_ALLOWED_MODELS
    ]

elif provider == "google":

    models = [
        model
        for model in models
        if model in GEMINI_ALLOWED_MODELS
    ]


if not models:

    st.error(
        f"No supported models are currently available for {provider_name}."
    )

    st.stop()


model = st.selectbox(
    "AI Model",
    models,
    width=400
)


# -------------------------
# Meeting notes input
# -------------------------

st.subheader("Meeting Notes")


uploaded_file = st.file_uploader(
    "Upload meeting notes",
    type=["pdf", "docx", "txt", "md"],
    help="Supported formats: PDF, DOCX, TXT, Markdown"
)


st.caption("Or paste meeting notes below.")


meeting_notes = st.text_area(
    "Meeting notes",
    height=300,
    placeholder="Paste your meeting notes here..."
)


# -------------------------
# Analysis
# -------------------------

if st.button("Analyze"):

    text_to_analyze = None

    # -------------------------
    # Uploaded file
    # -------------------------

    if uploaded_file is not None:

        try:

            text_to_analyze = extract_text(
                uploaded_file
            )

            st.success(
                f"Loaded: {uploaded_file.name}"
            )

        except ValueError as error:

            st.error(str(error))

            st.stop()


    # -------------------------
    # Pasted text
    # -------------------------

    elif meeting_notes.strip():

        text_to_analyze = meeting_notes.strip()


    # -------------------------
    # No input
    # -------------------------

    else:

        st.warning(
            "Please upload a file or enter meeting notes."
        )

        st.stop()


    # -------------------------
    # Generate analysis
    # -------------------------

    with st.spinner("Analyzing..."):

        result = analyze_document(
            text=text_to_analyze,
            provider=provider,
            model=model
        )


    # -------------------------
    # Display result
    # -------------------------

    st.success(
        f"Generated using {provider_name}: {model}"
    )

    st.markdown(result)