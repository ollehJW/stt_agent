"""Platform-admin-only operational views and auditable marketplace moderation."""
from datetime import date,datetime,time,timedelta
from typing import Literal
from zoneinfo import ZoneInfo
import shutil
from fastapi import APIRouter,Depends,HTTPException,Query,Request
from fastapi.responses import FileResponse
from pydantic import BaseModel,ConfigDict,Field
from psycopg.types.json import Jsonb
from .auth import database
from . import marketplace,library


def require_admin(request:Request):
    if not request.state.user.get('is_admin'):raise HTTPException(403,'관리자만 사용할 수 있습니다.')
    return request.state.user

router=APIRouter(prefix='/api/admin',dependencies=[Depends(require_admin)])
OWNER='u.full_name,u.employee_id,COALESCE(t.name,\'\') AS team_name,COALESCE(r.name,\'\') AS role_name'
JOINS=' JOIN platform.users u ON u.user_id=x.user_id LEFT JOIN platform.teams t ON t.team_id=u.team_id LEFT JOIN platform.roles r ON r.role_id=u.role_id '


def period(start:date|None,end:date|None):
    today=datetime.now(ZoneInfo('Asia/Seoul')).date()
    start=start or today-timedelta(days=29);end=end or today
    if end<start or (end-start).days>365:raise HTTPException(422,'조회 기간은 시작일 이후 최대 366일로 선택해 주세요.')
    tz=ZoneInfo('Asia/Seoul')
    return datetime.combine(start,time.min,tz),datetime.combine(end+timedelta(days=1),time.min,tz)


def audit(db,actor,target,action,reason,before,after):
    # Serialize datetimes consistently; never include session tokens or file paths.
    import json
    clean=lambda value:Jsonb(json.loads(json.dumps(value,default=str)))
    db.execute('INSERT INTO wiavoice.admin_audit(actor_id,target_id,action,reason,before_state,after_state) VALUES(%s,%s,%s,%s,%s,%s)',
               (actor,target,action,reason,clean(before),clean(after)))


@router.get('/options')
def options():
    with database() as db:
        users=db.execute('''SELECT u.user_id,u.full_name,u.employee_id,COALESCE(t.name,'') AS team_name
            FROM platform.users u LEFT JOIN platform.teams t ON t.team_id=u.team_id
            WHERE EXISTS(SELECT 1 FROM wiavoice.generation_runs g WHERE g.user_id=u.user_id)
            OR EXISTS(SELECT 1 FROM wiavoice.voices v WHERE v.user_id=u.user_id)
            OR EXISTS(SELECT 1 FROM wiavoice.market_voices m WHERE m.user_id=u.user_id)
            OR EXISTS(SELECT 1 FROM wiavoice.merge_action a WHERE a.user_id=u.user_id)
            ORDER BY u.full_name,u.employee_id''').fetchall()
        tracking=db.execute("SELECT value FROM wiavoice.admin_metadata WHERE key='tracking_started_at'").fetchone()
    return {'users':users,'tracking_started_at':tracking['value']}


@router.get('/operations')
def operations(request:Request,start:date|None=None,end:date|None=None,user_id:str=Query('',max_length=128),model:Literal['','qwen','fish','higgs']=''):
    begin,finish=period(start,end)
    where='created_at>=%s AND created_at<%s AND (%s=\'\' OR user_id=%s) AND (%s=\'\' OR model=%s)'
    params=(begin,finish,user_id,user_id,model,model)
    with database() as db:
        summary=db.execute('''SELECT count(*) AS total,count(*) FILTER(WHERE status='completed') AS completed,
            count(*) FILTER(WHERE status='failed') AS failed,count(*) FILTER(WHERE status='cancelled') AS cancelled,
            count(*) FILTER(WHERE status IN ('queued','loading','generating')) AS pending,
            count(DISTINCT user_id) AS users,COALESCE(sum(audio_seconds) FILTER(WHERE status='completed'),0) AS audio_seconds,
            avg(generation_seconds) FILTER(WHERE status='completed') AS average_seconds FROM wiavoice.generation_runs WHERE '''+where,params).fetchone()
        daily=db.execute("SELECT (created_at AT TIME ZONE 'Asia/Seoul')::date AS day,count(*) AS total,count(*) FILTER(WHERE status='completed') AS completed,count(*) FILTER(WHERE status='failed') AS failed FROM wiavoice.generation_runs WHERE "+where+' GROUP BY day ORDER BY day',params).fetchall()
        models=db.execute("SELECT model,count(*) AS total,count(*) FILTER(WHERE status='completed') AS completed,avg(generation_seconds) FILTER(WHERE status='completed') AS average_seconds,COALESCE(sum(audio_seconds),0) AS audio_seconds FROM wiavoice.generation_runs WHERE "+where+' GROUP BY model ORDER BY total DESC',params).fetchall()
        activity=db.execute('''SELECT u.user_id,u.full_name,u.employee_id,COALESCE(t.name,'') AS team_name,
            count(*) AS total,count(*) FILTER(WHERE g.status='completed') AS completed,
            COALESCE(sum(g.audio_seconds),0) AS audio_seconds,max(g.created_at) AS last_used
            FROM (SELECT * FROM wiavoice.generation_runs WHERE '''+where+''') g
            JOIN platform.users u ON u.user_id=g.user_id LEFT JOIN platform.teams t ON t.team_id=u.team_id
            GROUP BY u.user_id,u.full_name,u.employee_id,t.name ORDER BY total DESC,u.full_name LIMIT 100''',params).fetchall()
        errors=db.execute('SELECT g.*,u.full_name FROM (SELECT * FROM wiavoice.generation_runs WHERE '+where+
                         " AND status='failed' ORDER BY created_at DESC LIMIT 20) g JOIN platform.users u ON u.user_id=g.user_id ORDER BY g.created_at DESC",params).fetchall()
        snapshot=db.execute('''SELECT (SELECT count(*) FROM wiavoice.voices) AS saved,
            (SELECT count(*) FROM wiavoice.market_voices WHERE deleted_at IS NULL AND hidden_at IS NULL) AS published,
            (SELECT count(*) FROM wiavoice.market_voices WHERE deleted_at IS NULL AND hidden_at IS NOT NULL) AS hidden,
            (SELECT COALESCE(sum(download_count),0) FROM wiavoice.market_voices) AS downloads''').fetchone()
        downloads=db.execute("SELECT count(*) AS total FROM wiavoice.download_events WHERE created_at>=%s AND created_at<%s AND (%s='' OR user_id=%s)",(begin,finish,user_id,user_id)).fetchone()['total']
    engine=request.app.state.engine
    return {'summary':summary,'daily':daily,'models':models,'activity':activity,'errors':errors,'snapshot':snapshot,
            'period_downloads':downloads,'live':{'state':engine.state,'model':engine.model,'queued':request.app.state.queue.qsize()}}


@router.get('/voices')
def voices(kind:Literal['generation','saved','merge']='generation',start:date|None=None,end:date|None=None,
           q:str=Query('',max_length=100),user_id:str=Query('',max_length=128),model:Literal['','qwen','fish','higgs','merged']='',
           status:Literal['','queued','loading','generating','running','completed','failed','cancelled']='',offset:int=Query(0,ge=0)):
    begin,finish=period(start,end)
    table,key,title={'generation':('generation_runs','job_id','voice'),'saved':('voices','voice_id','name'),'merge':('merge_action','action_id','name')}[kind]
    where="x.created_at>=%s AND x.created_at<%s AND (%s='' OR x.user_id=%s) AND (%s='' OR strpos(lower(u.full_name||' '||u.employee_id||' '||COALESCE(t.name,'')||' '||x."+title+"),lower(%s))>0)"
    params=[begin,finish,user_id,user_id,q,q]
    if kind!='merge':where+=" AND (%s='' OR x.model=%s)";params.extend([model,model])
    if kind!='saved':where+=" AND (%s='' OR x.status=%s)";params.extend([status,status])
    source=' FROM wiavoice.'+table+' x'+JOINS+' WHERE '+where
    fields={'generation':'x.*','saved':'x.voice_id,x.name,x.user_id,x.model,x.speaker,x.emotion,x.duration_seconds,x.file_size,x.created_at',
            'merge':'x.action_id,x.name,x.user_id,x.status,x.progress,x.result_voice_id,x.error_message,x.created_at,x.completed_at,jsonb_array_length(x.input_voices) AS source_count'}[kind]
    with database() as db:
        total=db.execute('SELECT count(*) AS total'+source,params).fetchone()['total']
        rows=db.execute('SELECT '+fields+','+OWNER+source+' ORDER BY x.created_at DESC,x.'+key+' LIMIT 20 OFFSET %s',(*params,offset)).fetchall()
    for row in rows:row.pop('text',None)
    return {'items':rows,'total':total}


@router.get('/voices/{kind}/{key}')
def voice_detail(kind:Literal['generation','saved','merge'],key:str):
    table,id_field={'generation':('generation_runs','job_id'),'saved':('voices','voice_id'),'merge':('merge_action','action_id')}[kind]
    with database() as db:row=db.execute('SELECT x.*,'+OWNER+' FROM wiavoice.'+table+' x'+JOINS+' WHERE x.'+id_field+'=%s',(key,)).fetchone()
    if not row:raise HTTPException(404,'기록을 찾을 수 없습니다.')
    row.pop('audio_sha256',None);row.pop('request_hash',None)
    return row


@router.get('/saved/{key}/audio')
def saved_audio(key:str,request:Request):
    with database() as db:
        row=db.execute('SELECT * FROM wiavoice.voices WHERE voice_id=%s',(key,)).fetchone()
        if not row:raise HTTPException(404,'음성을 찾을 수 없습니다.')
        path=library.voice_directory(request.app.state.data,row['user_id'],key)/'audio.wav'
        if not path.is_file():raise HTTPException(404,'음성 파일이 없습니다.')
    return FileResponse(path,media_type='audio/wav')


@router.get('/marketplace')
def market_list(q:str=Query('',max_length=100),state:Literal['all','published','hidden','deleted']='all',
                user_id:str=Query('',max_length=128),offset:int=Query(0,ge=0)):
    where="(%s='' OR x.user_id=%s) AND (%s='' OR strpos(lower(x.name||' '||x.description||' '||u.full_name||' '||COALESCE(t.name,'')),lower(%s))>0)"
    params=[user_id,user_id,q,q]
    if state=='published':where+=' AND x.deleted_at IS NULL AND x.hidden_at IS NULL'
    elif state=='hidden':where+=' AND x.deleted_at IS NULL AND x.hidden_at IS NOT NULL'
    elif state=='deleted':where+=' AND x.deleted_at IS NOT NULL'
    source=' FROM wiavoice.market_voices x'+JOINS+' WHERE '+where
    with database() as db:
        total=db.execute('SELECT count(*) AS total'+source,params).fetchone()['total']
        rows=db.execute('SELECT x.voice_id,x.name,x.description,x.gender,x.user_id,x.created_at,x.updated_at,x.hidden_at,x.deleted_at,x.download_count,x.sample_seconds,'+OWNER+
            ',(SELECT count(*) FROM wiavoice.market_favorites f WHERE f.voice_id=x.voice_id) AS favorites'+source+' ORDER BY x.created_at DESC,x.voice_id LIMIT 20 OFFSET %s',(*params,offset)).fetchall()
    return {'items':rows,'total':total}


@router.get('/marketplace/{key}')
def market_detail(key:str):
    with database() as db:
        row=db.execute('SELECT x.*,'+OWNER+' FROM wiavoice.market_voices x'+JOINS+' WHERE x.voice_id=%s',(key,)).fetchone()
        if not row:raise HTTPException(404,'목소리를 찾을 수 없습니다.')
        history=db.execute('''SELECT a.audit_id,a.action,a.reason,a.before_state,a.after_state,a.created_at,u.full_name AS actor_name
            FROM wiavoice.admin_audit a LEFT JOIN platform.users u ON u.user_id=a.actor_id
            WHERE target_id=%s ORDER BY a.created_at DESC LIMIT 100''',(key,)).fetchall()
    return {'voice':row,'history':history}


@router.get('/marketplace/{key}/sample')
def sample(key:str,request:Request):
    with database() as db:row=db.execute('SELECT voice_id FROM wiavoice.market_voices WHERE voice_id=%s AND deleted_at IS NULL',(key,)).fetchone()
    if not row:raise HTTPException(404,'음성을 찾을 수 없습니다.')
    path=marketplace.directory(request.app.state.data,key)/'sample.wav'
    if not path.is_file():raise HTTPException(404,'샘플 파일이 없습니다.')
    return FileResponse(path,media_type='audio/wav')


class MarketChange(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    action:Literal['edit','hide','publish','delete']
    reason:str=Field(min_length=1,max_length=500)
    name:str|None=Field(default=None,min_length=1,max_length=100)
    description:str|None=Field(default=None,min_length=1,max_length=300)
    gender:Literal['male','female']|None=None


@router.post('/marketplace/{key}/actions')
def change_market(key:str,body:MarketChange,request:Request):
    with database() as db:
        row=db.execute('SELECT * FROM wiavoice.market_voices WHERE voice_id=%s AND deleted_at IS NULL FOR UPDATE',(key,)).fetchone()
        if not row:raise HTTPException(404,'등록된 목소리를 찾을 수 없습니다.')
        before={k:row[k] for k in ['name','description','gender','hidden_at','deleted_at']}
        if body.action=='edit':
            if body.name is None or body.description is None or body.gender is None:raise HTTPException(422,'이름·소개·성별을 입력해 주세요.')
            db.execute('UPDATE wiavoice.market_voices SET name=%s,description=%s,gender=%s,updated_at=now() WHERE voice_id=%s',(body.name,body.description,body.gender,key))
        elif body.action=='hide':db.execute('UPDATE wiavoice.market_voices SET hidden_at=COALESCE(hidden_at,now()),updated_at=now() WHERE voice_id=%s',(key,))
        elif body.action=='publish':db.execute('UPDATE wiavoice.market_voices SET hidden_at=NULL,updated_at=now() WHERE voice_id=%s',(key,))
        else:
            db.execute('UPDATE wiavoice.market_voices SET deleted_at=now(),updated_at=now() WHERE voice_id=%s',(key,))
            db.execute('DELETE FROM wiavoice.market_favorites WHERE voice_id=%s',(key,))
        after=db.execute('SELECT name,description,gender,hidden_at,deleted_at FROM wiavoice.market_voices WHERE voice_id=%s',(key,)).fetchone()
        audit(db,request.state.user['user_id'],key,body.action,body.reason,before,dict(after))
    if body.action=='delete':shutil.rmtree(marketplace.directory(request.app.state.data,key),ignore_errors=True)
    return {'ok':True}
