# 观测区归档与窗口分析

运行环境为 Python 3.11，仅使用标准库，无安装步骤。所有坐标按有理数精确计算，结果面积是 fractions.Fraction。CLI 的数据库只在测试临时目录中创建并自动清理。

运行完整回归：python3 -B main.py verify
运行真实保存、替换与重开演示：python3 -B main.py demo
也可直接运行：python3 -B -m unittest discover -s tests -v

## 输入与区域语义

坐标接受 int、Fraction 或可被 Fraction 解析的十进制/分数字符串；拒绝 float 和 bool。点为二元列表或元组。区域为至少一个显式闭合环，每环至少三条边。环的顶点顺序、起点、方向、重复闭合点和非重叠的共线中间顶点均保留。不允许零长度边或任意两边共线重叠。允许自交、不同环相交和顶点接触。

区域为所有环按奇偶规则填充所得内部的闭包，方向不影响结果。每条输入边都是原区域边界的一部分。窗口顺序为 (xmin,ymin,xmax,ymax)，是闭矩形；允许点或线窗口，拒绝反向窗口。相交包括仅接触边界，也包括退化窗口位于区域内部。面积为二维面积，所以退化窗口的面积为零。

## 公开调用

storage.connect(path) 返回自动提交模式的 SQLite 连接；调用者负责 close。storage.create_legacy(db) 在空库创建完整旧格式，不重置已有库。samples.build_legacy(db) 在空库构建四个真实区域及四个保存任务，返回 Archive。

Archive(db).put(region_id,rings) 原子新增或替换区域，返回从 1 开始的递增修订号。ID 为非空字符串，几何拒绝时不改变现有记录。read(id) 返回原始闭合环序列，坐标规范为 Fraction，不做重排或几何修复。revision(id) 返回修订号，ids() 返回排序 ID 元组。不存在的 ID 抛 KeyError。

Analysis(archive).query(window,region_ids=None) 返回按 ID 排序的 Hit 元组。Hit 有 region_id、area、boundary 三个字段，分别是观测区 ID、区域与窗口的精确相交面积、闭窗口是否与原区域边界有公共点。每个命中区域只返回一次；显式重复 ID 会去重。省略 ID 时查询当前全部区域，显式空序列得到空结果；不存在的 ID 抛 KeyError。位于洞内部的窗口不命中，接触洞边界则命中且可为零面积。

save(name,window,region_ids=None) 原子保存或替换具名任务。它绑定保存时的窗口及排序去重后的 ID 集合；省略 ID 时固定保存时的全部 ID。任务不固定几何版本，run(name) 总是分析这些 ID 的当前区域。task(name) 返回 (window,ids)，tasks() 返回排序任务名。不存在的任务抛 KeyError。既有 Analysis 对象每次调用读取当前归档，不缓存区域；新增区域不会自动进入已保存任务。

库的使用范围是维护窗口内单工作者。一次 query/run 内不允许其他调用交错修改同一连接或数据库。连接不跨线程共享。

## 旧持久格式

metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) 保存 storage_version='1'。
regions1(region_id TEXT PRIMARY KEY,revision INTEGER NOT NULL CHECK(revision>0),rings_json TEXT NOT NULL) 保存当前区域。
windows1(name TEXT PRIMARY KEY,window_json TEXT NOT NULL,ids_json TEXT NOT NULL) 保存任务。

rings_json 是环/点/坐标三层 JSON 数组，坐标为规范分数字符串，包含原闭合点及原序列。window_json 是四个有理数字符串，ids_json 是 ID 数组。Archive 当前支持版本 1，遇其他版本明确报错。

storage.atomic(db,before_commit=None) 提供 BEGIN IMMEDIATE、提交及异常回滚，覆盖 DDL 和 DML。零参数 before_commit 回调在提交前执行，异常同样回滚；不支持嵌套事务。调用者应在这一设施内部执行多表发布，不使用会隐式提交的 executescript。该设施不处理并发工作者或在线切换。

## 两代离线依赖

vendor.ring1.Region(rings) 是当前归档依赖，提供 contains(point)、area(window=None)、intersects(window)、boundary_touches(window)。它按奇偶规则计算标量结果，rings 属性保留输入序列。面积通过精确截线长度积分计算，不提供简单面输出或持久化。

vendor.face2.Face(vertices) 只接受一个显式闭合、正面积的简单环；拒绝自交、非相邻边接触和重叠边，允许凹面及任意方向。area(window=None)、contains、intersects、boundary_touches 使用同样的坐标和闭窗口约定，但 boundary_touches 指该简单面自身的边界。

vendor.face2.install(db) 创建 sdk2_faces(face_key TEXT PRIMARY KEY,vertices_json TEXT NOT NULL)。FaceStore(db) 的 put(key,vertices)、read(key)、keys()、delete(key) 提供原生简单面存取。put 校验后原子替换，失败保全旧值，read 返回 Face，缺失键抛 KeyError，删除缺失键无副作用。vertices_json 为闭合点数组，坐标是有理数字符串。SDK2 不依赖 SDK1。该表不带观测区、环序列或任务语义；旧库构造器不创建此表。

## 有限样例

bow 的环是 (0,0)→(2,2)→(0,2)→(2,0)→(0,0)，总面积 2，上下半窗口各为 1。内部竖线 x=1、y∈[1/4,1/2] 命中区域，面积为 0，boundary 为 false。

donut 为 [4,8]×[0,4] 外环和 [5,7]×[1,3] 内环，奇偶面积 12。洞的闭窗口面积为 0，但接触边界。
cross 为 [0,3]×[0,3] 与 [2,5]×[1,4] 的奇偶区域，面积 14，重叠部分内部不属于区域。
ell 为凹 L 形区域，面积 5。

upper/lower 固定 bow 的上下半窗口，hole 固定 donut 的洞窗口，survey 固定四个区域与总包围窗口。demo 将 bow 替换为面积 8 的矩形，既有 upper 任务结果从 1 变为 2，关闭连接后重开仍为 2。
