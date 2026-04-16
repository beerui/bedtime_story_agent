# 把你的助眠电台提交到各大播客平台

RSS 已经符合 Apple Podcasts / Spotify / 小宇宙 的提交要求（见 `validate.py` 的 RSS 合规检查）。本文档是逐平台操作指南——**从"有站点"到"被数十万人搜到"只差这一步**。

## 开始前准备

| 项 | 值 / 位置 |
|---|---|
| RSS 地址 | `https://<你的域名>/feed.xml`（部署后即可用） |
| 方形封面 | `https://<你的域名>/podcast-cover.png`（1400x1400 自动生成） |
| 主题 | 助眠 / 冥想 / 心理健康 |
| 语言 | 简体中文（`zh-cn`） |
| 分类 | Health & Fitness → Mental Health |
| 显性内容 | No |
| 节目类型 | Episodic（每期独立） |

**必做**：在 `monetization.json` 里填真实邮箱：
```json
"social": { "contact_email": "你@真实邮箱.com" }
```
各平台提交时会验证 `itunes:owner/email` 与注册账号一致——占位符会被拒。

---

## 1. Apple Podcasts Connect（全球第一渠道）

**网址**：https://podcastsconnect.apple.com

**流程**：

1. 用 Apple ID 登录（用你的 `contact_email` 相同 Apple ID 可以省一步）
2. 左上「+ → New Show」
3. 粘 RSS URL：`https://<你的域名>/feed.xml`
4. Apple 会抓取 RSS 并预览节目信息——看看标题/描述/封面都对不对
5. 点 "Submit for Review"
6. **审核时间**：24-72 小时。多数助眠类内容没问题；被拒多半是：
   - 封面有文字/版权图（我们的是自生成，没问题）
   - 节目里有明显脏话（我们助眠内容不会）
   - 描述涉嫌误导（没有）
7. 通过后出现在 Apple Podcasts 搜索（"助眠"、"失眠"、具体主题名）

**收录后 App 链接**：Apple Podcasts → 搜节目名 → 分享 → 复制链接。把这个链接填回 `monetization.json`：
```json
"subscribe": { "apple_podcasts_url": "https://podcasts.apple.com/..." }
```
站点的订阅按钮下次 publish 后就用官方链接而不是 `podcasts://` 协议。

## 2. 小宇宙（Chinese 主场）

**网址**：https://www.xiaoyuzhoufm.com/podcaster

**流程**：

1. 手机装小宇宙 App → 注册账号（手机号）
2. 网页端「创作者中心」登录
3. 「导入播客」→ 选「通过 RSS 导入」
4. 粘 RSS URL → 点"验证"
5. 填补充信息：地区、年龄分级、个人简介（复用 About 页内容即可）
6. 提交审核：**24 小时以内**通过，中文内容小宇宙审得很快
7. 通过后拿到 xiaoyuzhoufm.com 的节目页链接，同样回填到 `monetization.json`

**小宇宙独特优势**：
- 算法推荐机制活跃，新节目能被主动推
- 评论社区友好（相比 Apple 基本无互动）
- 支持竖屏节目页（方封面显示更好）——这也是为什么我们的 `podcast-cover.png` 是 1400x1400

## 3. Spotify for Podcasters

**网址**：https://podcasters.spotify.com

**流程**：

1. 用 Spotify 账号（普通用户账号即可）登录
2. 「Add a podcast」→ 粘 RSS URL
3. Spotify 发送 5 位数验证码到你 RSS 的 `itunes:owner/email`（再次强调：这个邮箱不能是占位符）
4. 输入验证码回到网页
5. 补充：类别 Health & Fitness → Mental Health；Country；Language zh-CN
6. Submit → **审核 1-5 天**

**收录后链接**形如 `https://open.spotify.com/show/<id>`，回填 `monetization.subscribe.spotify_url`。

## 4. Overcast（iOS 用户首选之一）

**网址**：https://overcast.fm/podcasterinfo

Overcast **自动收录所有 Apple Podcasts 上的节目**——只要 Apple 批准了你，不用单独提交，Overcast 会在 24h 内自动拉取。

如果 Apple 还没批准但你想先在 Overcast 露面，可以提交 RSS：
1. 上面 URL → 填 RSS 地址
2. 等 Marco Arment 手动审核（偶尔几天，通常 24h）

## 5. Pocket Casts / Podcast Index（一步到位）

**Podcast Index**（https://podcastindex.org）是一个开放的播客索引，被 Pocket Casts / Castro / Fountain / 等数十个现代客户端自动同步。

**提交流程**：
1. 去 https://podcastindex.org/add
2. 粘 RSS URL
3. Submit——**审核几分钟**
4. 同步后所有依赖 Podcast Index 的客户端都能搜到你

不用给每个客户端单独提交，这是效率最高的一步。

## 6. 喜马拉雅（移动端流量大）

喜马拉雅不直接支持 RSS 导入，需要：
1. https://www.ximalaya.com/ 申请主播认证
2. 审核通过后手动上传每期 MP3（或用它们的批量工具）
3. 每期的音频、标题、简介从 `episodes.json` 里拷贝即可（我们的结构化清单就是为这个准备的）

**自动化选项**：写个脚本读 `episodes.json` → 调喜马拉雅主播 API 批量上传。但主播 API 门槛高，先手动上传几期积累观众再考虑。

## 7. 荔枝 / 网易云音乐播客 / 其它中文平台

大多数中文平台都不支持 RSS 自动同步（版权风控）。策略：
- **荔枝**：个人播客认证后手动上传，受众年轻偏情感类
- **网易云音乐播客**：需要音乐人认证，门槛较高
- **Bilibili**：上传视频版（音频 + 封面静图），覆盖年轻人群

先做 Apple + 小宇宙 + Podcast Index 三家，能覆盖 80% 的中英文听众。

---

## 提交后回填到站点

每家平台给了你节目页链接后，把它们填到 `monetization.json`：

```json
"subscribe": {
  "apple_podcasts_url": "https://podcasts.apple.com/cn/podcast/.../id...",
  "spotify_url": "https://open.spotify.com/show/...",
  "xiaoyuzhou_url": "https://www.xiaoyuzhoufm.com/podcast/...",
  "overcast_url": "https://overcast.fm/..."
}
```

重跑 `publish.py`，首页的订阅按钮就会指向真实平台链接而不是 `podcasts://` 协议兜底——用户体验更直接。

## 常见问题

**Q: 提交后多久能出现在搜索结果？**
- Apple：通过后 4-24 小时索引
- 小宇宙：立即
- Spotify：通过后 24-48 小时

**Q: 封面被说 "too small / wrong dimensions" 怎么办？**
我们生成的是 1400x1400 RGB PNG 200KB，符合所有平台要求。如果被判定太小，可能是 Apple 在测试更大尺寸——可以临时把 `covers.generate_podcast_cover` 的 `size=1400` 改成 `size=3000` 重新生成并部署。

**Q: 我的 RSS 被拒，错误是 "feed contains no episodes"**
- 本地跑 `python3 validate.py` 看是否报 error 级别问题
- `curl -I https://<你的域名>/feed.xml` 确认文件可公开访问且 content-type 正确
- `curl https://<你的域名>/audio/<某期>.mp3` 确认音频 URL 可访问

**Q: 提交前能否用在线工具预检？**
- https://castfeedvalidator.com/ — 专门的 Apple Podcasts RSS 验证器
- https://validator.livewire.io/ — Podcast Index 官方验证

**Q: 如何提交到多个平台而不重复填信息？**
你的 RSS 已经包含所有必要信息。各平台的"节目信息"都是从 RSS 解析的——你只需要 5 个平台各 30 秒粘一下 URL。

---

## 下一步：内容分发之外

提交完成只是获得"**被搜到的资格**"。真正的增长来自：
1. **内容频次稳定**——Actions cron 每日自动生产（已配置）
2. **社交种子**——先手动在朋友圈 / 微博 / 小红书发几次，积累前 100 粉
3. **SEO 长尾**——我们的 18 主题页 + 22 单期页覆盖的搜索词，3-6 个月后开始看到 Google/Baidu 自然流量
4. **平台内推荐**——Apple/小宇宙 有自己的推荐机制；完播率 >60% 的节目会被算法推给更多听众

提交本身只是分发管道的起点。
