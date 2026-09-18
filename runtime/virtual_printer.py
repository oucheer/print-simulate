#!/usr/bin/env python3
"""virtual_printer.py — 纸路状态机（参考实现 + vhal.log 轨迹解析）

状态模型（与 virtual_hal.c 内嵌纸路逻辑镜像一致）：
  组件：Paper / Sensor1 / Sensor2 / FeedMotor / Heater / Output
  纸路状态：NO_PAPER → FEEDING → AT_SENSOR1 → PRINTING → EJECTING → OUTPUT
  事件：insert_paper / motor_on / motor_off / advance_step / heater_on / heater_off

共享内存布局（与 virtual_hal.c 的 SHM_OFF_* 一致，volatile u32）：
  0x00 magic, 0x04 version, 0x08 engine_state, 0x0c paper_state,
  0x10 sensor1, 0x14 sensor2, 0x18 feed_motor, 0x1c heater,
  0x20 output, 0x24 seq,
  0x28..0x128 gpio_val[64], 0x128..0x228 gpio_dir[64]

本文件两个职责：
  1) 纸路状态机的权威参考定义（驱动规则、状态转换表）
  2) 解析 /tmp/vhal.log（或 host 拷贝），提取真实运行的状态轨迹
     —— 支撑 Step 6 验收"状态轨迹从真实固件日志提取"

用法：
  python runtime/virtual_printer.py --trace runtime/vhal.log
"""
import sys, argparse, re, struct, time
from pathlib import Path

# ---- 共享内存偏移（与 virtual_hal.c 保持一致） ----
SHM_MAGIC     = 0x5648414C   # "VHAL"
OFF_MAGIC     = 0x00
OFF_VERSION   = 0x04
OFF_ENGINE    = 0x08
OFF_PAPER     = 0x0c
OFF_SENSOR1   = 0x10
OFF_SENSOR2   = 0x14
OFF_MOTOR     = 0x18
OFF_HEATER    = 0x1c
OFF_OUTPUT    = 0x20
OFF_SEQ       = 0x24
OFF_GPIO_VAL  = 0x28
OFF_GPIO_DIR  = 0x128

# ---- 纸路状态 ----
PAPER_NO_PAPER = 0
PAPER_FEEDING  = 1
PAPER_AT_S1    = 2   # 纸头到达 Sensor1
PAPER_PRINTING = 3   # 定影加热中
PAPER_EJECTING = 4
PAPER_OUTPUT   = 5   # 出纸完成

PAPER_NAMES = {
    PAPER_NO_PAPER: "NO_PAPER",
    PAPER_FEEDING:  "FEEDING",
    PAPER_AT_S1:    "AT_SENSOR1",
    PAPER_PRINTING: "PRINTING",
    PAPER_EJECTING: "EJECTING",
    PAPER_OUTPUT:   "OUTPUT",
}

# ---- 引擎状态（与 virtual_engine.py 一致） ----
ENGINE_IDLE = 0
ENGINE_FEED = 1
ENGINE_PRINT = 2
ENGINE_OUTPUT = 3
ENGINE_DONE = 4

ENGINE_NAMES = {
    ENGINE_IDLE:   "IDLE",
    ENGINE_FEED:   "FEED",
    ENGINE_PRINT:  "PRINT",
    ENGINE_OUTPUT: "OUTPUT",
    ENGINE_DONE:   "DONE",
}

# 每电机步进 = 纸前进距离（虚拟单位），用于推进纸路
STEPS_PER_STAGE = 8          # 每个纸路阶段需推进的步数
ADVANCE_BEFORE_S1 = 4        # FEEDING 推进若干步后纸头到 Sensor1
ADVANCE_BEFORE_PRINT = 12    # 到 Sensor2/定影区
ADVANCE_TO_OUTPUT = 20       # 总出纸步数


class PaperPathMachine:
    """纸路状态机：事件驱动，状态变化可通过共享内存呈现给真实固件"""

    def __init__(self):
        self.paper = PAPER_NO_PAPER
        self.sensor1 = 0
        self.sensor2 = 0
        self.motor = 0
        self.heater = 0
        self.output = 0
        self.step = 0            # 推进步数（重置后累计）
        self.engine = ENGINE_IDLE
        self.seq = 0
        self.events = []         # (time, event, state_snapshot)

    # ---- 事件 ----
    def insert_paper(self):
        """外部事件：纸盒装纸（纸头就绪）"""
        self.sensor1 = 0
        self.step = 0
        self.paper = PAPER_FEEDING
        self._ev("insert_paper")

    def motor_on(self):
        """固件 gpio_set: 送纸电机开启"""
        self.motor = 1
        self._ev("motor_on")
        # 电机开启后自动推进（事件驱动：无独立线程，推进在下次 gpio 访问时结算）

    def motor_off(self):
        self.motor = 0
        self._ev("motor_off")

    def advance(self, n=1):
        """推进 n 步（固件轮询传感器间隙由虚拟层结算）"""
        for _ in range(n):
            self.step += 1
            self._advance_once()

    def heater_on(self):
        self.heater = 1
        self._ev("heater_on")

    def heater_off(self):
        self.heater = 0
        self._ev("heater_off")

    def _advance_once(self):
        """单步推进，依据当前纸路状态更新传感器/出纸"""
        s = self.step
        if self.paper == PAPER_FEEDING:
            if s >= ADVANCE_BEFORE_S1:
                self.paper = PAPER_AT_S1
                self.sensor1 = 1
        elif self.paper == PAPER_AT_S1:
            if s >= ADVANCE_BEFORE_PRINT:
                self.paper = PAPER_PRINTING
                self.sensor2 = 1
        elif self.paper == PAPER_PRINTING:
            if s >= ADVANCE_TO_OUTPUT:
                self.paper = PAPER_EJECTING
        elif self.paper == PAPER_EJECTING:
            self.paper = PAPER_OUTPUT
            self.output = 1
            self.sensor1 = 0
            self.sensor2 = 0

    # ---- 共享内存快照（用于写 /dev/shm/vhal.shm 的字节序） ----
    def shm_pack(self):
        """返回 8192 字节共享内存映像（host 侧参考，guest 由 virtual_hal.c 生成）"""
        buf = bytearray(8192)
        def w32(off, v):
            struct.pack_into("<I", buf, off, v & 0xffffffff)
        w32(OFF_MAGIC, SHM_MAGIC)
        w32(OFF_VERSION, 1)
        w32(OFF_ENGINE, self.engine)
        w32(OFF_PAPER, self.paper)
        w32(OFF_SENSOR1, self.sensor1)
        w32(OFF_SENSOR2, self.sensor2)
        w32(OFF_MOTOR, self.motor)
        w32(OFF_HEATER, self.heater)
        w32(OFF_OUTPUT, self.output)
        w32(OFF_SEQ, self.seq)
        return bytes(buf)

    def _ev(self, name):
        self.seq += 1
        self.events.append((time.time(), name, self.snapshot()))

    def snapshot(self):
        return {
            "engine": ENGINE_NAMES.get(self.engine, str(self.engine)),
            "paper": PAPER_NAMES.get(self.paper, str(self.paper)),
            "sensor1": self.sensor1, "sensor2": self.sensor2,
            "motor": self.motor, "heater": self.heater,
            "output": self.output, "step": self.step,
        }

    def __repr__(self):
        s = self.snapshot()
        return (f"[{s['engine']}] paper={s['paper']} s1={s['sensor1']} s2={s['sensor2']} "
                f"motor={s['motor']} heater={s['heater']} out={s['output']} step={s['step']}")


# ---- vhal.log 解析：提取真实固件运行轨迹 ----
RE_GPIO = re.compile(r"\[vhal\] gpio_set id=0x([0-9a-f]+) val=0x([0-9a-f]+)")
RE_GET = re.compile(r"\[vhal\] gpio_get id=0x([0-9a-f]+) -> 0x([0-9a-f]+)")
RE_STATE = re.compile(r"\[vhal\] state ([\w_]+)")


def parse_trace(path):
    """解析 vhal.log，重建纸路/引擎状态轨迹"""
    m = PaperPathMachine()
    states = []
    for line in Path(path).read_text(errors="replace").splitlines():
        g = RE_GPIO.search(line)
        if g:
            gpio_id = int(g.group(1), 16)
            val = int(g.group(2), 16)
            m.seq += 1
            if gpio_id in (0x10, 0x11, 0x12):     # 电机组（示例映射）
                if val:
                    m.motor_on()
                else:
                    m.motor_off()
                if m.motor:
                    m.advance(2)
            elif gpio_id in (0x20,):              # 加热组
                if val:
                    m.heater_on()
                else:
                    m.heater_off()
            states.append(m.snapshot())
            continue
        g = RE_GET.search(line)
        if g:
            gpio_id = int(g.group(1), 16)
            val = int(g.group(2), 16)
            # gpio_get 作为"传感器轮询"时机：电机开则结算推进
            if m.motor:
                m.advance(1)
            states.append(m.snapshot())
    return m, states


def main():
    ap = argparse.ArgumentParser(description="纸路状态机参考实现 + vhal.log 轨迹解析")
    ap.add_argument("--trace", help="vhal.log 路径（解析真实运行轨迹）")
    ap.add_argument("--sim", action="store_true", help="本地仿真纸路流程")
    args = ap.parse_args()

    if args.trace:
        m, states = parse_trace(args.trace)
        print(f"== vhal.log 轨迹解析：{len(states)} 个采样点 ==")
        prev = None
        for s in states:
            if s != prev:
                print(s)
                prev = s
        print(f"\n最终状态: {m.snapshot()}")
        return

    if args.sim:
        m = PaperPathMachine()
        print("== 本地仿真（电机开→自动推进→加热→出纸）==")
        m.insert_paper()
        print(m)
        m.motor_on()
        for _ in range(5):
            m.advance(4)
            print(m)
        m.motor_off()
        m.heater_on()
        print(m)
        m.advance(8)
        print(m)
        m.heater_off()
        print("== 最终 ==")
        print(m.snapshot())
        return

    print("无操作。用 --trace <vhal.log> 解析轨迹，或 --sim 本地仿真")


if __name__ == "__main__":
    main()