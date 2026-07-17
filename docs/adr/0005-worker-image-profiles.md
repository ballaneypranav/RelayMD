# Worker image profiles

RelayMD jobs select stable, allowlisted worker-image profile keys rather than
raw container URIs. The initial profiles are `atom-openmm` (displayed as
AToM-OpenMM) and `gcncmcmd` (displayed as GCNCMC-MD). Operators map each
profile to a cluster-local SIF path or OCI/ORAS URI.

The legacy `relaymd-worker` image and SIF are compatibility aliases for
`atom-openmm` during the migration. New configuration uses explicit named
worker image sources.

The GCNCMC OpenMM environment input is committed under `images/gcncmcmd/`
(`openmm.yml` SHA-256:
`b649078b395dd0f801311e6e06dc12817c5d0a2aa9040e3a16a3fe30da9e86cc`).
GCNCMC-MD uses the public HTTPS GRAND source at
`https://github.com/essex-lab/grand.git`, pinned to the `v1.1.0` release
commit `f58784faeaaabbe054b306f7a474e0eaec5ff878`. Image builds must install
that exact revision and must not read the development checkout under `/scratch`.
