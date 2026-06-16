# 校园二手物品交易系统

基于 Flask + SQLite 的校园二手物品交易 Web 应用。

## 功能
- 用户注册 / 登录
- 商品发布、浏览、搜索、购买
- 购物车管理
- 管理员：商品管理（添加/删除/修改）、用户管理
- 分页展示（每页10条）

## 本地运行

```bash
pip install flask
python app.py
```

访问 http://localhost:5000

默认管理员：admin1 / adminpass1

## 线上部署指南

### 方式一：Render（推荐）

1. 注册 [Render](https://render.com) 账号（支持 GitHub 登录）
2. 点击 **New +** → **Web Service**
3. 连接你的 GitHub 仓库
4. 选择该仓库，Runtime 选 **Python**
5. Build Command: `pip install -r requirements.txt`
6. Start Command: `gunicorn app:app`
7. 选择 **Free** 计划，点击 **Create Web Service**
8. 等待部署完成即可访问

### 方式二：PythonAnywhere

1. 注册 [PythonAnywhere](https://www.pythonanywhere.com) 免费账号
2. 进入 **Dashboard** → **Web** → **Add a new web app**
3. 选择 **Flask** 和对应的 Python 版本
4. 通过 **Files** 页面上传所有项目文件
5. 在 **Web** 页面点击 **Reload**

### 方式三：Railway

1. 注册 [Railway](https://railway.app)（支持 GitHub 登录）
2. 点击 **New Project** → **Deploy from GitHub repo**
3. 连接你的仓库，Railway 会自动检测 Python 项目
4. Start Command: `gunicorn app:app`
5. 等待部署完成

## 默认账号

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 管理员 | admin1 | adminpass1 |
| 用户 | 请注册 | - |

管理员注册授权码：`regon`
管理员删除操作二级密码：`accon`
