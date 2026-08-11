from flask import Flask, render_template, request

from analyzer import analyze_document
from config import GEMINI_ALLOWED_MODELS, GROQ_ALLOWED_MODELS
from document_parser import extract_text
from router import ModelRouter


PROVIDER_OPTIONS = {
    "Google Gemini": "google",
    "Groq": "groq",
}

ALLOWED_MODELS = {
    "google": GEMINI_ALLOWED_MODELS,
    "groq": GROQ_ALLOWED_MODELS,
}


def get_available_models(router, provider):
    """Discover provider models and retain only supported application models."""
    return [
        model
        for model in router.get_models(provider)
        if model in ALLOWED_MODELS[provider]
    ]


def create_app(router_instance=None):
    app = Flask(__name__)
    router = router_instance or ModelRouter()

    @app.route("/", methods=["GET", "POST"])
    def index():
        provider = request.form.get("provider", "google")
        if provider not in PROVIDER_OPTIONS.values():
            provider = "google"

        notes = request.form.get("meeting_notes", "")
        result = None
        error = None
        success = None

        try:
            models = get_available_models(router, provider)
        except (ValueError, RuntimeError) as exception:
            models = []
            error = str(exception)

        selected_model = request.form.get("model")
        if selected_model not in models:
            selected_model = models[0] if models else None

        if request.method == "POST" and not error:
            uploaded_file = request.files.get("meeting_file")
            try:
                if uploaded_file and uploaded_file.filename:
                    text_to_analyze = extract_text(uploaded_file)
                    success = f"Loaded: {uploaded_file.filename}"
                elif notes.strip():
                    text_to_analyze = notes.strip()
                else:
                    raise ValueError("Please upload a file or enter meeting notes.")

                if not selected_model:
                    raise ValueError("No supported models are currently available.")

                result = analyze_document(
                    text=text_to_analyze,
                    provider=provider,
                    model=selected_model,
                    router_instance=router,
                )
                success = f"Generated using {provider}: {selected_model}"
            except (ValueError, RuntimeError) as exception:
                error = str(exception)

        return render_template(
            "index.html",
            provider=provider,
            providers=PROVIDER_OPTIONS,
            models=models,
            selected_model=selected_model,
            notes=notes,
            result=result,
            error=error,
            success=success,
        )

    @app.get("/models/<provider>")
    def models(provider):
        if provider not in PROVIDER_OPTIONS.values():
            return {"error": "Unsupported provider."}, 404
        try:
            return {"models": get_available_models(router, provider)}
        except (ValueError, RuntimeError) as exception:
            return {"error": str(exception)}, 400

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
