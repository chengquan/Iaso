import machine
import time
import uarray
import clock_set as clockgen
import rp2
import utime
from machine import Pin
# 硬件引脚定义 (根据实际连接调整)
STRAT_RD  = 1 
VSYNC_PIN = 0    # 垂直同步
HSYNC_PIN = 28   # 水平同步
PCLK_PIN = 27    # 像素时钟
DATA_PINS = [15, 14, 13, 12, 11, 10, 9, 8]  # D0(LSB)-D7(MSB)
SYS_CLK = 2

@rp2.asm_pio(set_init=rp2.PIO.OUT_LOW, autopush=False)
def pulse_until_high():
    #pull()
    label("pulse_until_high")
    set(pins, 0)          # 输出高
    nop() [5]             # 保持一会
    set(pins, 1)          # 输出低
    nop() [5]             # 保持一会
    in_(pins, 1)          # 采样输入
    mov(x, isr)           # 把采样结果存入X
    jmp(x_dec, "detected")# 如果x!=0则跳转到 detected
    jmp("pulse_until_high") # 否则继续循环
    label("detected")
    push()                # 结果压入FIFO
    label("haltedloop")
    jmp("haltedloop")
    # 🚨 不写 jmp → 状态机执行完后停住

class FrameCapture:
    def __init__(self, width=320, height=240):
        # 初始化GPIO
        self.start_rd = machine.Pin(STRAT_RD, machine.Pin.OUT)
        self.vsync = machine.Pin(VSYNC_PIN, machine.Pin.IN)
        self.hsync = machine.Pin(HSYNC_PIN, machine.Pin.IN)
        self.pclk = machine.Pin(PCLK_PIN, machine.Pin.IN)
        self.sys_clk = machine.Pin(SYS_CLK, machine.Pin.OUT)
        #self.sys_clk = []
        """
        初始化脉冲生成器
        :param pulse_pin: 脉冲输出引脚
        :param status_pin: 状态读取引脚
        """
        
        self.data_pins = [machine.Pin(p, machine.Pin.IN) for p in DATA_PINS]
        # 图像参数
        self.width = width
        self.height = height
        self.high_detected = False
        self.frame_buffer = uarray.array('B', [0] * (width * height))
        self.line_buffer = uarray.array('B', [0] * width)
        
        # 状态控制
        self.in_frame = False
        self.current_line = 0
        self.pixel_pos = 0
        self.frame_ready = False
        self.frame_complete = False
        self.start_rd.value(0)
        self.is_running = False
        self.sm = []
        # 设置初始状态
        # self.sm.exec(f"set(pins, {initial_state})")
        #self.sys_clk.value(0)
        
    def print_test(self, sm):
        self.sm.active(0)
        print("print_test")
        self.sm.restart()
        self.sm.active(1)
    
    def start_pulse(self):
        """启动脉冲循环"""
        #if not self.is_running:
        #self.sm.put(0)  # 发送任意值触发脉冲循环
        #self.sm.active(1)
        #self.sm.active(1)
        self.is_running = True
        self.high_detected = False
            #print("脉冲循环已启动") 

    def pulse_once(self):
        self.sm.restart()       # 触发一次
        self.sm.active(1)       #active the loop
        while self.sm.rx_fifo() == 0:
            pass
        self.sm.active(0)      #
        return self.sm.get() # 读取结果（阻塞等待一次执行完）

    def check_status(self):
        """检查状态并处理回调"""
        if self.sm.rx_fifo() > 0:
            # 读取状态值
            status = self.sm.get()
            #print(bin(status))
            if status == 1:
                self.high_detected = True
                #print("检测到高电平状态")
                
    
    def run_blocking(self, timeout_ms=5000):
        """阻塞式运行直到检测到高电平"""
        #print("456")
        self.start_pulse()
        #print("123")
        start_time = utime.ticks_ms()
        
        while not self.high_detected:
            self.check_status()
            
            # 检查超时
            if utime.ticks_diff(utime.ticks_ms(), start_time) > timeout_ms:
                #self.stop()
                print("time out")
                return False
            
            utime.sleep_ms(1)  # 避免忙等待
        #self.high_detected = False
        return True

    def rise_edge(self):
        self.sys_clk.value(0)
        time.sleep_us(5)
        self.sys_clk.value(1)
        time.sleep_us(5)
    
    def dummy_clk(self):
        for _ in range(100):
            self.sys_clk.value(0)
            time.sleep_us(1)
            self.sys_clk.value(1)
            time.sleep_us(1)       
    
    
    def start_rdframe(self):
        # 设置中断
        #time.sleep_us(10)
        self.start_rd.value(1)
        #self.rise_edge()
        #self.start_rd.value(0)
        self.frame_ready = False
        self.in_frame = False
        '''
        self.sm = rp2.StateMachine(
            0,
            pulse_loop_until_high,
            freq=10_000_000,  # 125MHz 时钟
            set_base=Pin(SYS_CLK),
            #in_base=Pin(HSYNC_PIN),
            jmp_pin=Pin(HSYNC_PIN)  # 用于条件跳转
        )
        '''
        self.sm = rp2.StateMachine(0, pulse_until_high, freq=125_000_000,
                      set_base=Pin(SYS_CLK), in_base=Pin(HSYNC_PIN))
        #self.sm.active(1)
        
        #self.sm.irq(self.capture_frame)
        print("Frame capture started")
    
    def save_frame_buffer_to_txt(self, filename="frame_buffer_dump.txt"):
        with open(filename, "w") as f:
            for y in range(128):
                line = []
                for x in range(128):
                    pixel = self.frame_buffer[y * 128 + x]
                    line.append(str(pixel))
                f.write(" ".join(line) + "\n")

    
    def print_frame_buffer(self, sample_size=10):
        """打印帧缓冲区的像素矩阵（默认为前10x10样本）"""
        print("\nFrame Buffer (128x128) - First {}x{} samples:".format(sample_size, sample_size))
        
        for y in range(min(sample_size, 128)):
            for x in range(min(sample_size, 128)):
                pixel = self.frame_buffer[y * 128 + x]
                # 格式化输出：十进制值 + 十六进制
                print("{:3d}({:02X})".format(pixel, pixel), end=' ')
            print("...")  # 表示后续数据省略
        
        # 打印统计信息
        total_pixels = 128 * 128
        print("\nStatistics:")
        print("- Total size: {} bytes".format(total_pixels))
        print("- First pixel: 0x{:02X} (Y=0, X=0)".format(self.frame_buffer[0]))
        print("- Center pixel: 0x{:02X} (Y=64, X=64)".format(self.frame_buffer[64*128 + 64]))
        print("- Last pixel: 0x{:02X} (Y=127, X=127)".format(self.frame_buffer[-1]))
        
    
    def capture_frame(self):
        """阻塞式捕获单帧"""
        #self.start_rdframe()
        #self.start_pulse_loop()
        while not self.in_frame:
            #self.rise_edge()
            #print("status")
            val = self.pulse_once()  # 每次只执行一次
            #print(val)
            if True:
                self.start_rd.value(0)
                pixel = 0
                for i, pin in enumerate(self.data_pins):
                    pixel |= (pin.value() << i)
                self.line_buffer[self.pixel_pos] = pixel
                self.pixel_pos += 1
                #print(pixel)               
            #else:  # 低电平（行结束）
                # 只有当正确接收到完整行时才保存
                if self.pixel_pos == self.width:
                    #print("line")
                    start_idx = self.current_line * self.width
                    end_idx = start_idx + self.width
                    self.frame_buffer[start_idx:end_idx] = self.line_buffer
                    
                    # 更新行计数器
                    self.current_line += 1
                    self.pixel_pos = 0
                    print(self.current_line)
                    
                    # 打印行进度（每10行）
                    #if self.current_line % 10 == 0:
                    #    print(f"Line {self.current_line}/{self.height} captured")     

                # 帧结束条件检查
                frame_complete = (
                    self.vsync.value() == 1 or          # VSYNC变高
                    self.current_line == self.height    # 达到最大行数
                )
                
                if frame_complete:
                    self.in_frame = True
                    self.frame_ready = True
                    # 统计信息
                    actual_lines = self.current_line
                    self.current_line = 0
                    print(f"Frame capture completed: {actual_lines} lines")
                    print(f"Expected height: {self.height}")
                #self.start_pulse()
        return self.frame_buffer
        #self.sm.restart()
        #self.sm.active(1)
        #print("done sm")
    

# 使用示例
if __name__ == "__main__":
    # 初始化捕获器 (假设图像分辨率320x240)
    capturer = FrameCapture(width=128, height=128)
    capturer.start_rdframe()
    try:
        print("等待帧同步信号...")
        frame = capturer.capture_frame()
        #capturer.save_as_ppm("capture.ppm")
        print("帧已保存为capture.ppm")
        
    except Exception as e:
        print(f"捕获失败: {e}")
    finally:
        # 禁用中断
        capturer.pclk.irq(handler=None)
