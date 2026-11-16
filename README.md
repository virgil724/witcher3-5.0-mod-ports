# Witcher 3 5.0 mod ports

> 本 repo 的程式碼、補丁與說明文件由 Claude（Anthropic 的 AI）撰寫，由 repo 擁有者審閱後發布。
> This repository (code, patches and docs) was written by Claude, an AI by Anthropic, and published by the repo owner.

讓幾個 4.04 時代的《巫師 3》模組能在 **5.0 版（重製版 / remaster，腳本版本 5.01c）** 上編譯、正常顯示中文。

**本 repo 不含任何模組本體。** 請先從 Nexus 下載原模組，再用這裡的工具套補丁。

## 支援的模組

| 模組 | 版本 | 問題 | 處理方式 |
|---|---|---|---|
| [Immersive Camera](https://www.nexusmods.com/witcher3/mods/8387) | 1.12.1 (Next-Gen) | 整份覆蓋 4.04b 的 `r4Player.ws` 等 12 個腳本，5.0 編譯失敗（`set` 成了保留字、缺 5.0 新增函式） | 腳本補丁 + 字串檔轉換 |
| [Better Icons - Definitive Edition (Next Gen)](https://www.nexusmods.com/witcher3/mods/10256) | 1.8.3 | 整份覆蓋 4.04b 的 13 個 UI 腳本 | 腳本補丁 + 字串檔轉換 |
| [Separate Upgrades Tab](https://www.nexusmods.com/witcher3/mods/13290) | 1.0.0 | 字串檔是舊格式 | 字串檔轉換 |

Sort Everything、Inventory Plus、SE_SUT_INVplus_Patch 原本就支援 5.0，不需處理。

### 問題一：腳本是 4.04b 的整份覆蓋

這兩個模組把整份原版腳本複製一份再改。5.0 的原版腳本已經大改，舊檔會把 5.0 新增的欄位、函式、`import` 全部蓋掉，導致編譯錯誤，例如：

```
Error [modimmersivecamng]game\player\r4player.ws(3428): syntax error, unexpected TOKEN_SET, expecting ')', near 'set'
```

補丁的做法是 **三方合併**：以 4.04b 原版為基底、5.01c 原版為我方、模組為對方，把模組自己的改動移植到 5.01c 原版上。4.04b / 5.01c 原版腳本取自 [ElementaryLewis/The-Witcher-3-Remastered-Changelog](https://github.com/ElementaryLewis/The-Witcher-3-Remastered-Changelog)。

手動處理的衝突：

- `horseRiding.ws`：用模組的騎馬鏡頭距離，保留 5.0 新增的 FOV 平滑。
- `mountHorse.ws`：用模組的 `OnGameCameraTick` / `OnGameCameraPostTick`。
- `LootPopup.ws`：5.0 改成先快取物品資料，因此改在快取時呼叫 `ReplacingBetterIcons(m_name)`，與原模組寫法不同但效果相同。

### 問題二：選單中文變成「▮▮」亂碼

5.0 的 `.w3strings` 容器版本是 **164（UTF-8）**，舊模組是 **162（UTF-16）**，5.0 讀舊檔會顯示亂碼。`strings` 指令把它們轉成 164，文字與 ID 不變。

## 使用方式

需要 Python 3.9+（只用標準函式庫）。

1. 從 Nexus 下載上表模組的**指定版本**，照原作者說明裝到 `The Witcher 3\Mods\`（包含 `bin\config\...` 的選單 XML 與按鍵設定）。
2. 執行：

   ```
   python w3port.py apply   "C:\Program Files (x86)\Steam\steamapps\common\The Witcher 3"
   python w3port.py strings "C:\Program Files (x86)\Steam\steamapps\common\The Witcher 3"
   ```

   - `apply` 會先比對每個檔案的 SHA-256，只有與指定版本完全一致才套用，不一致會顯示 `[FAIL]` 並跳過。
   - 原檔備份到 `The Witcher 3\Mods_w3port_backup\`，還原時複製回去即可。
   - 兩個指令都可重複執行，已處理過的檔案會跳過。
3. 啟動遊戲。若仍有編譯錯誤，請開 issue 並附上錯誤訊息。

## 已知限制

- 只在 Steam 版 5.01c 測試過（能編譯、進遊戲、模組選單中文正常）。
- Immersive Camera 改寫的鏡頭邏輯在 5.0 有被官方改動，編譯通過不代表每個鏡頭情境都與 4.04 時相同。
- 與其他也覆蓋同一批腳本的模組一起用時，仍需 Script Merger。

## 授權

- `w3port.py`：MIT。
- `patches/` 內容包含 CD PROJEKT RED 的原版腳本片段與各模組作者的程式片段，版權屬原作者，僅供已擁有遊戲與原模組的玩家套用。若原作者希望移除，請開 issue。

## 開發者：重新產生補丁

```
python w3port.py make <原始模組 Mods 資料夾> <移植後 Mods 資料夾>
```
