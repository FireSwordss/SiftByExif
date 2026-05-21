# SiftByExif

[![Build](https://github.com/FireSwordss/SiftByExif/actions/workflows/build.yml/badge.svg)](https://github.com/FireSwordss/SiftByExif/actions)
[![Version](https://img.shields.io/badge/version-1.0.0-blue)](https://github.com/FireSwordss/SiftByExif/releases)
[![License](https://img.shields.io/badge/license-non--commercial-lightgrey)](LICENSE)

磁盘恢复或正常导出后，按 EXIF 筛分照片：识别相机品牌 → 恢复原始文件名 → GPS 聚类定位 → 损坏扫描。

## 功能

| 功能 | 说明 |
|------|------|
| **相机照片检测** | 从混合文件中筛出相机/手机拍摄的照片，按品牌归类。支持 14 个品牌（Nikon/Canon/Sony/Fujifilm/Olympus/Panasonic/Pentax/Ricoh/Leica/Hasselblad/Samsung/Apple/DJI/GoPro），文件名 + EXIF 双重校验 |
| **恢复原始文件名** | 从 Nikon NEF 的 MakerNote 提取 FileNumber，重命名为 `DSC_XXXX.NEF`（其他品牌计划中） |
| **GPS 聚类排序** | 提取坐标，DBSCAN 聚类，按城市分文件夹。内置 136 个中国城市坐标离线匹配，可选 Nominatim 在线回退 |
| **损坏扫描** | 检查 NEF 文件结构完整性、EXIF 可读性、嵌入 JPEG 预览有效性 |

## 安装

### 直接使用（推荐）

下载 `SiftByExif.exe`，双击运行。无需安装 Python。

### pip（开发者）

```bash
pip install siftbyexif
sift-by-exif
```

### 依赖

- **Windows**: 需要安装 [ExifTool](https://exiftool.org/) 到默认路径（`%LOCALAPPDATA%\Programs\ExifTool\ExifTool.exe`）
- **macOS**: `brew install exiftool`

## 使用方法

1. 选择照片目录
2. 勾选需要的功能，选择品牌（默认全选）
3. 点击「开始扫描」
4. 检查报告，确认后点击「确认并执行」

**注意**：扫描阶段不会修改文件，确认后才执行操作。

## 损坏扫描说明

### 能检测到的情况

| 检查项 | 检测内容 | 严重程度 |
|--------|---------|----------|
| FILE_OPEN | 文件是否可读 | 高 |
| FILE_SIZE | 文件大小是否偏离同批次正常范围（median ± 3×IQR） | 中 |
| NEF_STRUCTURE | TIFF IFD 链是否完整，数据偏移是否超出文件末尾 | 高 |
| MAKERNOTE_SIZE | MakerNote 大小是否偏离同批次正常范围 | 中 |
| EXIF_PARSE | ExifTool 能否正常读取 ShutterCount 和 FileNumber | 中 |
| NEF_EMBEDDED | 嵌入 JPEG 预览是否能完整解码 | 高 |

### 不能检测的情况

- **像素级静默损坏**：JPEG 解码通过但像素数据错误（比特翻转），需与已知良好参考对比
- **RAW Bayer 数据损坏**：传感器原始数据错误但不影响文件结构，需实际显影查看
- **文件部分覆盖**：磁盘恢复中文件被其他数据覆盖，但结构恰巧仍然有效

### 已知误报场景

| 场景 | 原因 |
|------|------|
| **过曝/欠曝照片** | 纯白或纯黑的照片压缩率极高，文件大小明显偏离批次中位数，可能被 FILE_SIZE 误标。属于统计误报，非实际损坏 |
| **长曝光/连拍照片** | 长曝光 NEF 嵌入的 JPEG 预览较大，文件大小可能超出正常范围 |
| **不同拍摄模式** | 同一批次中混入不同分辨率/压缩比设置的 NEF，MakerNote 或文件大小可能偏离统计基线 |

以上场景标记为 MEDIUM，供人工复核。如确认正常，无需处理。

### 设计原则

- 扫描仅标记**疑似**损坏，不确认。最终判断由用户完成
- 被标记文件移入各自父目录下的 `疑似损坏/` 文件夹，**不删除**
- 原目录结构保持不变
- 批次统计按文件夹独立计算，避免不同场景文件相互干扰

## 限制

- 仅在 Nikon NEF 文件上充分测试。其他品牌的检测和扫描功能理论上通用但未验证（见 ROADMAP.md #4）
- 视频文件暂不支持（见 ROADMAP.md #1）
- 离线 GPS 仅覆盖中国大陆城市（见 ROADMAP.md #2）

## 许可

Copyright (c) 2026 FireSwordss. Free for non-commercial use.

详见 [LICENSE](LICENSE)。
