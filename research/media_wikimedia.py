"""Exact Wikimedia media hosts, including the 2026 thumbnail domain change.

MediaWiki advertises thumb.wikimedia.org for thumbnails; originals retain
upload.wikimedia.org. Keep both explicit rather than allowing arbitrary
subdomains. Source: https://meta.wikimedia.org/wiki/Tech/News/2026/36
"""

WIKIMEDIA_IMAGE_HOSTS = (
    'upload.wikimedia.org', 'thumb.wikimedia.org', 'commons.wikimedia.org',
)
# A changed image policy must reopen failed matching rows and revalidate their
# candidate lists. Existing HTTP responses, ledgers and image files are kept.
WIKIMEDIA_IMAGE_POLICY = 'wikimedia-thumbnails-v1'
