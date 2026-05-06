# RelayMD: Storage Module Internals

See [Storage Layout for Checkpoints and Inputs](storage-layout.md) for the actual S3 layout schema.

## Component

`relaymd-storage` is a shared Python package in `packages/relaymd-core/src/relaymd/storage/`. It exposes one class: `StorageClient`.

## Providers

Storage mode is selected by `storage_provider` in config:

1. `cloudflare_backblaze` (default)
2. `purdue`

It uses `boto3` synchronously, but wrapped internally so that consumers of `StorageClient` just call `client.upload_file(local_path, b2_key)` and `client.download_file(b2_key, local_path)`.

## Uploads

Uses `boto3.client("s3").upload_file(...)` with multipart threshold and concurrency. Writes always go directly to the B2 endpoint `https://s3.us-east-00[x].backblazeb2.com`.

## Downloads

- `cloudflare_backblaze`: uses `httpx.Client.stream(...)` to fetch from the Cloudflare Worker proxy (`https://relaymd-proxy.<user>.workers.dev`) using `DOWNLOAD_BEARER_TOKEN`.
- `purdue`: uses direct S3 download (`boto3` `download_file`) from `PURDUE_S3_ENDPOINT` (for example `https://s3.rcac.purdue.edu`).

Using `boto3.client("s3").download_file` would incur B2 egress fees and bypass the Cloudflare Bandwidth Alliance. The dual-endpoint setup is what makes checkpoints free.

## S3 Protocol Compatibility

Backblaze B2 supports the standard AWS S3 REST API. `boto3` thinks it is talking to S3. The region is ignored `us-east-1` placeholder, authentication relies on AWS Signature v4 compatibility, using `KEY_ID` as AWS Access Key and `APPLICATION_KEY` as Secret Key.
