"""Build-time trust anchor. Empty key deliberately disables network updates.

The release maintainer inserts ONLY the verified Ed25519 public key when
building the signed managed installer. Never commit or distribute private keys.
"""
PUBLIC_KEY = ""
BUILD_NUMBER = "70401"
FEED_URL = "https://github.com/moyashimisosoup/black-cut-auto-print/releases/download/update-feed/appcast.xml"
