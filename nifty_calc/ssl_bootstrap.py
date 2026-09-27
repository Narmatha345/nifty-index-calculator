"""Trust a locally installed root CA (e.g. from antivirus/corporate TLS
inspection) for outbound HTTPS calls, if one has been exported to
certs/local_root_ca.pem.

Some machines have security software that intercepts HTTPS traffic; Windows
(and tools like curl) already trust the injected root because the software
installs it into the OS certificate store, but Python's bundled `certifi`
CA list does not know about it, so `requests`/`curl_cffi` (and therefore
yfinance) fail with CertificateVerifyError even though the connection itself
is fine.

This is a no-op when certs/local_root_ca.pem doesn't exist, so it has no
effect on machines that don't need it. It must run before `yfinance` (or
anything using `requests`/`curl_cffi`) is imported, since those libraries
read the CA bundle env vars at session-creation time.
"""

from __future__ import annotations

import os
from pathlib import Path

import certifi

import config

_EXTRA_CA_PATH = config.ROOT_DIR / "certs" / "local_root_ca.pem"
_COMBINED_CA_PATH = config.CACHE_DIR / "combined_ca_bundle.pem"

_CA_ENV_VARS = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE")


def ensure_local_ca_trusted() -> None:
    if not _EXTRA_CA_PATH.exists():
        return
    if any(os.environ.get(var) for var in _CA_ENV_VARS):
        return  # caller/environment already configured a CA bundle - don't override it

    certifi_bundle = Path(certifi.where()).read_text()
    extra = _EXTRA_CA_PATH.read_text()
    combined = certifi_bundle + "\n" + extra

    _COMBINED_CA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _COMBINED_CA_PATH.exists() or _COMBINED_CA_PATH.read_text() != combined:
        _COMBINED_CA_PATH.write_text(combined)

    for var in _CA_ENV_VARS:
        os.environ[var] = str(_COMBINED_CA_PATH)
