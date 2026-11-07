# The only provider the app calls. Adding another one means a new file in
# providers/ plus an entry in router.py, and a model that has been checked
# against the full analysis schema in services/schema_models.py.
DEFAULT_PROVIDER = "nvidia"

# Chosen by probing the gateway against the real schema: this model is the
# one that returned all nine top-level keys with the nested item shape
# correct, in one pass, without a Markdown fence.
DEFAULT_MODEL = "minimaxai/minimax-m3.1-flash"

# 2048 dimensions. The 8b sibling is 4096 for no measurable gain on short
# titles, and doubles the stored embedding size.
EMBEDDING_MODEL = "nvidia/nemotron-3.5-embed-1b"
