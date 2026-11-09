"""Run a single Hpa Rating service on loopback; only the guest is behind HTTPS."""
import argparse
import os


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=("guest", "admin"))
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    os.environ["HPA_ENV"] = "production"
    guest = args.service == "guest"
    if guest:
        from app.launch import configure
        configure()
    else:
        from hpa_shared.runtime import prepare
        prepare("administration.settings")
        from administration.state import private_store
        from hpa_shared.registry import registry
        private_store()
        registry()

    from django.core.wsgi import get_wsgi_application
    from waitress import create_server
    # Caddy is on the same machine and replaces both forwarded headers.
    # Never trust a forwarded address or protocol on the private console.
    proxy = {"trusted_proxy": "127.0.0.1", "trusted_proxy_count": 1,
             "trusted_proxy_headers": {"x-forwarded-for", "x-forwarded-proto"}} if guest else {}
    server = create_server(get_wsgi_application(), host="127.0.0.1",
                           port=args.port if args.port is not None else (18100 if guest else 18101),
                           threads=4, connection_limit=100, channel_timeout=90,
                           max_request_body_size=(64 if guest else 1) * 1024 * 1024,
                           expose_tracebacks=False, **proxy)
    print(f"{args.service}: http://127.0.0.1:{server.effective_port}", flush=True)
    try:
        server.run()
    finally:
        server.close()


if __name__ == "__main__":
    main()
