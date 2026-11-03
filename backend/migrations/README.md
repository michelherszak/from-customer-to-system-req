# Alembic migrations

`versions/39b2fbb17b37_initial_schema.py` is the KuSys 1.0 bootstrap migration generated from `kusys.persistence.models.Base` with Alembic 1.20.0.

Verified during release assembly against a fresh SQLite compatibility database:

- `alembic upgrade head` succeeds;
- 52 application tables are created;
- Alembic head is `39b2fbb17b37`;
- the schema includes the current clarification answer field and all v1 aggregates.

Production/pilot uses PostgreSQL 18.6. For an existing installation, run `./kusys migrate`; that wrapper first creates and validates a full backup, then applies Alembic migrations.
