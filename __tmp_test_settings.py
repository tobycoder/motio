from app import create_app
from flask import g
from app.tenant_registry.client import LegacyTenant

app = create_app()
app.testing = True

with app.test_client() as client:
    with app.test_request_context('/', headers={'Host': '127.0.0.1'}):
        g.tenant_meta = LegacyTenant(
            id='123',
            slug='test-slug',
            naam='Test Tenant',
            settings={'application_roles': {'test': ['griffie']}},
            status='active',
            branding={},
            phrasing={},
            contact_email=None,
        )
        g.tenant = g.tenant_meta
        response = client.get('/settings/toepassingen', headers={'Host': '127.0.0.1'})
        print('status', response.status_code)
        print(response.data[:120])
