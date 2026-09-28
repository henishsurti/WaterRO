from __future__ import annotations

import hashlib, hmac, json, os, secrets, sqlite3, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import Cookie, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field

ROOT=Path(__file__).resolve().parents[1]
DB_PATH=Path(os.getenv('AQUAFLOW_DB', ROOT/'aquaflow.db'))
SCHEMA_PATH=ROOT/'database.sql'
APP_VERSION='9.0.0'
SESSION_TTL=int(os.getenv('AQUAFLOW_SESSION_TTL','28800'))
SECRET=os.getenv('AQUAFLOW_SECRET','change-this-local-secret')
COOKIE_SECURE=os.getenv('AQUAFLOW_COOKIE_SECURE','0')=='1'

@asynccontextmanager
async def lifespan(_app):
    init_db()
    yield

app=FastAPI(title='AquaFlow API',version=APP_VERSION,docs_url='/api/docs',redoc_url='/api/redoc',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=[o.strip() for o in os.getenv('AQUAFLOW_CORS','').split(',') if o.strip()],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])

class LoginIn(BaseModel):
    username:str=Field(min_length=1,max_length=80)
    password:str=Field(min_length=1,max_length=200)
    role:str=Field(pattern='^(admin|technician)$')
class SyncIn(BaseModel):
    data:dict[str,Any]

SESSIONS:dict[str,dict[str,Any]]={}

def conn():
    c=sqlite3.connect(DB_PATH,check_same_thread=False)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c

def init_db():
    with conn() as c:
        c.executescript(SCHEMA_PATH.read_text(encoding='utf-8'))
        row=c.execute('SELECT payload_json FROM app_state WHERE id=1').fetchone()
        if not row:
            # State is initialized by the first authenticated sync; relational tables are already seeded.
            c.execute("INSERT OR IGNORE INTO app_state(id,version,payload_json) VALUES(1,?,?)",(APP_VERSION,json.dumps({})))

def hash_password(password:str,salt:bytes|None=None)->str:
    salt=salt or secrets.token_bytes(16)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,210_000)
    return f'pbkdf2_sha256$210000${salt.hex()}${digest.hex()}'

def verify_password(password:str,stored:str)->bool:
    try:
        alg,iters,salt_hex,digest=stored.split('$',3)
        if alg!='pbkdf2_sha256': return False
        actual=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt_hex),int(iters)).hex()
        return hmac.compare_digest(actual,digest)
    except Exception:return False

def legacy_sha(password:str)->str:return hashlib.sha256(password.encode()).hexdigest()

def row_to_dict(r):return dict(r) if r else None

def public_user(r):
    return {'id':r['id'],'username':r['username'],'role':r['role'],'technician_id':r['technician_id'],'name':r['name'],'status':r['status']}

def auth(request:Request, csrf:bool=False):
    sid=request.cookies.get('af_session'); s=SESSIONS.get(sid or '')
    if not s or s['expires']<time.time(): raise HTTPException(401,'Authentication required')
    if csrf:
        token=request.headers.get('X-CSRF-Token','')
        if not token or not hmac.compare_digest(token,s['csrf']): raise HTTPException(403,'Invalid CSRF token')
    return s

def json_state_from_db(c):
    # Return frontend-compatible camelCase state while keeping relational storage authoritative.
    def rows(q,args=()): return [dict(x) for x in c.execute(q,args).fetchall()]
    customers=[]
    for x in rows('SELECT * FROM customers'):
        customers.append({**x,'altMobile':x.pop('alt_mobile'),'customerType':x.pop('customer_type'),'waterRoType':x.pop('water_ro_type'),'installDate':x.pop('install_date'),'installBy':x.pop('install_by'),'dueAmcDate':x.pop('due_amc_date'),'createdAt':x.pop('created_at'),'updatedAt':x.pop('updated_at')})
    ros=[]
    for x in rows('SELECT * FROM ro_machines'):
        ros.append({**x,'customerId':x.pop('customer_id'),'roType':x.pop('ro_type'),'serviceFrequency':x.pop('service_frequency'),'lastServiceDate':x.pop('last_service_date'),'nextServiceDate':x.pop('next_service_date'),'warrantyEnd':x.pop('warranty_end'),'purchaseDate':x.pop('purchase_date'),'installDate':x.pop('install_date'),'createdAt':x.pop('created_at'),'updatedAt':x.pop('updated_at')})
    amcs=[]
    for x in rows('SELECT * FROM amcs'):
        amcs.append({**x,'customerId':x.pop('customer_id'),'roId':x.pop('ro_id'),'startDate':x.pop('start_date'),'endDate':x.pop('end_date'),'paymentStatus':x.pop('payment_status'),'servicesIncluded':x.pop('services_included'),'servicesUsed':x.pop('services_used'),'createdAt':x.pop('created_at'),'updatedAt':x.pop('updated_at')})
    techs=[]
    for x in rows('SELECT * FROM technicians'):
        techs.append({**x,'createdAt':x.pop('created_at'),'updatedAt':x.pop('updated_at')})
    services=[]
    for x in rows('SELECT * FROM services'):
        sid=x['id']; parts=rows('SELECT name,quantity AS qty,unit_cost AS cost FROM service_parts WHERE service_id=?',(sid,))
        services.append({**x,'customerId':x.pop('customer_id'),'roId':x.pop('ro_id'),'technicianId':x.pop('technician_id'),'requestDate':x.pop('request_date'),'scheduledDate':x.pop('scheduled_date'),'dueDate':x.pop('due_date'),'partsUsed':parts,'laborCost':x.pop('labor_cost'),'partsCost':x.pop('parts_cost'),'additionalCharges':x.pop('additional_charges'),'discount':x.pop('discount'),'totalAmount':x.pop('total_amount'),'paymentStatus':x.pop('payment_status'),'paymentMode':x.pop('payment_mode'),'completedAt':x.pop('completed_at'),'createdAt':x.pop('created_at'),'updatedAt':x.pop('updated_at')})
    users=[]
    for x in rows('SELECT id,username,role,technician_id,name,status,created_at AS createdAt,updated_at AS updatedAt FROM users'):
        users.append(x)
    settings={r['key']:r['value'] for r in c.execute('SELECT key,value FROM settings').fetchall()}
    for k in ('pushEnabled',):
        if k in settings:
            try: settings[k]=json.loads(settings[k])
            except: pass
    state={'customers':customers,'roMachines':ros,'amcs':amcs,'technicians':techs,'services':services,'users':users,'settings':settings,'notificationsRead':{},'notificationsDismissed':{},'meta':{'updatedAt':datetime.now(timezone.utc).isoformat(),'version':APP_VERSION}}
    return state

def sync_relational(c,data,user):
    # Replace operational relational dataset transactionally. IDs remain client-stable.
    # Password hashes are server-owned: a browser bootstrap never receives them, so a sync
    # must preserve existing hashes rather than silently resetting credentials.
    existing_hashes={r['id']:r['password_hash'] for r in c.execute('SELECT id,password_hash FROM users').fetchall()}
    existing_by_username={r['username']:r['password_hash'] for r in c.execute('SELECT username,password_hash FROM users').fetchall()}
    tables=[('service_parts','service_id'),('services','id'),('amcs','id'),('ro_machines','customer_id'),('customers','id'),('technicians','id'),('users','id'),('settings','key')]
    # We intentionally delete in FK-safe order, then insert validated rows.
    for t,_ in tables:
        c.execute(f'DELETE FROM {t}')
    for u in data.get('users',[]):
        uid=u.get('id'); username=u.get('username'); supplied=u.get('password')
        password_hash=existing_hashes.get(uid) or existing_by_username.get(username)
        if supplied: password_hash=hash_password(supplied)
        if not password_hash: password_hash=hash_password('change-me-before-production')
        c.execute('INSERT INTO users(id,username,password_hash,role,technician_id,name,status) VALUES(?,?,?,?,?,?,?)',(uid,username,password_hash,u.get('role','technician'),u.get('technicianId'),u.get('name',''),u.get('status','Active')))
    for t in data.get('technicians',[]):
        c.execute('INSERT INTO technicians(id,code,name,mobile,email,status) VALUES(?,?,?,?,?,?)',(t.get('id'),t.get('code') or ('TECH-'+str(t.get('id'))),t.get('name',''),t.get('mobile',''),t.get('email',''),t.get('status','Active')))
    for x in data.get('customers',[]):
        c.execute('INSERT INTO customers(id,code,name,mobile,alt_mobile,email,customer_type,water_ro_type,address,area,city,state,pincode,install_date,install_by,due_amc_date,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(x.get('id'),x.get('code'),x.get('name'),x.get('mobile'),x.get('altMobile'),x.get('email'),x.get('customerType') or x.get('type','Residential'),x.get('waterRoType'),x.get('address'),x.get('area'),x.get('city'),x.get('state'),x.get('pincode'),x.get('installDate'),x.get('installBy'),x.get('dueAmcDate'),x.get('status','Active')))
    for x in data.get('roMachines',[]):
        c.execute('INSERT INTO ro_machines(id,customer_id,ro_type,model,price,details,brand,serial,install_date,purchase_date,warranty_end,location,service_frequency,last_service_date,next_service_date,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(x.get('id'),x.get('customerId'),x.get('roType') or x.get('purificationType'),x.get('model',''),float(x.get('price') or 0),x.get('details'),x.get('brand'),x.get('serial'),x.get('installDate'),x.get('purchaseDate'),x.get('warrantyEnd'),x.get('location'),x.get('serviceFrequency'),x.get('lastServiceDate'),x.get('nextServiceDate'),x.get('status','Active')))
    for x in data.get('amcs',[]):
        c.execute('INSERT INTO amcs(id,customer_id,ro_id,plan,start_date,end_date,amount,payment_status,services_included,services_used,status,terms) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(x.get('id'),x.get('customerId'),x.get('roId'),x.get('plan',''),x.get('startDate'),x.get('endDate'),float(x.get('amount') or 0),x.get('paymentStatus','Pending'),int(x.get('servicesIncluded') or 0),int(x.get('servicesUsed') or 0),x.get('status','Draft'),x.get('terms')))
    for x in data.get('services',[]):
        c.execute('INSERT INTO services(id,customer_id,ro_id,technician_id,type,request_date,scheduled_date,due_date,priority,status,complaint,remarks,work_performed,parts_cost,labor_cost,additional_charges,discount,total_amount,payment_status,payment_mode,signature,completed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(x.get('id'),x.get('customerId'),x.get('roId'),x.get('technicianId'),x.get('type','Service'),x.get('requestDate'),x.get('scheduledDate'),x.get('dueDate'),x.get('priority','Normal'),x.get('status','New'),x.get('complaint'),x.get('remarks'),x.get('workPerformed'),float(x.get('partsCost') or 0),float(x.get('laborCost') or 0),float(x.get('additionalCharges') or 0),float(x.get('discount') or 0),float(x.get('totalAmount') or 0),x.get('paymentStatus','Pending'),x.get('paymentMode'),x.get('signature'),x.get('completedAt')))
        for p in x.get('partsUsed') or []:
            c.execute('INSERT INTO service_parts(service_id,name,quantity,unit_cost) VALUES(?,?,?,?)',(x.get('id'),p.get('name','Part'),float(p.get('qty') or p.get('quantity') or 1),float(p.get('cost') or p.get('unit_cost') or 0)))
    for k,v in (data.get('settings') or {}).items(): c.execute('INSERT INTO settings(key,value) VALUES(?,?)',(k,json.dumps(v) if isinstance(v,(dict,list,bool)) else str(v)))
    c.execute('INSERT INTO app_state(id,version,payload_json,updated_at) VALUES(1,?,?,CURRENT_TIMESTAMP) ON CONFLICT(id) DO UPDATE SET version=excluded.version,payload_json=excluded.payload_json,updated_at=CURRENT_TIMESTAMP',(APP_VERSION,json.dumps(data,separators=(',',':'))))
    c.execute('INSERT INTO audit_log(user_id,action,entity_type,details) VALUES(?,?,?,?)',(user['id'],'SYNC','system',json.dumps({'source':'web','version':APP_VERSION})))


@app.get('/api/health')
def health():
    with conn() as c: db_ok=c.execute('SELECT 1').fetchone()[0]==1
    return {'ok':True,'service':'aquaflow-api','version':APP_VERSION,'database':db_ok,'time':datetime.now(timezone.utc).isoformat()}

@app.post('/api/auth/login')
def login(body:LoginIn,response:Response):
    with conn() as c:
        r=c.execute('SELECT * FROM users WHERE username=? AND role=? AND status="Active"',(body.username.strip(),body.role)).fetchone()
    if not r: raise HTTPException(401,'Invalid user ID or password')
    stored=r['password_hash']
    # Support the seeded V8 SHA-256 hashes once, then transparently upgrade on success.
    ok=verify_password(body.password,stored) or hmac.compare_digest(legacy_sha(body.password),stored)
    if not ok: raise HTTPException(401,'Invalid user ID or password')
    if not stored.startswith('pbkdf2_sha256$'):
        with conn() as c:c.execute('UPDATE users SET password_hash=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(hash_password(body.password),r['id']))
    sid=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(24); SESSIONS[sid]={'user':public_user(r),'csrf':csrf,'expires':time.time()+SESSION_TTL}
    response.set_cookie('af_session',sid,max_age=SESSION_TTL,httponly=True,samesite='lax',secure=COOKIE_SECURE,path='/')
    response.set_cookie('af_csrf',csrf,max_age=SESSION_TTL,httponly=False,samesite='lax',secure=COOKIE_SECURE,path='/')
    return {'user':public_user(r),'csrf_token':csrf,'expires_in':SESSION_TTL}

@app.get('/api/auth/me')
def me(request:Request): return {'user':auth(request)['user']}

@app.post('/api/auth/logout')
def logout(request:Request,response:Response):
    sid=request.cookies.get('af_session'); SESSIONS.pop(sid or '',None); response.delete_cookie('af_session',path='/');response.delete_cookie('af_csrf',path='/');return {'ok':True}

@app.get('/api/bootstrap')
def bootstrap(request:Request):
    auth(request)
    with conn() as c: return {'data':json_state_from_db(c),'version':APP_VERSION}

@app.post('/api/sync')
def sync(body:SyncIn,request:Request):
    user=auth(request,csrf=True)['user']; data=body.data
    if not isinstance(data,dict): raise HTTPException(422,'data must be an object')
    # Basic integrity validation before transaction.
    cust={x.get('id') for x in data.get('customers',[])}; ros={x.get('id') for x in data.get('roMachines',[])}; tech={x.get('id') for x in data.get('technicians',[])}
    for x in data.get('roMachines',[]):
        if x.get('customerId') not in cust: raise HTTPException(422,'RO references an unknown customer')
    for x in data.get('services',[]):
        if x.get('customerId') not in cust: raise HTTPException(422,'Service references an unknown customer')
        if x.get('roId') and x.get('roId') not in ros: raise HTTPException(422,'Service references an unknown RO')
        if x.get('technicianId') and x.get('technicianId') not in tech: raise HTTPException(422,'Service references an unknown technician')
    with conn() as c:
        try: sync_relational(c,data,user)
        except sqlite3.IntegrityError as e: raise HTTPException(422,f'Database validation failed: {e}')
    return {'ok':True,'saved_at':datetime.now(timezone.utc).isoformat()}

@app.get('/api/audit')
def audit(request:Request,limit:int=100):
    user=auth(request); 
    if user['user']['role']!='admin': raise HTTPException(403,'Admin access required')
    with conn() as c: return {'items':[dict(x) for x in c.execute('SELECT * FROM audit_log ORDER BY id DESC LIMIT ?',(min(max(limit,1),500),)).fetchall()]}

@app.get('/api/docs-info')
def docs_info(): return {'openapi':'/api/openapi.json','docs':'/api/docs'}

@app.get('/')
def root(): return FileResponse(ROOT/'index.html')

@app.get('/{path:path}')
def static_files(path:str):
    p=(ROOT/path).resolve()
    if ROOT in p.parents and p.is_file(): return FileResponse(p)
    raise HTTPException(404,'Not found')
