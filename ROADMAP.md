# SiftByExif - 未来更新路线图

## 已知缺陷与改进点

### 1. 视频文件支持

**现状**：所有功能（品牌检测、GPS提取、损坏扫描）仅处理图片格式（NEF/CR2/ARW/JPEG等），视频文件（MP4/MOV/AVI等）完全不参与扫描和分类。

**视频文件的 EXIF 信息**：多数相机/手机拍摄的视频也包含元数据：
- `Make` / `Model` — 可用于品牌识别
- GPS 坐标 — 部分相机和无人机写入 GPS 数据到视频元数据
- 创建日期 — 可用于按时间排序
- 视频编码格式/分辨率 — 可用于质量检查

**建议方案**：
- 品牌检测支持视频扩展名（`.mp4`, `.mov`, `.avi`, `.mts`, `.m2ts`）
- 使用 ExifTool 读取视频元数据（Make/Model/GPS）
- 视频不参与损坏扫描（或仅做基本文件完整性检查）
- GPS 提取后可与图片一起参与聚类

**优先级**：中

### 2. 手机品牌检测：ICC Profile 作为备选来源

**现状**：相机检测仅检查 EXIF `Make` (tag 271) 和 `Model` (tag 272)。部分手机品牌（如 Xiaomi）将厂商信息写入 ICC Profile 的 `Device Manufacturer` 字段，而非 EXIF Make，导致手机照片被漏检。

**示例**：Xiaomi 手机照片，ICC Profile 中 `Device Manufacturer = Xiaomi`，但 EXIF Make/Model 为空。

**建议方案**：
- Recovery 模式下增加 ICC Profile 检查作为第三层回退
- 读取 `Image.info.get('icc_profile')` 解析 `Device Manufacturer` 字段
- 匹配到已知品牌则计入检测结果

**优先级**：中

---

### 2. 离线 GPS 城市匹配：仅支持中国大陆

**现状**：`cities.json` 内置 136 个中国地级市坐标，`match_city()` 仅在 50km 半径内匹配。日本、欧洲、北美等地区的 GPS 坐标无法匹配到任何城市，会归入"其他"。

**建议方案**：
- 提供可替换的 `cities.json` 文件，用户可自行替换为其他国家的城市坐标
- 内置一个精简版全球主要城市坐标（~500 条）作为兜底
- 界面中显示"当前坐标数据：中国城市 (136)"，提示可替换

**优先级**：低（目前用户群体在中国大陆）

---

### 3. 在线地理编码：Nominatim 国内不可用

**现状**：`reverse_geocode_online()` 调用 `nominatim.openstreetmap.org`，在中国大陆网络环境下超时。已通过离线坐标匹配作为主力方案。

**建议方案**：
- 接入国内可用的地理编码 API（百度地图、高德地图），需用户提供 API Key
- 界面中增加"配置在线地理编码 API Key"选项

**优先级**：低

---

### 4. 非 Nikon 相机品牌支持不完整

**现状**：品牌检测覆盖 14 个品牌，理论上可识别所有常见相机。但以下功能仅在 Nikon NEF 上充分验证：

- **文件名恢复**：仅实现 Nikon FileNumber 提取，Canon/Sony/Fujifilm 的 MakerNote 标签虽有文档但未测试
- **NEF 结构检查**：TIFF IFD 链校验是 TIFF 通用逻辑，理论上适用于所有 RAW 格式（CR2/ARW/DNG 均基于 TIFF），但仅在 NEF 上测试过偏移量和标签号
- **MakerNote 解析**：Nikon MakerNote 为 TIFF 格式，其他品牌（Canon IFD3、Sony 嵌入式）格式各异，MakerNote 大小统计可能不准确
- **嵌入 JPEG 提取**：ExifTool `-JpgFromRaw` 是通用标签，理论上各品牌均支持，但仅在 NEF 上测试过完整 5568×3712 预览提取

**建议方案**：
- 建立一个各品牌 RAW 文件样本库用于回归测试
- 在 `renamer.py` 中根据品牌分支选择重命名逻辑
- 损坏扫描增加品牌感知的检查项

**优先级**：高

---

### 5. 损坏扫描：逐文件 ExifTool 调用性能

**现状**：`NEF_EMBEDDED` 检查对每个文件调用一次 ExifTool `-b -JpgFromRaw` 提取嵌入 JPEG，2248 个文件约需 30-40 分钟。

**建议方案**：
- 研究 ExifTool 批量提取嵌入 JPEG 的可行性（`-w` 一次性输出）
- 或使用多线程并行提取

**优先级**：中

---

### 6. 损坏扫描：动态阈值可能漏检

**现状**：FILE_SIZE 和 MAKERNOTE_SIZE 使用批次 `median ± 3*IQR` 的统计方法。DSC_2208/2209 嵌入 JPEG 损坏但文件大小完全正常，被结构检查漏过（后通过完整的 NEF_EMBEDDED 扫描检出）。

**已修复**：NEF_EMBEDDED 现作为所有文件的必检项，不再仅对已标记文件执行。

**未来优化**：研究 ExifTool 的 `-validate` 是否可检测 RAW 数据层损坏。

---

### 7. Windows 路径编码问题

**现状**：包含中文的路径在 Bash heredoc、subprocess stdout 等场景下出现 GBK/UTF-8 混用导致乱码。`.py` 文件用 Write 工具写入可避免编码问题。

**建议方案**：
- 所有文件路径操作统一使用 `os.path` 函数
- 避免在 heredoc 中硬编码中文路径
- ExifTool 调用使用 `-charset filename=gbk` 参数

**优先级**：已基本规避

---

### 8. 用户手动分类信息保留

**现状**：已通过规则强调"文件夹名即元数据"。GPS 排序在各自父目录内进行，疑似损坏也保留在父目录下。但批量处理时仍需注意。

**建议方案**：
- GUI 中增加"保留原始目录结构"的显式选项（默认开启）
- 扫描前显示将受影响的目录树预览

**优先级**：低

---

### 9. 进度显示精细化

**现状**：相机检测和 GPS 提取显示逐文件进度（`扫描中: 200/2248`），但损坏扫描和文件名恢复仅显示到文件夹级别（`损坏扫描: 沈阳 (3/7)`）。嵌入 JPEG 提取慢，用户盯着文件夹名不知道具体进度。

**建议方案**：
- GUI 给 `scan_folder()` 和 `rename_in_folder()` 传 `progress_cb`
- 进度格式改为 `损坏扫描: 沈阳/DSC_2208.NEF (45/200)`
- 回调频率控制：每 10 个文件刷新一次 UI，避免 Tkinter 过载

**优先级**：中

---

## 已完成的改进

- [x] 规则文件更新：禁止扁平化、禁止合并、禁止删除
- [x] 疑似损坏文件放在父目录内而非顶层
- [x] NEF_EMBEDDED 作为所有文件必检项
- [x] Pillow 只读缩略图的问题：已改用 ExifTool 提取完整嵌入 JPEG
- [x] 后台运行输出缓冲：使用 `python3 -u` + `flush=True`
- [x] 品牌筛选功能（GUI 已内置）
- [x] 离线中国城市坐标匹配（替代被墙的 Nominatim）

---

*创建日期：2026-05-21*
