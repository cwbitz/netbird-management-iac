# netbird-iac

[English](README.md) | [简体中文](README.zh-CN.md)

用 Ansible 幂等地把 **自托管 NetBird 服务端**部署到公网 Debian 系 VPS：合并版
`Management + Signal + Relay + STUN` 容器、NetBird Dashboard，以及内置 Traefik
反向代理（自动签发 Let's Encrypt 证书）。

## 部署内容

```
┌───────────────────────────── public VPS ──────────────────────────────┐
│  TCP 80/443                        UDP 3478                           │
│     │                                   │                             │
│  netbird-traefik ───────────────────────┼ netbird-server              │
│  (Let's Encrypt, TLS-ALPN)              │ (Management + Signal +      │
│     │                                   │  Relay + STUN + Dex)        │
│  netbird-dashboard                   (STUN)                           │
└───────────────────────────────────────────────────────────────────────┘
```

- **内置 Dex IdP**（NetBird ≥ 0.62）：开箱即用本地用户，无需外部 IdP；外部
  OIDC 提供方可事后在 Dashboard 里追加。
- **server 镜像已固定版本**（Renovate 跟踪）；dashboard 上游只发布滚动 tag，故跟随
  `latest`。

## 节点类型

`netbird` 伞形组下按**节点类型分组**，`hosts:` 播放目标与 `group_vars/<group>/`
即唯一事实来源：

| 分组 | 运行内容 | 入口 |
|---|---|---|
| `netbird_management` | 服务器栈（Management + Signal + Relay + STUN + dashboard + Traefik） | `make deploy`（`site.yml`、`tenant.yml`、`backup.yml`、`restore.yml`） |
| `netbird_agent` | 仅 NetBird agent —— 路由节点（`netbird_agent_routing: true`）或普通终端节点 | `make agent`（`agent.yml`） |

`netbird` 父组涵盖所有受管节点，因此主机 bootstrap、主机密钥刷新、ssh-agent
装填都作用于全部节点（`make host-bootstrap HOST=<name>` 针对单台主机，默认唯一的
management 节点）。

## 依赖

- 一台 Linux VM（≥ 1 CPU / 2 GB），公网可达 **TCP 80/443** 与 **UDP 3478**。
- 一个 **公网域名**，A 记录指向该 VM。
- Docker Engine + Compose v2 插件；缺失时通过 Docker 官方安装脚本
  （`https://get.docker.com`）自动安装（Debian 系）；设 `install_docker: false`
  可改为要求预装。
- 控制端：`mise` 或 `asdf`、`openssl`，以及对主机的 SSH 访问。`sshpass` 仅
  `make host-bootstrap` 的密码探测需要，由 `make install` 自动安装。`make install`
  还会安装固定的 Keychain 3（ssh-agent 兜底，仅当私钥权限被 OpenSSH 拒绝时使用，
  如 WSL 下）；所有走 SSH 的目标都经由共享脚本 `scripts/run-with-ssh-agent.sh`
  执行，并在私钥被拒时自动重试一次。

## 快速开始

```bash
make install                # 工具链 + Galaxy collections

make host-init HOST=netbird-1
#   生成文件无注释，主机自动写入 inventory，vault.yml 自动加密
#   编辑 inventory/host_vars/netbird-1/main.yml    （域名、ACME 邮箱）
#   用它编辑 vault（IP、SSH 凭据、owner）：
make vault-edit HOST=netbird-1

make dry-run && make deploy   # deploy 同时应用租户状态
```

`make lint`（语法检查 + `ansible-lint`）是 CI 运行的内部检查；不在 `make help`
中展示，开发者仍可在本地执行。

部署以**非 root 服务账号**执行（`site.yml` 默认拒绝 root，除非
`host_allow_root_login=true`）。首次以 root 创建一次：

```bash
make host-bootstrap      # 创建 ansible 账号 + sudo
# 然后在 vault.yml 指向它：
#   vault_host_ansible_user: ansible
#   vault_host_ansible_ssh_privkey_file: ~/.ssh/...   （或 vault_host_ansible_password）
```

`host-bootstrap` 按 `ansible → admin → root` 顺序探测，用第一个能登录的身份；若非
ansible，则创建该服务账号，并确保 Docker Engine + Compose v2 已安装（缺失时安装 Docker
CE），同时应用下方镜像源。对每个设置了 `vault_<id>_ssh_pubkey_file` 的身份，把该路径
公钥写入被控机对应账号（`ansible` / `admin` / `root`）；留空则忽略。ansible 身份未给
公钥时才设密码（自动生成并写入加密 vault），用每账号随机盐哈希并以
`update_password: on_create` 应用，因此在主机上手动改过的密码不会被覆盖。设置
`host_admin_enabled: true` 时会额外创建人工 `admin` 账号，且**始终**设置密码
（留空则自动生成写入加密 vault），用于控制台登录与 sudo，另可安装配置的公钥。
私钥路径由 `vault_<id>_ssh_privkey_file` 指定（仅接受路径，不接受内联字符串）。

填了 `owner_email` 时会通过 `/api/setup` 自动创建首个 owner；`owner_password` 留空则
由角色生成并写入加密的 `vault.yml`。同一次部署还会创建 `admin` service user
并签发其 PAT，存入 `vault_admin_service_user_access_token`（供 tenant 阶段使用），
然后删除一次性的 owner token。不填 email 时，浏览器打开 `https://<域名>/setup` 手动创建
（该页仅在实例无任何账号时可用）。

Tag：`netbird`、`netbird_preflight`、`netbird_config`、`netbird_deploy`、
`netbird_owner`，可用 `make deploy TAGS=netbird_config` 单独执行。

## 关于 IdP

默认使用服务端内置的 **Dex** IdP（NetBird ≥ 0.62），由 Dashboard 直接管理本地用户。
任何 **OIDC 兼容**的外部 IdP（Google / Entra / Okta / Keycloak / Zitadel /
**Authentik** / Pocket ID / 通用 OIDC）都可与本地用户并存：Dashboard →
**Settings → Identity Providers**，或 `POST /api/identity-providers`。这属于运行时的
租户配置，不属于服务端部署 role。

**已有自托管 Authentik 能直接用吗？** 可以。在 Authentik 建 **confidential
OAuth2/OpenID** provider → 填入 NetBird 的 redirect URL → 在 NetBird 加 *Generic
OIDC*，issuer 用 `https://authentik.example.com/application/o/netbird/`。面向**远程
公网用户**时注意：

- 用户浏览器**和** NetBird 服务端都要能访问该 issuer（discovery、JWKS、token，以及
  登录/同意页面），且证书必须是有效的公网 TLS。
- 若 Authentik 前面有只放行内网/CGNAT 的 IP 白名单，公网浏览器与公网 NetBird
  服务端都会被拒——需先公开 OIDC/登录路径，或把相关来源 IP 加白名单。
- 组同步：Authentik 的 `profile` scope 自带 `groups`，在 NetBird 开启 *JWT group
  sync* 用 `groups` claim 即可（Zitadel 用的是 *roles*，还需写 Action 转成扁平数组）。

## 租户 / ACL 配置即代码（community.ansible_netbird）

期望状态以「每主机 Ansible 变量」的形式维护：非机密放
`inventory/host_vars/<host>/main.yml`，机密/PII 放 `vault.yml`，变量名沿用
collection 原生名；playbook 把它们渲染到一个 gitignore 的生成目录
（`.cache/tenant_config/<host>/`）再声明式应用，支持纯名称→ID 解析、
按依赖顺序应用：

```bash
make plan          # 只读 diff（安全默认）
make apply         # 应用期望状态
```

`make deploy` 在部署服务器后会一并应用租户状态；只想改租户而不动服务器时用
`apply`；带 `TAGS=...` 时 `deploy` 仅做服务器。strict 模式（同时删除未纳管资源）
默认关闭，可在 `inventory/host_vars/<host>/main.yml` 设 `tenant_strict: true`
按主机开启。

需要 `vault_admin_service_user_access_token`（全新部署会自动创建；否则在
Team → Service Users 建 `admin` service user 及其 access token）。
可代码化范围：

| 资源 | 可否代码化 | 变量 |
|---|---|---|
| 组、Policies(ACL)、Posture checks | 可以 | `netbird_groups`、`netbird_policies`、`netbird_posture_checks` |
| Networks(路由器/资源)、DNS(nameservers/zones/settings) | 可以 | `netbird_networks`、`netbird_dns_*` |
| 账户设置（Dashboard settings） | 可以 | `netbird_settings` |
| Services | 可以 | `netbird_services`、`netbird_service_domains` |
| 用户 / 服务用户 | 可以* | 对象/角色/组可管；内置 IdP 密码是一次性 |
| Setup keys | 可以* | `netbird_setup_keys`；有效期 1..31536000 秒（最长 1 年，无法声明永不过期）；新建密钥的明文会写入 `vault.yml` 的 `vault_setup_key_<name>` |
| 外部 IdP | 可以* | client secret 需存 vault |
| **Peer（设备）** | **不可以** | 是入网设备，只能管其设置；设备用 setup key 重新入网 |
| 审计/事件 | 不可以 | 只读 |

`*` = 声明可代码化，但一次性密钥不可复现，需另存密码管理器。

部分选项需要服务器之外的额外基础设施（未设置的选项会被跳过）：
- `netbird_networks.routers` 需已入网的 peer；`netbird_services` /
  `netbird_service_domains` 需已注册的 proxy cluster。

## 备份与恢复

```bash
make backup                              # -> backup/<host>/<stamp>/
make restore FROM=backup/<host>/<stamp>  # 成对恢复
```

备份会停容器做一致的 SQLite 快照，把 `netbird_data` 卷打包到
`backup/<host>/<stamp>/`。加密密钥**不**在归档里：它在控制端的
`inventory/host_vars/<host>/vault.yml`，需另行备份。恢复时 `config.yaml` 由
该文件重新渲染，因此它必须与归档数据来自同一时刻的同一密钥，否则数据无法解密。
`backup/` 已 gitignore；请另存异地副本。

## 主机监控与主机安全（可选）

```bash
make monitoring
```

按主机 opt-in：设置 `monitoring_enabled: true` 后，安装
`prometheus-node-exporter` 与 `crowdsec`（基于 journald 的检测），以及
`crowdsec-firewall-bouncer`（nftables 拦截），并通过共享的 `agent` role（与
`make agent` 同一个）把主机加入 overlay：默认用租户 `endpoint` 组
（`peer_setup_key`，从 management 节点 vault 解析；`endpoint` 组不授予任何
exit/LAN 路由），各 exporter 随之绑定 overlay 地址，无需公网端口。node_exporter
默认监听 `127.0.0.1:9100` 再加 overlay 地址；可用 `node_exporter_listen_addr` 调整
本机监听地址。再设置 `alloy_enabled: true` 与 `loki_url`，Alloy 容器会把 journald
的 SSH 事件经 overlay 推送到中心 Loki。

```yaml
# inventory/host_vars/<host>/main.yml
monitoring_enabled: true
alloy_enabled: true
loki_url: "http://<loki-overlay-ip>:3100"
```

## 加入 agent 节点（路由节点与终端节点）

```bash
make agent     # 加入 netbird_agent 分组
```

在 agent-only 节点上运行 NetBird agent，使其成为 mesh peer。setup key
（`peer_setup_key`）决定其自动加入的分组，从而决定角色；它从 management 节点
vault 解析，因此 agent 节点不再保存该密钥副本。路由节点另设
`netbird_agent_routing: true` 以启用 IP 转发：

```yaml
# inventory/host_vars/<router>/main.yml
domain_name: "{{ vault_domain_name }}"
peer_setup_key: "{{ (hostvars[netbird_management_host] | default({})).vault_setup_key_home_router_enrollment }}"
netbird_agent_routing: true
```

被路由的网络资源（子网 / exit）与路由节点所在分组，在 management 节点的租户
配置（`netbird_networks`）中声明。

## 区域受限主机的镜像源（可选）

`make host-bootstrap`（可选，**不**在 `deploy` 内）可把主机指向替代软件源——适合中国
VPS。变量未设置时是 no-op，且不动部署基线：

```yaml
# inventory/host_vars/<host>/main.yml
host_apt_mirror: "https://mirrors.tuna.tsinghua.edu.cn/debian"
docker_registry_mirrors:
  - "https://docker.1ms.run"
```

## 目录

```
inventory/           # hosts.yml(.example)、group_vars/{netbird,netbird_management}、host_vars/example
playbooks/site.yml   # server preflight + management role
playbooks/tenant.yml # 租户 config-as-code（community.ansible_netbird）
playbooks/agent.yml  # 把路由/终端节点加入 mesh（agent role）
roles/management     # defaults（镜像版本）、tasks、templates/
roles/agent          # NetBird agent：加入 mesh（路由/终端节点、监控）
roles/monitoring     # 可选主机安全 + exporter（含 agent role）
roles/helpers/       # 共享的 vault 密钥生成
docs/RUNBOOK.md      # 运维手册（部署、备份恢复、回滚）
```

## 密钥

切勿提交 vault。单一 per-host 加密 vault `inventory/host_vars/<host>/vault.yml`
存放：用户提供、控制端生成并传给主机的输入（datastore/session/relay 密钥、
owner/ansible 密码），以及主机回传的密钥（`admin` PAT、setup key 明文）。
加密密钥中**只有 `vault_datastore_encryption_key` 需要你关注**：
**务必备份 `vault.yml`** 且恢复时必须沿用同一值，否则加密的用户数据不可恢复；
session cookie（`vault_session_cookie_encryption_key`）与 relay auth
（`vault_relay_auth_secret`）密钥为自动生成的内部密钥，**勿手改**（重生成只会让会话失效 /
relay 重新认证）。

## 许可证

见 `LICENSE`。
