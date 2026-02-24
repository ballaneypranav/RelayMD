# Infrastructure Documentation

## Infisical Secrets Reference
The application securely provisions credentials and configuration variables dynamically from Infisical at runtime. The following secrets have been configured dynamically under `/RelayMD` in the `prod` environment:

- `B2_APPLICATION_KEY`
- `B2_APPLICATION_KEY_ID`
- `B2_APPLICATION_KEY_NAME`
- `B2_ENDPOINT`
- `BUCKET_NAME`
- `RELAYMD_API_TOKEN`
- `RELAYMD_ORCHESTRATOR_URL`
- `TAILSCALE_AUTH_KEY`
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`
- `DOWNLOAD_BEARER_TOKEN`

## Tailscale Networking Provisioning (W-165)

RelayMD workers and orchestrator communicate only over the Tailscale tailnet. Workers do not accept inbound traffic; they initiate outbound calls to the orchestrator on the private network.

### Provisioning Steps

1. Create or designate a Tailscale account for RelayMD ownership and billing.
2. Install Tailscale on the orchestrator host with the official install script:
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   ```
3. Authenticate the orchestrator as a persistent (non-ephemeral) node:
   ```bash
   sudo tailscale up
   ```
4. Enable MagicDNS in the Tailscale admin console.
5. Record the orchestrator stable MagicDNS hostname and set:
   - `RELAYMD_ORCHESTRATOR_URL = http://<orchestrator-magicdns-hostname>:8000`
6. Generate a reusable **ephemeral** auth key in Tailscale admin (use `tag:relaymd-worker` when ACL tags are enabled).
7. Store the key and orchestrator URL in Infisical (`/RelayMD`, `prod`):
   - `TAILSCALE_AUTH_KEY`
   - `RELAYMD_ORCHESTRATOR_URL`

### Connectivity Verification

Run from a test node joined with the ephemeral key:

```bash
sudo tailscale up --auth-key "$TAILSCALE_AUTH_KEY"
curl -i http://<orchestrator-magicdns-hostname>:8000/healthz
```

Expected result:
- HTTP status `200 OK` from `/healthz`.

### ACL Guidance (Optional)

If ACLs are enabled, restrict worker nodes to orchestrator-only access and block worker-to-worker communication.
