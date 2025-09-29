# 作業系統題庫 Web 應用程式

這是一個基於 Flask 的 Web 應用程式，用於顯示和瀏覽作業系統題庫。

## 功能特色

- 📚 **章節瀏覽**: 按章節分類查看題目
- 📋 **所有題目**: 一次瀏覽所有題目，支援篩選和排序
- 🔍 **搜尋功能**: 關鍵字搜尋題目內容和章節
- 📊 **統計資訊**: 顯示題庫統計數據
- 📱 **響應式設計**: 支援手機和桌面瀏覽器
- 🎯 **互動功能**: 題目收合/展開功能

## 安裝和執行

### 前置需求
- Python 3.7+
- SQLite 資料庫（questions.db）

### 安裝步驟

1. 安裝依賴套件：
```bash
pip install flask
```

2. 確保資料庫檔案存在：
   - `questions.db` 應該在同一目錄下
   - 可以使用 `import_questions.py` 來匯入題目資料
    `python import_questions.py --db questions.db ch3`

3. 執行 Web 應用程式：
```bash
python web_app.py
```

1. 開啟瀏覽器造訪：
   - http://127.0.0.1:5000 (本機)
   - http://192.168.x.x:5000 (區域網路)

## 使用說明

### 首頁
- 顯示題庫統計資訊
- 章節列表快速導航
- 快速搜尋功能

### 章節瀏覽
- 點擊章節卡片查看該章節所有題目
- 顯示題目類型（選擇題/填空題）
- 顯示正確答案
- 點擊題目標題可收合/展開內容

### 所有題目
- 瀏覽全部題目
- 支援章節和題型篩選
- 支援排序功能
- 實時篩選結果

### 搜尋功能
- 關鍵字搜尋題目內容
- 支援章節名稱搜尋（如：ch1, ch2）
- 高亮顯示搜尋關鍵字
- 相關搜尋建議

## API 端點

應用程式提供以下 RESTful API：

- `GET /api/chapters` - 取得所有章節列表
- `GET /api/chapter/<chapter>` - 取得特定章節的題目
- `GET /api/stats` - 取得統計資訊
- `GET /api/search?q=<keyword>` - 搜尋題目

### API 使用範例

```bash
# 取得統計資訊
curl http://127.0.0.1:5000/api/stats

# 取得 ch1 章節題目
curl http://127.0.0.1:5000/api/chapter/ch1

# 搜尋關鍵字
curl "http://127.0.0.1:5000/api/search?q=記憶體"
```

## 資料庫結構

應用程式使用 SQLite 資料庫，包含兩個主要表格：

### questions 表格
- `id`: 題目 ID (主鍵)
- `chapter`: 章節 (如 ch1, ch2)
- `q_text`: 題目內容
- `q_text_norm`: 正規化題目內容
- `q_type`: 題目類型 (選擇題/填空題)
- `source_file`: 來源檔案
- `created_at`: 建立時間

### answers 表格
- `id`: 答案 ID (主鍵)
- `question_id`: 對應題目 ID (外鍵)
- `position`: 答案順序
- `answer_text`: 答案內容
- `created_at`: 建立時間

## 檔案結構

```
OS_libary/
├── web_app.py              # 主要 Flask 應用程式
├── import_questions.py     # 資料匯入工具
├── questions.db           # SQLite 資料庫
├── templates/             # HTML 模板
│   ├── base.html         # 基礎模板
│   ├── index.html        # 首頁
│   ├── chapter.html      # 章節頁面
│   ├── all_questions.html # 所有題目頁面
│   ├── search.html       # 搜尋頁面
│   └── search_results.html # 搜尋結果頁面
└── README.md             # 說明文件
```

## 技術特色

- **響應式設計**: 使用 Bootstrap 5 框架
- **資料庫操作**: SQLite with Row Factory
- **搜尋功能**: SQL LIKE 查詢
- **模板引擎**: Jinja2
- **API 支援**: RESTful JSON API
- **錯誤處理**: 完整的錯誤處理機制

## 開發者資訊

- 基於 `import_questions.py` 的資料庫邏輯開發
- 使用 Flask 微框架
- 前端使用 Bootstrap 5 和原生 JavaScript
- 支援中文內容和 UTF-8 編碼

## 授權

此專案為教育用途開發。