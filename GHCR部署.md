# 在新主机部署 GHCR 镜像

仓库的 GitHub Actions 工作流会从 `main` 分支的代码构建干净镜像，并推送到：

```text
ghcr.io/hicool-ml/pppoe-activation:latest
ghcr.io/hicool-ml/pppoe-activation:sha-<提交 SHA>
```

工作流使用 GitHub Actions 的短期 `GITHUB_TOKEN` 发布，无需把 PAT 保存到仓库。镜像包首次发布通常是私有的；私有包需要先登录 GHCR。若将包设为公开，拉取镜像无需登录。

## 拉取镜像

私有包需要 GitHub PAT classic，至少授予 `read:packages`：

```bash
docker login ghcr.io -u hicool-ml
docker pull ghcr.io/hicool-ml/pppoe-activation:latest
```

`docker login` 会交互式提示输入 PAT。不要把 PAT 写入命令、脚本或部署文档。公开包跳过 `docker login` 即可。

## 首次启动

本系统的 PPPoE 拨号、网卡和 VLAN 配置需要主机网络与 PPP 设备权限。以下命令按生产环境的运行方式启动；先确认目标主机已安装 Docker，且 `/dev/ppp` 存在：

```bash
sudo mkdir -p /opt/pppoe-activation/{instance,logs,data}
docker run -d \
  --name pppoe-activation \
  --hostname docker \
  --network host \
  --restart unless-stopped \
  --stop-timeout 30 \
  --cap-add=NET_ADMIN \
  --cap-add=NET_RAW \
  --device=/dev/ppp:/dev/ppp:rwm \
  -v /opt/pppoe-activation/instance:/opt/pppoe-activation/instance \
  -v /opt/pppoe-activation/logs:/opt/pppoe-activation/logs \
  -v /opt/pppoe-activation/data:/opt/pppoe-activation/data \
  ghcr.io/hicool-ml/pppoe-activation:latest
```

容器使用 host 网络，页面端口由应用配置决定（常见为激活页 `80`、管理页 `8081`、网卡配置页 `9999`），不需要 `-p`。`instance` 挂载保存 SQLite 数据库及网卡、VLAN 等设置；`logs` 和 `data` 分别保存日志和应用数据。更换镜像时保留这些主机目录即可保留配置。

如果迁移现有系统，请先把原数据库放到 `/opt/pppoe-activation/instance/database.db`，并按需复制日志、数据目录，然后再启动容器。不要在生产数据库上直接试运行新实例。

## 检查运行状态

```bash
docker ps --filter name=pppoe-activation
docker inspect pppoe-activation --format 'Health={{.State.Health.Status}} Restart={{.HostConfig.RestartPolicy.Name}} Network={{.HostConfig.NetworkMode}}'
docker logs --tail 100 pppoe-activation
curl -sS -o /dev/null -w 'activation: %{http_code}\n' http://127.0.0.1:80/
curl -sS -o /dev/null -w 'admin login: %{http_code}\n' http://127.0.0.1:8081/login
curl -sS -o /dev/null -w 'network config login: %{http_code}\n' http://127.0.0.1:9999/login
```

首次运行检查成功后，应登录管理页修改默认管理员密码，并在网卡配置页核对物理网卡、Trunk/VLAN 设置。
