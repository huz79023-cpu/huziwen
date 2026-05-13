# 普音 — 云端 AI 人声分离 部署指南

## 整体流程

```
你本地 (Mac)             阿里云
─────────────────        ─────────────────
写代码 (已完成)           
docker build              ACR (容器镜像仓库)
docker push       ───→    函数计算 FC (GPU)
                          获取 URL ← 最终产物
```

## 前置条件

- [x] Docker Desktop（已安装）
- [x] 阿里云账号（已实名认证）

---

## 第一步：创建阿里云容器镜像仓库 (ACR)

1. 登录 [阿里云容器镜像服务控制台](https://cr.console.aliyun.com)
2. 选择地域（推荐 **上海**，离你近延迟低）
3. **创建命名空间**（如 `puyin`）
4. **创建镜像仓库**：
   - 地域：上海
   - 命名空间：`puyin`
   - 仓库名称：`audio-separator`
   - 仓库类型：**公开**（方便拉取）
   - 创建后记录下仓库地址，格式如：`registry.cn-shanghai.aliyuncs.com/puyin/audio-separator`

---

## 第二步：本地构建并推送 Docker 镜像

打开终端，进入 cloud-separator 目录：

```bash
cd ~/Desktop/cloud-separator
```

### 1. 登录阿里云 ACR

```bash
docker login --username=你的阿里云账号 registry.cn-shanghai.aliyuncs.com
```

密码填：**你 ACR 的登录密码**（不是阿里云登录密码，在 ACR 控制台→访问凭证 获取）

### 2. 构建镜像（M1 Mac 需指定 platform）

```bash
docker build --platform linux/amd64 -t registry.cn-shanghai.aliyuncs.com/puyin/audio-separator:latest .
```

构建过程：
- 下载 PyTorch CUDA 镜像（~3GB）
- 安装 ffmpeg、demucs、flask
- **首次构建约 5-10 分钟**

### 3. 推送镜像到 ACR

```bash
docker push registry.cn-shanghai.aliyuncs.com/puyin/audio-separator:latest
```

推送完成后，你可以在 ACR 控制台看到镜像。

---

## 第三步：创建函数计算 FC (GPU)

1. 登录 [函数计算 FC 控制台](https://fcnext.console.aliyun.com)
2. 选择地域：**上海**
3. 点击 **创建函数**
4. 选择 **使用容器镜像**
5. 配置如下：

| 配置项 | 值 |
|--------|-----|
| **镜像配置** | 选择 ACR 中的镜像 → `puyin/audio-separator:latest` |
| **监听端口** | `9000` |
| **高级配置 → 是否使用 GPU** | ✅ 是 |
| **GPU 卡型** | Tesla T4 |
| **规格方案** | GPU 显存 16GB / vCPU 2核 / 内存 8GB |
| **启动命令** | 留空（用 Dockerfile 的 CMD） |
| **环境变量** | 留空 |

6. 点击 **创建**

### 获取 URL

创建完成后：
1. 进入函数详情页
2. 左侧 → **触发器**
3. 复制 **公网访问地址**

URL 格式：`https://xxx-xxx.cn-shanghai.fcapp.run`

---

## 第四步：测试

用 curl 测试：

```bash
# 上传一个音频文件测试分离
curl -X POST \
  -F "audio=@/path/to/song.wav" \
  -o separated.zip \
  https://你的触发器URL/invoke
```

成功的话会下载到一个 `separated.zip`，解压后有：
- `drums.wav` — 鼓
- `bass.wav` — 贝斯
- `other.wav` — 其他伴奏
- `vocals.wav` — 人声

---

## 第五步：给普音提供 URL

测试通过后，把触发器 URL 告诉我（ganganji队长），我加到普音的代码里。

---

## 故障排查

### 构建报错 "no matching manifest"
M1 Mac 上构建必须加 `--platform linux/amd64`

### 函数创建失败 "no enough resource"
换一个可用区试试，或者选择其他 GPU 卡型

### 请求超时
首次请求需要冷启动（加载模型 5-10 秒），后面会快。
如果频繁超时，可以在 FC 配置中增加超时时间。

### 上传文件太大
FC 同步调用有 6MB 限制，如果音频超过 6MB：
- 先用 Audacity/ffmpeg 截取一段测试
- 正式使用需要走 OSS 方案（后面再优化）

---

## 费用估算

- GPU T4 实例：约 ¥3.5/小时（按秒计费）
- 一次分离约 10-30 秒 → **约 ¥0.01-0.03**
- 不调用不收费
- 配合 **闲置预留实例** 模式可进一步降低成本（显存归零）
