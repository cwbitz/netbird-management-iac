# 运维手册

[English](RUNBOOK.md) | [简体中文](RUNBOOK.zh-CN.md)

自托管 NetBird 服务端的运维流程。概览见 `README.zh-CN.md`，设计说明与注意事项见
`AGENTS.md`。

## 0. 前置条件（一次性）

- 公网域名的 A 记录指向该主机，且 **TCP 80/443**、**UDP 3478** 已放行——首次部署
  **前**确认。
- 控制端：ansible-core（固定版本）、Python 3、`openssl`，以及 Galaxy collections：
  `make install`。
- 主机条目：`make host-init HOST=<hostname>` —— 脚手架 `host_vars/<host>/`
  （无注释）并加密 `vault.yml`，同时把主机加入 inventory 分组（`GROUP`，默认
  `netbird_management`；HOST 默认 `netbird-1`）。然后编辑
  `inventory/host_vars/<host>/main.yml`（域名、ACME 邮箱），并用
  `make vault-edit HOST=<host>` 编辑 vault（IP、SSH 凭据、owner）。
- 以 root 创建非 root 服务账号（一次性）：`make host-bootstrap`，然后在 `vault.yml`
  指向它。除非 `host_allow_root_login=true`，否则部署拒绝以 root 运行。
- vault 密码文件由 make 目标自动创建
  （`~/.config/projects/netbird-iac/ansible_vault_password`），请妥善保管。
- `sshpass` 仅 `make host-bootstrap` 的密码探测需要；`make install` 会自动安装
  （有免密 `apt-get` 则用 apt，否则 rootless 装到 `~/.local/bin`）。

## 1. 部署

```bash
make dry-run     # 干跑（--check --diff）
make deploy      # 部署服务器，随后应用租户状态（TAGS=... 则仅做服务器）
```

`make lint`（语法检查 + `ansible-lint`）是 CI 的内部检查；不在 `make help` 中展示，
开发者仍可在本地执行。

定向 tag：`netbird`、`netbird_preflight`、`netbird_config`、`netbird_deploy`、
`netbird_owner`（`make deploy TAGS=<tag>`）。

部署会校验输入与非 root 账号、把缺失的密钥生成进加密的 `vault.yml`（用户、控制端生成与
主机回传的密钥都在此）、把 `config.yaml` / `dashboard.env` / `docker-compose.yml` 渲染到 `{{ stack_dir }}`
（默认 `/opt/netbird`）、启动容器栈、等待 TLS 就绪，然后可选地创建首个 owner。

验证：

```bash
ansible -i inventory/hosts.yml netbird -m ansible.builtin.ping
curl -fsS https://<域名>/oauth2/.well-known/openid-configuration >/dev/null && echo ok
ssh <host> 'cd /opt/netbird && docker compose ps'
```

**首次部署 / GeoLite2**：服务端会阻塞启动直到从 `pkgs.netbird.io` 下载完 GeoLite2
数据库。若就绪检查超时，重跑 `make deploy`（数据库会保留），或预置数据库到数据卷并设
`disable_geolite_update: true`。

## 2. 首个 owner 与访问令牌

- 设置了 `vault_owner_email` 时，会通过 `/api/setup` 自动创建首个 owner（仅在实例尚无
  任何账号时可用）。同一次执行会创建 `admin` service user 及其 PAT，存为
  `vault_admin_service_user_access_token`。
- 不填 email 时，浏览器打开 `https://<域名>/setup` 创建 owner；然后在 Team →
  Service Users 创建 `admin` service user 及其 Access Token，并写入 `vault.yml` 的
  `vault_admin_service_user_access_token`。
- PAT 会过期（最长 365 天）。当 tenant 运行提示 token 被拒时，在 Dashboard 重新创建并
  更新 vault。
- **主机被重装/重镜像后**：`vault.yml` 里**主机回传的**密钥已失效（它们只存在于旧主机）。
  请把该文件移走备份——或直接删除——再重新部署：缺失文件会被重新生成（设置了
  `vault_owner_email` 时，首次 owner 引导会写入新的 PAT；`make apply` 会写入新的
  setup key）。若保留失效的非空值，则会一直沿用无效 token，tenant 每次运行都会报
  “token rejected”。

## 3. 日常变更（服务端）

- 编辑 `inventory/host_vars/<host>/main.yml`（非机密）或 vault（机密），然后
  `make deploy`。配置模板会触发重启 handler，因此配置变更会重启容器栈。
- 镜像版本在 `roles/management/defaults/main.yml`（由 Renovate 跟踪）；dashboard
  跟随 `latest`。
- 切勿编辑主机上 `{{ stack_dir }}` 下渲染出的文件——渲染才是唯一事实来源。

## 4. 租户配置即代码

```bash
make plan          # 只读 diff（安全默认）
make apply         # 应用期望状态
```

strict 模式（同时删除未纳管资源）默认关闭，可在
`inventory/host_vars/<host>/main.yml` 设 `tenant_strict: true` 按主机开启（或
`-e tenant_strict=true`）。

期望状态用 collection 原生变量写在 `inventory/host_vars/<host>/main.yml`（机密/PII 放
`vault.yml`）。playbook 会渲染出一个 gitignore 的生成目录
（`.cache/tenant_config/<host>/`）再应用。需要有效的
`vault_admin_service_user_access_token`。

路由网络与出口节点的执行顺序：

1. `make apply` —— 创建 `home-router` 组、setup key 以及路由网络（网关按
   `routers[].peer_groups` 绑定，此时无需 peer 已入网）；
2. 用该 setup key 让客户端入网 —— 它会自动加入 `home-router`，并自动成为这些
   网络的 routing peer。网络无需第二次 `make apply` 才会生效。

## 5. 备份与恢复

```bash
make backup                              # -> backup/<host>/<stamp>/
make restore FROM=backup/<host>/<stamp>
```

- `backup` 会停容器、打包 `netbird_data` 数据卷（`netbird_data.tgz`）、再启动
  容器。归档含用户 PII 与哈希后的凭据。
- 加密密钥**不**在归档里。它在控制端的
  `inventory/host_vars/<host>/vault.yml`——请**另行备份并妥善保护**。丢失
  `vault_datastore_encryption_key` 会导致归档数据不可恢复。
- `restore` 会替换数据卷再重新部署。`config.yaml` 由控制端当前的
  `vault.yml` 重新渲染，因此该文件必须与归档数据来自同一时刻的同一密钥。
- 加密密钥中**只有 `vault_datastore_encryption_key` 与恢复相关**；
  `vault_session_cookie_encryption_key` 与 `vault_relay_auth_secret` 为自动生成的
  内部密钥，无需关注（重生成只会让会话失效 / relay 重新认证）。

恢复后验证：OIDC discovery 地址可访问且用户能登录。

## 6. 升级与回滚

- **升级**：让 Renovate 更新固定 tag（或手动改
  `roles/management/defaults/main.yml`），再 `make deploy`。
- **版本回滚**：把 tag 改回上一版本，重跑 `make deploy`。
- **整体回滚**：从匹配的备份恢复（数据**和**同一份 `vault.yml`）。
- **配置回滚**：`git revert` 或改回 per-host 变量，再 `make deploy`。

## 7. 故障排查

| 现象 | 检查 / 处理 |
|---|---|
| TLS / OIDC 无响应 | 域名 A 记录是否指向主机；TCP 80/443 是否放行；`docker logs netbird-traefik`。 |
| STUN / relay 客户端失败 | UDP 3478 是否放行；Traefik 是否持有 `172.30.0.10`。 |
| 首次部署就绪检查超时 | GeoLite2 下载（见 §1）；重跑或预置数据库。 |
| tenant 运行提示 token 被拒 | PAT 过期——为 `admin` service user 重新创建并更新 vault（§2）。 |
| 主机被重装 / 重镜像 | `vault.yml` 内是旧主机回传的失效密钥——先删除这些键再部署，让新的 PAT/setup key 写入（§2）。 |
| vault 文件不可读 | 必须为 ansible-vault 加密；helper 会在下次运行时把明文文件就地重加密。 |
| SSH 拒绝私钥（`UNPROTECTED PRIVATE KEY FILE`、`are too open`） | 共享脚本 `scripts/run-with-ssh-agent.sh` 会自动启动固定版 Keychain agent、加载 vault 私钥并重试一次；仍失败则检查 `vault_*_ssh_privkey_file` 路径并运行 `make agent-load`。 |

常用命令：

```bash
make print [HOST=<host>]                        # 含解密 vault 的解析变量（单主机时 HOST 可省略）
ssh <host> 'cd /opt/netbird && docker compose logs -f netbird-server'
ssh <host> 'cd /opt/netbird && docker compose ps'
```

## 8. 密钥与安全

- 切勿提交 `vault.yml`、`backup/`（均已 gitignore）。
- 解密任何 vault 都需要 vault 密码文件。
- 请把 `vault.yml`（含 datastore 密钥）另存一份到异地，与数据备份分开存放。
