# 🚀 Heroku 部署完整教程

## 📋 準備工作清單

### ✅ 必要文件檢查
- [x] `heroku_bot.py` - 主要Bot程式（Heroku優化版）
- [x] `heroku_app.py` - Flask網頁包裝器
- [x] `requirements.txt` - Python依賴清單
- [x] `Procfile` - Heroku部署配置
- [x] `runtime.txt` - Python版本指定

### 📝 需要準備的資訊
- Bot Token: `8034089304:AAGTK_k3t1rmfo5JmUj9V8u1lYb9ji8k0Rg`
- 管理員用戶名: `uplusluke`
- Heroku帳戶（需要信用卡驗證，但不會扣費）

---

## 🌐 第一步：註冊Heroku帳戶

### 1. 訪問Heroku官網
```
https://www.heroku.com/
```

### 2. 點擊「Sign up for free」
- 填寫您的資訊
- 選擇「Python」作為主要開發語言
- 驗證郵箱

### 3. 信用卡驗證
- 進入帳戶設定 → Billing
- 添加信用卡（用於身份驗證，免費方案不會扣費）
- 完成驗證

---

## 💻 第二步：安裝Heroku CLI

### Windows用戶
1. 下載安裝程式：
```
https://devcenter.heroku.com/articles/heroku-cli#download-and-install
```
2. 執行安裝程式，按照提示完成安裝

### Mac用戶
```bash
brew tap heroku/brew && brew install heroku
```

### Linux用戶
```bash
curl https://cli-assets.heroku.com/install.sh | sh
```

### 驗證安裝
```bash
heroku --version
```

---

## 🔑 第三步：登入Heroku

### 1. 開啟命令提示字元（Windows）或終端機（Mac/Linux）

### 2. 執行登入指令
```bash
heroku login
```

### 3. 按任意鍵開啟瀏覽器
- 會自動開啟Heroku登入頁面
- 使用您的帳戶登入
- 看到「Logged in」訊息表示成功

---

## 📁 第四步：準備項目文件

### 1. 創建項目資料夾
```bash
mkdir telegram-bot-heroku
cd telegram-bot-heroku
```

### 2. 複製所有必要文件
將以下文件複製到項目資料夾：
- `heroku_bot.py`
- `heroku_app.py`
- `requirements.txt`
- `Procfile`
- `runtime.txt`

### 3. 檢查文件內容
確保所有文件都已正確複製，特別注意：
- `requirements.txt` 包含所有依賴
- `Procfile` 指向正確的應用文件
- `runtime.txt` 指定Python版本

---

## 🚀 第五步：創建Heroku應用

### 1. 初始化Git倉庫
```bash
git init
git add .
git commit -m "Initial commit"
```

### 2. 創建Heroku應用
```bash
heroku create your-bot-name-here
```
**注意：** 應用名稱必須是全球唯一的，建議使用：
- `telegram-bot-[您的名字]`
- `movie-bot-[隨機數字]`
- 或讓Heroku自動生成名稱（不指定名稱）

### 3. 記錄應用URL
創建成功後，記錄下您的應用URL：
```
https://your-app-name.herokuapp.com/
```

---

## ⚙️ 第六步：設定環境變數

### 1. 設定Bot Token
```bash
heroku config:set BOT_TOKEN=8034089304:AAGTK_k3t1rmfo5JmUj9V8u1lYb9ji8k0Rg
```

### 2. 設定管理員用戶名
```bash
heroku config:set ADMIN_USERNAME=uplusluke
```

### 3. 驗證設定
```bash
heroku config
```
應該看到：
```
BOT_TOKEN: 8034089304:AAGTK_k3t1rmfo5JmUj9V8u1lYb9ji8k0Rg
ADMIN_USERNAME: uplusluke
```

---

## 🚀 第七步：部署應用

### 1. 推送代碼到Heroku
```bash
git push heroku main
```

### 2. 等待部署完成
部署過程中您會看到：
```
-----> Building on the Heroku-22 stack
-----> Using buildpack: heroku/python
-----> Python app detected
-----> Installing python-3.11.0
-----> Installing pip dependencies
-----> Discovering process types
       Procfile declares types -> web
-----> Compressing...
-----> Launching...
       Released v1
       https://your-app-name.herokuapp.com/ deployed to Heroku
```

### 3. 確保應用正在運行
```bash
heroku ps:scale web=1
```

---

## ✅ 第八步：測試部署

### 1. 檢查應用狀態
```bash
heroku ps
```
應該看到：
```
=== web (Free): gunicorn heroku_app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120 (1)
web.1: up 2023/xx/xx xx:xx:xx +0000 (~ 1m ago)
```

### 2. 訪問網頁界面
在瀏覽器中打開：
```
https://your-app-name.herokuapp.com/
```
應該看到Bot狀態頁面

### 3. 測試Bot功能
1. 在Telegram中搜尋您的Bot
2. 發送 `/start` 指令
3. 測試各項功能
4. 管理員發送 `/admin` 測試管理功能

---

## 📊 第九步：監控和維護

### 1. 查看日誌
```bash
heroku logs --tail
```
實時查看應用日誌

### 2. 重啟應用
```bash
heroku restart
```
如果Bot無回應，可以重啟

### 3. 檢查健康狀態
訪問：
```
https://your-app-name.herokuapp.com/health
```

---

## 🔧 常見問題解決

### ❌ 問題1：Bot無法啟動
**症狀：** 日誌顯示錯誤或Bot不回應

**解決方案：**
```bash
# 檢查日誌
heroku logs --tail

# 檢查環境變數
heroku config

# 重啟應用
heroku restart
```

### ❌ 問題2：應用休眠
**症狀：** 免費方案30分鐘無活動後休眠

**解決方案：**
1. 升級到付費方案（$7/月）
2. 或使用外部服務定期ping您的應用

### ❌ 問題3：資料庫問題
**症狀：** SQLite相關錯誤

**解決方案：**
```bash
# 重新部署
git add .
git commit -m "Fix database"
git push heroku main
```

### ❌ 問題4：部署失敗
**症狀：** `git push heroku main` 失敗

**解決方案：**
```bash
# 檢查文件是否正確
ls -la

# 檢查Git狀態
git status

# 重新提交
git add .
git commit -m "Fix deployment"
git push heroku main --force
```

---

## 💰 升級到付費方案

### 何時需要升級？
- Bot用戶超過50人
- 需要24/7不間斷運行
- 免費方案550小時/月不夠用

### 如何升級？
1. 登入Heroku Dashboard
2. 選擇您的應用
3. 進入「Resources」頁面
4. 點擊「Change Dyno Type」
5. 選擇「Hobby」方案（$7/月）

### 升級後的好處
- ✅ 無休眠限制
- ✅ 自定義域名
- ✅ 更多運行時間
- ✅ 優先技術支援

---

## 🔄 更新Bot代碼

### 當您需要修改Bot功能時：

1. **修改本地文件**
2. **提交更改**
```bash
git add .
git commit -m "Update bot features"
```
3. **部署更新**
```bash
git push heroku main
```
4. **驗證更新**
```bash
heroku logs --tail
```

---

## 🆘 獲取幫助

### Heroku官方資源
- 📚 文檔：https://devcenter.heroku.com/
- 💬 社群：https://help.heroku.com/
- 📧 支援：透過Dashboard提交工單

### 緊急聯繫
如果遇到無法解決的問題：
1. 截圖錯誤訊息
2. 複製完整的錯誤日誌
3. 聯繫技術支援

---

## 🎉 部署成功！

恭喜您成功將Telegram Bot部署到Heroku！

### 📝 記錄重要資訊
- **應用名稱：** your-app-name
- **應用URL：** https://your-app-name.herokuapp.com/
- **Bot用戶名：** @your_bot_username
- **管理員：** @uplusluke

### 🚀 下一步
1. 測試所有Bot功能
2. 邀請用戶開始使用
3. 監控使用情況
4. 根據需要升級方案

您的Bot現在已經24/7運行在雲端了！🎊

