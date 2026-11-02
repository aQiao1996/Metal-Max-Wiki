# MM2R 0.99 interim 数据

本目录由数据管线自动生成，请勿手动修改 JSON 文件。输入来自 `data/raw/mm2r/0.99/` 下的 `candidates`、`special-equipment` 和 `c-units`，可在根目录执行 `pnpm data:normalize` 重建。

S-E 的来源快照通过 `pnpm data:collect:se` 单独获取，只保存数值表和获取地点事实。中文参考名与实机汉化名称分开保存；星级改造值逐项保留，不推算来源空缺。固定星级装备的其他星级可能仅是图鉴参考，不能视为实际可获取。

C 装置通过 `pnpm data:collect:c-units` 采集，保存面板改造值、特性和获取地点事实。中文说明区分主动指令与被动效果，保留适用孔位、耗弹和验证限制；命中、回避不换算为实际概率。通信转送品与无法获得的租赁部件单独标明。

interim 数据不是对本机 0.99 的确认：中文字段可能为空，所有记录仍保留来源状态和引用。只有 `verified_0_99` 的记录才可以进入 `data/processed`。
