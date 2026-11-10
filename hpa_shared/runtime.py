import os


def prepare(module):
    os.environ["DJANGO_SETTINGS_MODULE"] = module
    import django
    django.setup()
    from django.conf import settings
    if settings.CLOUD_ROLE == "guest":
        return  # The restricted public role never creates tables on the shared project.
    from django.core.management import call_command
    call_command("migrate", interactive=False, verbosity=0)


def serve(host, port, label):
    from django.core.servers.basehttp import ThreadedWSGIServer, WSGIRequestHandler
    from django.core.wsgi import get_wsgi_application
    with ThreadedWSGIServer((host, port), WSGIRequestHandler) as server:
        server.set_app(get_wsgi_application())
        print(f"{label} — http://{host}:{server.server_port}", flush=True)
        server.serve_forever()
