# 企业智脑 — Enterprise Brain

> **🚨 最高优先级规则：每完成一个文件/步骤后，必须停下来等用户审核。用户说"继续"才能进行下一步。严禁连续写多个文件，严禁在用户未审核的情况下运行代码。**

## 项目简介
私有化部署的企业 AI 智能分析平台。客户装在自己服务器上，上传公司文档和经营数据，AI 自动知识问答、数据分析、生成图表报告、异常监控。数据永不离开客户机器。

## 技术栈
- 后端: FastAPI + LangGraph + Chroma RAG
- 模型: Ollama (本地) + DeepSeek API (备用)
- 前端: Vue 3 + Element Plus
- 数据: pandas + matplotlib
- 部署: setup.sh + Docker

## 项目结构
```
企业智脑/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── agents/               # Multi-Agent (Orchestrator + Doc + Data + Chart + Export)
│   ├── api/v1/               # 聊天 API / 文档上传 / 告警
│   ├── models/               # Pydantic schemas
│   ├── common/               # 日志 / 配置
│   ├── rag/                  # 文档解析 / 向量检索
│   └── tools/                # 工具函数
├── frontend/                 # Vue 3
├── static/                   # 生成的图表
├── docs/                     # 文档
├── .env                      # 环境变量
└── pyproject.toml            # uv 依赖管理
```

## 开发流程
按 `开发计划-企业智脑.md` 执行，当前处于 **第一阶段 Day 2**。

## 已完成
- [x] 项目骨架 + .env
- [x] app/main.py (FastAPI 入口)
- [x] app/common/logger.py
- [x] app/rag/loader.py (PDF/Word/TXT 加载)
- [x] app/rag/retriever.py (向量化 + Chroma + 检索)

## 核心原则
- 先让用户审阅代码，确认后再运行测试
- 不跳过步骤，不一次写一堆
- 私有化部署 = 一台机器一个企业，物理隔离
- 数据不出客户服务器
