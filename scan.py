import machine
import time

class ScanChainController:
    def __init__(self, scan_len=32):
        # 引脚定义
        self.SCAN_IN = machine.Pin(7, machine.Pin.OUT)
        self.SCAN_OUT = machine.Pin(21, machine.Pin.IN)
        self.SCAN_CLK = machine.Pin(2, machine.Pin.OUT)
        self.SCAN_EN = machine.Pin(22, machine.Pin.OUT)
        self.SCAN_HEAL = machine.Pin(6, machine.Pin.OUT)        
        # 扫描链参数
        self.SC_LEN = scan_len
        self.clock_freq = 1_000_000  # 默认1MHz时钟
        
        # 初始化状态
        self.SCAN_EN.off()  # 默认禁用扫描链
        self.SCAN_CLK.off()
        self.SCAN_IN.off()
        self.SCAN_HEAL.off()    

    def _pulse_clock(self):
        """生成一个时钟脉冲"""
        self.SCAN_CLK.on()
        time.sleep_us(1)  # 保持时间
        self.SCAN_CLK.off()
        time.sleep_us(1)  # 恢复时间

    def set_Heal(self, state):
        """设置复位引脚状态"""
        self.SCAN_HEAL.value(state)
        print(f"Scan Heal pin set to {'HIGH' if state else 'LOW'}")

    def write_scan_chain(self, data):
        """
        写入扫描链数据
        参数:
            data: 整数类型，数据将被截断到SC_LEN位
        """
        if data < 0 or data >= (1 << self.SC_LEN):
            raise ValueError(f"Data exceeds {self.SC_LEN}-bit limit")
        
        self.SCAN_EN.on()  # 启用扫描链
        
        # 从LSB开始移位输入
        for i in range(self.SC_LEN):
            bit = (data >> i) & 0x01
            self.SCAN_IN.value(bit)
            self._pulse_clock()
        
        self.SCAN_EN.off()  # 禁用扫描链

    def read_scan_chain(self):
        """
        读取扫描链数据
        返回:
            SC_LEN位的整数值
        """
        self.SCAN_EN.on()  # 启用扫描链
        
        result = 0
        for i in range(self.SC_LEN):
            self._pulse_clock()
            bit = self.SCAN_OUT.value()
            result |= (bit << i)  # 从LSB开始组装
            
        self.SCAN_EN.off()
        return result

    def write_read_scan_chain(self, data):
        """
        同时写入和读取扫描链（全双工操作）
        返回:
            (写入的时钟周期数, 读取的数据)
        """
        self.SCAN_EN.on()
        
        read_data = 0
        for i in range(self.SC_LEN):
            # 写入数据
            bit_out = (data >> i) & 0x01
            self.SCAN_IN.value(bit_out)
            
            # 时钟上升沿
            self.SCAN_CLK.on()
            
            # 在时钟高电平期间读取
            bit_in = self.SCAN_OUT.value()
            read_data |= (bit_in << i)
            
            # 时钟下降沿
            self.SCAN_CLK.off()
        
        self.SCAN_EN.off()
        return (self.SC_LEN, read_data)

    def set_clock_freq(self, freq_hz):
        """设置扫描时钟频率（实际会有Python执行延迟）"""
        self.clock_freq = min(max(freq_hz, 1000), 10_000_000)  # 限制1kHz-10MHz

# 使用示例
if __name__ == "__main__":
    # 初始化扫描链（假设链长32位）
    scanner = ScanChainController(scan_len=32)
    scanner.set_Heal(0)
    try:
        # 测试写入和读取
        test_data = 0xABCD1234
        print(f"Writing data: {hex(test_data)}")
        scanner.write_scan_chain(test_data)
        
        # 读取验证
        read_val = scanner.read_scan_chain()
        print(f"Read back: {hex(read_val)}")
        
        # 全双工测试
        cycles, result = scanner.write_read_scan_chain(0x55AA55AA)
        print(f"Transferred {cycles} bits, received {hex(result)}")
        
    except Exception as e:
        print(f"Error: {e}")