# MM2R 0.99 interim 数据

本目录由数据管线自动生成，请勿手动修改 JSON 文件。输入来自 `data/raw/mm2r/0.99/candidates` 和 `data/raw/mm2r/0.99/special-equipment`，可在根目录执行 `pnpm data:normalize` 重建。

S-E 的来源快照通过 `pnpm data:collect:se` 单独获取，只保存数值表和获取地点事实。中文参考名与实机汉化名称分开保存；星级改造值逐项保留，不推算来源空缺。固定星级装备的其他星级可能仅是图鉴参考，不能视为实际可获取。

interim 数据不是对本机 0.99 的确认：中文字段可能为空，所有记录仍保留来源状态和引用。只有 `verified_0_99` 的记录才可以进入 `data/processed`。
