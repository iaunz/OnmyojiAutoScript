# ACTIVITYSHIKIGAMI 奖励结算超时排查（2026-09-12）

- 状态：DONE_WITH_CONCERNS。代码、回归测试和原始截图离线回放已验证；未连接实际游戏运行。
- 输入：`dev/260912-error/log.txt`、`picture1.png`、`picture2.png`，以及 `config/oas2.json` 的 `activity_shikigami` 配置。分支为 `dev`，排查时 HEAD 为 `e70f40ee`。

## 症状与根因

日志在点击挑战后已经进入 `run_general_battle`，两次点击准备，最后记录 `Start battle process`。因此本次卡点是战后奖励结算。用户截图 `picture2.png` 显示“获得奖励”弹窗。

`battle_wait_strategy` 原先只让第一个实例初始化类级 `battle_wait_plan`。后续装饰器的配置存入 `_temp_battle_wait_plan`，但正常调用不会使用它，只有显式进入 `with` 才会生效。先加载 EvoZone 等普通任务、再加载 ActivityShikigami 时，活动任务虽然声明 `success='activity'`，实际却调用 `_bw_success_default`。反向加载也会使普通任务误用活动策略。

复现脚本先导入 `tasks.EvoZone.script_task.ScriptTask`，再导入 `tasks.ActivityShikigami.script_task.ScriptTask`，拦截 `battle_wait_with_strategy` 并检查传入策略：修复前活动任务的 `success` 为 `default`，修复后为 `activity`，普通任务保持 `default`。

原始截图使用现有 `RuleImage` 的 RGB 模板匹配结果：

| 模板 | picture2 匹配度 | 阈值 | 结果 |
| --- | ---: | ---: | --- |
| I_UI_REWARD | 0.99397 | 0.73 | 匹配 |
| I_WIN | 0.29829 | 0.80 | 不匹配 |
| I_GREED_GHOST | 0.08016 | 0.80 | 不匹配 |
| I_REWARD | -0.23773 | 0.80 | 不匹配 |
| I_REWARD_GOLD | 0.49201 | 0.80 | 不匹配 |
| I_REWARD_GOLD_SNAKE_SKIN | 0.39812 | 0.80 | 不匹配 |

奖励详情模板 I_END_FIX_1/2/3 均未误匹配；picture1 也未匹配 I_UI_REWARD。现有活动奖励模板有效，无须调整图片、阈值或用户配置。

## 修改

- `tasks/Component/GeneralBattle/battle_wait.py`：每个装饰器持有自己的策略和选项；显式 `with` 覆盖通过 ContextVar 保存，并在退出或异常时恢复；随机操作只扩展当前调用的策略，选项不会跨任务或跨调用修改。
- `tests/tasks/Component/GeneralBattle/test_battle_wait.py`：新增双向加载顺序、随机操作开关、活动奖励关闭、嵌套上下文异常恢复和选项隔离测试。已有测试中的模拟成功处理器补充设置 `bw_ctx.success=True`，与当前返回战斗结果的语义一致。

## 验证

1. 修复前完整 `tests` 基线为 25 passed、3 failed：两个旧测试的模拟处理器没有设置成功状态，一个选项测试暴露了类级 options 共享问题。
2. 先新增五个针对根因的用例，修复前全部失败，其中活动奖励回放停留在 `Start battle process`，达到截图次数上限。
3. 修复后运行 `toolkit/python.exe -m pytest tests -q`：35 passed，2 条已有的 Pydantic 弃用警告。
4. 原始截图离线回放：先导入 EvoZone 再导入 ActivityShikigami；使用实际活动任务的战斗等待实现和 `RuleImage.match`，仅替换截图及设备操作；按 oas2 的配置关闭随机战斗操作。输入 picture2，模拟关闭弹窗后切换到 picture1。6 次截图、1 次位于排除区域之外的点击，返回 True，日志依次为 `Start battle process`、`Win battle`、`Get all reward`、`Battle done`。这验证了截图识别和控制流程，实际设备点击后的页面变化仍需游戏内复测。
5. `git diff --check` 通过。

## 相关历史与运行环境

策略框架由 `745ce5eb` 引入；`5a3eaddc` 增加选项支持。后续已有多次活动奖励模板与弹窗处理修正，本次根因是策略选择受任务加载顺序影响。

测试使用仓库自带的 Python 3.10。为运行测试安装 pytest 7.4.4；安装过程中发现新版本 pytest 会升级 packaging 并与 uiautomator2 冲突，已将 packaging 恢复到项目要求的 20.9。项目依赖文件未修改。
