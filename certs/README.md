# certs/

`local_root_ca.pem` is a root certificate exported from this machine's Windows
certificate store (Cert:\CurrentUser\Root). It is not a secret - it's a public
root certificate, typically installed here by antivirus/endpoint software
(e.g. AVG, corporate security tools) that performs TLS inspection on outbound
HTTPS traffic.

Python's own bundled CA store (`certifi`) doesn't know about this locally
installed root, even though Windows (and therefore tools like `curl`) already
trusts it. Without this file, `yfinance` downloads fail with
`CertificateVerifyError` on this machine even though the network connection
itself is fine.

`nifty_calc/ssl_bootstrap.py` merges this certificate with the standard
`certifi` bundle at runtime and points `requests`/`curl_cffi` at the combined
bundle. If this file is absent (e.g. on a different machine without this
interception), `ssl_bootstrap` is a no-op and normal certificate verification
applies.

If you regenerate this file for your own machine, find the intercepting
root's Common Name first (e.g. via `openssl s_client -connect
query1.finance.yahoo.com:443 -showcerts` and check the `issuer=` line), then
export that certificate from `Cert:\CurrentUser\Root` in PowerShell.
