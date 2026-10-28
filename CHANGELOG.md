# Changelog

## [2.2.0](https://github.com/cwbitz/netbird-management-iac/compare/v2.1.0...v2.2.0) (2026-10-28)


### Features

* **monitoring:** make the Alloy scrape interval configurable ([#8](https://github.com/cwbitz/netbird-management-iac/issues/8)) ([4360faa](https://github.com/cwbitz/netbird-management-iac/commit/4360faa72a06ad3a3d28a2c2bb7aebfb3afb97a9))

## [2.1.0](https://github.com/cwbitz/netbird-management-iac/compare/v2.0.0...v2.1.0) (2026-10-27)


### Features

* **monitoring:** add blocklist importer, metric push and web UI machine account ([#6](https://github.com/cwbitz/netbird-management-iac/issues/6)) ([8637be3](https://github.com/cwbitz/netbird-management-iac/commit/8637be3a4c2489f345ce0ec49f0d89259b2e6f90))

## [2.0.0](https://github.com/cwbitz/netbird-management-iac/compare/v1.0.0...v2.0.0) (2026-10-23)


### ⚠ BREAKING CHANGES

* **monitoring:** rename the raw journal matches and default components off
* **connection:** consolidate the managed-host wiring on the iac account
* **ssh:** host_vars must set host_admin_username and the host_<id>_ssh_* paths in main.yml; the old vault_* keys are no longer read.
* **bootstrap:** bootstrap_password and bootstrap_sudo_nopasswd are no longer read; set vault_host_ansible_password instead.
* **firewall:** firewall_ssh_port, firewall_public_tcp_ports and firewall_public_udp_ports are role constants; host_vars overrides are ignored (an -e extra var still wins).
* **monitoring:** host_vars must use the new names; the old keys are no longer read.
* **agent:** netbird_dns_manage is no longer read; remove it from host_vars.
* **management:** an existing override of admin_service_user_access_token_expire_in is ignored; operators must rename it to admin_service_user_access_token_expire_days.
* **monitoring:** the host_monitoring_* variables are renamed and the overlay/CrowdSec toggles are removed; enabling monitoring now always joins the host to the overlay and requires a setup key.
* **management:** the external Docker volume holding Traefik's ACME certificates is renamed, so an existing deployment creates a fresh empty volume and re-issues certificates on the next deploy.
* **vault:** existing hosts must merge vault_managed.yml into vault.yml before the next deploy.
* **vault:** SSH identity vault variables were renamed to the `vault_host_*` scheme, so existing `vault.yml` files must move the old `vault_root_*` / `vault_ansible_*` / `vault_admin_*` keys to their new names, and

### Features

* **agent:** run the NetBird agent as a standalone role ([800d7c5](https://github.com/cwbitz/netbird-management-iac/commit/800d7c5e880bc9127a646c42c7d85536987b950c))
* **audit:** cross-check the example knobs against the schema ([a400fef](https://github.com/cwbitz/netbird-management-iac/commit/a400feffe8f8d2ee264769a9931ac91e2c7cbdd2))
* **bootstrap:** add the host timezone knob ([226853d](https://github.com/cwbitz/netbird-management-iac/commit/226853d92b47bc8e60772044c527a528cea8d908))
* **bootstrap:** bootstrap one named host explicitly ([49c5aee](https://github.com/cwbitz/netbird-management-iac/commit/49c5aee4c9723f708abafb69979fa6db92f98b05))
* **host-init:** scaffold comment-free host vars and register the host ([62dd749](https://github.com/cwbitz/netbird-management-iac/commit/62dd74915bf7d378672610013c9b4893ee11a7d7))
* **host-security:** add opt-in firewall and SSH hardening roles ([ba32e38](https://github.com/cwbitz/netbird-management-iac/commit/ba32e386f002ac632ce4af4576abb461f4e7514f))
* **lint:** reject real identifiers in tracked files ([fe8faac](https://github.com/cwbitz/netbird-management-iac/commit/fe8faac655f5003924e82ea3a51d93b48b82a41f))
* **make:** converge monitoring in the one-shot deploy ([de0d4df](https://github.com/cwbitz/netbird-management-iac/commit/de0d4dfcd304a25d9cfb05fdef4c69b21ca570d0))
* **make:** optionally refresh SSH host keys before connecting ([06b4894](https://github.com/cwbitz/netbird-management-iac/commit/06b489455ac6d24ae3e3de697ba79d3a82fcbeed))
* **monitoring:** add opt-in host monitoring and host security ([745ad18](https://github.com/cwbitz/netbird-management-iac/commit/745ad189bbe0fc7e16fd0e7e4e9fd39e1bb3759c))
* **monitoring:** converge disabled components off ([c0e17a7](https://github.com/cwbitz/netbird-management-iac/commit/c0e17a7fd3256fc944e729bbbdcb03f47ab84e12))
* **monitoring:** rework the host monitoring role ([ba8c0ae](https://github.com/cwbitz/netbird-management-iac/commit/ba8c0ae3ad08d67287cf0c876e7cad9444e86c93))
* **monitoring:** ship journal presets to Loki and bind exporters to the overlay ([98cf2e7](https://github.com/cwbitz/netbird-management-iac/commit/98cf2e7480665d9325684386e2e436a847a56afb))
* **server:** gate the deploy on the server log, not on TLS retries ([806b253](https://github.com/cwbitz/netbird-management-iac/commit/806b253bedaffe7358918c8e0b0d9fa872c9d976))
* **tenant:** retry the apply on transient network failures ([1bf09e4](https://github.com/cwbitz/netbird-management-iac/commit/1bf09e4956351b75dd3fa9da8cdbeebdebacce9d))
* **tenant:** validate the desired state before rendering ([15abaae](https://github.com/cwbitz/netbird-management-iac/commit/15abaaeadf9020be5f66ad6b4478b1bb80336e62))
* **tooling:** audit the host example and normalise vault key order ([4b5190d](https://github.com/cwbitz/netbird-management-iac/commit/4b5190dae2f7e4db624d10acb4a88773520715a9))
* **validate:** gate the deploy on an operator knob schema ([9f8180a](https://github.com/cwbitz/netbird-management-iac/commit/9f8180a3c2b799dc52311d82b247879ab0d0e8b2))
* **vault-edit:** infer the host when the inventory holds a single host ([4dd9852](https://github.com/cwbitz/netbird-management-iac/commit/4dd9852a10f04b932a5ea56612e366c9c28f0032))


### Bug Fixes

* **backup:** keep the stack running across failed snapshot runs ([67a826d](https://github.com/cwbitz/netbird-management-iac/commit/67a826d47601e9c55e92b5810a87e8c590d0a20b))
* **bootstrap:** cap the SSH identity probe duration ([ca558de](https://github.com/cwbitz/netbird-management-iac/commit/ca558de78174c6fc53aa03c7b41c4a4ceaff848b))
* **bootstrap:** report the probe registration as a fact ([8d11fda](https://github.com/cwbitz/netbird-management-iac/commit/8d11fda2a5ee31ab6099f604ca8107bfa2431280))
* **bootstrap:** resolve the bootstrap target without a self-reference ([226a727](https://github.com/cwbitz/netbird-management-iac/commit/226a727fb779fe0e89f0811904899d7ea59b0077))
* **bootstrap:** verify password-sudo escalation ([15dc41e](https://github.com/cwbitz/netbird-management-iac/commit/15dc41e8fa2ad8a860b06d01207ad0f08df69b84))
* **bootstrap:** verify sudo escalation and install sudo before the grants ([034c28d](https://github.com/cwbitz/netbird-management-iac/commit/034c28d79921e7407d5c691d34639645cd6c8f7c))
* **compose:** pin the compose project names ([1772785](https://github.com/cwbitz/netbird-management-iac/commit/1772785996e5459659fb42a395c74cd1d08cdf69))
* **firewall:** only drop a legacy table that is loaded ([9e310d2](https://github.com/cwbitz/netbird-management-iac/commit/9e310d22cac25e0557e17f22a8b3ee761b1b1126))
* **helpers:** keep control-node tasks unprivileged under become ([863e796](https://github.com/cwbitz/netbird-management-iac/commit/863e7962b56e647e406ab53a59e50ea5d8320311))
* **helpers:** name store_secret in its validation error ([a90ffa4](https://github.com/cwbitz/netbird-management-iac/commit/a90ffa41f3ff029be4197cc89eb8ba651fb8f5e8))
* **hostkeys:** refresh known_hosts atomically and reject changed keys ([12c4b58](https://github.com/cwbitz/netbird-management-iac/commit/12c4b587c939aaf814e5808b1e425427409604a1))
* **make:** fail lint when a real host var is tracked ([7554fab](https://github.com/cwbitz/netbird-management-iac/commit/7554fab8ae0ace7459d8583a51ac2fdf955bfe06))
* **make:** keep validate-knobs a no-op without an inventory ([641c4f7](https://github.com/cwbitz/netbird-management-iac/commit/641c4f740dc5173c50c9999acc448e5c5b805a5d))
* **make:** strip blank lines from the scaffolded vault ([ba438f8](https://github.com/cwbitz/netbird-management-iac/commit/ba438f80d25169627ecfa6a2aff0c08aa20cda9c))
* **management:** default the stack directory ([a2aa286](https://github.com/cwbitz/netbird-management-iac/commit/a2aa2869ef3c1c7aec8a6c41bd25cd958aa7d22b))
* **monitoring:** warn instead of failing when the central Loki is unreachable ([449c468](https://github.com/cwbitz/netbird-management-iac/commit/449c468ab1f602a413006a4096cb577a27e1ce27))
* **playbooks:** stay unprivileged on the control node ([1f8cffa](https://github.com/cwbitz/netbird-management-iac/commit/1f8cffa63d05cd8f17e594b3e2c1ad89c86280c9))
* **preflight:** render the placeholder failure message ([d11ff15](https://github.com/cwbitz/netbird-management-iac/commit/d11ff15e347a36ae7306f9e9626456c47cd95425))
* **restore:** require the datastore key before touching data ([6343102](https://github.com/cwbitz/netbird-management-iac/commit/63431029d61ebfca687037f144294971f33b2b0b))
* **scripts:** default the inventory host helper to this project's group ([7e8936d](https://github.com/cwbitz/netbird-management-iac/commit/7e8936d541e190cb73702a59d64bf4bb58b6277d))
* **server:** converge an exposed-port change in one run ([2d915df](https://github.com/cwbitz/netbird-management-iac/commit/2d915df45c44186bc797c153e28b24216a082d23))
* **server:** publish the configured TLS port ([8cbc8dc](https://github.com/cwbitz/netbird-management-iac/commit/8cbc8dcd8128713a6b82453c8f74a500f1500ef8))
* **server:** shorten the TLS readiness wait and document the mirror knob ([8d3e5f4](https://github.com/cwbitz/netbird-management-iac/commit/8d3e5f45709d2bb6596dabcd2bf5e9e29131d5b5))
* **sshd:** run the key-only probe as the operator ([8e3b43e](https://github.com/cwbitz/netbird-management-iac/commit/8e3b43e303af8ef153e10e897389f6624e5a20d5))
* **tooling:** resolve the vault and cache paths from the project directory ([68ee2d0](https://github.com/cwbitz/netbird-management-iac/commit/68ee2d0bf143d901a0975a99926d961bb7a25bfa))


### Code Refactoring

* **agent:** always manage the host resolver ([8f60523](https://github.com/cwbitz/netbird-management-iac/commit/8f6052303d83ac2e2d63e3536626e6549e4045f9))
* **bootstrap:** drop the password and sudo passthrough knobs ([153a4f3](https://github.com/cwbitz/netbird-management-iac/commit/153a4f375403e15c5d7523a946096095827ef391))
* **connection:** consolidate the managed-host wiring on the iac account ([cedd10e](https://github.com/cwbitz/netbird-management-iac/commit/cedd10ea571694ae23516d05d245f7783a99c554))
* **firewall:** fix the port matrix in role constants ([2a14a4b](https://github.com/cwbitz/netbird-management-iac/commit/2a14a4beaa7ceb55c77b9afb692dec1f8f728999))
* **management:** encode the admin PAT lifetime unit in its name ([39feb6b](https://github.com/cwbitz/netbird-management-iac/commit/39feb6bc785df0e64ba143f516dd497bf72b4b61))
* **management:** rename netbird_server role to management ([cf24b34](https://github.com/cwbitz/netbird-management-iac/commit/cf24b3427b6df4b8ca2d13abbe5aaf9ec00a589c))
* **monitoring:** rename the Alloy journal knobs ([1399b6a](https://github.com/cwbitz/netbird-management-iac/commit/1399b6a1093fd2f5862f3ce9776be0d4cfab9b8e))
* **monitoring:** rename the raw journal matches and default components off ([9fd059a](https://github.com/cwbitz/netbird-management-iac/commit/9fd059a81d3d9e611a1159a9f117576466574aa9))
* **ssh:** keep the non-secret SSH identity settings in main.yml ([4562b40](https://github.com/cwbitz/netbird-management-iac/commit/4562b40effb5f635b0ef213646cce9f12853b6b0))
* **vault:** consolidate vault_managed.yml into a single vault.yml ([97571b8](https://github.com/cwbitz/netbird-management-iac/commit/97571b8ed8425256e31e216786b7883831a8d201))
* **vault:** unify identity variables and opt-in admin account ([5b6d753](https://github.com/cwbitz/netbird-management-iac/commit/5b6d75336e3bd210e52e00b1ac9d9cda1aff867f))

## 1.0.0 (2026-10-02)


### ⚠ BREAKING CHANGES

* **tenant:** fold apply-strict into apply via tenant_strict
* **secrets:** vault_managed.yml no longer holds control-generated keys. Run `make vault-migrate` once per existing host to move them into vault.yml.
* **make:** make targets were renamed/removed. Use install, lint, dry-run, deploy, print, ping, plan, apply, apply-strict, backup, restore.
* **tenant:** the committed netbird_config/ directory is removed; tenant resources must be declared as per-host variables and playbooks/tenant.yml no longer reads netbird_config/.
* **vars:** host_vars overrides must use the new names (host_ssh_*, domain_name, letsencrypt_email, owner_*, disable_geolite_update), and `-e tenant_commit=true` / `-e restore_from=...` replace the netbird_-prefixed extra vars.
* **netbird:** vault_pat is renamed to vault_admin_service_user_access_token (an empty/absent value on a fresh deploy is filled automatically), and the netbird_setup_pat_enabled / netbird_owner_create_pat variables are removed.
* **host-vars:** update any host_vars overrides to the new host_* names.
* **vault:** existing hosts must rename inventory/host_vars/<host>/vault_generated.yml to vault_managed.yml before the next deploy, otherwise the store/session encryption keys are regenerated and already-encrypted data becomes unrecoverable.

### Features

* **bootstrap:** authorize per-identity SSH public keys ([a2a75ef](https://github.com/cwbitz/netbird-iac/commit/a2a75ef755cf52176b28a6af67cc4f064548d2ee))
* **bootstrap:** provision a configured admin account ([15472a0](https://github.com/cwbitz/netbird-iac/commit/15472a016402d8b1702cfaf806b2f61963f3b391))
* **docker:** install Docker CE via the official get.docker.com script ([f87bc30](https://github.com/cwbitz/netbird-iac/commit/f87bc3029a383d1ffc5859fffd33ba5443a2f31b))
* **docker:** install Docker CE when it is missing ([88a6d07](https://github.com/cwbitz/netbird-iac/commit/88a6d073eaeee35db1599e155860d88c34e77172))
* **make:** apply the tenant state in deploy ([c8d699c](https://github.com/cwbitz/netbird-iac/commit/c8d699c4c4f3d8000e035f2db7ea091bd711eb2a))
* **make:** auto-install sshpass via check-deps ([5b2d764](https://github.com/cwbitz/netbird-iac/commit/5b2d764c55d1ae48a5b7eacdfcda970ea0267a7f))
* **make:** run host-bootstrap first in deploy and make tenant_strict strictly opt-in ([f503462](https://github.com/cwbitz/netbird-iac/commit/f503462f264620b511b81e28d19167b6101308b1))
* **netbird:** bootstrap the admin service-user access token ([1498ef9](https://github.com/cwbitz/netbird-iac/commit/1498ef9f17b9272700a7c1d6ec7bc40574cb33fb))
* **netbird:** generate the first-owner password ([4a834d4](https://github.com/cwbitz/netbird-iac/commit/4a834d46cc4f2375384628844b6597ff0cc98993))
* **tenant:** auto-converge routed networks on gateway enrollment ([0ccddbe](https://github.com/cwbitz/netbird-iac/commit/0ccddbe8a6a3b44d6deb91fdd2fd0e1f5482f5e9))
* **tenant:** persist newly created setup key secrets ([bde1b07](https://github.com/cwbitz/netbird-iac/commit/bde1b07cfb7bb79b3bb4bedf040bcbc6ec8f656e))


### Bug Fixes

* **bootstrap:** apply the probed SSH identity as play vars ([d8e4eb3](https://github.com/cwbitz/netbird-iac/commit/d8e4eb33248f6dfa4586bbd47ba483247a9badd9))
* **bootstrap:** avoid dynamic-only group and undefined-var lint warnings ([22bc3ed](https://github.com/cwbitz/netbird-iac/commit/22bc3ed0f0b3410935a164f9be8ba8b72a1d82c1))
* **example:** hardcode the root SSH user and drop vault_root_user ([71a9e6a](https://github.com/cwbitz/netbird-iac/commit/71a9e6a4ee6845a9ec620d4dfba64155c90666a9))
* **host-init:** scaffold an encrypted vault with safe permissions ([0ca5dc4](https://github.com/cwbitz/netbird-iac/commit/0ca5dc43c1b20326f6d6ca941e39c43d09457d61))
* **netbird:** make the check-mode dry-run work on a fresh host ([ff2f770](https://github.com/cwbitz/netbird-iac/commit/ff2f770680bf7b745c6c854869c8be5e75de2d76))
* **tenant:** drop the deprecated vault_pat fallback ([efe7561](https://github.com/cwbitz/netbird-iac/commit/efe75616c6cd17d6f7b337420855cab62afaccfa))
* **tenant:** resolve netbird_user auto_groups names to IDs ([6acb2d4](https://github.com/cwbitz/netbird-iac/commit/6acb2d4ce948fd6f6b3a23eb9744c5f2ac531985))


### Code Refactoring

* **host-vars:** rename netbird_* host knobs to host_* ([cf264d9](https://github.com/cwbitz/netbird-iac/commit/cf264d958b26f873fdd65ca8b6049730fdf56843))
* **make:** flatten and rename targets, drop ans-/netbird- prefixes ([84444f5](https://github.com/cwbitz/netbird-iac/commit/84444f5697ea0d53b8f184b4c6c9e7cf613b71e8))
* **secrets:** split vault.yml (control-authoritative) from vault_managed.yml (host-authoritative) ([42f8ef6](https://github.com/cwbitz/netbird-iac/commit/42f8ef68b52688b64c9a59c17ceef3c6cad24ee4))
* **tenant:** drive tenant config-as-code from per-host vars ([1b6f46c](https://github.com/cwbitz/netbird-iac/commit/1b6f46c34946200bfb9655b588a2e6f9bdb79073))
* **tenant:** fold apply-strict into apply via tenant_strict ([a7ffc1c](https://github.com/cwbitz/netbird-iac/commit/a7ffc1c64a82c059df4812f9112f492c4d17cbc6))
* **vars:** drop the netbird_ prefix from project-owned variables ([132b1c2](https://github.com/cwbitz/netbird-iac/commit/132b1c2916eb800e6fae192a9e465f66d56d298a))
* **vault:** rename vault_generated.yml to vault_managed.yml ([db8fba6](https://github.com/cwbitz/netbird-iac/commit/db8fba627ce66cc530462b3a9afc9155873dda78))
