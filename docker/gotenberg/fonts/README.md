# 自有字体目录

把**版本管理内的字体文件**（`.ttf` / `.ttc` / `.otf`）放进本目录，再构建镜像即可：

```powershell
docker compose build gotenberg
docker compose up -d gotenberg
docker exec ai-tender-gotenberg-1 fc-list :lang=zh | Measure-Object -Line   # 看装进去多少中文字体
```

## 为什么要自带

LibreOffice 用**已安装字体**计算分页与版面。字体缺失是最常见的排版与页码漂移原因，
而一旦分页漂移，「第 X 页的某块」就和用户手里的原件对不上，溯源能力直接失效
（[docs/调研/02](../../../docs/调研/02-接口调研-LibreOffice.md) 第 4 节）。

## 建议清单

| 用途 | 字体 |
| --- | --- |
| 公文正文 | 宋体（SimSun）、仿宋（FangSong）、楷体（KaiTi）、黑体（SimHei） |
| 公文标题 | 方正小标宋、方正黑体、方正楷体 |
| 界面/表格 | 微软雅黑（Microsoft YaHei） |
| 西文 | Times New Roman、Arial |

## 注意事项

1. **版权**：宋体、微软雅黑、方正系列属于商业字体，本目录的文件**不进版本库**（`.gitignore` 已排除），
   由部署方从已获授权的来源放入。基础镜像里通过 apt 安装的 Noto CJK / 文泉驿属于开源字体，可以直接分发。
2. **字体覆盖清单要留痕**：新增字体等于改变分页口径，按变更流程记一笔，并在转换后做页数一致性抽检。
3. **不要把字体挂成 volume**：同一份文档在不同机器上转出不同分页，等于溯源结果不可复现。