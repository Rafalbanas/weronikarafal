#!/usr/bin/python3
"""Incremental offsite media copy followed by a consistent SQLite snapshot."""
import datetime
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile

os.umask(0o077)
HOST = os.environ.get('WEDDING_BACKUP_HOST', 'stacjonarka')
REMOTE = os.environ['WEDDING_BACKUP_REMOTE']
# Paths enter SSH/rsync remote commands; accept only a simple absolute path.
if not REMOTE.startswith('/') or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/_-.' for c in REMOTE) or HOST.startswith('-') or any(c.isspace() for c in HOST):
    raise ValueError('Invalid backup destination')
MEDIA = Path('/storage/weronikarafal/uploads')
DATA = Path('/var/lib/weronikarafal-data')
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3']
def run(args):
    subprocess.run(args, check=True, timeout=3000)

with open('/run/weronikarafal-backup/lock', 'w') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if not os.path.ismount('/storage'):
        raise RuntimeError('/storage is not mounted')
    stamp = datetime.datetime.now(datetime.timezone.utc)
    folder = stamp.strftime('%Y-%m-%d')
    hour = stamp.strftime('%H')
    with tempfile.TemporaryDirectory(prefix='backup-', dir='/storage/weronikarafal') as stage:
        stage = Path(stage)
        snapshot = stage / 'guests.sqlite3'
        with sqlite3.connect(f'file:{DATA}/guests.sqlite3?mode=ro', uri=True) as source:
            with sqlite3.connect(snapshot) as dest:
                source.backup(dest)
        with sqlite3.connect(snapshot) as db:
            assert db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
            ids = [row[0] for row in db.execute('SELECT id FROM uploads')]
        for name in ids:
            if len(name) != 32 or any(c not in '0123456789abcdef' for c in name):
                raise RuntimeError('Invalid media identifier')
            if not (MEDIA / name).is_file():
                raise RuntimeError('Snapshot references missing media: ' + name)
        # Copy committed media first; never mirror deletions or unfinished uploads.
        listing = stage / 'media-list'
        listing.write_text(''.join(name + '\n' for name in ids))
        run(SSH + [HOST, f'umask 077; mkdir -p {REMOTE}/uploads {REMOTE}/database/{folder}; chmod 700 {REMOTE} {REMOTE}/uploads {REMOTE}/database {REMOTE}/database/{folder}'])
        rsync = ['rsync', '-rt', '--chmod=F600,D700', '--bwlimit=5120', '--partial-dir=.rsync-partial', '--delay-updates', '-e', ' '.join(SSH)]
        run(rsync + ['--files-from=' + str(listing), str(MEDIA) + '/', HOST + ':' + REMOTE + '/uploads/'])
        metadata = stage / 'metadata'
        metadata.mkdir()
        snapshot.rename(metadata / (hour + '.sqlite3'))
        if (DATA / 'details.json').exists():
            (metadata / (hour + '-details.json')).write_bytes((DATA / 'details.json').read_bytes())
        (metadata / (hour + '-status.json')).write_text(json.dumps({'completed_snapshot_utc': stamp.isoformat(), 'media_count': len(ids), 'uploads_directory': str(MEDIA)}, indent=2) + '\n')
        run(rsync + [str(metadata) + '/', HOST + ':' + REMOTE + '/database/' + folder + '/'])
        print('Backup completed:', stamp.isoformat(), 'media:', len(ids), flush=True)
