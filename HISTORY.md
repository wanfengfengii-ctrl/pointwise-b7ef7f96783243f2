# 历史修订与覆盖变化

本题在现有归档上新增历史变化分析。CONTRACT.md 的输入限制、奇偶闭区域语义、原接口与单工作者边界继续有效；不做 SDK 迁移。现有程序尚未提供下面三个新入口。原测试及已有文件均应保留。

## 历史入口

- Archive.enable_history() 返回 None。一次事务中启用留存并保存每个区域当时的当前修订；空归档也能启用。启用状态持久保存。重复调用无副作用，不恢复启用前已经被覆盖的修订。
- 启用后 Archive.put 的返回值及当前区域行为不变，但每次成功修改同时保留新修订。校验或提交前异常必须保全当前内容、修订号、历史内容及启用状态；失败操作不占用修订号。未启用时仍沿用原行为。
- Archive.read_revision(id,revision) 返回指定修订的原始闭合环序列，坐标为 Fraction，保留顺序、方向和闭合点。返回值不能因后续 put 改变，也不能反过来修改归档。不存在或未留存的区域/修订抛 KeyError。关闭重开后结果保持。历史表结构由实现自行选择，不改变旧库原有数据和保存任务的当前版语义。

## 变化入口

Analysis.changes(id,old_revision,new_revision,window) 返回
{'gained': (Fraction(...), ...), 'lost': (Fraction(...), ...)}。
两个元组各自按面积升序排列，重复面积不去重；没有分量时为 ()。

令 A、B 分别为指定旧版、新版的奇偶闭区域，W 为矩形窗口。
gained 报告 (interior(B) 减 A) 交 interior(W) 的每个连通分量面积；
lost 交换 A、B。只报告二维开集分量，面积严格为正。点接触或线接触不能连接两个分量；窗口裁剪也可能把原本相连的区域分开。这里的 interior 是二维内部，因此点或线窗口返回两个空元组。相同修订比较返回空结果，仍须确实存在该留存修订；缺失区域或修订抛 KeyError。

沿用原有理数坐标、几何输入及窗口校验，所有结果面积使用 Fraction。每版单独满足原输入限制；两版之间允许完整重合、反向重合、部分共线重叠和接触，不得合在一起按单版非法重叠拒绝。每次比较两版合计至多 160 条边。一次比较不交错写入，允许全量重算两版，不要求增量索引、并发恢复或斑块多边形导出。

## 调用样例

以下示例假定实现已经完成：

    from fractions import Fraction as F
    from archive import Archive
    from analysis import Analysis
    from storage import connect, create_legacy
    from history_examples import box

    db = connect(":memory:")
    create_legacy(db)
    archive = Archive(db)
    r1 = archive.put("zone", box(0, 0, 1, 1))
    archive.enable_history()
    r2 = archive.put("zone", box(2, 0, 3, 1))
    assert Analysis(archive).changes("zone", r1, r2, (-1, -1, 4, 2)) == {
        "gained": (F(1),), "lost": (F(1),)}
    db.close()

两版总面积都为 1，变化结果仍分别有新增和消失。另一例：旧版为 [10,11]×[10,11]，新版为 samples.BUTTERFLY，窗口 (-1,-1,3,3)，应得 gained=(F(1),F(1))、lost=()，不能合成一个面积 2 的斑块。其余有明确解析预期的输入见 history_examples.py：含洞填平、部分共边、人工切线、窗口移除连接部及分数面积。

## 已提供的非答案夹具

history_checks.py 不实现历史存储、变化几何或连通判定。FailingConnection.arm_commit_failure() 让下一次 connection.commit() 在真实提交前抛 BeforeCommit；它配合现有 storage.atomic 验证事务回滚，不要求产品增加专用故障注入 API。scaffold 子命令只检查样例的标量面积平衡和夹具自身，不声称验证斑块拓扑。

- python3 -B main.py verify：完整原回归。
- python3 -B main.py demo：当前归档的保存、替换和重开。
- python3 -B history_checks.py scaffold：新增夹具自检，初始树即可运行。
- python3 -B history_checks.py verify：完成开发后检查公开变化样例、留存启用、提交前失败、替换及文件重开。
- python3 -B history_checks.py demo：完成开发后展示比较修订 2 与 3，当前已到修订 4，重开后 gained 和 lost 仍各为 1。

公开检查是起点，不能替代独立小例参照及必要边界回归。交付简短说明，解释修订身份到分析的交接及开集连通判定不变量。沿用已有 .pointwise-runtime.json，把完整原回归、新功能核验和真实历史变化演示接通；该清单已有 version、kind、setup、verify、demo 的实际格式。初始清单仍运行原能力，开发完成后再更新核验和演示入口。
