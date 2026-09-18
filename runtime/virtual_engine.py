#!/usr/bin/env python3
"""virtual_engine.py — 引擎状态机（参考实现 + 引擎接口模拟器）

引擎状态机：IDLE → FEED → PRINT → OUTPUT → DONE
对应 mfp.afx 通过 pi_engfw_* 与引擎固件 MCU 的交互。

注意（Step 4 修正）：mfp.afx 的动态导出为 110 个
  engine_general_if_layer_public_if_*（bind=1，全在 .text 段），
  即"引擎固件接口"由 mfp.afx 自身提供；Virtual Engine 的职责是
  在其背后的 HAL 层（pi_hal_gpio_*）模拟引擎硬件行为（电机/传感器/加热），
  使 mfp.afx 的 act_prepare_print → act_print_execute 流程能走完。

本文件两个职责：
  1) 引擎状态机权威定义（IDLE→FEED→PRINT→OUTPUT→DONE）
  2) 打印作业生命周期模拟（与 virtual_printer 纸路联动）——
     作为 host 侧参考实现，guest 内由 virtual_hal.so 内嵌等价逻辑执行

用法：
  python runtime/virtual_engine.py --sim
"""
import argparse
import time

# ---- 引擎状态（与 virtual_printer.py 一致） ----
ENGINE_IDLE = 0
ENGINE_FEED = 1
ENGINE_PRINT = 2
ENGINE_OUTPUT = 3
ENGINE_DONE = 4

ENGINE_NAMES = {
    ENGINE_IDLE: "IDLE",
    ENGINE_FEED: "FEED",
    ENGINE_PRINT: "PRINT",
    ENGINE_OUTPUT: "OUTPUT",
    ENGINE_DONE: "DONE",
}

# 引擎固件报告（mfp.afx 期望的打印报告类型，Step 4 证据）
REPORT_PRINT_START = "print_start"      # Recv print start report page_index
REPORT_POWER_CTRL = "power_control"     # Power Control Report
REPORT_PAGE_END = "page_end"
REPORT_JOB_DONE = "job_done"


class VirtualEngine:
    """引擎状态机：驱动纸路推进，依据传感器反馈转移状态"""

    def __init__(self, printer=None):
        self.state = ENGINE_IDLE
        self.page_index = 0
        self.reports = []
        self.printer = printer          # 可选的纸路状态机联动对象
        self.log = []
        self.t0 = time.time()
        self._done_reported = False

    def name(self):
        return ENGINE_NAMES.get(self.state, str(self.state))

    def _set(self, s, reason):
        self.state = s
        self.log.append(f"{self.name()}  <- {reason}")

    def _report(self, rtype, **kw):
        self.reports.append((rtype, kw))
        self.log.append(f"REPORT {rtype} {kw}")

    # ---- 引擎事件（对应 mfp.afx 的 act_* 调用语义） ----
    def on_handshake(self):
        """act_handshake：固件与引擎握手"""
        self._report(REPORT_PRINT_START, page_index=self.page_index)
        self.log.append("HANDSHAKE ok")

    def on_prepare_print(self, page_index=0):
        """act_prepare_print：固件下发打印准备"""
        self.page_index = page_index
        if self.printer:
            self.printer.engine = ENGINE_FEED
            self.printer.insert_paper()
        self._set(ENGINE_FEED, "prepare_print")
        self._report(REPORT_POWER_CTRL, on=True)

    def on_print_execute(self):
        """act_print_execute：固件开始打印（电机+加热）"""
        if self.state == ENGINE_FEED:
            self._set(ENGINE_PRINT, "print_execute")
        if self.printer:
            self.printer.engine = ENGINE_PRINT
            self.printer.motor_on()
            self.printer.heater_on()

    def on_sensor(self, sensor_id, value):
        """传感器反馈（经 pi_hal_gpio_get 呈现给固件）"""
        if self.printer is None:
            return
        if sensor_id == 1 and value and self.state == ENGINE_FEED:
            self._set(ENGINE_PRINT, "sensor1 on")

    def on_paper_out(self):
        """纸路 OUTPUT 完成 → 引擎 OUTPUT → DONE"""
        if self.printer and self.printer.output and self.state != ENGINE_DONE:
            self._set(ENGINE_OUTPUT, "paper out")
            self._set(ENGINE_DONE, "job done")
            self._report(REPORT_JOB_DONE, page_index=self.page_index)

    def drive(self):
        """推进：依据纸路状态自动转移（供本地仿真调用）"""
        if self.printer is None:
            return
        if self.printer.paper == 5 and self.printer.output == 1:   # OUTPUT
            self.on_paper_out()

    def __repr__(self):
        return f"<VirtualEngine {self.name()} page={self.page_index}>"


def simulate():
    """本地仿真：完整打印作业生命周期 IDLE→FEED→PRINT→OUTPUT→DONE"""
    from virtual_printer import PaperPathMachine
    pr = PaperPathMachine()
    eng = VirtualEngine(printer=pr)

    print("== 引擎状态机仿真 ==")
    print(f"初始: {eng.name()}")

    eng.on_handshake()
    eng.on_prepare_print(page_index=1)
    print(f"prepare_print 后: {eng.name()} | paper={pr.snapshot()['paper']}")

    eng.on_print_execute()
    print(f"print_execute 后: {eng.name()} | motor={pr.motor} heater={pr.heater}")

    # 固件轮询传感器，纸路自动推进
    for i in range(8):
        pr.advance(4)
        eng.drive()
        snap = pr.snapshot()
        print(f"  step{i}: {eng.name()} | {snap['paper']} s1={snap['sensor1']} s2={snap['sensor2']}")

    print(f"\n最终: {eng.name()}")
    print("报告序列:")
    for r in eng.reports:
        print("  ", r)
    print("\n日志轨迹:")
    for l in eng.log:
        print("  ", l)


def main():
    ap = argparse.ArgumentParser(description="引擎状态机参考实现")
    ap.add_argument("--sim", action="store_true", help="本地仿真完整打印生命周期")
    args = ap.parse_args()
    if args.sim:
        simulate()
    else:
        print("用 --sim 运行引擎状态机仿真")


if __name__ == "__main__":
    main()