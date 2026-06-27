# Browser 计划索引

本目录存放 `browser_interact` 相关规划文档。

这些文档的目标是：

- 明确浏览器工具、网页端 live view、VNC 投屏与沙箱接入边界
- 说明当前仓库缺口、推荐技术栈和实现顺序
- 给后续实现者一份无需再做关键架构决策的落地说明

实现完成后，应将稳定规则分别沉淀到：

- `docs/team/`：长期工程规范与安全边界
- `docs/tools/`：工具说明、触发边界、模型约束
- 模块 README：运行时结构、依赖、部署方式与维护说明

## 当前文档

- [browser_interact VNC 与沙箱接入详细方案](01-browser-interact-vnc-sandbox-plan.md)
