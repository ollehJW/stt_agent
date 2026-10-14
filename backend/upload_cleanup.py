"""Expire temporary upload pairs only; durable voices are outside this directory.

Called synchronously on the single ASGI event loop, as are upload creation and
job enqueueing, so an upload cannot be acquired midway through deletion.
"""
import logging
import re
import time

TTL_SECONDS = 24 * 60 * 60
ACTIVE_STATUSES = {'queued', 'loading', 'generating'}
logger = logging.getLogger('wiavoice')


def protected_uploads(jobs, running_uploads=()):
    protected = set(running_uploads)
    for job in jobs:
        if job.get('status') in ACTIVE_STATUSES:
            request = job.get('request', {})
            if request.get('voice') == 'custom':
                protected.add(request.get('upload_id'))
    return protected


def cleanup_uploads(data, protected=(), now=None):
    """Use the newer file mtime, including legacy uploads lacking creation metadata."""
    root = data / 'uploads'
    if not root.is_dir() or root.is_symlink():
        return 0
    cutoff = (time.time() if now is None else now) - TTL_SECONDS
    keys = {p.stem for p in root.iterdir()
            if p.suffix in {'.wav', '.json'} and re.fullmatch(r'[a-f0-9]{32}', p.stem)}
    removed = 0
    for key in keys - set(protected):
        paths = [root / (key + suffix) for suffix in ('.wav', '.json')]
        try:
            if any(p.is_symlink() for p in paths):
                continue
            existing = [p for p in paths if p.exists()]
            if not existing or any(not p.is_file() for p in existing):
                continue
            if max(p.stat().st_mtime for p in existing) > cutoff:
                continue
            for p in existing:
                p.unlink(missing_ok=True)
            removed += 1
        except OSError:
            logger.exception('Could not remove expired upload %s; will retry', key)
    return removed
