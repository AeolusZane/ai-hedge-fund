# Bug Fix Agent 自进化效果评估方案

## 核心假设

Agent 的项目知识越丰富（ExperienceStore / PR Embedding / CodeUnderstandingStore），修复 bug 的效果越好。

## 实验设计

### 对照组设置

| 组别 | 名称 | 知识状态 | 模拟阶段 |
|------|------|---------|---------|
| A | 冷启动 | 三层知识全空 | 第 0 天 |
| B | 新手 | PR Embedding 全量同步，ExperienceStore 10 条 | 第 1-3 天 |
| C | 熟手 | PR Embedding + ExperienceStore 30 条 + 核心模块代码理解 | 第 7 天 |
| D | 老手 | 全部知识灌满，50+ 条经验，全模块代码理解 | 第 30 天 |

### 灌数据方法

**PR Embedding（pr_sync 全量同步）：**
```bash
python -m app.backend.domains.bug_fix.pr_sync \
  --project AI --repo corevo --since 90d --max-prs 200
```

**ExperienceStore（手动写入）：**
- 从历史 bug 的 post-fix 中提取 lesson
- 或手动编写项目常见 bug 模式

**CodeUnderstandingStore（主动预热）：**
- 对核心模块调用 analyze_agent 的代码理解流程
- 或直接写入已知模块的 summary

### 测试集

从项目历史中挑选 20-30 个已修复的 bug，要求：
- 覆盖不同模块（前端/后端/基础设施）
- 覆盖不同 bug 类型（逻辑错误/空指针/并发/性能/安全）
- 覆盖不同难度（单文件修复 / 跨文件修复 / 需要理解业务逻辑）
- 每个 bug 有明确的"正确修复"作为参照

## 量化指标

### 一级指标（核心）

| 指标 | 定义 | 计算方式 | 预期趋势 |
|------|------|---------|---------|
| **首次修复率** | 第一次 patch 就通过测试的比例 | 通过测试的 PR 数 / 总 bug 数 | A→D 递增 |
| **最终修复率** | 经过迭代后成功修复的比例 | 最终修复的 bug 数 / 总 bug 数 | A→D 递增 |
| **平均迭代次数** | 从 Phase 1 到 PR 被接受的平均轮数 | 总迭代次数 / 修复的 bug 数 | A→D 递减 |

### 二级指标（质量）

| 指标 | 定义 | 计算方式 |
|------|------|---------|
| **假设命中率** | Phase 3 的 hypothesis 是否命中真实根因 | 人工判断或对比最终修复 |
| **误改率** | patch 修改了不该改的文件的比例 | 修改的非相关文件数 / 总修改文件数 |
| **回归引入率** | 修复 bug 时引入新 bug 的比例 | 新引入的 bug 数 / 修复的 bug 数 |
| **PR 接受率** | PR 被人工 review 后接受的比例 | 接受的 PR 数 / 提交的 PR 数 |

### 三级指标（知识利用）

| 指标 | 定义 | 计算方式 |
|------|------|---------|
| **Knowledge Recall 命中率** | Phase 1 搜索到相关经验/PR 的比例 | 有命中结果的搜索数 / 总搜索数 |
| **经验引用率** | Phase 3 的假设中实际引用了历史经验的比例 | 引用了经验的假设数 / 总假设数 |
| **代码理解复用率** | Phase 2.5 命中缓存的比例 | 缓存命中数 / 总代码理解请求数 |
| **新经验产出率** | Post-fix 阶段提取出新 lesson 的比例 | 新增 lesson 数 / 修复的 bug 数 |

## 评估方法

### 方法 1：自动化评估（推荐先用）

```python
# 对每个 bug 运行 agent，记录指标
results = []
for bug in test_bugs:
    result = run_bug_fix_agent(bug)
    results.append({
        "bug_id": bug.id,
        "iterations": result.iteration_count,
        "first_fix_success": result.first_patch_passed,
        "final_success": result.final_patch_passed,
        "files_changed": result.changed_files,
        "hypothesis": result.hypothesis,
        "knowledge_hits": result.knowledge_recall_count,
    })
```

### 方法 2：人工评估（更准确但更慢）

- 对每个 bug 的 PR 做人工 review
- 评分维度：修复正确性(1-5) / 代码质量(1-5) / 是否引入回归(yes/no)

### 方法 3：对比评估（最有说服力）

```
同一个 bug：
  Agent A 的 patch vs Agent D 的 patch vs 人类开发者的 patch

三方对比：
  - 修改了哪些文件
  - 修改了多少行
  - 是否命中根因
  - 是否引入回归
```

## 可视化建议

### 学习曲线图

X 轴：已处理的 bug 数量（0, 5, 10, 20, 50）
Y 轴：首次修复率

```
修复率
100% |                                    ●────●
 80% |                              ●────●
 60% |                        ●────●
 40% |                  ●────●
 20% |      ●────●────●
  0% |──●──
     +──────────────────────────────────────────
       0    5   10   20   50   100  200  500
                    已处理 bug 数
```

### 知识层贡献度

对比单独开启每一层知识 vs 全开，看每层的独立贡献：

```
                    首次修复率
仅 ExperienceStore:    45%
仅 PR Embedding:       35%
仅 CodeUnderstanding:  40%
全开:                  70%
全关:                  20%
```

## 里程碑

| 阶段 | 目标 | 验证方式 |
|------|------|---------|
| M1 | 冷启动能跑通 | Agent A 能修复至少 30% 的简单 bug |
| M2 | 知识灌入有提升 | Agent B 比 Agent A 首次修复率高 15%+ |
| M3 | 飞轮转起来 | 连续处理 20 个 bug 后，后半段比前半段效果好 |
| M4 | 接近人类水平 | Agent D 的修复质量接近人类开发者的 patch |

## 数据收集清单

每次实验记录：
- [ ] 实验日期
- [ ] 使用的 agent 版本（commit hash）
- [ ] 知识状态（A/B/C/D）
- [ ] 测试集（哪些 bug ID）
- [ ] 每个 bug 的完整执行日志
- [ ] 一级指标汇总
- [ ] 二级指标汇总
- [ ] 关键发现和改进方向
