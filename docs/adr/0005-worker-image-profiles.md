# Worker image profiles

RelayMD jobs select stable, allowlisted worker-image profile keys rather than
raw container URIs. The initial profiles are `atom-openmm` (displayed as
AToM-OpenMM) and `gcncmcmd` (displayed as GCNCMC-MD). Operators map each
profile to a cluster-local SIF path or OCI/ORAS URI.

Only the two profile-specific OCI and SIF artifacts are published. Deployments
use explicit named profiles, so future worker environments can be added without
accepting raw image inputs. Upgrades from a database created before image keys
must reset that database; RelayMD does not perform an in-place backfill.

The GCNCMC OpenMM environment input is committed under `images/gcncmcmd/`
(`openmm.yml` SHA-256:
`262b32995509d88cca1b590fb9419fe8b381a240680954a128dbef9266a5c5e5`).
GCNCMC-MD uses the public HTTPS GRAND source at
`https://github.com/essex-lab/grand.git`, pinned to the `v1.1.0` release
commit `f58784faeaaabbe054b306f7a474e0eaec5ff878`. Image builds must install
that exact revision and must not read the development checkout under `/scratch`.
