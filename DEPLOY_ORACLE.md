# Oracle Cloud Always Free Deployment

目标：把 `codex/pbc-refactor` 部署到 Oracle Cloud Always Free 的 ARM VM 上。

这条线是真部署：

- 你的电脑关机也能继续跑
- 不依赖本地 `127.0.0.1`
- 数据保存在云主机磁盘

## 当前方案

- 云平台：Oracle Cloud Always Free
- 地区：默认 `ap-singapore-1`，可改
- 主机：`VM.Standard.A1.Flex`
- 备用机型：`VM.Standard.E2.1.Micro`
- 容器：`ghcr.io/sodawaitress/personal-buffett:codex-pbc-refactor`
- 端口：外网 `80` -> 容器 `8080`
- 数据目录：`/opt/personal-buffett/data`

## 先决条件

1. 你有 Oracle Cloud 账号
2. 本机已安装 OCI CLI
3. 本机已完成 `oci session authenticate`
4. 本机有 SSH 公钥
5. 仓库根目录有 `.env`，至少包含：

```env
GROQ_API_KEY=...
```

可选：

```env
FLASK_SECRET_KEY=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

## 一次性登录 Oracle

先登录：

```bash
/Users/poluovoila/bin/oci session authenticate --region ap-singapore-1
```

如果你想换区，把 `ap-singapore-1` 换成别的，比如：

- `ap-osaka-1`
- `ap-tokyo-1`

## 启动部署

在仓库根目录执行：

```bash
bash deploy/oracle/deploy_vm.sh
```

默认会：

1. 读取 `.env`
2. 读取 `~/.oci/config`
3. 创建或复用专用 VCN / 子网 / 安全列表 / Internet Gateway
4. 启动一台 `VM.Standard.A1.Flex` ARM 云主机
5. 用 cloud-init 自动安装 Docker
6. 自动拉取并运行 `personal-buffett` 容器
7. 输出公网 IP

## 常用环境变量

如果你想改默认值，可以在执行前临时带上：

```bash
OCI_REGION=ap-osaka-1 \
OCI_OCPUS=1 \
OCI_MEMORY_GB=6 \
OCI_BOOT_VOLUME_GB=50 \
bash deploy/oracle/deploy_vm.sh
```

可用变量：

- `OCI_REGION`
- `OCI_COMPARTMENT_ID`
- `OCI_CLI_PROFILE`
- `OCI_CLI_CONFIG_FILE`
- `OCI_AUTH_MODE`
- `OCI_SHAPE`
- `OCI_OCPUS`
- `OCI_MEMORY_GB`
- `OCI_BOOT_VOLUME_GB`
- `OCI_IMAGE_OS_VERSION`
- `SSH_PUBLIC_KEY_FILE`
- `IMAGE_TAG`

如果 `A1 Flex` 报容量不足，可以切到 `E2 Micro` 再试：

```bash
OCI_SHAPE=VM.Standard.E2.1.Micro \
OCI_IMAGE_OS_VERSION=24.04 \
bash deploy/oracle/deploy_vm.sh
```

## 部署后检查

脚本跑完后先打开：

- `http://<公网IP>/healthz`
- `http://<公网IP>/login`

再验证：

1. 注册本地账号
2. 搜索股票
3. 添加股票
4. 生成分析

## 登录服务器

```bash
ssh -i ~/.ssh/personal_buffett_oracle ubuntu@<公网IP>
```

## 常用排查

看 cloud-init：

```bash
ssh -i ~/.ssh/personal_buffett_oracle ubuntu@<公网IP> \
  'sudo tail -n 200 /var/log/cloud-init-output.log'
```

看容器：

```bash
ssh -i ~/.ssh/personal_buffett_oracle ubuntu@<公网IP> \
  'sudo docker ps && sudo docker logs --tail 200 personal-buffett'
```

## 已知限制

- 这是单机 SQLite，保持 1 台实例就行
- 现在先走 HTTP，后面再补域名和 HTTPS
- Oracle ARM 免费机型有时会抢不到容量，换区再试
- Oracle 官方也明确写了：`Out of host capacity` 代表当前 home region 的 Always Free 主机暂时没空位，后面重试即可
