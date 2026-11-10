# The single version of this application. It lives here rather than in a
# package metadata file because the project is not distributed as a package:
# it runs from the compose stack, and the only consumer of the version is a
# human reading a log line or a bug report.
#
# It is the version in CHANGELOG.md and in the git tag of the same name, and
# the three are meant to be moved together. A release is: bump this, add the
# section to CHANGELOG.md, tag v<version>.
__version__ = "0.6.0-alpha"

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
