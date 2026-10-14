"""Validate the platform's shared, revocable session; never issue local sessions."""
import hashlib
import os
import time
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row
from fastapi import HTTPException, Request

COOKIE = 'ax_platform_session'
PLATFORM_ORIGIN = 'https://axforwork.wia.co.kr'
load_dotenv(Path(os.getenv('WIAVOICE_AUTH_ENV', '/data/wiavoice/auth.env')), override=False)

@contextmanager
def database():
    try:
        with psycopg.connect(host=os.getenv('AX_DB_HOST', '127.0.0.1'),
                port=int(os.getenv('AX_DB_PORT', '5432')), dbname=os.getenv('AX_DB_NAME', 'wia_platform'),
                user=os.getenv('AX_DB_USER', 'wia_platform_admin'), password=os.getenv('AX_DB_PASSWORD', ''),
                connect_timeout=5, application_name='wiavoice',
                options='-c statement_timeout=10000', row_factory=dict_row) as db:
            yield db
    except psycopg.Error:
        raise HTTPException(503, '계정 서비스에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.') from None

def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()

def current_user(request: Request):
    token = request.cookies.get(COOKIE, '')
    if not token or len(token) > 256:
        raise HTTPException(401, '통합 로그인이 필요합니다.')
    with database() as db:
        user = db.execute('''SELECT u.user_id,u.full_name,u.employee_id,u.is_admin,u.must_change_password,
            COALESCE(t.name,'') AS team_name,s.expires_at
            FROM platform.sessions s JOIN platform.users u ON u.user_id=s.user_id
            LEFT JOIN platform.teams t ON t.team_id=u.team_id
            WHERE s.token_hash=%s AND s.expires_at>%s AND u.is_active=TRUE''',
            (token_hash(token), time.time())).fetchone()
    if not user:
        raise HTTPException(401, '로그인이 만료되었습니다. 다시 로그인해 주세요.')
    if user['must_change_password']:
        raise HTTPException(403, '플랫폼에서 비밀번호 설정을 완료해 주세요.')
    return dict(user)

def authorize(request: Request):
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        origin = request.headers.get('origin')
        if (origin and origin != PLATFORM_ORIGIN) or request.headers.get('sec-fetch-site') == 'cross-site':
            raise HTTPException(403, '허용되지 않는 요청 출처입니다.')
    if request.url.path in {'/api/health', '/api/auth/logout'}:
        return
    request.state.user = current_user(request)
    request.state.session_key = token_hash(request.cookies[COOKIE])

def revoke_session(request):
    with database() as db:
        db.execute('DELETE FROM platform.sessions WHERE token_hash=%s',
                   (token_hash(request.cookies.get(COOKIE, '')),))


def active_session_keys(keys):
    """DB failures raise: they must never be interpreted as session expiry."""
    if not keys:
        return set()
    with database() as db:
        rows = db.execute('''SELECT s.token_hash FROM platform.sessions s
            JOIN platform.users u ON u.user_id=s.user_id
            WHERE s.token_hash=ANY(%s) AND s.expires_at>%s
            AND u.is_active=TRUE AND u.must_change_password=FALSE''', (list(keys), time.time())).fetchall()
    return {row['token_hash'] for row in rows}
