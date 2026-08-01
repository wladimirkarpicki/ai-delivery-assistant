import streamlit as st
from analyzer import analyze_document


st.title("AI Delivery Manager Assistant")


text = st.text_area(
    "Paste meeting notes"
)


if st.button("Analyze"):

    result = analyze_document(text)

    st.write(result)