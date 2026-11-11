"""Cache policy for bodies that are authorised per Principal.

A 200 for an authorised file body is indistinguishable from a 200 for anybody
else once a browser or an intermediary caches it, so every route that streams
authorised content has to opt out of caching explicitly. Pragma and Expires only
cover HTTP/1.0 hops and must stay consistent with ``no-store``.
"""

NO_STORE_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "Expires": "0",
}