'''
Author: cyl0411 cyl0411@outlook.com
Date: 2025-07-22 13:57:47
LastEditors: cyl0411 cyl0411@outlook.com
LastEditTime: 2025-07-22 14:00:59
FilePath: \RP2040\0721\clock_set.py
Description: 

Copyright (c) 2025 by ${git_name_email}, All Rights Reserved. 
'''
import rp2
from machine import Pin

# PIO 程序：生成 50% 占空比方波
@rp2.asm_pio(set_init=rp2.PIO.OUT_LOW)
def pio_clock_gen():
    wrap_target()
    set(pins, 1) [1]  # 高电平持续 2 周期
    set(pins, 0) [1]  # 低电平持续 2 周期
    wrap()

class AdjustableClock:
    def __init__(self, pin_num=2, rstN_pin=26):
        self.sm = rp2.StateMachine(
            0,                          # 使用状态机 0
            pio_clock_gen,              # PIO 程序
            freq=2_000_000,             # 初始频率 1MHz (2MHz PIO → 1MHz 输出)
            set_base=Pin(pin_num)       # 输出引脚
        )
        self.pin = Pin(pin_num, Pin.OUT)
        self.rstN_pin = Pin(rstN_pin, Pin.OUT)
        self.current_freq = 0
        self.sm.active(0)  # 初始不启动

    def set_frequency(self, target_freq_hz):
        """设置输出频率 (0-20MHz)"""
        if target_freq_hz == 0:
            self.stop()
            return
        
        # PIO 频率 = 2 × 目标频率 (因为 2 周期 = 1 波形周期)
        pio_freq = 2 * target_freq_hz
        
        # 限制频率范围 (RP2040 PIO 最高 ~133MHz)
        pio_freq = min(max(pio_freq, 10), 40_000_000)  # 最低 5Hz，最高 20MHz
        
        self.sm.init(
            pio_clock_gen,
            freq=int(pio_freq),
            set_base=self.pin
        )
        self.sm.active(1)
        self.current_freq = target_freq_hz
        print(f"Clock set to {target_freq_hz} Hz (PIO freq: {pio_freq} Hz)")

    def set_rstN(self, state):
        """设置复位引脚状态"""
        self.rstN_pin.value(state)
        print(f"Reset pin set to {'HIGH' if state else 'LOW'}")

    def stop(self):
        """停止时钟输出"""
        self.sm.active(0)
        self.pin.low()
        self.current_freq = 0
        print("Clock stopped")

# 使用示例
if __name__ == "__main__":
    clock = AdjustableClock(pin_num=2)

    # 设置不同频率
    # clock.set_frequency(1_000_000)  # 1MHz
    clock.set_frequency(20_000_000)   # 20/2MHz (需确保电路支持)
    clock.set_frequency(0)            # 停止