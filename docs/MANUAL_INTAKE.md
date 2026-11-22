# Manual document intake through ChatGPT

Privacy Watch supports two complementary evidence paths.

## Automated public-source path
GitHub Actions reads explicitly configured public legal and PIPC sources and
stores extracted text, SHA-256 hashes, provenance URLs, failures and review
hypotheses. This pipeline MUST NOT log in as a user, probe nonpublic endpoints,
or scan services for vulnerabilities.

## Manual chat path
An operator can attach an original PDF, HWP, HWPX, DOC, DOCX, XLS, PPT or
scanned guideline to a ChatGPT conversation for targeted analysis. The file may
be used to establish the precise guideline text, version and cited provisions,
and compared with public NAVER policy and governing law.

**A chat upload is not automatically synchronized with GitHub Actions.**
A future run cannot silently read a chat attachment. To make a manual review
part of the scheduled monitor, separately add verified, publication-authorized
text and provenance to the repository through an explicit user-approved change.

Record the following when importing manually:
- issuing body and original public publication URL;
- document title, publication date, revision/version, file format;
- original file SHA-256 and extraction confidence (text/OCR/manual);
- exact cited section, related governing statutory provisions and effective dates;
- whether the source is binding law, administrative rule or nonbinding guidance;
- whether the information is safe for public repository storage.

Never commit private uploads, access tokens, personal data or materials lacking
publication permission to this public repository. A keyword overlap between
documents is an **unverified review lead**, not proof of illegality or of an
implemented vulnerability.

If an official download link is generated only by JavaScript and no direct
approved URL is available in the HTML, mark extraction as incomplete and
request manual review. Do not reverse-engineer private endpoints.
