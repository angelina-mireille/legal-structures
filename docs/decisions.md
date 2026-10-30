# Decisions

## 2026-10-25 (A2): full text stored only for US federal government works
Records keep the full text only for US federal government works (CFR, Federal Register, FinCEN guidance, FAR), which are public domain. Every other source (e.g. Cal. Fin. Code s. 3102) gets the URL and hash only; the downloaded copy is deleted after hashing.

## 2026-10-25 (A2): sha256 covers the raw bytes as retrieved or saved
The hash is of the file's exact bytes (HTML, PDF), not of extracted text, so anyone can re-check it with `shasum -a 256` and no extraction tool is involved.

## 2026-10-25 (A2): five sources saved by hand from a browser
Automated download was blocked for eCFR (31 CFR 1010.100, 501.601, 501.603, 501.604: redirected to a "Request Access" page) and for leginfo (Cal. Fin. Code s. 3102: HTTP 403 challenge page). The user saved these five pages from a browser on 2026-10-25. Their sha256 covers the file as saved, which may differ from the bytes a script would receive, so a later re-fetch can give a different hash without the law having changed. No unofficial copies were used.

## 2026-10-25 (A2): one record for FR 2026-21447, notice and appendix
The record `fr-2026-21447` covers both the notice and its appendix (the signed order), which are in the same govinfo PDF; the user checked that pages 2-5 contain the signed order. The govinfo PDF is used rather than the Federal Register XML, which has only image references for the appendix.

## 2026-10-25 (A2): FinCEN URL recorded after redirect
FIN-2019-G001 is recorded at the final `/system/files/` URL that served the hashed bytes (the `/sites/default/files/` link redirects there).

## 2026-10-27 (B1): EU output label renamed to "indicative criterion met (para 60)"
The EU output label is renamed from 'presumptively provider' to 'indicative criterion met (para 60)'. Reason: para 60 of the Commission GPAI guidelines calls the one-third test an indicative criterion; para 59 makes significant change the test; 'presumed' appears only in para 67, about high-impact capabilities.

## 2026-10-29 (B2): OCR for scanned pages of fr-2026-21447
Quotes from scanned pages of fr-2026-21447 are OCR transcriptions, each checked against the page image by me and marked as such.
