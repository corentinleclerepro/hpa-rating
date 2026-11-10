"""Exercise a disposable local PostgreSQL instance, including chunks, isolation and physical deletion."""
import hashlib
import hmac
from io import BytesIO
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from zipfile import ZipFile

import psycopg
from psycopg import sql

SITE = "hpa-rating.campcompagnon.fr"
ROOT = Path(__file__).resolve().parents[1]


def run(port, password):
    # The caller owns a fresh cluster. Never accept a remote host or a production connection string.
    default = dict(host="127.0.0.1", port=port, dbname="postgres", password=password)
    with psycopg.connect(user="postgres", **default, autocommit=True) as setup:
        if setup.execute("SELECT to_regnamespace('hpa_rating')").fetchone()[0] is not None:
            raise RuntimeError("Cette recette exige une base de test neuve.")
        setup.execute("CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role")
        setup.execute((ROOT/"deploy"/"supabase"/"schema.sql").read_text(encoding="utf8"))
        for change in ("access_requests.sql", "web_admin.sql"):
            setup.execute((ROOT/"deploy"/"supabase"/change).read_text(encoding="utf8"))
        for role in ("hpa_rating_guest", "hpa_rating_admin", "hpa_rating_webadmin"):
            setup.execute(sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(role),sql.Literal(password)))
    invite_key = secrets.token_urlsafe(48)
    os.environ.update(HPA_SUPABASE_ROLE="guest",HPA_GUEST_ORIGIN="https://"+SITE,HPA_INVITATION_KEY=invite_key,
                      HPA_CLOUD_APP_KEY=secrets.token_urlsafe(48),HPA_DB_PASSWORD=password,
                      HPA_DB_HOST="test.pooler.supabase.com",HPA_SUPABASE_PROJECT="a"*20,
                      DJANGO_SETTINGS_MODULE="app.settings")
    sys.path.insert(0, str(ROOT))
    from app import settings as app_settings
    app_settings.DATABASES["default"].update(HOST="127.0.0.1",PORT=port,USER="hpa_rating_guest",
                                            TIME_ZONE="GMT",OPTIONS={"sslmode":"disable"})
    import django
    django.setup()
    from django.test import Client
    from django.db import connections
    from hpa_shared.registry import canonical

    visitor = Client(enforce_csrf_checks=True, HTTP_HOST=SITE)
    assert visitor.get("/",secure=True).status_code == 200
    form = {"camping":"Test postal","email":"test@example.test","csrfmiddlewaretoken":visitor.cookies["hpa_csrf"].value}
    for _ in range(2):
        assert visitor.post("/demande-acces",form,secure=True,HTTP_ORIGIN="https://"+SITE).status_code == 303
    subprocess.run([sys.executable,"-B",str(ROOT/"tests"/"recette_admin_postgres.py")],check=True,
                   env={**os.environ,"HPA_TEST_PG_PORT":str(port),"HPA_CLOUD_APP_KEY":secrets.token_urlsafe(48)})
    with psycopg.connect(user="hpa_rating_guest",**default) as guest_sql:
        assert not guest_sql.execute("SELECT has_table_privilege(current_user,'hpa_rating.access_requests','SELECT')").fetchone()[0]
        assert not guest_sql.execute("SELECT has_schema_privilege(current_user,'hpa_rating_staff','USAGE')").fetchone()[0]
    with psycopg.connect(user="hpa_rating_webadmin",**default) as staff_sql:
        assert not staff_sql.execute("SELECT has_table_privilege(current_user,'hpa_rating.file_chunks','SELECT')").fetchone()[0]
        assert not staff_sql.execute("SELECT has_table_privilege(current_user,'hpa_rating.django_session','SELECT')").fetchone()[0]

    def api(client, method, path, data=None, expected=200, binary=False):
        headers={"HTTP_HOST":SITE, "HTTP_ORIGIN":"https://"+SITE,
                 "HTTP_X_CSRFTOKEN":client.cookies["hpa_csrf"].value if "hpa_csrf" in client.cookies else ""}
        reply=client.generic(method,path, (data if binary else json.dumps(data).encode()) if data is not None else b"",
                             secure=True, content_type="application/octet-stream" if binary else "application/json",**headers)
        body = b"".join(reply.streaming_content) if reply.streaming else reply.content
        assert reply.status_code == expected, (method,path,reply.status_code,expected,body[:160])
        return json.loads(body) if "application/json" in reply.get("Content-Type","") else body

    with psycopg.connect(user="hpa_rating_admin", **default, autocommit=True) as console:
        assert not console.execute("SELECT has_table_privilege(current_user,'hpa_rating.file_chunks','SELECT')").fetchone()[0]
        users=[]
        for name in ("alpha","beta"):
            code = secrets.token_urlsafe(24)
            fingerprint = hmac.new(invite_key.encode(),("invite:"+canonical(code)).encode(),hashlib.sha256).hexdigest()
            console.execute("INSERT INTO guests(id,label,digest,created_at) VALUES(%s,%s,%s,'2026-01-01')",(name,name,fingerprint))
            visitor=Client(enforce_csrf_checks=True)
            api(visitor,"GET","/connexion")
            api(visitor,"POST","/api/login",{"code":code})
            users.append(visitor)
        a,b=users
        data=api(a,"POST","/api/audits/demo",{},201)
        aid=data["audit"]["id"]
        base="/api/audits/"+aid
        snapshot=api(a,"GET",base)
        assert snapshot["evidence_count"] == 3
        cid=snapshot["audit"]["workflow"]["allowed_ids"][0]
        transfer=base+"/items/"+cid+"/evidence/transfers"
        size=5*1024*1024+73
        # Use random bytes so a ZIP cannot hide a broken large-file download.
        contents=secrets.token_bytes(size)
        ticket=api(a,"POST",transfer,{"files":[{"name":"recette.pdf","size":size}]},201)
        key=ticket["files"][0]
        chunk=ticket["chunk_bytes"]
        end=transfer+"/complete"
        api(b,"PUT",transfer+"/"+key+"/0",contents[:chunk],404,True)
        api(a,"PUT",transfer+"/"+key+"/0",contents[:chunk],200,True)
        api(a,"POST",end,{"files":[key]},409)
        api(a,"PUT",transfer+"/"+key+"/0",b"z"*chunk,409,True)
        for start in range(0,size,chunk):
            api(a,"PUT",transfer+"/"+key+"/"+str(start//chunk),contents[start:start+chunk],200,True)
        created=api(a,"POST",end,{"files":[key]},201)["evidences"][0]
        assert api(a,"POST",end,{"files":[key]},201)["evidences"][0]["id"] == created["id"]
        download=base+"/evidence/"+created["id"]+"/file"
        connections.close_all()
        assert api(a,"GET",download)==contents
        api(b,"GET",download,expected=404)
        clone=api(a,"POST",base+"/clone",{"name":"Copie de recette"},201)["audit"]
        clone_base="/api/audits/"+clone["id"]
        api(a,"DELETE",base,{"confirm_name":data["audit"]["name"]})
        copy=api(a,"GET",clone_base)
        file=next(e for e in copy["evidences"] if e["original_name"]=="recette.pdf")
        assert api(a,"GET",clone_base+"/evidence/"+file["id"]+"/file")==contents
        flow=copy["audit"]["workflow"]
        for _ in range(200):
            if flow["current"]=="summary": break
            if flow["next_id"]:
                flow=api(a,"PUT",clone_base+"/items/"+flow["next_id"],{"status":"IN_PROGRESS","advance":True})["workflow"]
            else:
                flow=api(a,"POST",clone_base+"/review-proofs",{"reviewed":True})["workflow"]
        assert flow["current"]=="summary"
        exported=api(a,"GET",clone_base+"/export/zip")
        with ZipFile(BytesIO(exported)) as bundle:
            packed=next(n for n in bundle.namelist() if n.endswith("recette.pdf"))
            assert bundle.read(packed)==contents
        api(a,"DELETE",clone_base,{"confirm_name":"Copie de recette"})
        with psycopg.connect(user="hpa_rating_guest",**default) as reader:
            assert reader.execute("SELECT count(*) FROM file_chunks").fetchone()[0]==0
            assert reader.execute("SELECT count(*) FROM file_blobs").fetchone()[0]==0
        console.execute("UPDATE guests SET revoked=1,version=version+1 WHERE id='alpha'")
        api(a,"GET","/api/audits",expected=401)
    connections.close_all()
    print("PostgreSQL : deux invités, reprise 5 Mio, PDF privé, copie, ZIP, effacement des octets, révocation et console limitée : OK")
