import streamlit as st

from analyzer import analyze_document
from router import ModelRouter



router = ModelRouter()



st.set_page_config(
    page_title="AI Delivery Assistant",
    layout="wide"
)


st.title(
    "AI Delivery Assistant"
)



# -------------------------
# Provider selection
# -------------------------

provider_options = {
    "Google": "google",
    "Groq": "groq"
}


provider_name = st.selectbox(
    "AI Provider",
    list(provider_options.keys())
)


provider = provider_options[provider_name]



# -------------------------
# Model selection
# -------------------------

@st.cache_data(ttl=3600)
def get_available_models(provider):

    return router.get_models(
        provider
    )



models = get_available_models(
    provider
)


model = st.selectbox(
    "AI Model",
    models
)



# -------------------------
# Input
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

        with st.spinner(
            "Analyzing..."
        ):

            result = analyze_document(
                text=meeting_notes,
                provider=provider,
                model=model
            )


        st.success(
            f"Generated using {provider_name}: {model}"
        )


        st.markdown(
            result
        )