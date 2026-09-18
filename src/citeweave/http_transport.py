"""Reuse the process trust store when constructing bounded local adapter clients."""

import ssl

# This is TLS configuration, not a response/model/retrieval cache. Verification
# remains enabled, including for installations that configure HTTPS upstreams.
TLS_CONTEXT = ssl.create_default_context()
