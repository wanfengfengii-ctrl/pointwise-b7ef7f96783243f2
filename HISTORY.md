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

### 结果解析

    result = analysis.changes("zone", old_revision, new_revision, window)
    assert set(result) == {"gained", "lost"}
    for key in ("gained", "lost"):
        areas = result[key]
        assert isinstance(areas, tuple)            # 升序元组，非列表
        assert areas == tuple(sorted(areas))       # 同面积重复项保留
        assert all(type(a) is Fraction and a > 0 for a in areas)
    # 标量守恒：新增面积之和减消失面积之和，等于新版与旧版窗口内面积之差
    balance = sum(result["gained"], F(0)) - sum(result["lost"], F(0))
    assert balance == Region(new_rings).area(window) - Region(old_rings).area(window)

`gained`/`lost` 为空时是 `()`，不是 `None`；元组长度即开集连通分量数，元组内每个 `Fraction` 是一个斑块的精确面积，顺序只按面积，不携带斑块坐标。方向反转时两键内容互换；两个修订号相同直接返回两个空元组，但该修订必须已留存，否则抛 `KeyError`。


## 已提供的非答案夹具

history_checks.py 不实现历史存储、变化几何或连通判定。FailingConnection.arm_commit_failure() 让下一次 connection.commit() 在真实提交前抛 BeforeCommit；它配合现有 storage.atomic 验证事务回滚，不要求产品增加专用故障注入 API。scaffold 子命令只检查样例的标量面积平衡和夹具自身，不声称验证斑块拓扑。

- python3 -B main.py verify：完整原回归（含新增历史测试）加历史夹具核验。
- python3 -B main.py demo：当前归档的保存、替换、重开，并演示修订 2 与 3 的真实历史变化。
- python3 -B history_checks.py scaffold：新增夹具自检，初始树即可运行。
- python3 -B history_checks.py verify：检查公开变化样例、留存启用、提交前失败、替换及文件重开。
- python3 -B history_checks.py demo：比较修订 2 与 3，当前已到修订 4，重开后 gained 和 lost 仍各为 1。
- python3 -B history_walkthrough.py：独立小例，自上而下打印留存、异地增减、退化窗口与同版比较。

## 实现说明（版本交接与连通不变量）

### 历史存储

新增表 `region_history(region_id, revision, rings_json)`，主键为 `(region_id, revision)`；启用状态记在旧 `metadata` 表的 `history_enabled='1'` 键。旧表 `regions1`、`windows1` 的结构与当前版语义完全不变，未启用历史时不创建新表。

- `enable_history()` 在单个 `storage.atomic` 事务内建表、写启用标记并把每个区域当时的当前修订复制进历史表；空归档同样可启用。已启用则立即返回，整库字节级无变化，因此重复调用无副作用，也不会追溯启用前已被覆盖的修订。
- 启用后 `put` 先在事务外完成全部几何校验（`Region(rings)`），再在同一事务内更新 `regions1` 并向 `region_history` 插入同一新修订。任何异常都由 `storage.atomic` 回滚，当前内容、修订号、历史内容与启用状态四项同时保全，失败不占用修订号。
- `read_revision` 只读历史表并经 `normalize_rings` 返回全新的环对象；调用方修改返回值既不能写回归档，也不会影响后续读取。未启用历史、区域缺失或修订未留存均抛 `KeyError`。修订身份是 `(region_id, revision)` 整数对，`Analysis.changes` 以该身份从历史表取两版原始环，与当前版解耦——当前区域已推进到更高修订不影响历史比较。

### 变化几何与开集连通不变量

`changes.py` 把两版所有边先精确裁剪到闭窗口并在窗口边界处劈分，再以全部顶点 x、边与窗口边交点 x、版内及跨版边交点 x 切成垂直条带。条带内任一水平线上两版的奇偶成员关系恒定，因此 gained（interior(B) 减 A）与 lost（反向）在条带内都是若干开梯形，面积为宽度乘开区间高度，全程 `Fraction` 运算。

连通判定遵循两条不变量：

1. 只有二维开集分量被报告，点窗口、线窗口和零面积残段一律不计。
2. 相邻条带的两个开梯形仅在它们的开 y 区间有正长度交叠时才由并查集合并；仅点接触或线接触时交叠长度为零，永不连接，窗口裁剪也能据此把原本相连的区域分成多个斑块。同面积分量各自保留，结果按面积升序排列。

`tests/test_history.py` 另用 `reference_changes.py` 的水平条带分解（独立于生产的垂直分解）交叉验证全部公开样例、反向比较与多组窗口网格，并校验 gained 减负 lost 恒等于两版窗口内面积差。

