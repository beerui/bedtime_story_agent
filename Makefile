# Bedtime Story Agent — 常用命令入口
#
# 第一次来的用户：敲 `make launch` 看当前卡在哪、下一步做什么。
# 日常使用：`make help` 列全部可用 target。
#
# 所有 target 都是纯粹的封装，具体逻辑在对应的 .py / .sh 里——
# 这个 Makefile 的唯一目的是让用户不用记住文件名。

BASE_URL ?= https://beerui.github.io/bedtime_story_agent

.PHONY: help install launch doctor check test \
        produce produce-one site site-preview \
        backfill-titles backfill-loudness backfill-scenes backfill-all \
        deploy-content deploy-gh-pages clean clean-site

# ---- default ----

help:  ## 列出所有可用命令
	@echo "Bedtime Story Agent — 常用命令"
	@echo ""
	@echo "快速上手:"
	@echo "  make launch         诊断当前仓库状态，看下一步做什么"
	@echo "  make produce        生产 3 期新节目（需 DASHSCOPE_API_KEY）"
	@echo "  make site-preview   本机预览生成的站点"
	@echo ""
	@echo "全部 target:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ---- setup ----

install:  ## 装依赖（首次使用）
	pip install -r requirements.txt

# ---- 诊断 ----

launch:  ## 启动前诊断，告诉你当前卡点在哪
	python3 launch.py

doctor:  ## 全站静态健康诊断（生成后跑）
	python3 doctor.py

doctor-remote:  ## 检查已部署站点: make doctor-remote URL=https://xxx
	python3 doctor.py --remote $(URL)

check: test  ## 跑全套校验（tests + validate + doctor）
	python3 validate.py
	@if [ -d site ]; then python3 doctor.py; fi

test:  ## 跑单元测试（50+ 个）
	python3 -m unittest \
		tests.test_publish_helpers \
		tests.test_cosyvoice_synthesize \
		tests.test_prosody \
		-v

# ---- 内容生产 ----

produce:  ## 随机 3 期新内容（音频 only，约 10 分钟）
	python3 batch.py --count 3 --audio-only

produce-one:  ## 指定主题产 1 期: make produce-one THEME=AI焦虑夜_数字排毒
	python3 batch.py --themes $(THEME) --audio-only

# ---- 站点生成 ----

site:  ## 从 outputs/ 生成可部署站点
	python3 publish.py --copy-audio --base-url $(BASE_URL)

site-preview:  ## 生成并在本机 :8888 预览
	python3 publish.py --copy-audio --base-url $(BASE_URL) --serve

# ---- 回填（对已有期补齐元数据） ----

backfill-titles:  ## 用 LLM 给已有期生成章节标题
	python3 backfill_chapter_titles.py

backfill-loudness:  ## 对已有期跑 LUFS 归一
	python3 backfill_loudness.py

backfill-scenes:  ## 用 Pollinations.ai 补场景图（慢，~15 min）
	python3 backfill_scenes.py

backfill-all: backfill-titles backfill-loudness backfill-scenes  ## 三个回填全跑

# ---- 部署 ----

deploy-content:  ## 推 outputs/ 到 origin/content 分支（Actions 会消费）
	./seed_content.sh

deploy-gh-pages:  ## 直接推 site/ 到 gh-pages（绕过 Actions）
	./deploy.sh $(BASE_URL)

# ---- 清理 ----

clean-site:  ## 删 site/ 重新生成
	rm -rf site

clean: clean-site  ## 删全部生成物（不删 outputs/）
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
