"""
Generic 320x240 ST7789 SPI display driver
"""

from machine import Pin, SoftSPI, SPI
import st7789py as st7789
import time

TFA = 40
BFA = 40
WIDE = 1
TALL = 0
SCROLL = 0      # orientation for scroll.py
FEATHERS = 1    # orientation for feathers.py

def config(rotation=0):
    """
    配置开发板与屏幕的连接引脚
    """
    sck = Pin(18, Pin.OUT)  # 此处sck对应屏幕SCL
    sda = Pin(19, Pin.OUT) # 此处sda对应屏幕mosi
    res = Pin(20, Pin.OUT)
    dc = Pin(17, Pin.OUT)

    blc = Pin(21,Pin.OUT)     # 此处blc应屏幕BLC
    blc.value(1)               # 设置BLC高电平(点亮屏幕)

    time.sleep(1)

    spi0 = SPI(0, baudrate=50000000, phase = 1, polarity = 1, sck=sck, mosi=sda, miso=None)
    print("SPI0:", spi0)
    return st7789.ST7789(spi0, 240, 240,
        reset=res,
        cs=None,
        dc=dc,
        rotation=rotation)
