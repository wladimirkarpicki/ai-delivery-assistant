import streamlit as st

from analyzer import analyze_document
from router import ModelRouter
from config import (
    GROQ_ALLOWED_MODELS,
    GEMINI_ALLOWED_MODELS
)


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

meeting_notes = st.text_area(
    "Paste meeting notes",
    height=300
)


# -------------------------
# Analysis
# -------------------------

if st.button("Analyze"):

    if not meeting_notes.strip():

        st.warning(
            "Please enter meeting notes first."
        )

    else:

        with st.spinner("Analyzing..."):

            result = analyze_document(
                text=meeting_notes,
                provider=provider,
                model=model
            )

        st.success(
            f"Generated using {provider_name}: {model}"
        )

        st.markdown(result)