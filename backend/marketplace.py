"""Shared reference voices, published only after preview and explicit consent."""
import re
import shutil
from uuid import uuid4
from fastapi import HTTPException
from .auth import database

SAMPLE_TEXT = '안녕하세요. 오늘도 만나서 반갑습니다. 지금부터 새로운 이야기를 들려드릴게요.'
CONSENT_VERSION = '2026-10-14-v1'
CONSENT_TEXT = '등록하는 음성이 임직원의 목소리인 경우, 해당 개인에게 음성 업로드, AI 음성 생성 및 플랫폼 이용자 대상 공유·다운로드에 대해 설명하고 동의를 받았음을 서약합니다. 또한 이 음성을 등록하고 공유할 권한이 있음을 확인합니다.'


def directory(data, key):
    if not re.fullmatch(r'[a-f0-9]{32}', key): raise HTTPException(404, '목소리를 찾을 수 없습니다.')
    return data / 'marketplace' / key


def public(row, user_id):
    result = {key: row[key] for key in ['voice_id','name','description','gender','download_count','sample_text','reference_seconds','sample_seconds','created_at']}
    owner_display_name = ' '.join(str(row.get(key) or '').strip() for key in ['owner_team','owner_name','owner_role'] if row.get(key) and str(row[key]).strip() != '미지정')
    result.update(owner_name=row.get('owner_name', ''), owner_display_name=owner_display_name, is_owner=row['user_id']==user_id,
                  favorite=bool(row.get('favorite',False)),
                  audio_url=f'/wiavoice/api/marketplace/{row["voice_id"]}/sample',
                  download_url=f'/wiavoice/api/marketplace/{row["voice_id"]}/reference')
    return result


def list_voices(user_id, search='', mine=False, favorites=False, offset=0, limit=8, sort='popular'):
    where = '''m.deleted_at IS NULL AND m.hidden_at IS NULL AND (%s=FALSE OR m.user_id=%s)
        AND (%s='' OR strpos(lower(m.name || ' ' || m.description), lower(%s))>0)
        AND (%s=FALSE OR f.user_id IS NOT NULL)'''
    params=(user_id,mine,user_id,search,search,favorites)
    source=''' FROM wiavoice.market_voices m JOIN platform.users u ON u.user_id=m.user_id
        LEFT JOIN platform.teams t ON t.team_id=u.team_id
        LEFT JOIN platform.roles r ON r.role_id=u.role_id
        LEFT JOIN wiavoice.market_favorites f ON f.voice_id=m.voice_id AND f.user_id=%s WHERE '''+where
    order = 'm.created_at DESC,m.voice_id' if sort=='latest' else 'm.download_count DESC,m.created_at DESC,m.voice_id'
    with database() as db:
        total=db.execute('SELECT count(*) AS total'+source,params).fetchone()['total']
        rows=db.execute('SELECT m.*,u.full_name AS owner_name,t.name AS owner_team,r.name AS owner_role,(f.user_id IS NOT NULL) AS favorite'+source+
                        ' ORDER BY '+order+' LIMIT %s OFFSET %s',(*params,limit,offset)).fetchall()
    return {'items':[public(row,user_id) for row in rows],'total':total}


def publish(data,user_id,job,name,description,reference,audio,seconds,gender):
    target=None
    try:
        with database() as db:
            db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',('market:'+user_id+':'+job['id'],))
            existing=db.execute('SELECT * FROM wiavoice.market_voices WHERE user_id=%s AND source_job_id=%s',(user_id,job['id'])).fetchone()
            if existing:
                if existing['deleted_at']: raise HTTPException(409,'삭제한 등록입니다. 샘플을 새로 생성해 주세요.')
                return public(existing,user_id)
            key=uuid4().hex
            target=directory(data,key)
            target.mkdir(mode=0o700,parents=True)
            (target/'reference.wav').write_bytes(reference)
            (target/'sample.wav').write_bytes(audio)
            row=db.execute('''INSERT INTO wiavoice.market_voices
                (voice_id,user_id,source_job_id,name,description,sample_text,reference_seconds,sample_seconds,consent_version,consent_text,gender)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *''',
                (key,user_id,job['id'],name,description,job['request']['text'],seconds,job['seconds'],CONSENT_VERSION,CONSENT_TEXT,gender)).fetchone()
        return public(row,user_id)
    except BaseException:
        if target: shutil.rmtree(target,ignore_errors=True)
        raise


def get_voice(key):
    with database() as db:
        row=db.execute('SELECT * FROM wiavoice.market_voices WHERE voice_id=%s AND deleted_at IS NULL AND hidden_at IS NULL',(key,)).fetchone()
    if not row: raise HTTPException(404,'목소리를 찾을 수 없습니다.')
    return row


def favorite(user_id,key,enabled):
    with database() as db:
        row=db.execute('SELECT voice_id FROM wiavoice.market_voices WHERE voice_id=%s AND deleted_at IS NULL AND hidden_at IS NULL FOR UPDATE',(key,)).fetchone()
        if not row: raise HTTPException(404,'목소리를 찾을 수 없습니다.')
        if enabled:
            db.execute('INSERT INTO wiavoice.market_favorites(user_id,voice_id) VALUES (%s,%s) ON CONFLICT DO NOTHING',(user_id,key))
        else: db.execute('DELETE FROM wiavoice.market_favorites WHERE user_id=%s AND voice_id=%s',(user_id,key))
    return {'favorite':enabled}


def delete_voice(data,user_id,key):
    path=directory(data,key)
    with database() as db:
        row=db.execute('UPDATE wiavoice.market_voices SET deleted_at=now() WHERE voice_id=%s AND user_id=%s AND deleted_at IS NULL RETURNING voice_id',(key,user_id)).fetchone()
        if not row: raise HTTPException(404,'등록한 목소리를 찾을 수 없습니다.')
        db.execute('DELETE FROM wiavoice.market_favorites WHERE voice_id=%s',(key,))
    # The row tombstone prevents access immediately; the reaper retries disk cleanup.
    shutil.rmtree(path,ignore_errors=True)
    return {'ok':True}


def cleanup(data):
    root=data/'marketplace'
    if not root.exists() or not any(root.iterdir()): return
    with database() as db:
        rows=db.execute('SELECT voice_id FROM wiavoice.market_voices WHERE deleted_at IS NOT NULL').fetchall()
    for row in rows: shutil.rmtree(directory(data,row['voice_id']),ignore_errors=True)


def count_download(key,user_id=None):
    with database() as db:
        row=db.execute('UPDATE wiavoice.market_voices SET download_count=download_count+1 WHERE voice_id=%s AND deleted_at IS NULL AND hidden_at IS NULL RETURNING download_count',(key,)).fetchone()
        if not row: raise HTTPException(404,'목소리를 찾을 수 없습니다.')
        db.execute('INSERT INTO wiavoice.download_events(voice_id,user_id) VALUES(%s,%s)',(key,user_id))
    return row['download_count']
