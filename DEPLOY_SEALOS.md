# Sealos Deployment

目标：把 `main` 分支的最新稳定版本部署成一个长期可访问的公网服务。

## 推荐方式

使用 Sealos 的 GitHub Deploy 或 App Launchpad。

原因：

- 7 天免费试用
- 不需要信用卡
- 有持久卷
- 有自动公网地址
- 对中国访问路径更友好

官方参考：

- Pricing: `https://sealos.io/pricing/`
- Persistent Volume: `https://sealos.io/docs/guides/app-launchpad/persistent-volume`
- Environments: `https://sealos.io/docs/guides/app-launchpad/environments/`
- Add a Domain: `https://sealos.io/docs/guides/app-launchpad/add-a-domain`

## 当前仓库已准备好的部署能力

- `Dockerfile`
- `.dockerignore`
- `Procfile`
- `/healthz` 健康检查
- `RADAR_DB_PATH` 可配置 SQLite 路径

分支：

- `main`

仓库：

- `https://github.com/Sodawaitress/personal-buffett`

## 必填环境变量

在 Sealos 环境变量里填：

```env
FLASK_SECRET_KEY=<随机32字节以上密钥>
GROQ_API_KEY=<你的 Groq key>
RADAR_DB_PATH=/data/radar.db
FLASK_DEBUG=0
```

可选：

```env
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
```

如果先不做 Google 登录，就留空。

## 卷配置

给应用挂一个持久卷：

- Mount Path: `/data`

SQLite 会写到：

- `/data/radar.db`

## 端口与健康检查

容器端口：

- `8080`

健康检查：

- Path: `/healthz`

预期返回：

```json
{"ok": true}
```

## 代码来源

优先用 GitHub 分支部署：

- Branch: `main`

如果 Sealos 直接识别 Dockerfile，就不用手写启动命令。

也可以直接填镜像：

- `ghcr.io/sodawaitress/personal-buffett:main`

仓库里已经加了 GitHub Actions：

- `.github/workflows/publish-image.yml`

推到 `main` 后会自动构建并推送镜像到 GHCR。

镜像已验证可匿名拉取。

如果你走 YAML / K8s 导入，也可以直接用：

- `deploy/personal-buffett.k8s.yaml`

## 部署后检查

上线后先验证：

1. `/healthz` 返回 `200`
2. `/login` 能打开
3. 注册一个本地账号能成功
4. 添加股票搜索可用
5. 生成股东信能跑

## 已知限制

- SQLite 只适合单实例
- 不要开多副本
- 长任务目前还是进程内线程，不是独立队列

所以部署时保持：

- 1 replica
