import machine
import time
import array
import micropython
import utime
import clock_set as clockgen
# 从原始代码中复制的常量定义
pixelX = 55
pixelY = 63

# 全局变量 (volatile 等效)
last_interrupt_time = 0
interrupt_time_difference = 0
is_first_interrupt = True
pixel_collected = False
event_act = False

# 常量定义 (来自Iaso.h)
IasoOpShift = 18
IasoDevShift = 16
IasoBits = 20

IasoWr = 0x40000
IasoRd = 0x80000
IasoMem = 0x20000
HeloosReg = 0x00000



MODE_REG = 20
# bit0 ->  1:dvp frame    0: edge frame
# bit1 ->  1:dvp clk on   0: dvp clk off
# bit2 ->  1:jls clk on   0: jls clk off
# bit3 ->  1:edge clk on  0: edge clk off
# bit4 ->  1:tile clk on  0: tile clk off
# bit5 ->  1:pos X on     0: pos X off
# bit6 ->  1:pos Y on     0: pos Y off

# 0 1 2 3 
WINLEN_REG = 0
# 4 5 6 7 
RDOUTDLY_REG = 4

Pixel_X_Heat = 8
Pixel_Y_Heat = 9

SUB_BGD_REG = 10

# 11 12
delayN_pixrst = 11
# 13 14 
delayS_pixrst = 13

# 15 16
delayN_rampen = 15
# 17 18 
delayS_rampen = 17

# 200 201
delayN_Aryrst = 200
# 202 203 
delayS_Aryrst = 202

JLS_NEAR = 21
# 22 23 24
EDG_THR = 22

# 25 - 88
Block_DIFF = 25

# 89-152
Tile_Value = 89


#frame_rdout
START_RD = 1
VSYNC    = 0
HSYNC    = 28
PCLK     = 27
PIX_D7 = 8
PIX_D6 = 9
PIX_D5 = 10
PIX_D4 = 11
PIX_D3 = 12
PIX_D2 = 13
PIX_D1 = 14
PIX_D0 = 15

#scan chain

SCAN_HEAL = 6

SCAN_IN = 7
SCAN_OUT = 21
SCAN_CLK = 2
SCAN_EN  = 22

# ====================== Iaso 类实现 ======================
class Iaso:
    def __init__(self, mosi_pin, miso_pin, sck_pin):
        self.mosi = machine.Pin(mosi_pin, machine.Pin.OUT)
        self.miso = machine.Pin(miso_pin, machine.Pin.IN)
        self.sck = machine.Pin(sck_pin, machine.Pin.OUT)
        
        # SPI 配置默认值
        self.bit_order = 1  # MSBFIRST=1, LSBFIRST=0
        self.data_mode = 2   # SPI_MODE2
        self.clock_div = 128
        self.delay = self.clock_div // 2
        
        # 根据SPI模式设置时钟极性
        if self.data_mode in [0, 1]:
            self.ckp = 0
        else:  # mode 2 or 3
            self.ckp = 1
            
        if self.data_mode in [0, 2]:
            self.cke = 0
        else:  # mode 1 or 3
            self.cke = 1

    def set_bit_order(self, order):
        self.bit_order = 1 if order == 1 else 0  # MSBFIRST or LSBFIRST

    def set_data_mode(self, mode):
        self.data_mode = mode
        # 更新时钟极性
        if mode == 0:
            self.ckp = 0
            self.cke = 0
        elif mode == 1:
            self.ckp = 0
            self.cke = 1
        elif mode == 2:
            self.ckp = 1
            self.cke = 0
        elif mode == 3:
            self.ckp = 1
            self.cke = 1

    def set_clock_divider(self, div):
        self.clock_div = div
        self.delay = max(1, div // 2)  # 确保延迟至少为1

    def transfer(self, val):
        out = 0
        # 处理位序
        if self.bit_order == 1:  # MSBFIRST
            val = ((val & 0x01) << 7) | ((val & 0x02) << 5) | \
                  ((val & 0x04) << 3) | ((val & 0x08) << 1) | \
                  ((val & 0x10) >> 1) | ((val & 0x20) >> 3) | \
                  ((val & 0x40) >> 5) | ((val & 0x80) >> 7)

        # 执行8位传输
        for bit in range(8):
            self.sck.value(self.ckp ^ 1)  # 时钟起始边沿
            
            # 延迟
            for _ in range(self.delay):
                pass
            
            # 在时钟前沿采样/输出
            if self.cke:  # 前沿采样
                bval = self.miso.value()
                if self.bit_order == 1:  # MSBFIRST
                    out = (out << 1) | bval
                else:
                    out = (out >> 1) | (bval << 7)
            else:         # 前沿输出
                self.mosi.value(1 if (val >> bit) & 1 else 0)
            
            # 延迟
            for _ in range(self.delay):
                pass
                
            self.sck.value(self.ckp)  # 时钟结束边沿
            
            # 延迟
            for _ in range(self.delay):
                pass
            
            # 在时钟后沿采样/输出
            if not self.cke:  # 后沿采样
                bval = self.miso.value()
                if self.bit_order == 1:  # MSBFIRST
                    out = (out << 1) | bval
                else:
                    out = (out >> 1) | (bval << 7)
            else:            # 后沿输出
                self.mosi.value(1 if (val >> bit) & 1 else 0)
            
            # 延迟
            for _ in range(self.delay):
                pass
        
        return out

    def transfer16(self, data):
        if self.bit_order == 1:  # MSBFIRST
            msb = self.transfer((data >> 8) & 0xFF)
            lsb = self.transfer(data & 0xFF)
            return (msb << 8) | lsb
        else:  # LSBFIRST
            lsb = self.transfer(data & 0xFF)
            msb = self.transfer((data >> 8) & 0xFF)
            return (lsb << 8) | msb

    def transfer_bits(self, val, bits):
        out = 0
        # 处理位序
        if self.bit_order == 1:  # MSBFIRST
            temp = 0
            for bit in range(bits):
                temp |= ((val >> bit) & 1) << (bits - 1 - bit)
            val = temp

        # 执行指定位数的传输
        for bit in range(bits):
            self.sck.value(self.ckp ^ 1)  # 时钟起始边沿
            
            # 延迟
            for _ in range(self.delay):
                pass
            
            # 在时钟前沿采样/输出
            if self.cke:  # 前沿采样
                bval = self.miso.value()
                if self.bit_order == 1:  # MSBFIRST
                    out = (out << 1) | bval
                else:
                    out = (out >> 1) | (bval << (bits - 1))
            else:         # 前沿输出
                self.mosi.value((val >> bit) & 1)
            
            # 延迟
            for _ in range(self.delay):
                pass
                
            self.sck.value(self.ckp)  # 时钟结束边沿
            
            # 延迟
            for _ in range(self.delay):
                pass
            
            # 在时钟后沿采样/输出
            if not self.cke:  # 后沿采样
                bval = self.miso.value()
                if self.bit_order == 1:  # MSBFIRST
                    out = (out << 1) | bval
                else:
                    out = (out >> 1) | (bval << (bits - 1))
            else:            # 后沿输出
                self.mosi.value((val >> bit) & 1)
            
            # 延迟
            for _ in range(self.delay):
                pass
        
        return out

    def iaso_send(self, haddr, hdata):
        # 发送地址和数据
        self.transfer_bits(haddr, IasoBits)
        self.transfer_bits(hdata, IasoBits)

    def iaso_read(self, haddr):
        # 发送地址
        self.transfer_bits(haddr, IasoBits)
        # 读取数据
        return self.transfer_bits(0, IasoBits)

    # Iaso windows length 长度设置
    def iaso_SetWinLen(self, data):
        # 小端模式写入（低字节在前）
        self.iaso_send(IasoWr + HeloosReg + WINLEN_REG,     (data >> 0)  & 0xFF)  # 字节0 (LSB)
        self.iaso_send(IasoWr + HeloosReg + WINLEN_REG + 1, (data >> 8)  & 0xFF)  # 字节1
        self.iaso_send(IasoWr + HeloosReg + WINLEN_REG + 2, (data >> 16) & 0xFF)  # 字节2
        self.iaso_send(IasoWr + HeloosReg + WINLEN_REG + 3, (data >> 24) & 0xFF)  # 字节3 (MSB)
    
    def iaso_GetWinLen(self):
        """读取当前窗口长度（32位）"""
        b0 = self.iaso_read(IasoRd + HeloosReg + WINLEN_REG)
        b1 = self.iaso_read(IasoRd + HeloosReg + WINLEN_REG + 1)
        b2 = self.iaso_read(IasoRd + HeloosReg + WINLEN_REG + 2)
        b3 = self.iaso_read(IasoRd + HeloosReg + WINLEN_REG + 3)
        data = (b3 << 24) | (b2 << 16) | (b1 << 8) | b0   
        print("WinLen is %d" %data)
        return data  

    # Iaso RdOutDly length 长度设置
    def iaso_SetRdOutDly(self, data):
        # 小端模式写入（低字节在前）
        self.iaso_send(IasoWr + HeloosReg + RDOUTDLY_REG,     (data >> 0)  & 0xFF)  # 字节0 (LSB)
        self.iaso_send(IasoWr + HeloosReg + RDOUTDLY_REG + 1, (data >> 8)  & 0xFF)  # 字节1
        self.iaso_send(IasoWr + HeloosReg + RDOUTDLY_REG + 2, (data >> 16) & 0xFF)  # 字节2
        self.iaso_send(IasoWr + HeloosReg + RDOUTDLY_REG + 3, (data >> 24) & 0xFF)  # 字节3 (MSB)
    
    def iaso_GetRdOutDly(self):
        """读取当前窗口长度（32位）"""
        b0 = self.iaso_read(IasoRd + HeloosReg + RDOUTDLY_REG)
        b1 = self.iaso_read(IasoRd + HeloosReg + RDOUTDLY_REG + 1)
        b2 = self.iaso_read(IasoRd + HeloosReg + RDOUTDLY_REG + 2)
        b3 = self.iaso_read(IasoRd + HeloosReg + RDOUTDLY_REG + 3)
        data = (b3 << 24) | (b2 << 16) | (b1 << 8) | b0   
        print("ReadOutDelay is %d" %data)
        return data  
    
    # Iaso edge_thr length 长度设置
    def iaso_SetEdgeThr(self, data):
        # 小端模式写入（低字节在前）
        self.iaso_send(IasoWr + HeloosReg + EDG_THR,     (data >> 0)  & 0xFF)  # 字节0 (LSB)
        self.iaso_send(IasoWr + HeloosReg + EDG_THR + 1, (data >> 8)  & 0xFF)  # 字节1
        self.iaso_send(IasoWr + HeloosReg + EDG_THR + 2, (data >> 16) & 0x1F)  # 字节2
    
    def iaso_GetEdgeThr(self):
        """读取当前窗口长度（21位）"""
        b0 = self.iaso_read(IasoRd + HeloosReg + EDG_THR)
        b1 = self.iaso_read(IasoRd + HeloosReg + EDG_THR + 1)
        b2 = self.iaso_read(IasoRd + HeloosReg + EDG_THR + 2)
        data =  (b2 << 16) | (b1 << 8) | b0   
        print("Edge Threshold is %d" %data)
        return data  
    
    Block_DIFF
    
    #    
    def iaso_ModelSet(self, 
                    dvp_frame=None,    # bit0: 1=dvp frame, 0=edge frame
                    dvp_clk=None,      # bit1: 1=dvp clk on, 0=off
                    locoi_clk=None,      # bit2: 1=jls clk on, 0=off
                    edge_clk=None,     # bit3: 1=edge clk on, 0=off
                    tile_clk=None,    # bit4: 1=tile clk on, 0=off
                    pos_x=None,       # bit5: 1=pos X on, 0=off
                    pos_y=None,        # bit6: 1=pos Y on, 0=off
                    raw_value=None):   # 直接设置原始值（优先级最高）
        """
        设置Iaso模式寄存器（MODE_REG = 20）
        参数可单独设置每个bit位，或直接传入原始值
        """
        if raw_value is not None:
            # 直接使用原始值模式
            self.iaso_send(IasoWr + HeloosReg + MODE_REG, raw_value)
            return

        # 读取当前寄存器值（保持未修改的位不变）
        current = self.iaso_read(IasoRd + HeloosReg + MODE_REG)
        
        # 按参数更新各个bit位
        if dvp_frame is not None:
            current = (current & ~0x01) | (1 if dvp_frame else 0)
        if dvp_clk is not None:
            current = (current & ~0x02) | ((1 if dvp_clk else 0) << 1)
        if locoi_clk is not None:
            current = (current & ~0x04) | ((1 if locoi_clk else 0) << 2)
        if edge_clk is not None:
            current = (current & ~0x08) | ((1 if edge_clk else 0) << 3)
        if tile_clk is not None:
            current = (current & ~0x10) | ((1 if tile_clk else 0) << 4)
        if pos_x is not None:
            current = (current & ~0x20) | ((1 if pos_x else 0) << 5)
        if pos_y is not None:
            current = (current & ~0x40) | ((1 if pos_y else 0) << 6)

        # 写入更新后的值
        self.iaso_send(IasoWr + HeloosReg + MODE_REG, current)

    def iaso_GetMod(self):
        """
        读取并打印MODE_REG(20)寄存器所有比特位的状态
        格式：
        [bit6] pos_y: ON/OFF
        [bit5] pos_x: ON/OFF
        ...
        [bit0] dvp_frame: ON/OFF
        """
        data = self.iaso_read(IasoRd + HeloosReg + MODE_REG)
        
        # 比特位定义 (bit位置: (名称, 描述))
        bit_defs = {
            6: ("pos_y",    "Position Y enable"),
            5: ("pos_x",    "Position X enable"),
            4: ("tile_clk", "Tile clock enable"),
            3: ("edge_clk", "Edge clock enable"),
            2: ("locoi_clk",  "LOCO-I clock enable"),
            1: ("dvp_clk",  "DVP clock enable"),
            0: ("dvp_frame","Frame type (0=Edge 1=DVP)")
        }
        
        print(f"\nMODE_REG Status (0x{data:02X}):")
        print("-" * 40)
        for bit in sorted(bit_defs.keys(), reverse=True):
            name, desc = bit_defs[bit]
            state = "ON" if (data & (1 << bit)) else "OFF"
            print(f"[bit{bit}] {name:8}: {state:3} | {desc}")
        print("-" * 40)
        print(f"Raw value: {data} (0x{data:02X})\n")
        
        return data

    def iaso_SetPixHeat(self, x, y):
        self.iaso_send(IasoWr + HeloosReg + Pixel_X_Heat, x)
        self.iaso_send(IasoWr + HeloosReg + Pixel_Y_Heat, y)

    def iaso_GetPixHeat(self):
        data = self.iaso_read(IasoRd + HeloosReg + Pixel_X_Heat)
        print("X Pos is %d" %data)
        data = self.iaso_read(IasoRd + HeloosReg + Pixel_Y_Heat)
        print("Y Pos is %d" %data)

    def iaso_SetSubBGD(self, data):
        self.iaso_send(IasoWr + HeloosReg + SUB_BGD_REG, (data)  & 0xFF)

    def iaso_GetSubBGD(self):
        data = self.iaso_read(IasoRd + HeloosReg + SUB_BGD_REG)
        print("sub bgd data is %d" %data)

    def iaso_SetDlyN_PixRst(self, data):
        # 小端模式写入（低字节在前）
        self.iaso_send(IasoWr + HeloosReg + delayN_pixrst,     (data >> 0)  & 0xFF)  # 字节0 (LSB)
        self.iaso_send(IasoWr + HeloosReg + delayN_pixrst + 1, (data >> 8)  & 0xFF)  # 字节1
    
    def iaso_GetDlyN_PixRst(self):
        b0 = self.iaso_read(IasoRd + HeloosReg + delayN_pixrst)
        b1 = self.iaso_read(IasoRd + HeloosReg + delayN_pixrst + 1)
        data = (b1 << 8) | b0   
        print("DlyN_PixRst is %d" %data)
        return data  

    def iaso_SetDlyS_PixRst(self, data):
        # 小端模式写入（低字节在前）
        self.iaso_send(IasoWr + HeloosReg + delayS_pixrst,     (data >> 0)  & 0xFF)  # 字节0 (LSB)
        self.iaso_send(IasoWr + HeloosReg + delayS_pixrst + 1, (data >> 8)  & 0xFF)  # 字节1
    
    def iaso_GetDlyS_PixRst(self):
        b0 = self.iaso_read(IasoRd + HeloosReg + delayS_pixrst)
        b1 = self.iaso_read(IasoRd + HeloosReg + delayS_pixrst + 1)
        data = (b1 << 8) | b0   
        print("DlyS_PixRst is %d" %data)
        return data  

    def iaso_SetDlyN_Ramp(self, data):
        # 小端模式写入（低字节在前）
        self.iaso_send(IasoWr + HeloosReg + delayN_rampen,     (data >> 0)  & 0xFF)  # 字节0 (LSB)
        self.iaso_send(IasoWr + HeloosReg + delayN_rampen + 1, (data >> 8)  & 0xFF)  # 字节1
    
    def iaso_GetDlyN_Ramp(self):
        b0 = self.iaso_read(IasoRd + HeloosReg + delayN_rampen)
        b1 = self.iaso_read(IasoRd + HeloosReg + delayN_rampen + 1)
        data = (b1 << 8) | b0   
        print("DlyN_Ramp is %d" %data)
        return data  

    def iaso_SetDlyS_Ramp(self, data):
        # 小端模式写入（低字节在前）
        self.iaso_send(IasoWr + HeloosReg + delayS_rampen,     (data >> 0)  & 0xFF)  # 字节0 (LSB)
        self.iaso_send(IasoWr + HeloosReg + delayS_rampen + 1, (data >> 8)  & 0xFF)  # 字节1
    
    def iaso_GetDlyS_Ramp(self):
        b0 = self.iaso_read(IasoRd + HeloosReg + delayS_rampen)
        b1 = self.iaso_read(IasoRd + HeloosReg + delayS_rampen + 1)
        data = (b1 << 8) | b0   
        print("DlyS_Ramp is %d" %data)
        return data  

    def iaso_SetDlyN_AryRst(self, data):
        # 小端模式写入（低字节在前）
        self.iaso_send(IasoWr + HeloosReg + delayN_Aryrst,     (data >> 0)  & 0xFF)  # 字节0 (LSB)
        self.iaso_send(IasoWr + HeloosReg + delayN_Aryrst + 1, (data >> 8)  & 0xFF)  # 字节1
    
    def iaso_GetDlyN_AryRst(self):
        b0 = self.iaso_read(IasoRd + HeloosReg + delayN_Aryrst)
        b1 = self.iaso_read(IasoRd + HeloosReg + delayN_Aryrst + 1)
        data = (b1 << 8) | b0   
        print("DlyN_AryRst is %d" %data)
        return data  

    def iaso_SetDlyS_AryRst(self, data):
        # 小端模式写入（低字节在前）
        self.iaso_send(IasoWr + HeloosReg + delayS_Aryrst,     (data >> 0)  & 0xFF)  # 字节0 (LSB)
        self.iaso_send(IasoWr + HeloosReg + delayS_Aryrst + 1, (data >> 8)  & 0xFF)  # 字节1
    
    def iaso_GetDlyS_AryRst(self):
        b0 = self.iaso_read(IasoRd + HeloosReg + delayS_Aryrst)
        b1 = self.iaso_read(IasoRd + HeloosReg + delayS_Aryrst + 1)
        data = (b1 << 8) | b0   
        print("DlyS_AryRst is %d" %data)
        return data  

    def iaso_SetJlsNear(self, data):
        self.iaso_send(IasoWr + HeloosReg + JLS_NEAR, (data)  & 0x07)

    def iaso_GetJlsNear(self):
        data = self.iaso_read(IasoRd + HeloosReg + JLS_NEAR)
        print("Jls Near is %d" %data)


    def iaso_GetBlockDiff(self, num):
        data = self.iaso_read(IasoRd + HeloosReg + Block_DIFF + num)
        print("Block diff at %d is %d" %(num,data))


    def iaso_SetTileVal(self, num, data):
        self.iaso_send(IasoRd + HeloosReg + Tile_Value + num, (data >> 0)  & 0x0F)

    def iaso_GetTileVal(self, num):
        data = self.iaso_read(IasoRd + HeloosReg + Tile_Value + num)
        print("Tile Value at %d is %d" %(num,data))



    def iaso_MemWr(self, addr, data):
        self.iaso_send(IasoWr + IasoMem + addr, data)

    def iaso_MemRd(self, addr):
        return self.iaso_read(IasoRd + IasoMem + addr)

    def iaso_NN_THWr(self, layer, th):
        self.iaso_send(IasoWr + HeloosReg + layer, th)

    def iaso_NN_THRd(self, layer):
        return self.iaso_read(IasoRd + HeloosReg + layer)




# ====================== 中断处理函数 ======================
def handle_interrupt(pin):
    global last_interrupt_time, interrupt_time_difference
    global is_first_interrupt, pixel_collected, event_act
    
    current_time = time.ticks_us()
    if is_first_interrupt:
        last_interrupt_time = current_time
        is_first_interrupt = False
    else:
        interrupt_time_difference = time.ticks_diff(current_time, last_interrupt_time)
        is_first_interrupt = True
        # 分离中断（在MicroPython中需要重新附加）
        pin.irq(handler=None)
        pixel_collected = True
    event_act = True

def config_interrupt(pin_num=2):
    global is_first_interrupt, pixel_collected, event_act
    is_first_interrupt = True
    pixel_collected = False
    event_act = False
    
    pin = machine.Pin(pin_num, machine.Pin.IN)
    pin.irq(handler=handle_interrupt, trigger=machine.Pin.IRQ_FALLING)


# ====================== 主程序 ======================
# 初始化Iaso (使用原始引脚定义)
#                   mosi_pin,       miso_pin, sck_pin

def setup():
    myIaso = Iaso(mosi_pin=3, miso_pin=4, sck_pin=5)  # 使用GPIO3/4/5       
    sys_clk = clockgen.AdjustableClock(pin_num=2, rstN_pin=26)

    # 设置不同频率
    # clock.set_frequency(1_000_000)  # 1MHz
    sys_clk.set_frequency(20_000_000)   # 20MHz (需确保电路支持)
    # clock.set_frequency(0)            # 停止   
    sys_clk.set_rstN(0)
    # 初始化串口
    uart = machine.UART(0, baudrate=9600)
    
    # 初始化IO
    # check_io_init()
    
    # 初始化Iaso
    myIaso.begin = lambda: None  # MicroPython中不需要特殊begin
    myIaso.set_bit_order(1)  # MSBFIRST
    myIaso.set_data_mode(2)  # SPI_MODE2
    myIaso.set_clock_divider(32)  # SPI_CLOCK_DIV128
    
    print("delay 1s")
    time.sleep(1)
    sys_clk.set_rstN(1)
    time.sleep(1)
    # Iaso初始化序列
    
    myIaso.iaso_ModelSet( 
                 dvp_frame=True,    # bit0: 1=dvp frame, 0=edge frame
                 dvp_clk=True,      # bit1: 1=dvp clk on, 0=off
                 locoi_clk=False,      # bit2: 1=locoi clk on, 0=off
                 edge_clk=False,     # bit3: 1=edge clk on, 0=off
                 tile_clk=False,    # bit4: 1=tile clk on, 0=off
                 pos_x=False,       # bit5: 1=pos X on, 0=off
                 pos_y=False        # bit6: 1=pos Y on, 0=off
                 )    # 直接设置原始值（优先级最高）
    myIaso.iaso_GetMod()  # 获取当前模式寄存器状态
    myIaso.iaso_SetWinLen(30010+256)
    myIaso.iaso_GetWinLen()
    #myIaso.iaso_SetRdOutDly()
    #myIaso.iaso_GetRdOutDly()
    myIaso.iaso_SetSubBGD(0)
    myIaso.iaso_GetSubBGD()
    myIaso.iaso_SetDlyN_PixRst(100)
    myIaso.iaso_GetDlyN_PixRst()
    myIaso.iaso_SetDlyS_PixRst(10)
    myIaso.iaso_GetDlyS_PixRst() 
    myIaso.iaso_SetDlyN_Ramp(30000)
    myIaso.iaso_GetDlyN_Ramp()
    myIaso.iaso_SetDlyS_Ramp(10)
    myIaso.iaso_GetDlyS_Ramp()   
    myIaso.iaso_SetDlyN_AryRst(256)
    myIaso.iaso_GetDlyN_AryRst()
    myIaso.iaso_SetDlyS_AryRst(30010)
    myIaso.iaso_GetDlyS_AryRst()     
    myIaso.iaso_SetJlsNear(1)
    myIaso.iaso_GetJlsNear()
    myIaso.iaso_SetEdgeThr(10000)
    myIaso.iaso_GetEdgeThr()
    #0-63
    myIaso.iaso_GetBlockDiff(10)
    myIaso.iaso_SetTileVal(11, 1)
    #0-63
    myIaso.iaso_GetTileVal(11)
    myIaso.iaso_SetPixHeat(10,11)
    myIaso.iaso_GetPixHeat()
    
    
    sys_clk.set_frequency(0)   # 20MHz (需确保电路支持)
    print("Iaso SPI setup complete")
    #
    # 设置像素输出
    # myIaso.iaso_PixOutput(pixelX, pixelY)
    # val_x = myIaso.iaso_PixReadX()
    # val_y = myIaso.iaso_PixReadY()
    # print(f"Pixel X: {val_x}, Y: {val_y}")
    
    # 设置阈值
    # myIaso.iaso_NN_THWr(FC2TH_Reg, 1)
    # val_th = myIaso.iaso_NN_THRd(FC2TH_Reg)
    # print(f"FC2TH is {val_th}")
    
    # 禁用加热
    # myIaso.iaso_PixHeatDisable()
    
    # 获取图像
    # Get_Image73x73()
    # Get_Image32x32()

def loop():
    # 初始化LED
    led     = machine.Pin(25, machine.Pin.OUT)
    while True:
        led.on()
        time.sleep_ms(300)
        led.off()
        time.sleep_ms(300)
        # 检查最大值
        # check_max_value()

# 运行主程序
if __name__ == "__main__":
    setup()
    loop()