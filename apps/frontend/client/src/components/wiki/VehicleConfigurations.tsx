import { ChevronDown } from 'lucide-react'

import type { VehicleDetails } from '@/data/knowledge/schema'
import {
  formatVehicleMount,
  isFixedVehicleMount,
} from '@/data/knowledge/vehicle-terms'

interface VehicleConfigurationsProps {
  vehicle: VehicleDetails
  vehicleId: string
}

/** 按来源阶段展示独立配置，设计预设不当作升级顺序。 */
export function VehicleConfigurations({
  vehicle,
  vehicleId,
}: VehicleConfigurationsProps) {
  const groups = new Map<number, VehicleDetails['configurations']>()
  for (const setup of vehicle.configurations) {
    const list = groups.get(setup.stage) ?? []
    list.push(setup)
    groups.set(setup.stage, list)
  }
  const isDesign = vehicle.configurations.every(
    (setup) => setup.kind === 'preset',
  )
  const isFixed = vehicle.configurations.every(
    (setup) => setup.kind === 'fixed',
  )
  return (
    <section
      id="configurations"
      aria-labelledby="configurations-heading"
      className="min-w-0 scroll-mt-24"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2
          id="configurations-heading"
          className="text-xl font-semibold text-[var(--mm-navy)]"
        >
          {isDesign ? '设计预设' : '底盘配置'}
        </h2>
        <span className="text-muted-foreground font-mono text-xs">
          {vehicle.configurations.length} 个来源配置
        </span>
      </div>
      <p className="text-muted-foreground mt-3 text-sm leading-7">
        {isDesign
          ? '下列方案都是设计时的预设，不是后续升级阶段。'
          : isFixed
            ? '来源仅列出一个固定配置，单孔改造选项另行保留。'
            : '相同阶段可能包含不同分支，具体升级连接请对照游戏内改造菜单。'}
      </p>
      {[...groups]
        .sort(([left], [right]) => left - right)
        .map(([stage, setups], groupIndex) => (
          <div key={stage} className="mt-6 min-w-0">
            {!isDesign && !isFixed && (
              <h3 className="mb-3 text-xs font-semibold tracking-wide text-[var(--mm-signal)]">
                阶段 {stage}
              </h3>
            )}
            <div className="border-border border-t">
              {setups.map((setup, index) => (
                <details
                  key={setup.id}
                  id={`setup-${setup.id}`}
                  name={`vehicle-${vehicleId}`}
                  open={groupIndex === 0 && index === 0}
                  className="group border-border min-w-0 border-b"
                >
                  <summary className="focus-visible:ring-ring flex min-h-14 cursor-pointer list-none items-center justify-between gap-4 py-4 focus-visible:ring-2 focus-visible:outline-none [&::-webkit-details-marker]:hidden">
                    <span className="min-w-0">
                      <span className="block text-sm font-semibold text-[var(--mm-navy)]">
                        {setup.name_reference}
                      </span>
                      <span className="text-muted-foreground mt-1 block text-xs">
                        {setup.trait_name}
                      </span>
                    </span>
                    <ChevronDown
                      className="text-muted-foreground size-4 shrink-0 transition-transform group-open:rotate-180 motion-reduce:transition-none"
                      aria-hidden="true"
                    />
                  </summary>
                  <div className="min-w-0 pb-5">
                    <p className="text-muted-foreground text-xs break-words">
                      型号原文：{setup.name_ja}
                    </p>
                    <dl className="bg-card border-border mt-4 grid gap-4 rounded border p-4 sm:grid-cols-3">
                      <div>
                        <dt className="text-muted-foreground text-xs">
                          底盘重量
                        </dt>
                        <dd className="mt-1 text-sm font-medium">
                          {setup.weight_raw
                            ? `${setup.weight_raw}t`
                            : '来源未注明'}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-muted-foreground text-xs">特性</dt>
                        <dd className="mt-1 text-sm font-medium">
                          {setup.trait_name}
                          <span className="text-muted-foreground mt-1 block text-xs font-normal">
                            {setup.trait_ja}
                          </span>
                        </dd>
                      </div>
                      <div>
                        <dt className="text-muted-foreground text-xs">
                          物品栏
                        </dt>
                        <dd className="mt-1 text-sm font-medium">
                          {setup.cargo_raw} 格
                        </dd>
                      </div>
                    </dl>
                    <dl className="mt-4 grid gap-x-6 sm:grid-cols-2">
                      {setup.holes_raw.map((hole, holeIndex) => (
                        <div
                          key={holeIndex}
                          className="border-border grid min-w-0 grid-cols-[3rem_minmax(0,1fr)] gap-3 border-b py-3 text-sm"
                        >
                          <dt className="text-muted-foreground">
                            孔 {holeIndex + 1}
                          </dt>
                          <dd className="min-w-0 break-words">
                            {formatVehicleMount(hole)}
                            {isFixedVehicleMount(hole) && (
                              <>
                                <span className="text-muted-foreground ml-2 text-xs">
                                  固定武装
                                </span>
                                <span className="text-muted-foreground mt-1 block text-xs">
                                  {hole}
                                </span>
                              </>
                            )}
                          </dd>
                        </div>
                      ))}
                    </dl>
                    {setup.fixed_armament_raw !== null && (
                      <p className="text-muted-foreground mt-4 text-xs leading-6">
                        固定武装安装限制（来源原文）：{setup.fixed_armament_raw}
                      </p>
                    )}
                    {setup.issues.length > 0 && (
                      <p className="text-muted-foreground mt-3 text-xs leading-6">
                        此配置存在来源空缺或差异，未据此推算数值。
                      </p>
                    )}
                  </div>
                </details>
              ))}
            </div>
          </div>
        ))}
    </section>
  )
}
