import os,sys,tempfile
from pathlib import Path
# Tests are intended to run with pytest and the backend dependencies installed.
import pytest
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app

@pytest.fixture()
def client(tmp_path,monkeypatch):
    app.DB_PATH=tmp_path/'test.db'
    app.SESSIONS.clear()
    app.init_db()
    with app.conn() as c:
        c.execute("INSERT INTO users(id,username,password_hash,role,name,status) VALUES(?,?,?,?,?,?)",('u1','admin',app.hash_password('admin123'),'admin','Admin','Active'))
    with TestClient(app.app) as c: yield c

def test_health(client):
    r=client.get('/api/health'); assert r.status_code==200 and r.json()['database'] is True

def test_login_and_me(client):
    r=client.post('/api/auth/login',json={'username':'admin','password':'admin123','role':'admin'}); assert r.status_code==200
    assert client.get('/api/auth/me').json()['user']['username']=='admin'

def test_bootstrap_requires_auth(client):
    assert client.get('/api/bootstrap').status_code==401
