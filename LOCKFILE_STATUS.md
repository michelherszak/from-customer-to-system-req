# Lockfile status

KuSys pins every direct application dependency to an exact version. The release also contains deterministic lock-generation and verification scripts:

- `ops/release/lock_backend.sh` → `backend/uv.lock`
- `ops/release/lock_frontend.sh` → `apps/frontend/package-lock.json`, followed by typecheck and production build

The execution sandbox used to assemble this archive could not reach npm package registries, and it does not contain a Python 3.14 interpreter usable by `uv`. Therefore a truthful resolved transitive frontend lock and a Python-3.14-resolved `uv.lock` could not be generated here. They are intentionally **not fabricated**.

Before a production release, run:

```bash
./kusys locks
./kusys verify
```

and commit the generated lockfiles. Docker images are exactly tagged; production operators should additionally resolve those tags to registry digests and record the digests in the release manifest.
