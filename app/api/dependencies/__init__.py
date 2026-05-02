"""FastAPI dependency factories.

Auth deps live here so they can be reused across every router without
each route module importing `app.api.deps` and the auth domain
separately.
"""
